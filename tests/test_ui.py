"""C 검사 — 담당 C(김영헌), 화면 동작 (브라우저). 실행: python -m tests.test_ui
시험 로그(dashboard/sample_logs)로 대시보드를 띄우고 진짜 브라우저(창 없음)로 클릭·키보드를 눌러 확인.
playwright 가 없으면 건너뜀: pip install playwright && python -m playwright install chromium
"""
import json
import logging
import shutil
import socket
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit

from werkzeug.serving import make_server

from dashboard.app import SAMPLE_ROOT, app

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sync_playwright = None

KPI = "() => [...document.querySelectorAll('.kpi_cell')].map(c => [c.querySelector('.kpi_value').textContent, c.querySelector('.kpi_sub').textContent])"
CELL = """([id, s, x, y]) => { const ch = chart_of(id); const [px, py] = ch.convertToPixel({seriesIndex: s}, [x, y]);
          const r = document.getElementById(id).getBoundingClientRect(); return {x: r.left + px, y: r.top + py}; }"""


def _serve(log_root):
    app.config["LOG_ROOT"] = log_root
    logging.getLogger("werkzeug").setLevel(logging.ERROR)  # 요청마다 찍히는 서버 로그 끔
    srv = make_server("127.0.0.1", 0, app)  # 빈 포트 아무거나
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}/"


def _launch(p):
    try:
        return p.chromium.launch(channel="chrome", headless=True)  # 설치된 Chrome 이 있으면 그걸로
    except Exception:
        return p.chromium.launch(headless=True)


def _log(name, file):
    return [json.loads(line) for line in (SAMPLE_ROOT / name / file).read_text(encoding="utf-8").splitlines() if line.strip()]


def _open(browser, url, errors):
    pg = browser.new_page(viewport={"width": 1920, "height": 1080})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(url)
    pg.wait_for_function("() => typeof state !== 'undefined' && state.bundle !== null", timeout=20000)  # 첫 실험 로그를 받을 때까지
    return pg


def _select_exp(pg, exp):
    pg.select_option("#exp", exp)
    pg.wait_for_function(f"() => state.exp === '{exp}'")


def check_kpi(browser, url, errors):
    """KPI 숫자 = 로그 숫자, 실제 실패는 성공률에 들어가고 일부러 넣은 시험 요청은 빠짐"""
    pg = _open(browser, url, errors)
    train = _log("exp_pref_seed42", "train.jsonl")
    for r in (1, 2, 3):
        pg.evaluate(f"() => set_round({r})")
        g = next(x for x in train if x["target"] == "global" and x["round"] == r)
        kpi = pg.evaluate(KPI)
        assert kpi[1][0] == f"{g['acc'] * 100:.1f}%", (r, kpi[1])
        assert kpi[2][0] == f"{min(g['acc_by_digit']) * 100:.1f}%", (r, kpi[2])
    pg.evaluate("() => set_round(2)")
    rate, sub = pg.evaluate(KPI)[3]
    assert rate == "94.4%" and "실패 1건" in sub, (rate, sub)  # ReadTimeout 1건

    _select_exp(pg, "exp_random_seed42_inject")
    pg.evaluate("() => set_round(2)")
    rate, sub = pg.evaluate(KPI)[3]
    assert rate == "100.0%" and "시험 요청 2건 별도" in sub, (rate, sub)
    expect(pg.locator("#p_requests tr.row_warning")).to_have_count(2)
    pg.evaluate("() => set_pin({type: 'client', id: 'C1'})")  # 배정 밖 엣지로 보낸 시험 요청도 C1 요청이라 강조
    expect(pg.locator("#p_requests tr.row_warning:not(.dim)")).to_have_count(2)
    pg.close()


def check_linking(browser, url, errors):
    """엣지 고정 → 소속 클라·엣지→중앙 줄만 강조, Esc 해제 / 실패 칸 클릭 → 라운드 이동 + 요청 목록"""
    pg = _open(browser, url, errors)
    pg.evaluate("() => set_pin({type: 'edge', id: 'E1'})")
    expect(pg.locator("#pin_chip")).to_contain_text("E1 + 소속 클라 3")
    expect(pg.locator("#p_clients tbody tr:not(.dim)")).to_have_count(3)
    lit_e1s = pg.evaluate("""() => { const o = chart_of('p_comm_heatmap').getOption(); const yi = o.yAxis[0].data.indexOf('E1→S');
                                     return o.series[0].data.filter(d => d.value[1] === yi).every(d => d.itemStyle.opacity === 1); }""")
    assert lit_e1s, "E1 고정인데 E1→S 줄이 흐려짐"
    pg.keyboard.press("Escape")
    expect(pg.locator("#pin_chip")).to_be_hidden()
    expect(pg.locator("#p_clients tbody tr.dim")).to_have_count(0)

    yi = pg.evaluate("() => chart_of('p_comm_heatmap').getOption().yAxis[0].data.indexOf('C5→E2')")
    pt = pg.evaluate(CELL, ["p_comm_heatmap", 1, 1, yi])  # 실패 칸만 모아 둔 두 번째 시리즈의 R2 칸
    pg.mouse.click(pt["x"], pt["y"])
    pg.wait_for_function("() => state.pinned && state.pinned.id === 'C5'")
    assert pg.evaluate("() => state.round") == 2
    expect(pg.locator("#p_requests tr.row_critical")).to_contain_text("ReadTimeout")
    pg.close()


def check_keyboard_and_hover(browser, url, errors):
    """←/→ 라운드 이동(범위 밖 안 넘어감), 칸 위에 멈춰 있으면 다시 그리기 반복 없음, 벗어나면 강조 해제"""
    pg = _open(browser, url, errors)
    pg.evaluate("() => set_round(1)")
    pg.keyboard.press("ArrowLeft")
    assert pg.evaluate("() => state.round") == 1
    for _ in range(5):
        pg.keyboard.press("ArrowRight")
    assert pg.evaluate("() => state.round") == 3

    pg.evaluate("() => { window.__n = 0; subscribe(() => window.__n++); }")
    pt = pg.evaluate(CELL, ["p_data", 0, 0, 0])
    pg.mouse.move(pt["x"], pt["y"])
    pg.wait_for_function("() => state.hover && state.hover.type === 'digit'")
    n0 = pg.evaluate("() => window.__n")
    pg.mouse.move(pt["x"] + 1, pt["y"])  # 같은 칸 안에서 조금 움직여도
    pg.mouse.move(pt["x"], pt["y"] + 1)
    assert pg.evaluate("() => window.__n") == n0, "칸 위에 있는데 다시 그리기가 반복됨"
    pg.mouse.move(2, 2)
    pg.wait_for_function("() => state.hover === null")
    pg.close()


def check_layout(browser, url, errors):
    """1920×1080 한 화면: 페이지 스크롤·패널 넘침 없음"""
    pg = _open(browser, url, errors)
    assert pg.evaluate("() => document.documentElement.scrollHeight - innerHeight") <= 0
    assert pg.evaluate("() => [...document.querySelectorAll('.panel')].filter(p => p.scrollHeight > p.clientHeight).length") == 0
    top_h = pg.evaluate("() => document.getElementById('top').offsetHeight")
    pg.evaluate("() => set_status('run-20261119-130512/exp_random_seed42: 실행 중으로 보임 · 끝난 라운드 7/20 · 2초마다 자동 갱신 ' + 'x'.repeat(80))")
    assert pg.evaluate("() => document.getElementById('top').offsetHeight") == top_h, "긴 상태 문구에 머리말이 줄바꿈됨"
    assert pg.evaluate("() => document.documentElement.scrollWidth - innerWidth") <= 0, "긴 상태 문구에 페이지가 옆으로 넘침"
    _select_exp(pg, "exp_random_seed42_inject")
    pg.evaluate("() => set_round(2)")  # 결과 칸이 가장 긴 라운드 (409 시험 2건)
    wide = pg.evaluate("() => [...document.querySelectorAll('#p_requests, #p_clients, .sub_table')].filter(e => e.scrollWidth > e.clientWidth).map(e => e.id || e.className)")
    assert not wide, f"표가 옆으로 잘림: {wide}"
    pg.close()


def check_tabs(browser, url, errors):
    """심층 분석 탭: 패널 4개 그림, 선택 상태를 개요와 같이 씀, 새로고침해도 같은 탭, 돌아오면 개요 차트 크기 정상"""
    pg = _open(browser, url, errors)
    pg.evaluate("() => set_pin({type: 'client', id: 'C1'})")
    pg.get_by_role("tab", name="심층 분석").click()
    expect(pg.get_by_role("tab", name="심층 분석")).to_have_attribute("aria-selected", "true")
    for pid in ("p_local", "p_traffic", "p_rank", "p_sim"):
        assert pg.evaluate(f"() => chart_of('{pid}').getOption().series.length") > 0, pid
    assert pg.evaluate("() => state.pinned.id") == "C1"  # 개요에서 고정한 게 그대로
    sim = pg.evaluate("""() => { const o = chart_of('p_sim').getOption(); const ys = o.yAxis[0].data.map(v => v.split(' ')[0]);
                                 return o.series[0].data.map(d => [ys[d.value[1]], ys[d.value[0]], d.itemStyle.opacity]); }""")
    assert all(op == 1 for a, c, op in sim if "C1" in (a, c)) and all(op < 1 for a, c, op in sim if "C1" not in (a, c))  # C1 의 줄·열만 밝음
    assert "가진 숫자" in pg.evaluate("() => chart_of('p_local').getOption().title[0].text")
    assert pg.evaluate("() => [...document.querySelectorAll('.analysis .panel')].filter(p => p.scrollHeight > p.clientHeight).length") == 0
    pg.reload()
    pg.wait_for_function("() => typeof state !== 'undefined' && state.bundle !== null")
    assert pg.evaluate("() => state.tab") == "analysis" and pg.locator("main.regions").is_hidden()
    pg.get_by_role("tab", name="개요").click()
    assert pg.evaluate("() => chart_of('p_tree').getWidth()") > 100  # 숨었다 나와도 차트 크기 정상
    pg.close()


def check_run_tab(browser, url, errors):
    """실험 실행 탭: 토글 → 미리보기 갱신, 잘못된 값이면 실행 버튼 막힘, 기본값으로 되돌림, 엣지 순위 ↑↓, 라운드 키 안 먹음"""
    pg = _open(browser, url, errors)
    pg.get_by_role("tab", name="실험 실행").click()
    expect(pg.locator("#kpi")).to_be_hidden()  # 이 탭에서는 KPI·범례·실험·라운드 컨트롤 숨김
    expect(pg.locator("#round")).to_be_hidden()
    pv = pg.locator("#run_preview table")
    expect(pv).to_contain_text("C1·C2·C4")  # 기본 설정의 선호 배정 E1
    expect(pg.locator("#run_go")).to_be_enabled()
    expect(pg.locator("#run_changed")).to_have_text("기본값 그대로")
    expect(pg.locator("#run_inject_round")).to_be_disabled()  # 결함 주입을 켜야 라운드 입력

    pg.get_by_label("C2 숫자 6").check(force=True)  # 칸은 글자 span 이 덮고 있음 → force
    expect(pg.locator("#run_sum_C2")).to_have_text("4개 · 300장")
    expect(pg.locator("#run_changed")).to_have_text("기본값과 다른 칸 1개 (주황)")
    expect(pv).to_contain_text("0·1·2·3·4·5·6")  # E1 숫자에 6 추가

    for d in (3, 4, 5, 6):  # C2 숫자를 다 끄면 오류 + 실행 막힘
        pg.get_by_label(f"C2 숫자 {d}").uncheck(force=True)
    expect(pg.locator("#run_errors")).to_contain_text("C2")
    expect(pg.locator("#run_row_C2")).to_have_class("bad_row")
    expect(pg.locator("#run_go")).to_be_disabled()
    pg.get_by_role("button", name="기본값으로").click()
    pg.fill("#run_rounds", "0")  # 입력칸 자체도 빨갛게 + 한글 라벨 오류
    expect(pg.locator("#run_rounds")).to_have_attribute("aria-invalid", "true")
    expect(pg.locator("#run_errors")).to_contain_text("라운드 수")

    pg.get_by_role("button", name="기본값으로").click()
    expect(pg.locator("#run_sum_C2")).to_have_text("3개 · 400장")
    expect(pg.locator("#run_go")).to_be_enabled()

    pg.get_by_label("클라 지연·중단 + 엣지 대기 제한").check()  # 지연·중단 주입: 미리보기에 R5 실제 제출 클라
    expect(pv).to_contain_text("R5 E1 제출 클라")
    expect(pv).to_contain_text("C1·C4 + C2 늦게 (대기 제한에 걸리면 빠짐)")
    pg.select_option("#run_fault_drop_client", "C2")  # 지연 클라와 같은 클라 → 오류
    expect(pg.locator("#run_errors")).to_contain_text("지연·중단")
    expect(pg.locator("#run_go")).to_be_disabled()
    pg.get_by_role("button", name="기본값으로").click()
    expect(pg.locator("#run_fault_round")).to_be_disabled()

    pg.get_by_role("button", name="E1 순위에서 C6 올리기").click()  # 4위 → 3위
    expect(pg.locator(".run_edge").first.locator("li").nth(2)).to_contain_text("C6")
    r0 = pg.evaluate("() => state.round")
    pg.keyboard.press("ArrowRight")
    assert pg.evaluate("() => state.round") == r0
    assert pg.evaluate("() => document.documentElement.scrollHeight - innerHeight") <= 0
    pg.close()


def check_fault_view(browser, url, errors):
    """지연·중단 실험 (시험 로그 exp_pref_seed42_fault, R5: C2 지연 → 대기 제한 넘겨 409, C6 중단)
    트리 아래 빠진 이유, 비교 실험 = 같은 배정의 기본 실험, 비교를 직접 고르면 그 뒤로 안 바꿈"""
    pg = _open(browser, url, errors)
    _select_exp(pg, "exp_pref_seed42_fault")
    pg.wait_for_function("() => state.compare_exp === 'exp_pref_seed42'")  # 무작위가 아니라 같은 선호 배정 기본 실험
    pg.evaluate("() => set_round(5)")
    note = pg.evaluate("() => chart_of('p_tree').getOption().title[0].text")
    assert "C2 늦게 제출 → 거부 409" in note and "C6 제출 없음(중단)" in note, note
    assert pg.evaluate("() => chart_of('p_tree').getOption().series[0].right") >= 180  # '시험 1 · 미참여' 가 안 잘리게 여백
    pg.evaluate("() => set_round(4)")
    assert pg.evaluate("() => chart_of('p_tree').getOption().title[0].text") == ""  # 빠진 클라 없는 라운드
    pg.select_option("#compare_exp", "exp_random_seed42_inject")  # 직접 고름
    _select_exp(pg, "exp_pref_seed42")
    assert pg.evaluate("() => state.compare_exp") == "exp_random_seed42_inject"
    picks = pg.evaluate("""() => { const ex = ['exp_pref_seed42', 'exp_pref_seed42_inject', 'exp_random_seed42', 'exp_random_seed7',
                                               'run-1/exp_pref_seed42_inject_fault', 'run-2/exp_random_seed7_fault', 'run-3/exp_pref_seed7'];
                                    return ex.map(e => default_compare(e, ex)); }""")
    assert picks == ["exp_random_seed42", "exp_pref_seed42", "exp_pref_seed42", "run-3/exp_pref_seed7",
                     "exp_pref_seed42_inject", "exp_random_seed7", "exp_random_seed7"], picks  # 꼬리표 하나씩, 시드 같은 것
    pg.close()


def check_compare_caption(browser, url, errors):
    """실험 비교 해석이 과장하지 않음: 설정이 다르면 그렇다고, 빠진 라운드가 마지막이면 '회복' 이라고 안 함"""
    pg = _open(browser, url, errors)
    _select_exp(pg, "exp_pref_seed42_fault")
    pg.wait_for_function("() => state.compare_bundle && state.compare_exp === 'exp_pref_seed42'")
    cap = lambda: pg.evaluate("() => document.querySelector('#p_compare caption').textContent")
    pg.evaluate("""() => { const c = state.compare_bundle; c.config = {...c.config, lr: 0.05}; notify(); }""")  # 학습률이 다르면
    assert "학습 설정이 다름 (학습률)" in cap(), cap()
    pg.evaluate("""() => { const b = state.bundle, c = state.compare_bundle; c.config = {...b.config};
        b.train = b.train.map(x => (x.round === 6 && x.target === 'C6' ? {...x, participated: false} : x));  // 마지막 라운드에 빠짐
        notify(); }""")
    assert "R7 부터" not in cap(), cap()
    pg.close()


def check_algo_tab(browser, url, errors):
    """알고리즘 비교 탭 (작은 가짜 결과): 표·곡선·산점도·히트맵, epoch·시드 바꾸기, 알고리즘 고정 → 다른 줄 흐림"""
    pg = _open(browser, url, errors)
    pg.get_by_role("tab", name="알고리즘 비교").click()
    expect(pg.locator("#p_algo_table tbody tr")).to_have_count(2)
    expect(pg.locator("#kpi")).to_be_hidden()
    assert pg.evaluate("() => chart_of('p_algo_curve').getOption().series.length") == 2
    assert pg.evaluate("() => chart_of('p_algo_tradeoff').getOption().series.length") == 2  # epoch 1·5
    expect(pg.locator("#p_algo_table caption")).to_contain_text("FedProx μ=1 정확도 -2.0%p")
    pg.locator("#algo_epoch label", has_text="5").click()
    assert pg.evaluate("() => algo_ui.epoch") == 5
    pg.locator("#algo_seed label", has_text="42").click()
    expect(pg.locator("#p_algo_table tbody tr").first).not_to_contain_text("~")  # 시드 하나면 범위 없음
    pg.locator("#p_algo_table tbody tr").nth(1).click()  # FedProx 고정
    expect(pg.locator("#p_algo_table tbody tr.dim")).to_have_count(1)
    assert pg.evaluate("() => document.documentElement.scrollHeight - innerHeight") <= 0
    pg.close()


def check_sample_blocks_run(browser, url, errors):
    """시험 로그를 보는 중이면 미리보기는 되고 실행은 막힘 (이유 표시)"""
    pg = _open(browser, url, errors)
    pg.get_by_role("tab", name="실험 실행").click()
    expect(pg.locator("#run_preview table")).to_contain_text("C1·C2·C4")
    expect(pg.locator("#run_errors")).to_contain_text("시험 로그")
    expect(pg.locator("#run_go")).to_be_disabled()
    pg.close()


def check_empty_run(browser, url, errors):
    """시작 직후 죽은 실험(기록 0개)도 오류 없이 안내 문구"""
    pg = _open(browser, url, errors)
    expect(pg.locator("#status")).to_contain_text("끝난 라운드")  # '없음' 또는 '0/3 · 자동 갱신'
    expect(pg.locator("#kpi")).to_contain_text("0 라운드")
    pg.close()


def check_run_fail(browser, url, errors):
    """서버 포트가 막혀 run_all 이 바로 실패: '실패' 와 실행 기록 표시, 버튼 다시 켜짐, 상태 확인 반복 멈춤"""
    from hfl.common import load_config
    u = urlsplit(load_config()["central_url"])
    blocker = socket.socket()
    blocker.bind((u.hostname, u.port))
    blocker.listen()
    try:
        pg = browser.new_page(viewport={"width": 1920, "height": 1080})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url + "#run")
        expect(pg.locator("#run_preview table")).to_contain_text("C1·C2·C4")
        pg.fill("#run_rounds", "1")
        pg.get_by_role("button", name="실행").click()
        expect(pg.locator("#run_state")).to_contain_text("실패", timeout=60000)
        expect(pg.locator("#run_log")).to_contain_text("포트")
        expect(pg.locator("#run_go")).to_be_enabled()
        pg.wait_for_function("() => run_ui.watching === null", timeout=5000)
        pg.close()
    finally:
        blocker.close()


def check_no_logs(browser, url, errors):
    """로그가 하나도 없어도 실험 실행 탭은 열려서 첫 실험을 돌릴 수 있음"""
    pg = browser.new_page(viewport={"width": 1920, "height": 1080})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(url)
    expect(pg.locator("#kpi")).to_contain_text("로그가 없습니다")
    pg.get_by_role("tab", name="실험 실행").click()
    expect(pg.locator("#run_preview table")).to_contain_text("C1·C2·C4")
    pg.close()


def _append_round(exp_dir, full, r):
    """시험 로그에서 라운드 r 줄만 실행 중인 실험 폴더에 이어 씀 (runner 가 쓰는 것처럼)"""
    for name in ("train.jsonl", "comm.jsonl"):
        rows = [x for x in full[name] if x["round"] == r]
        with open(exp_dir / name, "a", encoding="utf-8") as f:
            f.writelines(json.dumps(x, ensure_ascii=False) + "\n" for x in rows)


def check_live(browser, url, errors, root):
    """실행 중 화면 갱신: 새 라운드를 따라감, 중간에 열어도 마지막 라운드부터, 예전 라운드를 보고 있으면 그대로 둠, 새 실험은 목록·비교에 추가"""
    full = {n: _log("exp_pref_seed42", n) for n in ("train.jsonl", "comm.jsonl")}
    run = root / "exp_pref_seed42"
    pg = _open(browser, url, errors)
    assert pg.evaluate("() => [state.round, done_rounds(state.bundle)]") == [1, 1]
    expect(pg.locator("#status")).to_contain_text("자동 갱신")

    _append_round(run, full, 2)
    pg.wait_for_function("() => state.round === 2", timeout=8000)  # 마지막 라운드를 보던 중 → 따라감
    late = _open(browser, url, errors)  # 실행 중간에 연 화면도 라운드 1이 아니라 마지막 라운드부터
    assert late.evaluate("() => state.round") == 2
    late.close()

    pg.evaluate("() => set_pin({type: 'client', id: 'C3'})")
    pg.evaluate("() => set_round(1)")  # 예전 라운드로 돌아가 있으면
    _append_round(run, full, 3)
    pg.wait_for_function("() => done_rounds(state.bundle) === 3", timeout=8000)
    assert pg.evaluate("() => [state.round, state.pinned && state.pinned.id, document.getElementById('round').max]") == [1, "C3", "3"]
    expect(pg.locator("#status")).to_contain_text("실행 끝")

    shutil.copytree(SAMPLE_ROOT / "exp_random_seed42_inject", root / "exp_random_seed42_inject")  # 다음 실험이 생기면
    expect(pg.locator("#exp option")).to_have_count(2, timeout=8000)
    pg.wait_for_function("() => state.compare_exp === 'exp_random_seed42_inject'", timeout=8000)  # 자기와 비교하던 걸 다른 배정 실험으로
    pg.close()


def test_ui():
    if sync_playwright is None:
        print("SKIP test_ui (playwright 없음)")
        return
    empty_root = Path(tempfile.mkdtemp())
    shutil.copytree(SAMPLE_ROOT / "exp_pref_seed42", empty_root / "exp_empty")
    (empty_root / "exp_empty" / "train.jsonl").unlink()
    (empty_root / "exp_empty" / "comm.jsonl").unlink()
    no_logs_root = Path(tempfile.mkdtemp())  # 실험 폴더가 하나도 없음
    algo_root = Path(tempfile.mkdtemp())  # 알고리즘 비교 결과(가짜) + 실험 하나
    shutil.copytree(SAMPLE_ROOT / "exp_pref_seed42", algo_root / "exp_pref_seed42")
    from tests.test_dashboard import make_algo_fixture
    make_algo_fixture(algo_root)
    live_root = Path(tempfile.mkdtemp())  # 라운드 1까지만 쓴 '실행 중' 실험
    run = live_root / "exp_pref_seed42"
    shutil.copytree(SAMPLE_ROOT / "exp_pref_seed42", run)
    for name in ("train.jsonl", "comm.jsonl"):
        rows = [x for x in _log("exp_pref_seed42", name) if x["round"] <= 1]
        (run / name).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            plan = [(SAMPLE_ROOT, [check_kpi, check_linking, check_keyboard_and_hover, check_layout, check_tabs, check_sample_blocks_run, check_fault_view, check_compare_caption]),
                    (algo_root, [check_algo_tab]),
                    (empty_root, [check_empty_run, check_run_tab]),
                    (no_logs_root, [check_no_logs, check_run_fail]),
                    (live_root, [lambda b, u, e: check_live(b, u, e, live_root)])]
            for root, checks in plan:
                srv, url = _serve(root)
                try:
                    for check in checks:  # 검사마다 새 페이지 → 서로 상태 공유 없음
                        errors = []
                        check(browser, url, errors)
                        name = "check_live" if check.__name__ == "<lambda>" else check.__name__
                        assert not errors, (name, errors)
                        print("PASS", name)
                finally:
                    srv.shutdown()
            browser.close()
    finally:
        shutil.rmtree(empty_root)
        shutil.rmtree(no_logs_root)
        shutil.rmtree(algo_root)
        shutil.rmtree(live_root)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    test_ui()
