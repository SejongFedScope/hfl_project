"""데이터 분할 — 담당 A(이건), WBS 2.2

클라마다 config 의 client_digits 숫자만 보유. 같은 숫자를 가진 클라끼리도 이미지가 겹치지 않게 나눔.
MNIST 미러: https://ossci-datasets.s3.amazonaws.com/mnist/
"""


def load_mnist(cfg):
    """처음 실행 때 cfg["data_dir"] 에 자동 다운로드.
    → {"train_x": (60000, 784) float 0~1, "train_y": (60000,) int,
       "test_x": (10000, 784) float 0~1, "test_y": (10000,) int}
    """
    raise NotImplementedError  # TODO 2.2.1


def make_split(cfg, train_y):
    """숫자 d 이미지 번호를 시드로 섞고, d 를 가진 클라끼리 앞에서부터 잘라 나눔 → 겹침 없음.
    클라당 cfg["samples_per_client"] 장 (숫자 3개면 400장씩, 4개면 300장씩).
    → {"C1": [MNIST train 인덱스 ...], ..., "C6": [...]}
    """
    raise NotImplementedError  # TODO 2.2.2


def split_summary(split, train_y):
    """→ {"C1": {"n": 1200, "digit_counts": [숫자 0~9 개수 10개]}, ...}"""
    raise NotImplementedError  # TODO 2.2.3
