"""데이터 분할 — 담당 A(이건), WBS 2.2

클라마다 config 의 client_digits 숫자만 보유. 같은 숫자를 가진 클라끼리도 이미지가 겹치지 않게 나눔.
MNIST 미러: https://ossci-datasets.s3.amazonaws.com/mnist/
"""
import gzip
from pathlib import Path

import numpy as np
import requests

BASE_DIR = Path(__file__).resolve().parent.parent  # 프로젝트 루트
MIRROR = "https://ossci-datasets.s3.amazonaws.com/mnist/"
FILES = {
    "train_x": "train-images-idx3-ubyte.gz",
    "train_y": "train-labels-idx1-ubyte.gz",
    "test_x": "t10k-images-idx3-ubyte.gz",
    "test_y": "t10k-labels-idx1-ubyte.gz",
}


def _data_dir(cfg):
    """cfg["data_dir"] 가 상대 경로면 프로젝트 루트 기준 (실행 위치와 무관)."""
    d = Path(cfg["data_dir"])
    return d if d.is_absolute() else BASE_DIR / d


def _download(url, path):
    """임시 파일에 받은 뒤 이름을 바꿔, 중간에 끊겨도 깨진 파일이 남지 않게 함."""
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(r.content)
    tmp.replace(path)


def _read_idx(path, expect_magic, header_len):
    """MNIST idx 형식(gzip) 읽기. 앞 header_len 바이트는 크기 정보, 그 뒤가 0~255 값."""
    with gzip.open(path, "rb") as f:
        raw = f.read()
    magic = int.from_bytes(raw[:4], "big")
    if magic != expect_magic:
        raise ValueError(f"{path.name}: MNIST 파일이 아닙니다 (magic {magic})")
    return np.frombuffer(raw, dtype=np.uint8, offset=header_len)


def load_mnist(cfg):
    """처음 실행 때 cfg["data_dir"] 에 자동 다운로드.
    → {"train_x": (60000, 784) float 0~1, "train_y": (60000,) int,
       "test_x": (10000, 784) float 0~1, "test_y": (10000,) int}
    """
    d = _data_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    for name in FILES.values():
        p = d / name
        if not p.exists():
            _download(MIRROR + name, p)

    out = {}
    for key, name in FILES.items():
        if key.endswith("_x"):
            pixels = _read_idx(d / name, 2051, 16)              # 이미지: 헤더 16바이트
            out[key] = pixels.reshape(-1, 784).astype(np.float64) / 255.0   # 밝기 0~1
        else:
            out[key] = _read_idx(d / name, 2049, 8).astype(np.int64)        # 라벨: 헤더 8바이트

    if out["train_x"].shape != (60000, 784) or out["test_x"].shape != (10000, 784):
        raise ValueError("MNIST 크기가 예상과 다릅니다. data 폴더를 지우고 다시 실행하세요")
    return out


def make_split(cfg, train_y):
    """숫자 d 이미지 번호를 시드로 섞고, d 를 가진 클라끼리 앞에서부터 잘라 나눔 → 겹침 없음.
    클라당 cfg["samples_per_client"] 장 (숫자 3개면 400장씩, 4개면 300장씩).
    → {"C1": [MNIST train 인덱스 ...], ..., "C6": [...]}
    """
    train_y = np.asarray(train_y)
    seed = cfg["seed"]
    per_client = cfg["samples_per_client"]
    client_digits = cfg["client_digits"]

    # 클라별 숫자 하나당 장수 (클라 전체 장수를 같게 맞춤: 명세 "클라별 전체 이미지 수 동일")
    per_digit = {}
    for c, digits in client_digits.items():
        if per_client % len(digits) != 0:
            raise ValueError(f"{c}: {per_client}장을 숫자 {len(digits)}개로 똑같이 나눌 수 없습니다")
        per_digit[c] = per_client // len(digits)

    split = {c: [] for c in client_digits}
    for d in range(10):
        owners = [c for c, digits in client_digits.items() if d in digits]  # config 순서 (C1, C4 …)
        if not owners:
            continue
        idx = np.flatnonzero(train_y == d)
        need = sum(per_digit[c] for c in owners)
        if need > len(idx):
            raise ValueError(f"숫자 {d}: {need}장이 필요한데 {len(idx)}장뿐입니다")

        rng = np.random.default_rng([seed, d])   # 숫자마다 독립 시드 → 같은 시드면 같은 결과
        idx = rng.permutation(idx)
        start = 0
        for c in owners:                          # 앞에서부터 잘라 나눔 → 클라끼리 겹침 없음
            split[c].extend(idx[start:start + per_digit[c]].tolist())
            start += per_digit[c]

    return {c: sorted(int(i) for i in v) for c, v in split.items()}


def split_summary(split, train_y):
    """→ {"C1": {"n": 1200, "digit_counts": [숫자 0~9 개수 10개]}, ...}"""
    train_y = np.asarray(train_y)
    return {
        c: {"n": len(idx),
            "digit_counts": np.bincount(train_y[idx], minlength=10).astype(int).tolist()}
        for c, idx in split.items()
    }