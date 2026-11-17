"""클라이언트 배정 — 담당 B(윤효연), WBS 3.2

학습 시작 전에 한 번 배정하고 학습 중에는 유지. 엣지 정원 cfg["edge_capacity"] (= 3).
"""
import random

from matching.games import HospitalResident

N_DIGITS = 10  # MNIST 숫자 0~9


def _client_order(cfg):
    """설정 파일에 적힌 클라 순서 (C1, C2, ...). 결과 목록을 늘 이 순서로 정렬."""
    return list(cfg["client_prefs"])


def pref_assign(cfg):
    """matching 패키지 HospitalResident: 클라 = resident, 엣지 = hospital.
    cfg["client_prefs"], cfg["edge_prefs"], 정원 → {"E1": [클라 3명], "E2": [클라 3명]}
    """
    capacities = {e: cfg["edge_capacity"] for e in cfg["edge_prefs"]}
    game = HospitalResident.create_from_dictionaries(cfg["client_prefs"], cfg["edge_prefs"], capacities)
    matching = game.solve(optimal="resident")  # 클라(지원자) 쪽에 유리한 안정 매칭
    by_name = {edge.name: [c.name for c in clients] for edge, clients in matching.items()}
    order = _client_order(cfg)
    return {e: sorted(by_name.get(e, []), key=order.index) for e in cfg["edge_prefs"]}


def random_assign(cfg):
    """cfg["seed"] 고정 무작위, 정원 지킴 → {"E1": [...], "E2": [...]}"""
    order = _client_order(cfg)
    shuffled = order[:]
    random.Random(cfg["seed"]).shuffle(shuffled)
    cap = cfg["edge_capacity"]
    result = {}
    for i, e in enumerate(cfg["edge_prefs"]):
        chunk = shuffled[i * cap:(i + 1) * cap]  # 섞은 순서대로 정원만큼 잘라 담음
        result[e] = sorted(chunk, key=order.index)
    return result


def make_assignment(cfg, method):
    """method "pref" / "random" → 배정 dict"""
    if method == "pref":
        return pref_assign(cfg)
    if method == "random":
        return random_assign(cfg)
    raise ValueError(f"모르는 배정 방식: {method!r} (pref / random 중 하나)")


def check_assignment(assignment, cfg):
    """→ {"unassigned": [...], "duplicated": [...], "capacity_violation": [...],
          "client_pref_rank": {"C1": 1, ...}, "mean_pref_rank": float}
    client_pref_rank = 배정된 엣지가 그 클라 선호 몇 순위인지 (1 = 1순위)
    미배정·중복 클라는 순위를 정할 수 없어서 None, 평균에서도 빠짐.
    """
    edges_of = {c: [] for c in _client_order(cfg)}  # 클라 → 배정된 엣지 목록
    for e, clients in assignment.items():
        for c in clients:
            edges_of.setdefault(c, []).append(e)

    unassigned = [c for c, es in edges_of.items() if len(es) == 0]
    duplicated = [c for c, es in edges_of.items() if len(es) > 1]
    capacity_violation = [e for e, clients in assignment.items() if len(clients) > cfg["edge_capacity"]]

    client_pref_rank = {}
    for c, es in edges_of.items():
        prefs = cfg["client_prefs"].get(c, [])
        if len(es) == 1 and es[0] in prefs:
            client_pref_rank[c] = prefs.index(es[0]) + 1
        else:
            client_pref_rank[c] = None
    ranks = [r for r in client_pref_rank.values() if r is not None]
    mean_pref_rank = sum(ranks) / len(ranks) if ranks else None

    return {
        "unassigned": unassigned,
        "duplicated": duplicated,
        "capacity_violation": capacity_violation,
        "client_pref_rank": client_pref_rank,
        "mean_pref_rank": mean_pref_rank,
    }


def edge_composition(assignment, summary):
    """summary = data_split.split_summary 결과
    → {"E1": {"clients": [...], "n_clients": 3, "n": 표본 합, "digit_counts": [10개]}, ...}
    """
    result = {}
    for e, clients in assignment.items():
        digit_counts = [0] * N_DIGITS
        for c in clients:
            for d, k in enumerate(summary[c]["digit_counts"]):
                digit_counts[d] += int(k)
        result[e] = {
            "clients": list(clients),
            "n_clients": len(clients),
            "n": sum(int(summary[c]["n"]) for c in clients),
            "digit_counts": digit_counts,
        }
    return result
