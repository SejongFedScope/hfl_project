# 공개 코드 사용 기록

## FedProx (FedAvg 학습·집계 코드)

| 항목 | 내용 |
|---|---|
| 저장소 | https://github.com/litian96/FedProx |
| commit | `d2a4501f319f1594b732d88315c5ca1a72855f50` |
| 라이선스 | MIT (Copyright (c) 2019 Tian Li) |
| 사용 목적 | 명세 "필수 구현에서는 저장소의 FedAvg 학습·집계 코드를 활용" |
| 사용 방식 | 원본은 TensorFlow 1.x (`requirements.txt`: `tensorflow-gpu==1.10`, 설치 가능한 Python은 3.6까지). 팀 결정 D2·D3에 따라 Python 3.11 + NumPy로 이식 |

### 원본 → 우리 코드 대응

| 원본 | 우리 코드 | 담당 | 상태 |
|---|---|---|---|
| `flearn/trainers/fedbase.py` `aggregate` (표본 수 가중 평균) | `hfl/aggregate.py` `weighted_average` | A | 이식 완료 (11/14) |
| `flearn/models/mnist/mclr.py` (784→10 소프트맥스 회귀, 교차 엔트로피, SGD) | `hfl/model.py` `init_weights` `train_local` `evaluate` | A | 이식 완료 (11/16) |
| `flearn/models/mnist/mclr.py` `solve_inner` (epoch × 미니배치) | `hfl/model.py` `train_local` | A | 이식 완료 (11/16) |
| `flearn/utils/model_utils.py` `batch_data` (섞은 뒤 batch_size씩) | `hfl/model.py` `train_local` 내부 | A | 이식 완료 (11/16) |
| `flearn/models/mnist/mclr.py` `test` (정답 수, 손실) | `hfl/model.py` `evaluate` | A | 이식 완료 (11/16) |
| `flearn/trainers/fedavg.py` 라운드 루프 (배포 → 학습 → 집계) | `servers/central.py` `servers/edge.py` `runner/client_runner.py` (REST로 분리) | B | 구현 완료 (11/18) |
| `data/mnist/` 분할 (기기 1,000개) | `hfl/data_split.py` (명세 숫자별 분할로 교체) | A | 이식 완료 (11/15) |

### 수정 사항

**aggregate → weighted_average**
1. 입력 형식: `[(표본 수, 레이어별 배열들), ...]` → 모델 리스트 + 표본 수 리스트 (팀 함수 틀)
2. 모델 형식: TF 레이어별 배열 → 7,850개 1차원 배열 (`docs/api.md`)
3. 원본은 중앙 1단계 집계 → 엣지 1차·중앙 2차 집계에서 같은 함수 공용 (명세 "기존 중앙 집계 구조에 엣지 집계 단계 추가")
4. 입력 검사 추가
5. 계산식은 원본과 같음: `Σ(n × w) / Σn` (float64)

**라운드 루프 (fedavg.py → servers · runner)**
1. 원본은 한 프로세스 안에서 `배포 → 학습 → 집계`를 반복 → 중앙 1 · 엣지 2 서버와 runner(클라 6개)로 나누고 Flask REST로 모델 전달 (`docs/api.md`)
2. 원본의 중앙 집계 앞에 엣지 1차 집계 단계 추가 (명세 "기존 중앙 집계 구조에 엣지 집계 단계 추가"). 두 단계 모두 같은 `weighted_average` 사용
3. 클라 학습 seed는 (설정 seed, 라운드, 클라 ID)만으로 정함 (`runner/client_runner.py` `client_seed`). 원본의 고정 seed 100 대체. 배정 방식과 무관해서 두 실험의 학습 조건이 같음

**모델 이식 시 확인된 원본 세부 사항** (반영 결과: 아래 두 가지 모두 `hfl/model.py` 헤더에 기록)
- `mclr.py`가 `kernel_regularizer=l2_regularizer(0.001)`을 선언하지만, 손실 `sparse_softmax_cross_entropy`에 정규화 항을 더하지 않아 학습에는 적용되지 않음 → 이식본도 정규화 없이 구현 (원본 실제 동작과 같음)
- `batch_data`는 매번 `np.random.seed(100)`으로 섞음 → 이식본은 runner가 넘기는 `seed`로 섞음 (명세 "시드를 설정 파일로 관리", 라운드·클라마다 다른 순서)

### 원본 실행 기록

명세 "공개 FedAvg 코드로 MNIST 학습을 실행" → **아직 실행하지 않음 (11/19 기준)**. 심화 기간(11/20~)에 진행 예정 (MNIST · mclr · fedavg).

**환경 변경 (원본과 다른 점):** 원본 `requirements.txt`는 `tensorflow-gpu==1.10`(Python 3.6까지 설치 가능)이지만, **원본 1.10 대신 Python 3.7 + TensorFlow 1.15(CPU)로 실행**한다. 이유: 1.10은 현재 환경에서 설치가 어렵고, 1.15는 같은 TF 1.x API(`tf.layers`, `tf.Session`)를 쓰므로 코드 수정 없이 돌아갈 것으로 보임. 실행 후 실제로 코드 수정이 필요했는지도 아래에 적는다.

실행 후 추가할 것: 명령, `pip freeze`, 결과 로그, 코드 수정 여부.

### 우리 이식본 실행 기록

**모델 단독 · 2단계 집계 시뮬레이션** (11/16, 이건) — `python -m tests.test_learning --sim 5`, 서버 없이 클라 6 → 엣지 2 → 중앙, 시드 42

| 라운드 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 공동 정확도 | 0.7763 | 0.7989 | 0.8165 | 0.8247 | 0.8358 |
| 손실 | 1.5566 | 1.1888 | 0.9876 | 0.8615 | 0.7806 |

2단계와 1단계(클라 6개 한 번에 평균)의 공동 모델 최대 차이 8.3e-17 (같은 모델).

**서버 · runner 실험** (11/18, 윤효연 실행, 20라운드) — 결과는 `docs/report.md` 4절. 선호·무작위 배정 모두 공동 정확도 87.62%, 손실 0.4757.

### 심화 (11/20~11/26, 계획)

FedProx 비교를 하게 되면 같은 저장소(MIT)의 `flearn/trainers/fedprox.py`와 `flearn/optimizer/pgd.py`(근접항)를 참고. 확정되면 사용한 파일, commit, 수정 사항을 위 표와 같은 방식으로 추가.