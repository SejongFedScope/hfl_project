"""C 검사 — 담당 C(김영헌), 로그 API 엣지 케이스 · 실험 실행 탭 API. 실행: python -m tests.test_dashboard"""
import shutil
import socket
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from hfl.common import load_config

from dashboard.app import ALGO, ANALYSIS, REGIONS, SAMPLE_ROOT, SCRIPTS, app


def _logs_with_edge_cases():
    root = Path(tempfile.mkdtemp())
    shutil.copytree(SAMPLE_ROOT / "exp_pref_seed42", root / "exp_ok")
    (root / "exp_broken").mkdir()  # 설정만 있고 분할·배정이 없는 깨진 폴더
    shutil.copy(SAMPLE_ROOT / "exp_pref_seed42" / "config.json", root / "exp_broken" / "config.json")
    shutil.copytree(SAMPLE_ROOT / "exp_pref_seed42", root / "exp_cut")
    with open(root / "exp_cut" / "train.jsonl", "a", encoding="utf-8") as f:
        f.write('{"round": 9, "tar')  # 프로세스가 죽어서 잘린 마지막 줄
    shutil.copytree(SAMPLE_ROOT / "exp_pref_seed42", root / "exp_empty")
    (root / "exp_empty" / "train.jsonl").unlink()  # 시작 직후 죽어서 기록 없음
    (root / "exp_empty" / "comm.jsonl").unlink()
    return root


def test_edge_cases():
    root = _logs_with_edge_cases()
    app.config["LOG_ROOT"] = root
    c = app.test_client()
    try:
        assert c.get("/api/experiments").get_json() == ["exp_cut", "exp_empty", "exp_ok"]  # 깨진 폴더는 목록에서 빠짐
        assert c.get("/api/exp_broken/bundle").status_code == 404
        r = c.get("/api/nope/bundle")  # /api 오류는 HTML 이 아니라 {"message"} (수업 5장 에러 형식)
        assert r.status_code == 404 and r.is_json and r.get_json()["message"]
        r = c.post("/api/experiments")
        assert r.status_code == 405 and r.get_json()["message"]
        for bad in ("nope", "..", "..%2F..%2Fconfigs", "exp_ok%2F.."):  # 로그 폴더 밖으로 못 나감
            assert c.get(f"/api/{bad}/bundle").status_code == 404, bad

        ok = c.get("/api/exp_ok/bundle").get_json()
        cut = c.get("/api/exp_cut/bundle").get_json()
        assert len(cut["train"]) == len(ok["train"])  # 잘린 줄만 건너뜀
        assert all("indices" not in v for v in ok["split"]["clients"].values())  # 화면에 안 쓰는 인덱스는 뺌

        empty = c.get("/api/exp_empty/bundle").get_json()
        assert empty["train"] == [] and empty["comm"] == [] and empty["assignment"]["assignment"]

        html = c.get("/").get_data(as_text=True)  # Jinja 템플릿: 개요·분석 패널과 스크립트가 목록대로 나오고 로그 출처가 보임
        panel_ids = [p["id"] for r in REGIONS for p in r["panels"]] + [p["id"] for p in ANALYSIS] + [p["id"] for p in ALGO]
        assert all(f'id="{i}"' in html for i in panel_ids) and html.count('<script src="/static/') == len(SCRIPTS) + 1  # + echarts
        assert "실제 로그" in html and "{%" not in html and "{{" not in html

        app.config["LOG_ROOT"] = root / "없는_폴더"
        assert c.get("/api/experiments").get_json() == []
    finally:
        shutil.rmtree(root)


def test_make_report():
    """시험 로그로 보고서 생성: 표시 사이만 바뀌고 사람이 쓴 글은 그대로, 시험 요청은 성공률에서 빠짐"""
    from scripts import make_report
    root = Path(tempfile.mkdtemp())
    try:
        shutil.copytree(SAMPLE_ROOT / "exp_pref_seed42", root / "logs" / "exp_pref_seed42")
        shutil.copytree(SAMPLE_ROOT / "exp_random_seed42_inject", root / "logs" / "exp_random_seed42_inject")
        shutil.copytree(SAMPLE_ROOT / "exp_random_seed42_inject", root / "logs" / "exp_random_seed42")  # 결함 주입 없는 무작위 실험으로 씀
        cfg_path = root / "logs" / "exp_random_seed42" / "config.json"
        cfg_path.write_text(cfg_path.read_text(encoding="utf-8").replace('"inject": true', '"inject": false'), encoding="utf-8")
        report = root / "docs" / "report.md"
        report.parent.mkdir()
        report.write_text("손으로 쓴 머리말\n<!-- auto:conditions -->\n옛 표\n<!-- /auto:conditions -->\n손으로 쓴 해석\n"
                          + "".join(f"<!-- auto:{k} -->\n<!-- /auto:{k} -->\n" for k in ("preference", "edges", "performance", "comm")), encoding="utf-8")

        make_report.main(["--logs", str(root / "logs"), "--out", str(report)])
        text = report.read_text(encoding="utf-8")
        assert "손으로 쓴 머리말" in text and "손으로 쓴 해석" in text and "옛 표" not in text
        assert "| 시드 | 42 |" in text and "두 실험 학습 조건 동일 | 예" in text
        assert "엣지 간 숫자 분포 차이 (0 = 같음, 1 = 완전히 다름): 선호 **0.67**, 무작위 **0.00**" in text
        assert "| 선호 + 결함 주입 |" in text and "2 (409 2)" in text  # 시험 요청은 따로 셈
        assert (root / "docs" / "img" / "report_acc.svg").exists() and (root / "docs" / "img" / "report_edge_digits.svg").exists()

        report.write_text("표시 없음", encoding="utf-8")  # 표시가 없으면 덮어쓰지 않고 멈춤
        try:
            make_report.main(["--logs", str(root / "logs"), "--out", str(report)])
            raise AssertionError("표시가 없는데 멈추지 않음")
        except SystemExit:
            assert report.read_text(encoding="utf-8") == "표시 없음"
    finally:
        shutil.rmtree(root)


def test_run_validation():
    """실험 실행 탭: 기본값 미리보기, 잘못된 입력은 400 (서버가 다시 검사), 시험 로그 모드는 실행 금지"""
    app.config["LOG_ROOT"] = Path(tempfile.mkdtemp())  # 앞 검사가 바꿔 둔 폴더(시험 로그면 실행 409)에 안 기대게
    c = app.test_client()
    d = c.get("/api/run/defaults").get_json()
    pv = c.post("/api/run/preview", json=d).get_json()["preview"]
    assert pv["pref"]["assignment"] == {"E1": ["C1", "C2", "C4"], "E2": ["C3", "C5", "C6"]} and pv["pref"]["violations"] == 0
    assert pv["random"]["mean_pref_rank"] == 1.5
    bad_cases = {
        "숫자 0개": {"client_digits": {**d["client_digits"], "C2": []}},
        "안 나눠짐": {"client_digits": {**d["client_digits"], "C2": [0, 1, 2, 3, 4, 5, 6]}},
        "숫자 범위 밖": {"client_digits": {**d["client_digits"], "C2": [3, 10]}},
        "엣지 선호 동점(중복)": {"edge_prefs": {**d["edge_prefs"], "E1": ["C1", "C1", "C2", "C3", "C4", "C5"]}},
        "클라 선호 빠짐": {"client_prefs": {**d["client_prefs"], "C3": ["E2"]}},
        "라운드 0": {"rounds": 0},
        "학습률 글자": {"lr": "0.1"},
        "정수에 소수": {"batch_size": 3.5},
        "참·거짓": {"seed": True},
        "배정 방식 없음": {"methods": []},
        "모르는 배정 방식": {"methods": ["pref", "best"]},
        "초기 모델": {"init_model": "ones"},
        "주입 라운드 > 라운드": {"inject": True, "rounds": 3, "inject_round": 5},
        "클라 7번째": {"client_digits": {**d["client_digits"], "C7": [1]}},
        "숫자에 글자 섞임": {"client_digits": {**d["client_digits"], "C1": [1, "a"]}},
        "숫자에 객체": {"client_digits": {**d["client_digits"], "C1": [{}, {}]}},
        "선호에 숫자 섞임": {"client_prefs": {**d["client_prefs"], "C1": ["E1", 1]}},
        "MNIST 장수 초과": {"samples_per_client": 3000, "client_digits": {**d["client_digits"], "C1": [5], "C2": [5]}},  # 숫자 5 는 5,421장뿐
        "한 숫자에 몰림": {"client_digits": {c: [1] for c in d["client_digits"]}},  # 1,200 × 6 > 6,742
    }
    for name, change in bad_cases.items():
        r = c.post("/api/run/preview", json={**d, **change})
        assert r.status_code == 400 and r.get_json()["errors"] and r.get_json()["message"], name
        assert c.post("/api/run", json={**d, **change}).status_code == 400, name
    assert c.post("/api/run/preview", json={**d, "inject": False, "inject_round": None}).status_code == 200  # 주입을 끄면 주입 라운드는 안 봄
    for raw in ('{"seed": NaN}', '{"rounds": Infinity}', "[1, 2]", '"x"', "5"):  # 화면은 안 보내지만 API 를 직접 부르면 → 500 이 아니라 400
        assert c.post("/api/run/preview", data=raw, content_type="application/json").status_code == 400, raw
    assert c.post("/api/run", data="{}", content_type="text/plain").status_code == 415  # 다른 사이트의 단순 POST(사전 확인 없음) 차단
    assert c.post("/api/run/stop").status_code == 415
    assert c.get("/api/run/status", headers={"Host": "evil.example:5050"}).status_code == 403  # DNS rebinding 차단
    app.config["LOG_ROOT"] = SAMPLE_ROOT  # 시험 로그를 보고 있으면 (--sample 등) 실행 금지 → git 에 있는 시험 로그를 안 덮어씀
    assert c.get("/api/run/defaults").get_json()["run_allowed"] is False
    assert c.post("/api/run", json=d).status_code == 409
    for raw in ('{"seed": ' + "9" * 400 + "}", "[" * 100000 + "]" * 100000):  # 아주 큰 정수, 아주 깊은 중첩 → 500 아님
        assert c.post("/api/run/preview", data=raw, content_type="application/json").status_code == 400, raw[:20]


def make_algo_fixture(root):
    """알고리즘 비교 결과 작은 가짜 (담당 A scripts/compare_algorithms.py 와 같은 모양): epoch 1·5 × FedAvg·FedProx μ=1, 시드 42·7, 3라운드"""
    import json
    out = root / "algo_compare"
    results = []
    for seed in (42, 7):
        for e in (1, 5):
            for algo, mu in (("fedavg", 0.0), ("fedprox", 1.0)):
                exp_id = f"alg_{algo}_e{e}_seed{seed}"
                acc = [0.7 + 0.05 * r - (0.02 if mu else 0) for r in range(3)]
                (out / exp_id).mkdir(parents=True)
                (out / exp_id / "train.jsonl").write_text("".join(json.dumps(
                    {"target": "global", "round": r + 1, "acc": a, "acc_by_digit": [a - 0.01 * d for d in range(10)]}) + "\n" for r, a in enumerate(acc)), encoding="utf-8")
                results.append({"seed": seed, "exp_id": exp_id, "algorithm": algo, "mu": mu, "q": None, "local_epochs": e,
                                "final_acc": acc[-1], "final_loss": 0.5, "best_acc": acc[-1], "final_min_digit_acc": acc[-1] - 0.09,
                                "acc_drop_rounds": 0, "final_client_acc_min": 0.4, "mean_update_norm": 0.5 if mu else 1.0,
                                "final_own_acc_min": 0.8, "final_digit_acc_std": 0.07,
                                "history": [{"round": r + 1, "acc": a} for r, a in enumerate(acc)]})
    (out / "summary.json").write_text(json.dumps({"rounds": 3, "structure": "single_central", "seeds": [42, 7], "results": results}), encoding="utf-8")


def test_algo_api():
    """알고리즘 비교 API: 결과가 없으면 404 + 만드는 명령, 있으면 실험마다 마지막 라운드 숫자별 정확도까지"""
    root = Path(tempfile.mkdtemp())
    app.config["LOG_ROOT"] = root
    c = app.test_client()
    try:
        r = c.get("/api/algo")
        assert r.status_code == 404 and "compare_algorithms" in r.get_json()["hint"]
        make_algo_fixture(root)
        d = c.get("/api/algo").get_json()
        assert len(d["results"]) == 8 and all(len(x["final_by_digit"]) == 10 for x in d["results"])
        assert c.get("/api/experiments").get_json() == []  # algo_compare 폴더는 실험 목록에 안 섞임
        import json
        summary = json.loads((root / "algo_compare" / "summary.json").read_text(encoding="utf-8"))
        summary["results"][0]["exp_id"] = "../../outside"  # summary 안 이름으로 폴더 밖을 못 읽음
        (root / "algo_compare" / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        assert c.get("/api/algo").get_json()["results"][0]["final_by_digit"] is None
        (root / "algo_compare" / "summary.json").write_text("{\"results\": [", encoding="utf-8")  # 쓰는 도중
        r = c.get("/api/algo")
        assert r.status_code == 500 and r.is_json and "hint" in r.get_json()
    finally:
        app.config["LOG_ROOT"] = SAMPLE_ROOT
        shutil.rmtree(root, ignore_errors=True)


def test_run_fault():
    """실험 실행 탭의 지연·중단 주입: 미리보기에 엣지별 실제 제출 클라, 잘못된 조합은 400 (담당 B check_fault 그대로)"""
    c = app.test_client()
    d = c.get("/api/run/defaults").get_json()
    pv = c.post("/api/run/preview", json={**d, "fault_on": True}).get_json()["preview"]
    assert pv["pref"]["fault_edges"] == {"E1": {"sure": ["C1", "C4"], "late": ["C2"]}, "E2": {"sure": ["C3", "C5"], "late": []}}  # C6 중단, C2 는 늦게 (장담 못 함)
    r = c.post("/api/run/preview", json={**d, "fault_on": True, "fault": {**d["fault"], "deadline_sec": 0.3}})  # 평소 라운드에도 3명이 못 모임 → 실행이 멈췄던 값
    assert r.status_code == 400 and [e["field"] for e in r.get_json()["errors"]] == ["fault.deadline_sec"]
    r = c.post("/api/run/preview", json={**d, "fault_on": True, "local_epochs": 10})  # 학습량이 크면 기본 2초도 모자람
    assert r.status_code == 400 and "fault.deadline_sec" in [e["field"] for e in r.get_json()["errors"]]
    r = c.post("/api/run/preview", json={**d, "fault_on": True, "fault": {**d["fault"], "round": 30}})
    assert "fault.round" in [e["field"] for e in r.get_json()["errors"]]  # 라운드 칸에 표시
    bad = {"같은 클라 지연·중단": {"drop_client": "C2"}, "라운드 범위 밖": {"round": 99}, "없는 클라": {"delay_client": "C9"},
           "지연 0초": {"delay_sec": 0}, "대기 제한 글자": {"deadline_sec": "2"}}  # (엣지 정원 3, 빠지는 클라 최대 2 → 엣지가 비는 경우는 없음)
    for name, ch in bad.items():
        body = {**d, "fault_on": True, "fault": {**d["fault"], **ch}}
        r = c.post("/api/run/preview", json=body)
        assert r.status_code == 400 and any(e["field"].startswith("fault") for e in r.get_json()["errors"]), (name, r.get_json())
    assert c.post("/api/run/preview", json={**d, "fault_on": False, "fault": None}).status_code == 200  # 끄면 안 봄


def test_run_markers():
    """화면에서 돌린 실험의 '멈춤' 표시: 덜 끝난 실험에만, 대시보드가 꺼졌다 켜져도 '중간에 끊김', 같은 초 -2 는 뒤로"""
    import json
    from dashboard import runs
    root = Path(tempfile.mkdtemp())
    try:
        for tag in ("run-20990101-000000", "run-20990101-000000-2"):
            shutil.copytree(SAMPLE_ROOT / "exp_pref_seed42", root / tag / "exp_pref_seed42")  # 시험 로그 = 3라운드 다 끝남
        cut = root / "run-20990101-000000" / "exp_random_seed42"
        shutil.copytree(SAMPLE_ROOT / "exp_pref_seed42", cut)
        rows = [x for x in map(json.loads, (cut / "train.jsonl").read_text(encoding="utf-8").splitlines()) if x["round"] <= 1]
        (cut / "train.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")  # 1/3 라운드에서 멈춤
        app.config["LOG_ROOT"] = root
        c = app.test_client()
        assert c.get("/api/experiments").get_json() == ["run-20990101-000000/exp_pref_seed42", "run-20990101-000000/exp_random_seed42",
                                                        "run-20990101-000000-2/exp_pref_seed42"]
        assert c.get("/api/run-20990101-000000/exp_pref_seed42/bundle").get_json()["ended"] is None  # 다 끝난 실험
        assert c.get("/api/run-20990101-000000/exp_random_seed42/bundle").get_json()["ended"] == {"reason": "interrupted"}  # 재시작 뒤

        runs.job.update(proc=None, dir=root / "run-20990101-000000", tag="run-20990101-000000", rounds=3, marked=False,
                        exps=["run-20990101-000000/exp_pref_seed42", "run-20990101-000000/exp_random_seed42"])
        runs._mark_ended("stopped")  # 두 실험 중 두 번째에서 중지한 경우
        assert not (root / "run-20990101-000000" / "exp_pref_seed42" / "ended.json").exists()
        assert c.get("/api/run-20990101-000000/exp_random_seed42/bundle").get_json()["ended"]["reason"] == "stopped"
    finally:
        runs.job.update(proc=None, dir=None, tag=None, exps=[], marked=False, rounds=0)
        app.config["LOG_ROOT"] = SAMPLE_ROOT
        shutil.rmtree(root, ignore_errors=True)


def _ports_free(cfg):
    for url in [cfg["central_url"], *cfg["edge_urls"].values()]:
        u = urlsplit(url)
        with socket.socket() as sk:
            sk.settimeout(1)
            if sk.connect_ex((u.hostname, u.port)) == 0:
                return False
    return True


def _wait(c, cond, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        st = c.get("/api/run/status").get_json()
        if cond(st):
            return st
        time.sleep(0.5)
    raise AssertionError(f"시간 초과: {st}")


def test_run_real():
    """실제 실행: 바꾼 설정으로 학습 → run-…/exp_… 가 목록에 뜸, 기존 실험 그대로 / 중지하면 서버까지 꺼짐"""
    cfg = load_config()
    if not _ports_free(cfg):
        print("SKIP test_run_real (서버 포트 사용 중: 떠 있는 run_all 을 끄고 다시)")
        return
    root = Path(tempfile.mkdtemp())
    shutil.copytree(SAMPLE_ROOT / "exp_pref_seed42", root / "exp_pref_seed42")  # 원래 실험 (덮어쓰면 안 됨)
    before = (root / "exp_pref_seed42" / "train.jsonl").read_bytes()
    app.config["LOG_ROOT"] = root
    c = app.test_client()
    try:
        d = c.get("/api/run/defaults").get_json()
        body = {**d, "rounds": 2, "seed": 7, "methods": ["pref"], "client_digits": {**d["client_digits"], "C2": [3, 4, 5, 6]}}
        r = c.post("/api/run", json=body)
        assert r.status_code == 202, r.get_json()
        exp = r.get_json()["exps"][0]
        assert exp.endswith("/exp_pref_seed7")
        assert c.post("/api/run", json=body).status_code == 409  # 한 번에 하나
        st = _wait(c, lambda s: not s["running"])
        assert st["returncode"] == 0, st["log_tail"]
        assert c.get("/api/experiments").get_json() == ["exp_pref_seed42", exp]
        b = c.get(f"/api/{exp}/bundle").get_json()
        assert b["config"]["seed"] == 7 and b["config"]["client_digits"]["C2"] == [3, 4, 5, 6]
        assert sum(x["target"] == "global" for x in b["train"]) == 2
        assert (root / "exp_pref_seed42" / "train.jsonl").read_bytes() == before

        r = c.post("/api/run", json={**body, "rounds": 100})  # 중지: run_all 과 서버 3개 모두 꺼져야 다음 실행 가능
        assert r.status_code == 202
        _wait(c, lambda s: (root / r.get_json()["exps"][0] / "train.jsonl").exists())
        st = c.post("/api/run/stop", json={}).get_json()
        assert st["stopped"] and not st["running"]
        assert st["log_tail"], "중지하면 실행 기록이 사라짐 (출력 버퍼)"
        _wait(c, lambda s: _ports_free(cfg), timeout=15)
        stopped = c.get(f"/api/{r.get_json()['exps'][0]}/bundle").get_json()
        assert stopped["ended"]["reason"] == "stopped"  # 화면이 '실행 중'으로 착각하지 않게
    finally:
        app.config["LOG_ROOT"] = SAMPLE_ROOT
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    for t in (test_edge_cases, test_make_report, test_run_validation, test_algo_api, test_run_fault, test_run_markers, test_run_real):
        t()
        print("PASS", t.__name__)
