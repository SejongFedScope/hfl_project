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

**모델 이식 시 확인된 원본 세부 사항** (반영 결과: `hfl/model.py` 헤더 수정 사항 3·4번)
- `mclr.py`가 `kernel_regularizer=l2_regularizer(0.001)`을 선언하지만, 손실 `sparse_softmax_cross_entropy`에 정규화 항을 더하지 않아 학습에는 적용되지 않음 → 이식본도 정규화 없이 구현 (원본 실제 동작과 같음)
- `batch_data`는 매번 `np.random.seed(100)`으로 섞음 → 이식본은 runner가 넘기는 `seed`로 섞음 (명세 "시드를 설정 파일로 관리", 라운드·클라마다 다른 순서)

**원본과 다르게 둔 것 (11/25 피드백 반영, 같은 조건 비교는 이건이 측정)**

같은 조건 = 선호 배정과 같은 FedAvg 20라운드, 시드 42, 학습률 0.1, 배치 32, 로컬 epoch 1 (단일 중앙 집계로 측정 — FedAvg는 엣지 유무와 상관없이 같음, `docs/aggregation_check.md` 1.5절).

| 항목 | 원본 | 우리 | 같은 조건 20라운드 정확도 | 이유 |
|---|---|---|---|---|
| 입력 전처리 | 픽셀마다 `(x − μ)/(σ + 0.001)`, μ·σ는 **학습+시험 70,000장** (`data/mnist/generate_niid.py` 20~22행) | `/255`로 0~1 (`hfl/data_split.py`) | 우리 87.62% · 원본 방식 89.54% · 학습 데이터 60,000장으로만 μ·σ 89.49% | 원본 방식은 시험 데이터 통계가 학습 입력에 섞임. 연합학습에서 중앙이 모든 클라 데이터의 픽셀 통계를 미리 아는 것도 실제와 맞지 않음. 클라마다 따로 구하면 클라마다 입력 척도가 달라짐 → 데이터와 무관한 고정 척도 `/255` 선택. 정확도는 약 1.9%p 낮음 |
| 초기 모델 | `tf.layers.dense` 기본 Glorot uniform (W ±0.087, b 0) | 전부 0 (`init_model: zeros`, 선택 `normal`) | zeros 87.62% · Glorot 87.30 / 87.56 / 87.23% (초기화 시드 0·1·2) | 명세 "같은 초기 모델에서 시작" — 0은 시드와 무관하게 모든 실험이 같은 모델에서 시작. 차이 0.4%p 이내 |
| 학습 설정 | 원본 MNIST 실행 학습률 0.03 · 배치 10 · 로컬 epoch 20 (클라 1,000개 중 10개 선택) | 학습률 0.1 · 배치 32 · 로컬 epoch 1 | — | 팀 결정 D5 기본값. 우리 조건(클라 6개 전원 참여, 클라당 1,200장)에서 20라운드 안에 수렴하고, 로컬 epoch 1로 클라 쏠림을 작게 둠. 심화 비교에서 epoch 5·10도 실험 (`docs/algorithm_comparison.md`) |
| 수치 정밀도 | float32 (TF) | float64 (NumPy 기본) | — | 집계·평가를 같은 정밀도로. 결과 차이는 측정하지 않음 |
| 평가 시점 | 라운드 **시작 전** 공동 모델 평가 (`fedavg.py`, 원본 실행 로그 "At round 0"이 학습 전) | 2차 집계 **후** 평가 (`servers/central.py`) | — | 명세 "한 라운드의 실행 순서" 7번: 중앙 집계 후 공동 모델을 평가. 그래서 우리 라운드 r 값 = 원본 라운드 r+1 시작 시점 값에 해당 |
| 손실 보고 | `test`가 정답 수(합)와 손실(평균) | 정확도(0~1)·평균 손실·숫자별 정확도 | — | 명세 "정확도 0~1" |

재현 (원본 방식 전처리·Glorot 비교): 별도 스크립트 없이 `hfl/data_split.py`의 `/255` 대신 표준화를, `hfl/model.py`의 `init_weights` 대신 Glorot uniform을 넣고 `python -m scripts.compare_algorithms --seeds 42 --epochs 1 --mu 0`으로 측정. 레포 코드는 바꾸지 않음.

### 원본 실행 기록

명세 "공개 FedAvg 코드로 MNIST 학습을 실행" → **11/19 실행 완료 (이건)**. 원본 저장소를 우리 레포 밖 별도 폴더에 받아 실행.

**환경**
- Windows 10 · CPU (GPU 없음, CUDA 관련 경고는 GPU 미사용 안내)
- **원본 1.10 대신 1.15로 실행**: 원본 `requirements.txt`는 `tensorflow-gpu==1.10`(Python 3.6까지 설치 가능) → Python 3.7.9 + `tensorflow==1.15.0`(CPU)
- 주요 패키지: `tensorflow==1.15.0` `numpy==1.18.5` `protobuf==3.20.3` `scipy==1.7.3` `tqdm` `Pillow` `matplotlib` (numpy·protobuf는 TF 1.15와 맞는 버전으로 고정)

<details><summary>pip freeze 전체</summary>

```
absl-py==2.1.0
astor==0.8.1
colorama==0.4.6
cycler==0.11.0
fonttools==4.38.0
gast==0.2.2
google-pasta==0.2.0
grpcio==1.62.3
h5py==3.8.0
importlib-metadata==6.7.0
Keras-Applications==1.0.8
Keras-Preprocessing==1.1.2
kiwisolver==1.4.5
Markdown==3.4.4
MarkupSafe==2.1.5
matplotlib==3.5.3
numpy==1.18.5
opt-einsum==3.3.0
packaging==24.0
Pillow==9.5.0
protobuf==3.20.3
pyparsing==3.1.4
python-dateutil==3.0.0
scipy==1.7.3
six==1.17.0
tensorboard==1.15.0
tensorflow==1.15.0
tensorflow-estimator==1.15.1
termcolor==2.3.0
tqdm==4.68.2
typing_extensions==4.7.1
tzdata==2026.6
Werkzeug==2.2.3
wrapt==1.16.0
zipp==3.15.0
```
</details>

**수정한 것 (데이터 준비만)**
- README의 전처리 데이터(Google Drive) 링크가 삭제됨, `generate_niid.py`가 쓰는 `sklearn.datasets.fetch_mldata`는 scikit-learn 0.22에서 삭제됨
- → `data/mnist/generate_niid.py`를 복사한 `generate_niid_idx.py`에서 **MNIST 읽는 부분만** 같은 MNIST 원본 idx 파일 4개(train 60,000 + test 10,000 = 70,000장) 읽기로 바꿈. 클라 1,000개 분할 로직(숫자 2종 · power law)은 원본 그대로
- 원본 분할 스크립트는 시드를 고정하지 않아 실행마다 클라별 장수가 조금씩 다름 (이번 실행 train 61,693장, README 통계 69,035장은 train+test 합)
- 학습·집계 코드(`main.py`, `flearn/trainers/fedavg.py`, `fedbase.py`, `flearn/models/mnist/mclr.py`)는 **수정 없이** TF 1.15에서 실행됨

**명령**
```
cd data/mnist && python generate_niid_idx.py <MNIST idx .gz 폴더>
python -u main.py --dataset=mnist --optimizer=fedavg --model=mclr --learning_rate=0.03 --num_rounds=20 --clients_per_round=10 --eval_every=1 --batch_size=10 --num_epochs=20 --drop_percent=0
```
(`--seed` 생략 → 원본 기본값 0. 실행 로그의 Arguments에 `seed : 0`, `mu : 0` = 근접항 없는 FedAvg)

**결과** (클라 1,000개 중 라운드마다 10개 선택, round 0 = 학습 전 평가)

| 라운드 | 0 | 1 | 5 | 7 | 8 | 10 | 15 | 19 | 20 |
|---|---|---|---|---|---|---|---|---|---|
| 테스트 정확도 | 0.1047 | 0.4224 | 0.5695 | 0.7663 | 0.4050 | 0.5826 | 0.6740 | 0.8242 | 0.7967 |
| 학습 손실 | 2.7035 | 1.9035 | 1.2092 | 0.7741 | 2.7848 | 1.6054 | 1.1051 | 0.5710 | — |

- 20라운드 학습 손실 "—": 원본 `fedavg.py`의 최종 평가는 정확도 2줄만 출력하고 학습 손실은 출력하지 않음 (코드 수정 없이 실행했으므로 그대로 둠)
- 정확도가 라운드마다 오르내림 (예: 7라운드 0.766 → 8라운드 0.405). 클라마다 숫자 2종만 갖고(non-IID), 라운드마다 다른 10개 클라를 뽑으며, 로컬 20 epoch로 클라 모델이 자기 숫자 쪽으로 많이 치우치기 때문 (FedProx 논문이 다루는 문제)
- 근거 파일(레포에는 올리지 않고 실행 폴더에 보관): 전체 실행 로그 `logs/mnist_fedavg_r20.txt`, 환경 `pip_freeze.txt`, 수정한 데이터 스크립트 `data/mnist/generate_niid_idx.py`
- 이 실행은 **공개 코드 환경 구성·실행·로그 생성 기록**이며 우리 실험과 수치를 비교하지 않음 (분할·클라 수·설정·초기 모델이 모두 다름)

### 우리 이식본 실행 기록

**모델 단독 · 2단계 집계 시뮬레이션** (11/16, 이건) — `python -m tests.test_learning --sim 5`, 서버 없이 클라 6 → 엣지 2 → 중앙, 시드 42

| 라운드 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 공동 정확도 | 0.7763 | 0.7989 | 0.8165 | 0.8247 | 0.8358 |
| 손실 | 1.5566 | 1.1888 | 0.9876 | 0.8615 | 0.7806 |

2단계와 1단계(클라 6개 한 번에 평균)의 공동 모델 최대 차이 8.3e-17 (같은 모델).

**서버 · runner 실험** (11/18, 윤효연 실행, 20라운드) — 결과는 `docs/report.md` 4절. 선호·무작위 배정 모두 공동 정확도 87.62%, 손실 0.4757.

### 심화 6.A 알고리즘 비교 (11/23~, 이건)

명세 심화 목표: "동일한 단일 중앙 집계 구조에서 FedAvg·FedProx를 비교하고, 여력이 있으면 q-FedAvg를 추가". 단일 중앙 집계 구조 = 명세의 "기존 중앙 집계 구조"(엣지 단계를 추가하기 전, 중앙 하나가 클라를 바로 집계). 분할·시드·초기 모델·학습 설정은 필수 실험과 같게 둔다.

**사용할 공개 코드 (11/23 확인)**

| 알고리즘 | 원본 | 핵심 동작 | 이식할 곳 |
|---|---|---|---|
| FedAvg | litian96/FedProx `flearn/trainers/fedavg.py` (commit d2a4501, MIT) | 이미 이식 (`model.py`, `aggregate.py`) | — |
| FedProx | 같은 저장소 `flearn/trainers/fedprox.py`, `flearn/optimizer/pgd.py` | 로컬 SGD 갱신 `w ← w − lr·(∇F(w) + μ·(w − w_global))` (`vstar` = 라운드 시작 공동 모델). 집계는 FedAvg와 같음 | `model.py` `train_local`에 `mu` 옵션 (기본 0 = FedAvg) |
| q-FedAvg (q-FFL) | litian96/fair_flearn `flearn/trainers/qffedavg.py`, `flearn/trainers/fedbase.py` `aggregate2` (commit f09797113147b5ae66eb0348e93f575d5d63baed, MIT) | 클라: 학습 전 손실 F, Δw = (w_global − w_local)/lr, Δ = F^q·Δw, h = q·F^(q−1)·‖Δw‖² + F^q/lr. 중앙: w ← w_global − ΣΔ / Σh | `aggregate.py`에 새 함수 |

**원본에서 확인한 세부 사항 (이식 때 처리)**
- FedProx 원본은 `drop_percent > 0`일 때 낙오 클라에 임의 epoch 수만 학습시킴 → 우리 비교는 모든 클라 참여(명세 기본 조건)라 이 부분은 이식하지 않음
- FedProx 원본은 라운드마다 클라 간 gradient 차이를 출력만 함 → 결과에 영향 없어 이식하지 않음
- q-FedAvg 원본의 F는 **학습 전 공동 모델의 자기 학습 데이터 손실**, 집계는 표본 수 가중치 없이 클라별 Δ·h 합. q = 0이면 Δ = Δw, h = 1/lr → 단순 평균. 우리 클라는 모두 1,200장이라 q = 0일 때 FedAvg와 같아야 함 (이식 검사 기준)
- 원본은 클라 선택이 무작위(FedProx: 1,000개 중 일부, q-FedAvg: 표본 수 비례) → 우리는 6개 전원 참여

**이식 결과 (11/23)**
- FedProx: `hfl/model.py` `train_local` 의 `mu` 옵션 (수정 사항 7번). 원본 낙오 클라 처리·gradient 차이 출력은 이식하지 않음
- q-FedAvg: `hfl/aggregate.py` `q_fedavg` (원본 Δ·h 계산 + `aggregate2`). 학습 전 손실 F 는 `scripts/compare_algorithms.py` 에서 `evaluate`로 계산. 레이어별 배열 → 7,850개 1차원 배열, 클래스 메서드 → 독립 함수, 입력 검사 추가 외에는 원본과 같음
- 원본과 다르게 쓴 것: 보폭 진단 옵션 `--q-lscale`(기본 1 = 원본). 1이 아니면 L 을 원본의 1/배수로 바꿈 → 진단 1회에만 사용, 결과 표·결론에는 원본 규칙(1)만 사용 (`docs/algorithm_comparison.md` 6절)

**실행 방식 (팀 확인 완료)**: Flask 서버 없이 한 프로세스에서 클라 6 → 중앙 루프를 돌리고, 결과는 `logs/<exp_id>/` 같은 로그 형식으로 저장 (`algorithm` 필드에 fedavg / fedprox / qfedavg). 실행 파일: `scripts/compare_algorithms.py` (A 담당, 팀 확인 11/23). 결과 문서: `docs/algorithm_comparison.md` (위치는 팀 확인 후 변경 가능).