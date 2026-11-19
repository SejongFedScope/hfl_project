"""A 검사 — 담당 A(이건), WBS 2.1.3 · 2.2.4 · 2.3.5. 실행: python -m tests.test_learning

모델 단독 확인(2.3.5): python -m tests.test_learning --sim [라운드수]
  Flask 없이 클라 6 → 엣지 2 → 중앙 루프를 돌리고 1단계(클라 6개 한 번에 평균)와 비교,
  결과를 logs/sim_a/summary.json 에 저장 (실행 기록).
"""
import sys

import numpy as np

from hfl.aggregate import weighted_average
from hfl.common import exp_dir, load_config, write_json
from hfl.data_split import load_mnist, make_split, split_summary
from hfl.model import N_PARAMS, evaluate, init_weights, train_local

# docs/aggregation_check.md 손계산 예제 (클라: 엣지, 표본 수, 모델)
HAND_CLIENTS = {
    "C1": ("E1", 100, [1, 0, 2]),
    "C2": ("E1", 200, [2, 1, 0]),
    "C3": ("E1", 100, [4, 3, 2]),
    "C4": ("E2", 50, [0, 0, 2]),
    "C5": ("E2", 50, [2, 2, 0]),
    "C6": ("E2", 100, [2, 0, 1]),
}
HAND_E1, HAND_E2, HAND_CENTRAL = [2.25, 1.25, 1.0], [1.5, 0.5, 1.0], [2.0, 1.0, 1.0]


def _edge(edge_id):
    rows = [(n, w) for e, n, w in HAND_CLIENTS.values() if e == edge_id]
    return weighted_average([w for _, w in rows], [n for n, _ in rows]), sum(n for n, _ in rows)


def test_two_stage_hand_example():
    """docs/aggregation_check.md 손계산 예제 (클라 6 → 엣지 2 → 중앙): 손계산값 = weighted_average 결과"""
    e1, n1 = _edge("E1")
    e2, n2 = _edge("E2")
    assert n1 == 400 and np.allclose(e1, HAND_E1)            # 1차 집계 (클라 표본 수 비례)
    assert n2 == 200 and np.allclose(e2, HAND_E2)
    central = weighted_average([e1, e2], [n1, n2])           # 2차 집계 (엣지 전체 표본 수 비례)
    assert np.allclose(central, HAND_CENTRAL)


def test_two_stage_equals_flat():
    """2단계 집계 = 클라 6개를 한 번에 가중 평균. 배정을 바꿔도 공동 모델이 같음 (명세 '비교 실험 해석' 근거)"""
    e1, n1 = _edge("E1")
    e2, n2 = _edge("E2")
    flat = weighted_average([w for _, _, w in HAND_CLIENTS.values()],
                            [n for _, n, _ in HAND_CLIENTS.values()])
    assert np.allclose(weighted_average([e1, e2], [n1, n2]), flat)

    rng = np.random.default_rng(42)                          # 실제 크기 7,850, 무작위 배정 20회
    ws = [rng.normal(size=7850) for _ in range(6)]
    ns = [1200] * 6
    flat = weighted_average(ws, ns)
    for _ in range(20):
        g = rng.permutation(6)
        a, b = g[:3], g[3:]
        ea = weighted_average([ws[i] for i in a], [ns[i] for i in a])
        eb = weighted_average([ws[i] for i in b], [ns[i] for i in b])
        assert np.allclose(weighted_average([ea, eb], [3600, 3600]), flat)


def test_split_no_overlap():
    """클라 간 인덱스 겹침 0, 클라당 표본 수 = samples_per_client, 같은 시드 → 같은 분할"""
    cfg = load_config()
    train_y = load_mnist(cfg)["train_y"]
    split = make_split(cfg, train_y)
    summary = split_summary(split, train_y)

    all_idx = [i for idx in split.values() for i in idx]
    assert len(all_idx) == len(set(all_idx))                    # 클라 간 겹침 0 (같은 숫자 클라끼리 포함)
    for c, idx in split.items():
        assert len(idx) == cfg["samples_per_client"]           # 클라별 전체 이미지 수 동일
        assert summary[c]["n"] == cfg["samples_per_client"]
        held = {d for d, k in enumerate(summary[c]["digit_counts"]) if k > 0}
        assert held == set(cfg["client_digits"][c])            # 지정 숫자만 보유
        assert set(int(train_y[i]) for i in idx) == held       # 인덱스의 실제 라벨로 다시 확인
    assert make_split(cfg, train_y) == split                    # 같은 시드 → 같은 분할
    assert make_split({**cfg, "seed": cfg["seed"] + 1}, train_y) != split   # 시드가 다르면 다른 분할


def _toy_data(n=600, seed=0):
    """가짜 784차원 데이터: 숫자마다 고유한 패턴 + 잡음 (모델 단독 검사용, MNIST 불필요)"""
    rng = np.random.default_rng(seed)
    y = rng.integers(0, 10, n)
    centers = np.random.default_rng(99).random((10, 784))
    x = np.clip(centers[y] + 0.3 * rng.normal(size=(n, 784)), 0, 1)
    return x, y


def test_model_basic():
    """init 0·길이 7,850 / 입력 w 안 바뀜 / 같은 seed → 같은 결과 / 학습 후 손실 감소 / evaluate 형식"""
    cfg = load_config()
    x, y = _toy_data()
    w0 = init_weights()
    assert w0.shape == (N_PARAMS,) and not w0.any()
    assert not init_weights(cfg).any()  # 설정 기본값 init_model "zeros"
    wn = init_weights({"init_model": "normal", "seed": 7})
    assert wn.shape == (N_PARAMS,) and wn.any() and np.array_equal(wn, init_weights({"init_model": "normal", "seed": 7}))  # 같은 시드 → 같은 초기 모델
    before = w0.copy()
    w1, tl1 = train_local(w0, x, y, cfg, seed=1)
    assert np.array_equal(w0, before) and w1 is not w0          # 입력 w 를 건드리지 않음
    w1b, tl1b = train_local(w0, x, y, cfg, seed=1)
    assert np.array_equal(w1, w1b) and tl1 == tl1b              # 같은 seed → 같은 결과
    w1c, _ = train_local(w0, x, y, cfg, seed=2)
    assert not np.array_equal(w1, w1c)                          # 다른 seed → 다른 배치 순서
    acc0, loss0, _ = evaluate(w0, x, y)
    acc1, loss1, by_digit = evaluate(w1, x, y)
    assert abs(loss0 - np.log(10)) < 1e-9                       # 0 모델 손실 = ln10
    assert loss1 < loss0 and abs(tl1 - loss1) < 1e-9            # 학습 후 손실 감소, train_loss = (x,y) 손실
    assert 0.0 <= acc1 <= 1.0 and acc1 > acc0
    assert len(by_digit) == 10 and all(0.0 <= a <= 1.0 for a in by_digit)


SIM_ASSIGN = {"E1": ["C1", "C2", "C3"], "E2": ["C4", "C5", "C6"]}  # 임의 예시 (배정과 무관함을 보이는 것이 목적)


def simulate(rounds=5, two_stage=True):
    """서버 없이 라운드 루프. → (공동 모델, [{round, acc, loss}], 마지막 숫자별 정확도)"""
    cfg = load_config()
    data = load_mnist(cfg)
    split = make_split(cfg, data["train_y"])
    w, hist = init_weights(), []
    for r in range(1, rounds + 1):
        ups = {}
        for c, idx in split.items():
            seed = cfg["seed"] + r * 100 + int(c[1:])             # 라운드·클라마다 다른 순서, 설정 시드로 고정
            ups[c], _ = train_local(w, data["train_x"][idx], data["train_y"][idx], cfg, seed)
        n = {c: len(split[c]) for c in split}
        if two_stage:
            edges = [(weighted_average([ups[c] for c in m], [n[c] for c in m]), sum(n[c] for c in m))
                     for m in SIM_ASSIGN.values()]
            w = weighted_average([e for e, _ in edges], [k for _, k in edges])
        else:
            w = weighted_average([ups[c] for c in sorted(split)], [n[c] for c in sorted(split)])
        acc, loss, by_digit = evaluate(w, data["test_x"], data["test_y"])
        hist.append({"round": r, "acc": acc, "loss": loss})
        print(f"{'2단계' if two_stage else '1단계'} round {r}: acc={acc:.4f} loss={loss:.4f}")
    return w, hist, by_digit


def run_simulation(rounds=5):
    w1, h1, _ = simulate(rounds, False)
    w2, h2, d2 = simulate(rounds, True)
    same = bool(np.allclose(w1, w2))
    print("1단계 == 2단계 공동 모델:", same, " 최대 차이:", float(np.abs(w1 - w2).max()))
    write_json(exp_dir(load_config(), "sim_a") / "summary.json",
               {"rounds": rounds, "assign": SIM_ASSIGN, "two_stage": h2, "one_stage": h1,
                "acc_by_digit_last": d2, "one_equals_two": same, "max_abs_diff": float(np.abs(w1 - w2).max())})


if __name__ == "__main__":
    if "--sim" in sys.argv:
        rest = [a for a in sys.argv[1:] if a != "--sim"]
        run_simulation(int(rest[0]) if rest else 5)
        sys.exit(0)
    for t in (test_two_stage_hand_example, test_two_stage_equals_flat, test_split_no_overlap, test_model_basic):
        try:
            t()
            print("PASS", t.__name__)
        except NotImplementedError:
            print("TODO", t.__name__)
    print("ok")