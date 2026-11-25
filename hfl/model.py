"""모델 — 담당 A(이건), WBS 2.3

공개 FedProx 저장소(litian96/FedProx) MNIST 기본 모델 mclr = 소프트맥스 회귀 (784 → 10).
파라미터 = 숫자 7,850개 1차원 배열: W(784×10)를 행 순서로 편 뒤 b(10)를 붙임 (docs/api.md 전송 형식과 같음).

[출처] flearn/models/mnist/mclr.py (init, solve_inner, test), flearn/utils/model_utils.py (batch_data),
       flearn/optimizer/pgd.py (FedProx 근접항, 심화 6.A)
       https://github.com/litian96/FedProx  commit d2a4501f319f1594b732d88315c5ca1a72855f50  (MIT)
[수정] 1. TensorFlow 1.x → NumPy 이식 (Python 3.11, 팀 결정 D2·D3)
       2. 모델을 레이어별 배열 대신 7,850개 1차원 배열로 표현 (docs/api.md)
       3. 원본은 L2 정규화를 선언만 하고 손실에 더하지 않음 → 이식본도 정규화 없음 (실제 동작과 같음)
       4. 배치 섞기: 원본은 매번 seed 100 고정 → 호출자가 넘기는 seed 사용 (명세 "시드를 설정 파일로 관리")
       5. 원본 test 는 정답 수(합)·손실(평균) → 정확도(0~1)·평균 손실·숫자별 정확도로 반환
       6. 초기 모델: 원본 tf.layers.dense 기본값은 Glorot uniform (W 범위 ±√(6/794) ≈ ±0.087, b = 0).
          우리는 모든 실험이 같은 초기 모델에서 시작하도록(명세 "같은 초기 모델", 재현성) 기본 zeros.
          init_model (zeros / normal) 선택은 김영헌 추가 (11/19). 같은 조건 20라운드: zeros 87.62%, Glorot 87.2~87.6%
       7. [심화 6.A] FedProx: 원본 pgd.py 의 갱신 w ← w − lr·(∇F(w) + μ·(w − w_global)) 를 train_local 에 이식.
          w_global = 라운드 시작 모델(= 입력 w, 원본 vstar). μ 는 cfg["mu"] (없으면 0 = FedAvg, 결과 비트 단위 동일).
          원본처럼 W·b 모든 파라미터에 적용
       8. 수치 정밀도: 원본(TF) float32 → NumPy 기본 float64 (집계·평가를 같은 정밀도로)
       9. 학습 설정(lr 0.1 · 배치 32 · 로컬 epoch 1)은 원본 값이 아니라 팀 결정 D5 기본값 (docs/third_party.md)
"""
import numpy as np

N_IN, N_OUT = 784, 10
N_PARAMS = N_IN * N_OUT + N_OUT  # 7,850


def _unpack(w):
    """7,850 배열 → W (784, 10), b (10,)  (W 는 w 의 뷰, 복사 없음)"""
    w = np.asarray(w, dtype=np.float64)
    if w.shape != (N_PARAMS,):
        raise ValueError(f"모델 길이가 {N_PARAMS} 이어야 함: {w.shape}")
    return w[:N_IN * N_OUT].reshape(N_IN, N_OUT), w[N_IN * N_OUT:]


def _pack(W, b):
    return np.concatenate([W.ravel(), b])


def _softmax(z):
    z = z - z.max(axis=1, keepdims=True)  # 수치 안정화
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _loss(p, y):
    """평균 cross-entropy"""
    return float(-np.log(np.clip(p[np.arange(len(y)), y], 1e-12, None)).mean())


def init_weights(cfg=None):
    """→ 길이 7,850 배열. 모든 클라가 같은 초기 모델에서 시작 (명세 "초기 모델을 설정 파일로 관리").
    cfg["init_model"]: "zeros"(기본, 전부 0) / "normal"(cfg["seed"] 로 정규분포 N(0, 0.01²), 같은 시드 → 같은 모델)
    """
    kind = (cfg or {}).get("init_model", "zeros")
    if kind == "zeros":
        return np.zeros(N_PARAMS, dtype=np.float64)
    if kind == "normal":
        return np.random.default_rng(cfg["seed"]).normal(0.0, 0.01, N_PARAMS)
    raise ValueError(f"모르는 init_model: {kind!r} (zeros / normal)")


def train_local(w, x, y, cfg, seed):
    """로컬 학습 (미니배치 SGD).

    w: 시작 모델 (7,850,), x: (n, 784), y: (n,)
    cfg: local_epochs, lr, batch_size 사용. cfg["mu"] 가 있으면 FedProx 근접항 (심화 6.A, 기본 0 = FedAvg)
    seed: 배치 순서 고정 (같은 seed → 같은 결과)
    → (new_w, train_loss)  new_w 는 w 를 건드리지 않은 새 배열, train_loss 는 학습 후 (x, y) cross-entropy
    """
    W0, b0 = _unpack(w)                             # 라운드 시작 모델 (FedProx 의 w_global)
    W, b = W0.copy(), b0.copy()                     # 입력 w 는 건드리지 않음
    mu = float(cfg.get("mu", 0.0))
    y = np.asarray(y, dtype=np.int64)
    n = len(y)
    lr, bs = float(cfg["lr"]), int(cfg["batch_size"])
    rng = np.random.default_rng(seed)
    for _ in range(int(cfg["local_epochs"])):
        order = rng.permutation(n)                  # epoch 마다 섞음 (원본 batch_data 와 같은 방식)
        for s in range(0, n, bs):
            idx = order[s:s + bs]
            xb, yb = x[idx], y[idx]
            g = _softmax(xb @ W + b)                # (m, 10)
            g[np.arange(len(yb)), yb] -= 1.0        # dL/dz = p - onehot
            g /= len(yb)
            gW, gb = xb.T @ g, g.sum(axis=0)
            if mu:                                  # FedProx 근접항 μ·(w − w_global)
                gW = gW + mu * (W - W0)
                gb = gb + mu * (b - b0)
            W -= lr * gW
            b -= lr * gb
    train_loss = _loss(_softmax(x @ W + b), y)
    return _pack(W, b), train_loss


def evaluate(w, x, y):
    """→ (acc, loss, acc_by_digit)  acc 0~1, loss cross-entropy, acc_by_digit 숫자 0~9 정확도 10개 리스트"""
    W, b = _unpack(w)
    y = np.asarray(y, dtype=np.int64)
    p = _softmax(x @ W + b)
    correct = p.argmax(axis=1) == y
    by_digit = [float(correct[y == d].mean()) if (y == d).any() else 0.0 for d in range(N_OUT)]
    return float(correct.mean()), _loss(p, y), by_digit