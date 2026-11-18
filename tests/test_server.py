"""B 검사 — 담당 B(윤효연), WBS 3.2.6 · 3.4.3. 실행: python -m tests.test_server"""
from hfl.assign import check_assignment, edge_composition, make_assignment
from hfl.common import DEFAULT_CONFIG, read_json
from hfl.model import N_PARAMS
from servers import central, edge


def _default_cfg():
    # 손계산 기대값이 default.json 기준이라 HFL_CONFIG 와 상관없이 기본 설정을 씀
    return read_json(DEFAULT_CONFIG)


def test_assignment_no_violation():
    """pref·random 둘 다 미배정·중복·정원 위반 0"""
    cfg = _default_cfg()
    for method in ("pref", "random"):
        a = make_assignment(cfg, method)
        chk = check_assignment(a, cfg)
        assert chk["unassigned"] == [], (method, chk)
        assert chk["duplicated"] == [], (method, chk)
        assert chk["capacity_violation"] == [], (method, chk)
        assert sorted(c for cs in a.values() for c in cs) == sorted(cfg["client_prefs"]), (method, a)

    # pref 손계산: 1순위로 E1 을 고른 클라가 4명(C1 C2 C4 C6) → E1 이 자기 순위대로 C1 C4 C2 를 남기고 C6 탈락 → C6 은 2순위 E2
    a = make_assignment(cfg, "pref")
    assert a == {"E1": ["C1", "C2", "C4"], "E2": ["C3", "C5", "C6"]}, a
    chk = check_assignment(a, cfg)
    assert chk["client_pref_rank"] == {"C1": 1, "C2": 1, "C3": 1, "C4": 1, "C5": 1, "C6": 2}, chk
    assert abs(chk["mean_pref_rank"] - 7 / 6) < 1e-12, chk

    # random 은 시드가 같으면 몇 번을 돌려도 같은 결과
    assert make_assignment(cfg, "random") == make_assignment(cfg, "random")

    # 일부러 망가뜨린 배정을 검사가 잡아내는지: C5 미배정, C6 중복, E1 정원 초과
    bad = {"E1": ["C1", "C2", "C4", "C6"], "E2": ["C3", "C6"]}
    chk = check_assignment(bad, cfg)
    assert chk["unassigned"] == ["C5"], chk
    assert chk["duplicated"] == ["C6"], chk
    assert chk["capacity_violation"] == ["E1"], chk
    assert chk["client_pref_rank"]["C5"] is None and chk["client_pref_rank"]["C6"] is None, chk


def test_edge_composition():
    """엣지별 클라 수·표본 합·숫자별 표본 수 (split_summary 모양의 가짜 입력으로 확인)"""
    cfg = _default_cfg()
    summary = {}
    for c, digits in cfg["client_digits"].items():
        per = cfg["samples_per_client"] // len(digits)  # 숫자 3개면 400, 4개면 300
        summary[c] = {"n": cfg["samples_per_client"], "digit_counts": [per if d in digits else 0 for d in range(10)]}

    comp = edge_composition({"E1": ["C1", "C2", "C4"], "E2": ["C3", "C5", "C6"]}, summary)
    assert comp["E1"] == {"clients": ["C1", "C2", "C4"], "n_clients": 3, "n": 3600,
                          "digit_counts": [800, 800, 800, 400, 400, 400, 0, 0, 0, 0]}, comp
    assert comp["E2"] == {"clients": ["C3", "C5", "C6"], "n_clients": 3, "n": 3600,
                          "digit_counts": [0, 0, 0, 400, 400, 400, 600, 600, 600, 600]}, comp


def test_reject_409():
    """Flask test_client: 지난 버전 제출, 배정 안 된 클라 제출 → 409
    거부된 요청은 서버 상태를 바꾸지 않아야 함. (전원 제출 전까지만 보내서 집계·로그 기록은 안 일어남)
    """
    w = [0.0] * N_PARAMS

    # 중앙
    s = central.app.test_client()
    up = {"edge_id": "E1", "version": 1, "weights": w, "n_samples": 3600}
    _expect_409(s.post("/edge_update", json=up), "not started")
    assert s.post("/start", json={"exp_id": "exp_test409", "edges": ["E1", "E2"]}).status_code == 200
    _expect_409(s.post("/edge_update", json={**up, "version": 0}), "version mismatch")  # 지난 버전
    _expect_409(s.post("/edge_update", json={**up, "edge_id": "E9"}), "unknown edge")
    st = s.get("/status").get_json()
    assert st["version"] == 1 and st["submitted"] == [], st
    r = s.post("/edge_update", json=up)  # 정상 제출은 받음 (2개 중 1개라 아직 집계 안 함)
    assert r.status_code == 200 and r.get_json() == {"ok": True, "received": 1, "aggregated": False, "version": 1}

    # 엣지
    edge.app.config["EDGE_ID"] = "E1"
    e = edge.app.test_client()
    cu = {"client_id": "C1", "version": 1, "weights": w, "n_samples": 1200, "train_loss": 0.5}
    _expect_409(e.post("/client_update", json=cu), "not started")
    assert e.post("/start", json={"exp_id": "exp_test409", "clients": ["C1", "C2", "C4"]}).status_code == 200
    _expect_409(e.post("/client_update", json={**cu, "client_id": "C3"}), "client not assigned to this edge")
    _expect_409(e.post("/client_update", json={**cu, "version": 0}), "version mismatch")  # 지난 버전
    st = e.get("/status").get_json()
    assert st["version"] == 1 and st["received"] == [], st
    r = e.post("/client_update", json=cu)
    assert r.status_code == 200 and r.get_json() == {"ok": True, "received": 1, "expected": 3, "edge_submitted": False}


def _expect_409(resp, error):
    assert resp.status_code == 409, (resp.status_code, resp.get_json())
    assert resp.get_json() == {"ok": False, "error": error}, resp.get_json()


if __name__ == "__main__":
    test_assignment_no_violation()
    test_edge_composition()
    test_reject_409()
    print("ok")
