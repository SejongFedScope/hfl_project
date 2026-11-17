"""B 검사 — 담당 B(윤효연), WBS 3.2.6 · 3.4.3. 실행: python -m tests.test_server"""
from hfl.assign import check_assignment, edge_composition, make_assignment
from hfl.common import DEFAULT_CONFIG, read_json


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
    """Flask test_client: 지난 버전 제출, 배정 안 된 클라 제출 → 409"""
    raise NotImplementedError  # TODO 3.4.3


if __name__ == "__main__":
    test_assignment_no_violation()
    test_edge_composition()
    test_reject_409()
    print("ok")
