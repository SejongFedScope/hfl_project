"""모델 — 담당 A(이건), WBS 2.3

공개 FedProx 저장소(litian96/FedProx) MNIST 기본 모델 mclr = 소프트맥스 회귀 (784 → 10).
파라미터 = 숫자 7,850개 1차원 배열: W(784×10)를 행 순서로 편 뒤 b(10)를 붙임 (docs/api.md 전송 형식과 같음).
"""
N_IN, N_OUT = 784, 10
N_PARAMS = N_IN * N_OUT + N_OUT  # 7,850


def init_weights():
    """→ 길이 7,850 배열, 전부 0 (모든 실험이 같은 초기 모델에서 시작)."""
    raise NotImplementedError  # TODO 2.3.2


def train_local(w, x, y, cfg, seed):
    """로컬 학습 (미니배치 SGD).

    w: 시작 모델 (7,850,), x: (n, 784), y: (n,)
    cfg: local_epochs, lr, batch_size 사용
    seed: 배치 순서 고정 (같은 seed → 같은 결과)
    → (new_w, train_loss)  new_w 는 w 를 건드리지 않은 새 배열, train_loss 는 학습 후 (x, y) cross-entropy
    """
    raise NotImplementedError  # TODO 2.3.3


def evaluate(w, x, y):
    """→ (acc, loss, acc_by_digit)  acc 0~1, loss cross-entropy, acc_by_digit 숫자 0~9 정확도 10개 리스트"""
    raise NotImplementedError  # TODO 2.3.4
