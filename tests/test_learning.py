"""A 검사 — 담당 A(이건), WBS 2.1.3 · 2.2.4. 실행: python -m tests.test_learning"""
import numpy as np

from hfl.aggregate import weighted_average

# docs/aggregation_check.md 손계산 예제 (클라: 엣지, 표본 수, 모델)
HAND_CLIENTS = {
    "C1": ("E1", 100, [1, 0, 2]),
    "C2": ("E1", 200, [2, 1, 0]),
    "C3": ("E1", 100, [4, 3, 2]),
    "C4": ("E2", 50, [0, 0, 2]),
    "C5": ("E2", 50, [2, 2, 0]),
    "C6": ("E2", 100, [2, 0, 1]),
}
HAND_E1, HAND_E2, HAND_CENTRAL = [2.25, 1.25, 1.0], [1.5, 0.5, 1.0], [2.0, 1.0, 1.0]


def _edge(edge_id):
    rows = [(n, w) for e, n, w in HAND_CLIENTS.values() if e == edge_id]
    return weighted_average([w for _, w in rows], [n for n, _ in rows]), sum(n for n, _ in rows)


def test_two_stage_hand_example():
    """docs/aggregation_check.md 손계산 예제 (클라 6 → 엣지 2 → 중앙): 손계산값 = weighted_average 결과"""
    e1, n1 = _edge("E1")
    e2, n2 = _edge("E2")
    assert n1 == 400 and np.allclose(e1, HAND_E1)            # 1차 집계 (클라 표본 수 비례)
    assert n2 == 200 and np.allclose(e2, HAND_E2)
    central = weighted_average([e1, e2], [n1, n2])           # 2차 집계 (엣지 전체 표본 수 비례)
    assert np.allclose(central, HAND_CENTRAL)


def test_two_stage_equals_flat():
    """2단계 집계 = 클라 6개를 한 번에 가중 평균. 배정을 바꿔도 공동 모델이 같음 (명세 '비교 실험 해석' 근거)"""
    e1, n1 = _edge("E1")
    e2, n2 = _edge("E2")
    flat = weighted_average([w for _, _, w in HAND_CLIENTS.values()],
                            [n for _, n, _ in HAND_CLIENTS.values()])
    assert np.allclose(weighted_average([e1, e2], [n1, n2]), flat)

    rng = np.random.default_rng(42)                          # 실제 크기 7,850, 무작위 배정 20회
    ws = [rng.normal(size=7850) for _ in range(6)]
    ns = [1200] * 6
    flat = weighted_average(ws, ns)
    for _ in range(20):
        g = rng.permutation(6)
        a, b = g[:3], g[3:]
        ea = weighted_average([ws[i] for i in a], [ns[i] for i in a])
        eb = weighted_average([ws[i] for i in b], [ns[i] for i in b])
        assert np.allclose(weighted_average([ea, eb], [3600, 3600]), flat)


def test_split_no_overlap():
    """클라 간 인덱스 겹침 0, 클라당 표본 수 = samples_per_client, 같은 시드 → 같은 분할"""
    raise NotImplementedError  # TODO 2.2.4


if __name__ == "__main__":
    for t in (test_two_stage_hand_example, test_two_stage_equals_flat, test_split_no_overlap):
        try:
            t()
            print("PASS", t.__name__)
        except NotImplementedError:
            print("TODO", t.__name__)
    print("ok")
