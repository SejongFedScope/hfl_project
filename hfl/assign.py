"""클라이언트 배정 — 담당 B(윤효연), WBS 3.2

학습 시작 전에 한 번 배정하고 학습 중에는 유지. 엣지 정원 cfg["edge_capacity"] (= 3).
"""


def pref_assign(cfg):
    """matching 패키지 HospitalResident: 클라 = resident, 엣지 = hospital.
    cfg["client_prefs"], cfg["edge_prefs"], 정원 → {"E1": [클라 3명], "E2": [클라 3명]}
    """
    raise NotImplementedError  # TODO 3.2.2


def random_assign(cfg):
    """cfg["seed"] 고정 무작위, 정원 지킴 → {"E1": [...], "E2": [...]}"""
    raise NotImplementedError  # TODO 3.2.3


def make_assignment(cfg, method):
    """method "pref" / "random" → 배정 dict"""
    raise NotImplementedError  # TODO 3.2


def check_assignment(assignment, cfg):
    """→ {"unassigned": [...], "duplicated": [...], "capacity_violation": [...],
          "client_pref_rank": {"C1": 1, ...}, "mean_pref_rank": float}
    client_pref_rank = 배정된 엣지가 그 클라 선호 몇 순위인지 (1 = 1순위)
    """
    raise NotImplementedError  # TODO 3.2.4


def edge_composition(assignment, summary):
    """summary = data_split.split_summary 결과
    → {"E1": {"clients": [...], "n_clients": 3, "n": 표본 합, "digit_counts": [10개]}, ...}
    """
    raise NotImplementedError  # TODO 3.2.5
