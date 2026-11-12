"""A 검사 — 담당 A(이건), WBS 2.1.3 · 2.2.4. 실행: python -m tests.test_learning"""


def test_two_stage_hand_example():
    """docs/aggregation_check.md 손계산 예제 (클라 6 → 엣지 2 → 중앙): 손계산값 = weighted_average 결과"""
    raise NotImplementedError  # TODO 2.1.3


def test_split_no_overlap():
    """클라 간 인덱스 겹침 0, 클라당 표본 수 = samples_per_client, 같은 시드 → 같은 분할"""
    raise NotImplementedError  # TODO 2.2.4


if __name__ == "__main__":
    test_two_stage_hand_example()
    test_split_no_overlap()
    print("ok")
