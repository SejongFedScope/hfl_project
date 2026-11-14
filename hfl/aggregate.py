"""2단계 집계 — 담당 A(이건), WBS 2.1

엣지(1차)와 중앙(2차)이 같은 함수를 씀. 이미지가 아니라 모델 파라미터를 표본 수로 가중 평균.

출처: litian96/FedProx (MIT License, commit d2a4501)
      flearn/trainers/fedbase.py  BaseFedarated.aggregate(self, wsolns)
수정 사항 (docs/third_party.md 참고)
  1. 입력: 원본 [(표본 수, 레이어별 배열 리스트), ...] → 모델 리스트, 표본 수 리스트 (팀 함수 틀)
  2. 모델: TF 레이어별 배열 → 7,850개 1차원 배열 하나 (docs/api.md 전송 형식)
  3. 클래스 메서드 → 독립 함수. 엣지 1차·중앙 2차 집계에서 공용 (원본은 중앙 1단계만)
  4. 입력 검사 추가 (개수 불일치, 표본 수 0 이하)
"""
import numpy as np


def weighted_average(list_of_weights, list_of_n):
    """list_of_weights: 모델 배열 k개, list_of_n: 각 모델의 표본 수 k개
    → 자리별 Σ(n × w) / Σn  (길이 7,850 배열)
    """
    if len(list_of_weights) != len(list_of_n):
        raise ValueError("list_of_weights와 list_of_n의 개수가 다릅니다")
    if len(list_of_weights) == 0:
        raise ValueError("집계할 모델이 없습니다")

    # ---- 원본 fedbase.aggregate 와 같은 흐름 ----
    total_weight = 0.0
    base = np.zeros(len(list_of_weights[0]), dtype=np.float64)
    for w, soln in zip(list_of_n, list_of_weights):   # w = 그 모델의 로컬 표본 수
        if w <= 0:
            raise ValueError("표본 수는 모두 양수여야 합니다")
        soln = np.asarray(soln, dtype=np.float64)
        if soln.shape != base.shape:
            raise ValueError("모델 길이가 서로 다릅니다")
        total_weight += w
        base += w * soln                               # 원본: base[i] += w*v.astype(np.float64)

    averaged_soln = base / total_weight                # 원본: [v / total_weight for v in base]
    return averaged_soln