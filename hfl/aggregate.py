"""2단계 집계 — 담당 A(이건), WBS 2.1

엣지(1차)와 중앙(2차)이 같은 함수를 씀. 이미지가 아니라 모델 파라미터를 표본 수로 가중 평균.
"""

import numpy as np


def weighted_average(list_of_weights, list_of_n):
    """list_of_weights: 모델 배열 k개, list_of_n: 각 모델의 표본 수 k개
    → 자리별 Σ(n × w) / Σn  (길이 7,850 배열)
    """
    W = np.asarray(list_of_weights, dtype=np.float64)  # (k, 7850)
    n = np.asarray(list_of_n, dtype=np.float64)        # (k,)

    if W.ndim != 2:
        raise ValueError("list_of_weights는 같은 길이 모델들의 리스트여야 합니다")
    if len(n) != len(W):
        raise ValueError("list_of_weights와 list_of_n의 개수가 다릅니다")
    if np.any(n <= 0):
        raise ValueError("표본 수는 모두 양수여야 합니다")

    return (n[:, None] * W).sum(axis=0) / n.sum()

