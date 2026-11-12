"""2단계 집계 — 담당 A(이건), WBS 2.1

엣지(1차)와 중앙(2차)이 같은 함수를 씀. 이미지가 아니라 모델 파라미터를 표본 수로 가중 평균.
"""


def weighted_average(list_of_weights, list_of_n):
    """list_of_weights: 모델 배열 k개, list_of_n: 각 모델의 표본 수 k개
    → 자리별 Σ(n × w) / Σn  (길이 7,850 배열)
    """
    raise NotImplementedError  # TODO 2.1.1
