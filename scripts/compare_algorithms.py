"""알고리즘 비교 — 담당 A(이건), 심화 6.A

명세 심화: "동일한 단일 중앙 집계 구조에서 FedAvg·FedProx를 비교하고, 여력이 있으면 q-FedAvg를 추가".
q-FedAvg: 클라 학습은 FedAvg 와 같고, 중앙 집계만 hfl.aggregate.q_fedavg (손실^q 가중, fair_flearn 원본).
단일 중앙 집계 구조 = 엣지 단계를 추가하기 전 구조 (클라 6 → 중앙 S 1개가 바로 표본 수 가중 평균).
Flask 서버 없이 한 프로세스에서 라운드 루프를 돌림. 분할·시드·초기 모델·학습률·배치는 필수 실험과 같음
(클라 학습 seed 도 runner 의 client_seed 를 그대로 씀 → 같은 클라·같은 라운드는 같은 배치 순서).

실행: python -m scripts.compare_algorithms                 (기본: epoch 1·5 × FedAvg, FedProx μ 0.01·0.1·1, 설정 시드)
      python -m scripts.compare_algorithms --seeds 42 7 123 --epochs 1 5 10 --q 1 5 --q-epochs 1 --report   (보고서용 전체 비교)
      python -m scripts.compare_algorithms --seeds 42 --epochs 1 --mu 0 --q 1 --q-lscale 10   (q-FedAvg 보폭 진단, 문서 안 바꿈)
      python -m scripts.compare_algorithms --report-only      (실행 없이 summary.json 으로 문서만 다시 만듦)

결과: logs/algo_compare/<exp_id>/ 에 config.json, split.json, train.jsonl (형식은 docs/log_format.md 와 같음,
      엣지가 없어서 assignment.json·comm.jsonl 은 만들지 않음 → 기존 화면 실험 목록에는 안 나타남)
      logs/algo_compare/summary.json 에 실험별 요약.
      --report 이면 docs/algorithm_comparison.md 의 <!-- auto:... --> 구간(표)과 docs/img/algo_acc_e*.svg(그래프) 갱신.
"""
import argparse
import json

import numpy as np

from hfl.aggregate import q_fedavg, weighted_average
from hfl.common import BASE_DIR, append_jsonl, exp_dir, load_config, read_json, write_json
from hfl.data_split import load_mnist, make_split, split_summary
from hfl.model import evaluate, init_weights, train_local
from runner.client_runner import client_seed

OUT = "algo_compare"


def exp_name(cfg, algo, p, lscale=1.0):
    tag = {"fedavg": "fedavg", "fedprox": f"fedprox_mu{p:g}", "qfedavg": f"qfedavg_q{p:g}"}[algo]
    if algo == "qfedavg" and lscale != 1:
        tag += f"_ls{lscale:g}"
    return f"alg_{tag}_e{cfg['local_epochs']}_seed{cfg['seed']}"


def run_one(cfg, data, split, summary, algo, p, rounds, lscale=1.0):
    """한 알고리즘·설정으로 rounds 라운드. p = FedProx 의 μ 또는 q-FedAvg 의 q. → 요약 dict"""
    mu = p if algo == "fedprox" else 0.0
    q = p if algo == "qfedavg" else None
    run_cfg = dict(cfg, mu=mu)
    if q is not None:
        run_cfg["q"] = q
    if q is not None and lscale != 1:
        run_cfg["q_lscale"] = lscale
    exp_id = exp_name(cfg, algo, p, lscale)
    d = exp_dir(cfg, f"{OUT}/{exp_id}")
    log = d / "train.jsonl"
    log.unlink(missing_ok=True)
    write_json(d / "config.json", {**run_cfg, "exp_id": exp_id, "algorithm": algo, "structure": "single_central",
                                   "assign_method": None, "inject": False, "fault_on": False, "kind": "config"})
    write_json(d / "split.json", {"seed": cfg["seed"], "clients": {
        c: {**summary[c], "indices": split[c]} for c in split}})

    cids = sorted(split)
    n = {c: len(split[c]) for c in cids}
    # 공정성 지표용: 공동 모델을 각 클라가 가진 숫자의 시험 이미지로만 평가 (클라 입장의 정확도)
    own_test = {c: np.isin(data["test_y"], cfg["client_digits"][c]) for c in cids}
    w = init_weights(cfg)
    hist = []
    for r in range(1, rounds + 1):
        ups, client_acc, norms, pre_loss = [], {}, {}, {}
        for c in cids:
            idx = split[c]
            if algo == "qfedavg":                                        # 학습 전 공동 모델의 자기 학습 데이터 손실 F
                pre_loss[c] = evaluate(w, data["train_x"][idx], data["train_y"][idx])[1]
            new_w, tl = train_local(w, data["train_x"][idx], data["train_y"][idx], run_cfg, client_seed(cfg, r, c))
            acc, loss, by_digit = evaluate(new_w, data["test_x"], data["test_y"])
            norms[c] = float(np.linalg.norm(new_w - w))                  # 공동 모델에서 벗어난 크기
            client_acc[c] = acc
            ups.append(new_w)
            append_jsonl(log, {"exp": exp_id, "kind": "measured", "target": c, "round": r, "model_version": r,
                               "edge": "S", "n": n[c], "train_loss": tl, "eval_data": "test", "acc": acc,
                               "loss": loss, "acc_by_digit": by_digit, "participated": True,
                               "update_norm": norms[c], **({"pre_loss": pre_loss[c]} if pre_loss else {})})
        if algo == "qfedavg":                                            # 중앙 1회 집계
            # 원본: 보폭 상수 L = 1/lr. --q-lscale 진단에서만 lr × lscale 로 바꿔 L 을 1/lscale 배로 (원본과 다름)
            w = q_fedavg(w, ups, [pre_loss[c] for c in cids], q, cfg["lr"] * lscale)
        else:                                                            # FedAvg·FedProx 공통
            w = weighted_average(ups, [n[c] for c in cids])
        acc, loss, by_digit = evaluate(w, data["test_x"], data["test_y"])
        own = {c: evaluate(w, data["test_x"][m], data["test_y"][m])[0] for c, m in own_test.items()}
        append_jsonl(log, {"exp": exp_id, "kind": "measured", "target": "global", "round": r,
                           "model_version": r + 1, "eval_data": "test", "acc": acc, "loss": loss,
                           "acc_by_digit": by_digit, "edge_n": {"S": sum(n.values())}, "acc_by_client": own})
        hist.append({"round": r, "acc": acc, "loss": loss, "min_digit_acc": min(by_digit),
                     "client_acc_min": min(client_acc.values()),
                     "client_acc_std": float(np.std(list(client_acc.values()))),
                     "mean_update_norm": float(np.mean(list(norms.values()))),
                     "digit_acc_std": float(np.std(by_digit)),
                     "own_acc_min": min(own.values()), "own_acc_std": float(np.std(list(own.values())))})
        print(f"[{exp_id}] round {r:2d}  acc={acc:.4f}  loss={loss:.4f}")

    accs = [h["acc"] for h in hist]
    last = hist[-1]
    return {"exp_id": exp_id, "algorithm": algo, "mu": run_cfg["mu"], "q": q, "q_lscale": lscale, "local_epochs": cfg["local_epochs"],
            "final_acc": last["acc"], "final_loss": last["loss"], "best_acc": max(accs),
            "final_min_digit_acc": last["min_digit_acc"],
            "acc_drop_rounds": sum(1 for a, b in zip(accs, accs[1:]) if b < a),   # 직전보다 떨어진 라운드 수
            "mean_abs_change": float(np.mean(np.abs(np.diff(accs)))) if len(accs) > 1 else 0.0,
            "final_client_acc_min": last["client_acc_min"], "final_client_acc_std": last["client_acc_std"],
            "mean_update_norm": float(np.mean([h["mean_update_norm"] for h in hist])),
            "final_digit_acc_std": last["digit_acc_std"],
            "final_own_acc_min": last["own_acc_min"], "final_own_acc_std": last["own_acc_std"],
            "history": hist}


DOC = BASE_DIR / "docs" / "algorithm_comparison.md"
IMG = BASE_DIR / "docs" / "img"
ALGO_STYLE = [("#1b1f24", ""), ("#2a78d6", "6 4"), ("#1baf7a", "6 4"), ("#d6502a", "2 3"),
              ("#8b5cf6", "1 0"), ("#c026d3", "4 2")]  # FedAvg = 진한 실선, q-FedAvg = 보라 계열


def label(x):
    if x["algorithm"] == "fedavg":
        return "FedAvg"
    if x["algorithm"] == "fedprox":
        return f"FedProx μ={x['mu']:g}"
    return f"q-FedAvg q={x['q']:g}"


def key(x):
    return (x["algorithm"], x["mu"], x.get("q"))


def stat(vals, fmt="{:.4f}"):
    """시드 여러 개 → '평균 (최소~최대)', 시드 1개면 값만"""
    if len(vals) == 1:
        return fmt.format(vals[0])
    return f"{fmt.format(float(np.mean(vals)))} ({fmt.format(min(vals))}~{fmt.format(max(vals))})"


def own_max(x):
    """마지막 라운드 공동 모델의 클라별 공동 정확도 최댓값 (원본 plot_fairness.py 의 best 10%, 클라 6개라 최댓값).
    summary.json 에는 없어서 그 실험의 train.jsonl 을 읽음 → summary.json 형식(화면이 읽는 파일)은 그대로. 로그가 없으면 None"""
    path = exp_dir(load_config(), f"{OUT}/{x['exp_id']}") / "train.jsonl"
    try:
        with open(path, encoding="utf-8") as f:
            rows = [r for r in map(json.loads, f) if r.get("target") == "global" and "acc_by_client" in r]
        return max(rows[-1]["acc_by_client"].values()) if rows else None
    except OSError:
        return None


def build_doc(res):
    """summary.json → docs/algorithm_comparison.md 의 auto 구간 + docs/img/algo_acc_e*.svg"""
    from scripts.make_report import fill, svg_lines, table   # 김영헌 make_report 의 표·그래프·auto 구간 함수 재사용
    results, seeds = res["results"], sorted({x["seed"] for x in res["results"]})
    epochs = sorted({x["local_epochs"] for x in results})
    algos = []
    for x in results:
        k = key(x)
        if k not in algos:
            algos.append(k)
    pick = lambda e, a, sd=None: [x for x in results if x["local_epochs"] == e and key(x) == a
                                  and (sd is None or x["seed"] == sd)]

    head = ["로컬 epoch", "알고리즘", "최종 정확도", "최종 손실", "최저 숫자 정확도", "하락 라운드 수",
            "클라 정확도 최솟값", "평균 변화량", "클라별 공동 정확도 최솟값", "클라별 공동 정확도 최댓값", "클라 간 표준편차",
            "숫자별 정확도 표준편차"]
    rows = []
    for e in epochs:
        for a in algos:
            xs = pick(e, a)
            if not xs:                                   # q-FedAvg 는 일부 epoch 에서만 실행
                continue
            mx = [own_max(x) for x in xs]
            best = "—" if None in mx else stat(mx)
            rows.append([e, label(xs[0]), stat([x["final_acc"] for x in xs]), stat([x["final_loss"] for x in xs]),
                         stat([x["final_min_digit_acc"] for x in xs]), stat([x["acc_drop_rounds"] for x in xs], "{:.1f}"),
                         stat([x["final_client_acc_min"] for x in xs]), stat([x["mean_update_norm"] for x in xs]),
                         stat([x["final_own_acc_min"] for x in xs]), best,
                         stat([x["final_own_acc_std"] for x in xs]),
                         stat([x["final_digit_acc_std"] for x in xs])])
    summary_md = (f"시드 {', '.join(map(str, seeds))} · 라운드 {res['rounds']} · 단일 중앙 집계. "
                  f"값 = 시드 평균 (최소~최대).\n\n" + table(head, rows))

    head2 = ["로컬 epoch", "시드"] + [label(next(x for x in results if key(x) == a)) for a in algos] + ["정확도 1위"]
    rows2 = []
    for e in epochs:
        for sd in seeds:
            got = [pick(e, a, sd) for a in algos]
            accs = [g[0]["final_acc"] if g else None for g in got]
            best = label(got[int(np.argmax([-1 if v is None else v for v in accs]))][0])
            rows2.append([e, sd] + ["—" if v is None else f"{v:.4f}" for v in accs] + [best])
    seed_md = "시드별 최종 공동 정확도 (같은 순서가 시드마다 반복되는지 확인).\n\n" + table(head2, rows2)

    IMG.mkdir(parents=True, exist_ok=True)
    imgs = []
    gseed = load_config()["seed"] if load_config()["seed"] in seeds else seeds[0]   # 그래프는 설정 시드(42) 기준
    short = lambda x: {"fedavg": "FedAvg", "fedprox": f"Prox μ={x['mu']:g}",
                       "qfedavg": f"qFed q={x.get('q') or 0:g}"}[x["algorithm"]]  # 범례 칸이 좁아 짧게
    for e in epochs:
        series = []
        for k, a in enumerate(algos):
            xs = pick(e, a, gseed)
            if not xs:
                continue
            x = xs[0]
            color, dash = ALGO_STYLE[k % len(ALGO_STYLE)]
            series.append((short(x), [h["acc"] for h in x["history"]], color, dash))
        name = f"algo_acc_e{e}.svg"
        svg_lines(series, f"라운드별 공동 정확도 (로컬 epoch {e}, 시드 {gseed})", IMG / name)
        imgs.append(f"![로컬 epoch {e}](img/{name})")
    curve_md = "\n\n".join(imgs)

    text = DOC.read_text(encoding="utf-8")
    text = fill(text, "algo_summary", summary_md)
    text = fill(text, "algo_seeds", seed_md)
    text = fill(text, "algo_curves", curve_md)
    DOC.write_text(text, encoding="utf-8")
    print(f"{DOC.relative_to(BASE_DIR)} 갱신")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=None, help="기본: 설정 파일 rounds")
    ap.add_argument("--epochs", type=int, nargs="+", default=[1, 5], help="로컬 epoch 값들")
    ap.add_argument("--mu", type=float, nargs="+", default=[0.01, 0.1, 1.0], help="FedProx μ 값들 (FedAvg 는 항상 포함)")
    ap.add_argument("--q", type=float, nargs="+", default=[], help="q-FedAvg q 값들 (기본: 실행 안 함)")
    ap.add_argument("--q-epochs", type=int, nargs="+", default=None, help="q-FedAvg 를 돌릴 로컬 epoch (기본: --epochs 전부)")
    ap.add_argument("--q-lscale", type=float, default=1.0,
                    help="[진단] q-FedAvg 보폭 상수 배수 (기본 1 = 원본). 1이 아니면 summary_diag.json 에 따로 저장, 문서 갱신 안 함")
    ap.add_argument("--seeds", type=int, nargs="+", default=None, help="시드 값들 (기본: 설정 파일 seed). 시드마다 분할도 다시 만듦")
    ap.add_argument("--report", action="store_true", help="실행 후 docs/algorithm_comparison.md 표·그래프 갱신")
    ap.add_argument("--report-only", action="store_true", help="실행 없이 summary.json 으로 문서만 갱신")
    args = ap.parse_args()

    base = load_config()
    summary_path = exp_dir(base, OUT) / "summary.json"
    if args.report_only:
        build_doc(read_json(summary_path))
        return
    rounds = args.rounds or base["rounds"]
    data = load_mnist(base)

    results = []
    for sd in args.seeds or [base["seed"]]:
        seed_cfg = dict(base, seed=sd)
        split = make_split(seed_cfg, data["train_y"])                   # 시드가 바뀌면 분할도 바뀜
        summary = split_summary(split, data["train_y"])
        for e in args.epochs:
            cfg = dict(seed_cfg, local_epochs=e)
            results.append({"seed": sd, **run_one(cfg, data, split, summary, "fedavg", 0.0, rounds)})
            for mu in args.mu:
                if mu > 0:
                    results.append({"seed": sd, **run_one(cfg, data, split, summary, "fedprox", mu, rounds)})
            if args.q_epochs is None or e in args.q_epochs:
                for q in args.q:
                    results.append({"seed": sd, **run_one(cfg, data, split, summary, "qfedavg", q, rounds,
                                                          args.q_lscale)})

    res = {"rounds": rounds, "structure": "single_central", "seeds": args.seeds or [base["seed"]], "results": results}
    if args.q_lscale != 1:                               # 진단 실행은 본 결과(summary.json)를 덮지 않음
        summary_path = summary_path.with_name("summary_diag.json")
        args.report = False
    write_json(summary_path, res)
    print("\n| 실험 | 최종 정확도 | 최종 손실 | 최고 정확도 | 최저 숫자 정확도 | 하락 라운드 수 | 클라 정확도 최솟값 | 평균 변화량 |")
    print("|---|---|---|---|---|---|---|---|")
    for x in results:
        print(f"| {x['exp_id']} | {x['final_acc']:.4f} | {x['final_loss']:.4f} | {x['best_acc']:.4f} | "
              f"{x['final_min_digit_acc']:.4f} | {x['acc_drop_rounds']} | {x['final_client_acc_min']:.4f} | "
              f"{x['mean_update_norm']:.4f} |")
    if args.report:
        build_doc(res)


if __name__ == "__main__":
    main()