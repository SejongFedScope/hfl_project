"""클라이언트 실행 프로그램 — 담당 B(윤효연), WBS 3.5

한 프로그램에서 클라 6개를 순서대로 학습·제출. 서버 3개가 떠 있어야 함.
실행: python -m runner.client_runner --method pref   (random, --inject)
"""
import argparse
import time

from hfl.assign import check_assignment, edge_composition, make_assignment
from hfl.comm import call, from_wire, to_wire, wait_ready
from hfl.common import append_jsonl, exp_dir, load_config, write_json
from hfl.data_split import load_mnist, make_split, split_summary
from hfl.model import evaluate, train_local

LOG_FILES = ("config.json", "split.json", "assignment.json", "train.jsonl", "comm.jsonl")


def make_exp_id(cfg, method, inject):
    """→ "exp_pref_seed42", "exp_pref_seed42_inject" …"""
    return f"exp_{method}_seed{cfg['seed']}" + ("_inject" if inject else "")


def client_seed(cfg, round_no, cid):
    """train_local 에 넘길 seed. (설정 seed, 라운드, 클라 ID) 만으로 정함.
    배정 방식·실행 순서와 무관 → 두 실험에서 같은 클라·같은 라운드는 같은 배치 순서 (PDF 9쪽 "학습 설정을 동일하게 유지")
    """
    return cfg["seed"] * 1_000_000 + round_no * 1_000 + list(cfg["client_digits"]).index(cid) + 1


def prepare(cfg, method, data, inject):
    """분할 → 배정 → 배정 검사 (위반 있으면 중단) → logs/<exp_id>/ 에 config.json, split.json, assignment.json
    exp_id = "exp_<method>_seed<seed>" (+ "_inject")
    → (exp_id, out_dir, split, assignment)
    """
    exp_id = make_exp_id(cfg, method, inject)
    split = make_split(cfg, data["train_y"])
    summary = split_summary(split, data["train_y"])
    assignment = make_assignment(cfg, method)
    check = check_assignment(assignment, cfg)
    bad = {k: check[k] for k in ("unassigned", "duplicated", "capacity_violation") if check[k]}
    if bad:
        raise RuntimeError(f"배정 위반이 있어 실험을 시작하지 않음: {bad}")

    out_dir = exp_dir(cfg, exp_id)
    for name in LOG_FILES:  # 같은 실험을 다시 돌리면 .jsonl 이 이어 붙어 두 실행이 섞임 → 지난 기록 지우고 시작
        (out_dir / name).unlink(missing_ok=True)

    write_json(out_dir / "config.json", {
        **cfg, "exp_id": exp_id, "algorithm": "fedavg", "assign_method": method, "inject": inject, "kind": "config",
    })
    write_json(out_dir / "split.json", {
        "seed": cfg["seed"],
        "clients": {c: {**summary[c], "indices": split[c]} for c in split},
    })
    write_json(out_dir / "assignment.json", {
        "method": method,
        "capacity": cfg["edge_capacity"],
        "client_prefs": cfg["client_prefs"],
        "edge_prefs": cfg["edge_prefs"],
        "assignment": assignment,
        "check": check,
        "edge_composition": edge_composition(assignment, summary),
    })
    return exp_id, out_dir, split, assignment


def _ok_json(resp, what):
    """200 이면 응답 JSON, 아니면 실험 중단 (반쯤 진행된 라운드로 계속 가지 않게)"""
    if resp is None:
        raise RuntimeError(f"{what}: 응답 없음 (comm.jsonl 의 error 확인)")
    if resp.status_code != 200:
        raise RuntimeError(f"{what}: {resp.status_code} {resp.text[:200]}")
    return resp.json()


def inject_faults(cfg, exp_id, comm_log, round_no, cid, edge, update):
    """거부돼야 할 요청 2건을 일부러 보냄 (kind "injected"). update = 이 클라의 진짜 제출 본문
    1. 지난 버전 모델 제출 → 담당 엣지가 409 version mismatch
    2. 배정 안 된 엣지에 제출 → 409 client not assigned to this edge
    둘 중 하나라도 받아들여지면 서버 검사가 빠진 것 → 실험 중단
    """
    other = next(e for e in cfg["edge_urls"] if e != edge)
    stale = update["version"] - 1
    cases = [
        (edge, {**update, "version": stale}, stale, "version mismatch"),
        (other, update, update["version"], "client not assigned to this edge"),
    ]
    for dst, body, version, expected in cases:
        resp = call("POST", cfg["edge_urls"][dst], "/client_update", cid, dst, comm_log, exp_id, round_no, version,
                    body=body, timeout=cfg["request_timeout_sec"], kind="injected")
        got = (resp.status_code, resp.json().get("error")) if resp is not None else None
        if got != (409, expected):
            raise RuntimeError(f"결함 주입: {cid} → {dst} 는 409 {expected!r} 여야 하는데 {got}")


def run(method, inject):
    """서버 준비 대기 → /start → 라운드 반복:
    엣지 순서대로 담당 클라마다 GET /model → train_local → evaluate → train.jsonl → POST /client_update
    라운드 끝: 중앙 /status 로 버전 r+1 확인, train.jsonl 에 duration_ms
    → exp_id
    """
    cfg = load_config()
    if inject and not 1 <= cfg["inject_round"] <= cfg["rounds"]:
        raise ValueError(f"inject_round {cfg['inject_round']} 이 라운드 범위(1~{cfg['rounds']}) 밖")
    data = load_mnist(cfg)
    exp_id, out_dir, split, assignment = prepare(cfg, method, data, inject)
    train_log, comm_log = out_dir / "train.jsonl", out_dir / "comm.jsonl"
    central, edge_urls = cfg["central_url"], cfg["edge_urls"]
    edges = list(assignment)

    def req(http_method, url, path, src, dst, round_no, version, body=None, kind="measured"):
        return call(http_method, url, path, src, dst, comm_log, exp_id, round_no, version,
                    body=body, timeout=cfg["request_timeout_sec"], kind=kind)

    for url in [central, *(edge_urls[e] for e in edges)]:
        wait_ready(url)

    # 시작 설정: round 0, kind config
    _ok_json(req("POST", central, "/start", "runner", "S", 0, None, {"exp_id": exp_id, "edges": edges}, "config"), "중앙 /start")
    for e in edges:
        _ok_json(req("POST", edge_urls[e], "/start", "runner", e, 0, None, {"exp_id": exp_id, "clients": assignment[e]}, "config"), f"{e} /start")

    for r in range(1, cfg["rounds"] + 1):
        t0 = time.perf_counter()
        injected = False
        for e in edges:
            for cid in assignment[e]:
                got = _ok_json(req("GET", edge_urls[e], "/model", cid, e, r, r), f"{cid} → {e} GET /model")
                if got["version"] != r:
                    raise RuntimeError(f"{cid}: 라운드 {r} 인데 버전 {got['version']} 모델을 받음")

                idx = split[cid]
                new_w, train_loss = train_local(from_wire(got["weights"]), data["train_x"][idx], data["train_y"][idx],
                                                cfg, client_seed(cfg, r, cid))
                acc, loss, acc_by_digit = evaluate(new_w, data["test_x"], data["test_y"])
                append_jsonl(train_log, {
                    "exp": exp_id,
                    "round": r,
                    "model_version": r,  # 학습을 시작한 버전
                    "target": cid,
                    "edge": e,
                    "n": len(idx),
                    "train_loss": train_loss,
                    "eval_data": "test",
                    "acc": acc,
                    "loss": loss,
                    "acc_by_digit": acc_by_digit,
                    "participated": True,
                    "kind": "measured",
                })

                update = {"client_id": cid, "version": r, "weights": to_wire(new_w), "n_samples": len(idx), "train_loss": train_loss}
                if inject and r == cfg["inject_round"] and not injected:  # 라운드 첫 클라가 진짜 제출 전에 시험 요청 2건
                    inject_faults(cfg, exp_id, comm_log, r, cid, e, update)
                    injected = True
                _ok_json(req("POST", edge_urls[e], "/client_update", cid, e, r, r, update), f"{cid} → {e} POST /client_update")

        status = _ok_json(req("GET", central, "/status", "runner", "S", r, r + 1), "중앙 /status")
        if status["version"] != r + 1:
            raise RuntimeError(f"라운드 {r} 끝났는데 중앙 버전이 {status['version']} (기대 {r + 1})")
        append_jsonl(train_log, {
            "exp": exp_id,
            "round": r,
            "model_version": r + 1,  # 이 라운드 집계 결과 버전
            "target": "round",
            "duration_ms": round((time.perf_counter() - t0) * 1000, 3),
            "kind": "measured",
        })
        print(f"[{exp_id}] 라운드 {r}/{cfg['rounds']}  정확도 {status['last_eval']['acc']:.4f}")
    return exp_id


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", choices=["pref", "random"], default="pref")
    ap.add_argument("--inject", action="store_true", help="inject_round 에 거부돼야 할 요청 2건을 일부러 보냄")
    a = ap.parse_args()
    run(a.method, a.inject)
