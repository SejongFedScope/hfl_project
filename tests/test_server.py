"""B 검사 — 담당 B(윤효연), WBS 3.2.6 · 3.4.3 · 6.B. 실행: python -m tests.test_server"""
import tempfile
import time

from hfl.assign import check_assignment, edge_composition, make_assignment
from hfl.common import DEFAULT_CONFIG, read_json
from hfl.model import N_PARAMS
from runner.client_runner import check_fault
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


def test_edge_deadline():
    """심화 6.B: 엣지 대기 시간 제한. 중앙 대신 가짜 call 로 엣지가 중앙에 보낸 것만 확인 (서버를 안 띄움)
    - deadline_sec 없으면 제한 시간이 지나도 전원을 기다림 (기본 동작 그대로)
    - deadline_sec 있으면 시간이 지나면 온 클라만으로 집계 → 버전 +1, 늦은 제출은 409 deadline passed
    """
    sent = []

    class Resp:
        status_code = 200

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    def fake_call(method, base, path, *args, body=None, **kw):
        if path == "/model":
            return Resp({"version": 1, "weights": [0.0] * N_PARAMS})
        sent.append(body)
        return Resp({"ok": True})

    real_call, real_log_dir = edge.call, edge.cfg["log_dir"]
    edge.call, edge.cfg["log_dir"] = fake_call, tempfile.mkdtemp(prefix="hfl_deadline_")  # 기록은 임시 폴더로
    try:
        edge.app.config["EDGE_ID"] = "E1"
        e = edge.app.test_client()
        up = {"version": 1, "weights": [1.0] * N_PARAMS, "train_loss": 0.5}

        # 제한 없음: 2명만 내고 기다려도 집계 안 함
        e.post("/start", json={"exp_id": "exp_test_deadline", "clients": ["C1", "C2", "C4"]})
        e.get("/model")
        e.post("/client_update", json={**up, "client_id": "C1", "n_samples": 100})
        time.sleep(0.3)
        assert e.get("/status").get_json()["version"] == 1 and sent == []

        # 제한 0.2초: C1·C4 만 내면 시간이 지나 둘만으로 집계
        e.post("/start", json={"exp_id": "exp_test_deadline", "clients": ["C1", "C2", "C4"], "deadline_sec": 0.2})
        e.get("/model")
        e.post("/client_update", json={**up, "client_id": "C1", "n_samples": 100})
        e.post("/client_update", json={**up, "client_id": "C4", "n_samples": 300})
        time.sleep(0.5)
        assert e.get("/status").get_json()["version"] == 2
        assert len(sent) == 1 and sent[0]["n_samples"] == 400 and sent[0]["version"] == 1, sent
        _expect_409(e.post("/client_update", json={**up, "client_id": "C2", "n_samples": 200}), "deadline passed")
        _expect_409(e.post("/client_update", json={**up, "client_id": "C1", "n_samples": 100}), "version mismatch")  # 낸 클라가 또 내면 그냥 지난 버전
    finally:
        edge.call, edge.cfg["log_dir"] = real_call, real_log_dir


def test_check_fault():
    """심화 6.B 설정 검사: 기본값은 통과, 틀린 값은 실험 시작 전에 ValueError"""
    cfg = _default_cfg()
    check_fault(cfg, {"E1": ["C1", "C2", "C4"], "E2": ["C3", "C5", "C6"]})  # pref 배정
    check_fault(cfg, {"E1": ["C2", "C3", "C4"], "E2": ["C1", "C5", "C6"]})  # random 배정
    bad = [
        ({"round": 0}, None),
        ({"round": cfg["rounds"] + 1}, None),
        ({"drop_client": "C9"}, None),
        ({"drop_client": "C2"}, None),  # 지연·중단이 같은 클라
        ({"deadline_sec": 0}, None),
        ({}, {"E1": ["C2", "C6"], "E2": ["C1", "C3", "C4", "C5"]}),  # E1 에 남는 클라 없음
    ]
    for change, assignment in bad:
        try:
            check_fault({**cfg, "fault": {**cfg["fault"], **change}}, assignment)
        except ValueError:
            continue
        raise AssertionError(f"통과하면 안 되는 설정: {change} {assignment}")


def _expect_409(resp, error):
    assert resp.status_code == 409, (resp.status_code, resp.get_json())
    assert resp.get_json() == {"ok": False, "error": error}, resp.get_json()


if __name__ == "__main__":
    test_assignment_no_violation()
    test_edge_composition()
    test_reject_409()
    test_edge_deadline()
    test_check_fault()
    print("ok")
