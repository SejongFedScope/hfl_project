"""C 검사 — 담당 C(김영헌), 화면 동작 (브라우저). 실행: python -m tests.test_ui
시험 로그(dashboard/sample_logs)로 대시보드를 띄우고 진짜 브라우저(창 없음)로 클릭·키보드를 눌러 확인.
playwright 가 없으면 건너뜀: pip install playwright && python -m playwright install chromium
"""
import json
import logging
import shutil
import sys
import tempfile
import threading
from pathlib import Path

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
    pg.close()


def check_empty_run(browser, url, errors):
    """시작 직후 죽은 실험(기록 0개)도 오류 없이 안내 문구"""
    pg = _open(browser, url, errors)
    expect(pg.locator("#status")).to_contain_text("끝난 라운드가 없음")
    expect(pg.locator("#kpi")).to_contain_text("0 라운드")
    pg.close()


def test_ui():
    if sync_playwright is None:
        print("SKIP test_ui (playwright 없음)")
        return
    empty_root = Path(tempfile.mkdtemp())
    shutil.copytree(SAMPLE_ROOT / "exp_pref_seed42", empty_root / "exp_empty")
    (empty_root / "exp_empty" / "train.jsonl").unlink()
    (empty_root / "exp_empty" / "comm.jsonl").unlink()
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            plan = [(SAMPLE_ROOT, [check_kpi, check_linking, check_keyboard_and_hover, check_layout]), (empty_root, [check_empty_run])]
            for root, checks in plan:
                srv, url = _serve(root)
                try:
                    for check in checks:  # 검사마다 새 페이지 → 서로 상태 공유 없음
                        errors = []
                        check(browser, url, errors)
                        assert not errors, (check.__name__, errors)
                        print("PASS", check.__name__)
                finally:
                    srv.shutdown()
            browser.close()
    finally:
        shutil.rmtree(empty_root)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    test_ui()
