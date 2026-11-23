"""알고리즘 비교 — 담당 A(이건), 심화 6.A

명세 심화: "동일한 단일 중앙 집계 구조에서 FedAvg·FedProx를 비교하고, 여력이 있으면 q-FedAvg를 추가".
단일 중앙 집계 구조 = 엣지 단계를 추가하기 전 구조 (클라 6 → 중앙 S 1개가 바로 표본 수 가중 평균).
Flask 서버 없이 한 프로세스에서 라운드 루프를 돌림. 분할·시드·초기 모델·학습률·배치는 필수 실험과 같음
(클라 학습 seed 도 runner 의 client_seed 를 그대로 씀 → 같은 클라·같은 라운드는 같은 배치 순서).

실행: python -m scripts.compare_algorithms                 (기본: epoch 1·5 × FedAvg, FedProx μ 0.01·0.1·1)
      python -m scripts.compare_algorithms --rounds 20 --epochs 1 --mu 0 0.1

결과: logs/algo_compare/<exp_id>/ 에 config.json, split.json, train.jsonl (형식은 docs/log_format.md 와 같음,
      엣지가 없어서 assignment.json·comm.jsonl 은 만들지 않음 → 기존 화면 실험 목록에는 안 나타남)
      logs/algo_compare/summary.json 에 실험별 요약.
"""
import argparse

import numpy as np

from hfl.aggregate import weighted_average
from hfl.common import append_jsonl, exp_dir, load_config, write_json
from hfl.data_split import load_mnist, make_split, split_summary
from hfl.model import evaluate, init_weights, train_local
from runner.client_runner import client_seed

OUT = "algo_compare"


def exp_name(cfg, algo, mu):
    tag = "fedavg" if algo == "fedavg" else f"fedprox_mu{mu:g}"
    return f"alg_{tag}_e{cfg['local_epochs']}_seed{cfg['seed']}"


def run_one(cfg, data, split, summary, algo, mu, rounds):
    """한 알고리즘·설정으로 rounds 라운드. → 요약 dict"""
    run_cfg = dict(cfg, mu=mu if algo == "fedprox" else 0.0)
    exp_id = exp_name(cfg, algo, mu)
    d = exp_dir(cfg, f"{OUT}/{exp_id}")
    log = d / "train.jsonl"
    log.unlink(missing_ok=True)
    write_json(d / "config.json", {**run_cfg, "exp_id": exp_id, "algorithm": algo, "structure": "single_central",
                                   "assign_method": None, "inject": False, "fault_on": False, "kind": "config"})
    write_json(d / "split.json", {"seed": cfg["seed"], "clients": {
        c: {**summary[c], "indices": split[c]} for c in split}})

    cids = sorted(split)
    n = {c: len(split[c]) for c in cids}
    w = init_weights(cfg)
    hist = []
    for r in range(1, rounds + 1):
        ups, client_acc, norms = [], {}, {}
        for c in cids:
            idx = split[c]
            new_w, tl = train_local(w, data["train_x"][idx], data["train_y"][idx], run_cfg, client_seed(cfg, r, c))
            acc, loss, by_digit = evaluate(new_w, data["test_x"], data["test_y"])
            norms[c] = float(np.linalg.norm(new_w - w))                  # 공동 모델에서 벗어난 크기
            client_acc[c] = acc
            ups.append(new_w)
            append_jsonl(log, {"exp": exp_id, "kind": "measured", "target": c, "round": r, "model_version": r,
                               "edge": "S", "n": n[c], "train_loss": tl, "eval_data": "test", "acc": acc,
                               "loss": loss, "acc_by_digit": by_digit, "participated": True,
                               "update_norm": norms[c]})
        w = weighted_average(ups, [n[c] for c in cids])                  # 중앙 1회 집계 (FedAvg·FedProx 공통)
        acc, loss, by_digit = evaluate(w, data["test_x"], data["test_y"])
        append_jsonl(log, {"exp": exp_id, "kind": "measured", "target": "global", "round": r,
                           "model_version": r + 1, "eval_data": "test", "acc": acc, "loss": loss,
                           "acc_by_digit": by_digit, "edge_n": {"S": sum(n.values())}})
        hist.append({"round": r, "acc": acc, "loss": loss, "min_digit_acc": min(by_digit),
                     "client_acc_min": min(client_acc.values()),
                     "client_acc_std": float(np.std(list(client_acc.values()))),
                     "mean_update_norm": float(np.mean(list(norms.values())))})
        print(f"[{exp_id}] round {r:2d}  acc={acc:.4f}  loss={loss:.4f}")

    accs = [h["acc"] for h in hist]
    last = hist[-1]
    return {"exp_id": exp_id, "algorithm": algo, "mu": run_cfg["mu"], "local_epochs": cfg["local_epochs"],
            "final_acc": last["acc"], "final_loss": last["loss"], "best_acc": max(accs),
            "final_min_digit_acc": last["min_digit_acc"],
            "acc_drop_rounds": sum(1 for a, b in zip(accs, accs[1:]) if b < a),   # 직전보다 떨어진 라운드 수
            "mean_abs_change": float(np.mean(np.abs(np.diff(accs)))) if len(accs) > 1 else 0.0,
            "final_client_acc_min": last["client_acc_min"], "final_client_acc_std": last["client_acc_std"],
            "mean_update_norm": float(np.mean([h["mean_update_norm"] for h in hist])),
            "history": hist}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=None, help="기본: 설정 파일 rounds")
    ap.add_argument("--epochs", type=int, nargs="+", default=[1, 5], help="로컬 epoch 값들")
    ap.add_argument("--mu", type=float, nargs="+", default=[0.01, 0.1, 1.0], help="FedProx μ 값들 (FedAvg 는 항상 포함)")
    args = ap.parse_args()

    base = load_config()
    rounds = args.rounds or base["rounds"]
    data = load_mnist(base)
    split = make_split(base, data["train_y"])
    summary = split_summary(split, data["train_y"])

    results = []
    for e in args.epochs:
        cfg = dict(base, local_epochs=e)
        results.append(run_one(cfg, data, split, summary, "fedavg", 0.0, rounds))
        for mu in args.mu:
            if mu > 0:
                results.append(run_one(cfg, data, split, summary, "fedprox", mu, rounds))

    write_json(exp_dir(base, OUT) / "summary.json", {"rounds": rounds, "structure": "single_central",
                                                     "seed": base["seed"], "results": results})
    print("\n| 실험 | 최종 정확도 | 최종 손실 | 최고 정확도 | 최저 숫자 정확도 | 하락 라운드 수 | 클라 정확도 최솟값 | 평균 변화량 |")
    print("|---|---|---|---|---|---|---|---|")
    for x in results:
        print(f"| {x['exp_id']} | {x['final_acc']:.4f} | {x['final_loss']:.4f} | {x['best_acc']:.4f} | "
              f"{x['final_min_digit_acc']:.4f} | {x['acc_drop_rounds']} | {x['final_client_acc_min']:.4f} | "
              f"{x['mean_update_norm']:.4f} |")


if __name__ == "__main__":
    main()
