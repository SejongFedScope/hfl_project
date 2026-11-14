# 공개 코드 사용 기록

## FedProx (FedAvg 학습·집계 코드)

| 항목 | 내용 |
|---|---|
| 저장소 | https://github.com/litian96/FedProx |
| commit | `d2a4501f319f1594b732d88315c5ca1a72855f50` |
| 라이선스 | MIT (Copyright (c) 2019 Tian Li) |
| 사용 목적 | 명세 "필수 구현에서는 저장소의 FedAvg 학습·집계 코드를 활용" |
| 사용 방식 | 원본은 TensorFlow 1.x (Python 3.7 필요). 팀 결정 D2·D3에 따라 Python 3.11 + NumPy로 이식 |

### 원본 → 우리 코드 대응

| 원본 | 우리 코드 | 담당 | 상태 |
|---|---|---|---|
| `flearn/trainers/fedbase.py` `aggregate` (표본 수 가중 평균) | `hfl/aggregate.py` `weighted_average` | A | 이식 완료 (11/14) |
| `flearn/models/mnist/mclr.py` (784→10 소프트맥스 회귀, 교차 엔트로피, SGD) | `hfl/model.py` `init_weights` `train_local` `evaluate` | A | 11/16 |
| `flearn/models/mnist/mclr.py` `solve_inner` (epoch × 미니배치) | `hfl/model.py` `train_local` | A | 11/16 |
| `flearn/utils/model_utils.py` `batch_data` (섞은 뒤 batch_size씩) | `hfl/model.py` `train_local` 내부 | A | 11/16 |
| `flearn/models/mnist/mclr.py` `test` (정답 수, 손실) | `hfl/model.py` `evaluate` | A | 11/16 |
| `flearn/trainers/fedavg.py` 라운드 루프 (배포 → 학습 → 집계) | `servers/` + `runner/` (REST로 분리) | B | |
| `data/mnist/` 분할 (기기 1,000개) | `hfl/data_split.py` (명세 숫자별 분할로 교체) | A | 11/15 |

### 수정 사항

**aggregate → weighted_average**
1. 입력 형식: `[(표본 수, 레이어별 배열들), ...]` → 모델 리스트 + 표본 수 리스트 (팀 함수 틀)
2. 모델 형식: TF 레이어별 배열 → 7,850개 1차원 배열 (`docs/api.md`)
3. 원본은 중앙 1단계 집계 → 엣지 1차·중앙 2차 집계에서 같은 함수 공용 (명세 "기존 중앙 집계 구조에 엣지 집계 단계 추가")
4. 입력 검사 추가
5. 계산식은 원본과 같음: `Σ(n × w) / Σn` (float64)

**11/16 모델 이식 시 확인된 원본 세부 사항** (이식 때 반영 여부 결정)
- `mclr.py`가 `kernel_regularizer=l2_regularizer(0.001)`을 선언하지만, 손실 `sparse_softmax_cross_entropy`에 정규화 항을 더하지 않아 학습에는 적용되지 않음 → 이식본도 정규화 없이 구현 (원본 실제 동작과 같음)
- `batch_data`는 매번 `np.random.seed(100)`으로 섞음 → 이식본은 runner가 넘기는 `seed`로 섞음 (명세 "시드를 설정 파일로 관리", 라운드·클라마다 다른 순서)

### 원본 실행 기록

명세 "공개 FedAvg 코드로 MNIST 학습을 실행" → 11/18 오전 예정 (Python 3.7 + TF 1.15 별도 환경, MNIST · mclr · fedavg).
결과 로그·환경(`pip freeze`)·명령을 여기에 추가.