"""11/19 필수 점검표 자동 검사 — 공동 (5.5). 명세 '필수 구현' 6개를 실제 로그로 O/X 확인.
실행 순서: python -m scripts.run_all → python -m tests.test_requirements
"""
import sys

import numpy as np

from dashboard.app import app
from hfl.common import BASE_DIR, load_config, read_json
from hfl.data_split import load_mnist
from scripts.make_report import read_jsonl

TRAIN_FIELDS = {
    "global": {"exp", "round", "model_version", "target", "eval_data", "acc", "loss", "acc_by_digit", "edge_n", "kind"},
    "client": {"exp", "round", "model_version", "target", "edge", "n", "train_loss", "eval_data", "acc", "loss", "acc_by_digit", "participated", "kind"},
    "edge": {"exp", "round", "model_version", "target", "clients", "client_n", "n_samples", "kind"},
    "round": {"exp", "round", "model_version", "target", "duration_ms", "kind"},
}
COMM_FIELDS = {"exp", "round", "model_version", "src", "dst", "api", "latency_ms", "ok", "status", "error", "req_bytes", "bytes", "kind"}


def load(d):
    return {"id": d.name, "config": read_json(d / "config.json"), "split": read_json(d / "split.json"),
            "assignment": read_json(d / "assignment.json"), "train": read_jsonl(d / "train.jsonl"), "comm": read_jsonl(d / "comm.jsonl")}


def kind_of(target):
    return "global" if target == "global" else "round" if target == "round" else "edge" if target.startswith("E") else "client"


def check_split(exps, train_y):
    """1. 클라별 특정 숫자만 보유, 이미지 중복 없음, 클라별 이미지 수 같음"""
    for e in exps:
        cfg = e["config"]
        seen = set()
        for c, info in e["split"]["clients"].items():
            idx = info["indices"]
            labels = set(np.asarray(train_y)[idx].tolist())
            assert labels == set(cfg["client_digits"][c]), f"{e['id']} {c}: 보유 숫자 {sorted(labels)} ≠ 설정 {cfg['client_digits'][c]}"
            assert len(idx) == cfg["samples_per_client"], f"{e['id']} {c}: {len(idx)}장"
            assert not (seen & set(idx)), f"{e['id']} {c}: 다른 클라와 이미지 겹침"
            seen |= set(idx)
    return f"클라 {len(exps[0]['split']['clients'])}개, 클라당 {exps[0]['config']['samples_per_client']}장, 숫자 라벨 = 설정, 겹침 0"


def check_topology(exps):
    """2. 중앙 1 · 엣지 2 · 클라 6 (명세 기본 구성 그대로인지 봄. 구성을 바꾼 설정이면 여기만 X 가 정상)"""
    for e in exps:
        a = e["assignment"]["assignment"]
        clients = [c for cs in a.values() for c in cs]
        assert len(a) == 2 and len(clients) == 6 and len(set(clients)) == 6, f"{e['id']}: 엣지 {len(a)} · 클라 {len(clients)}"
        to_central = {r["dst"] for r in e["comm"] if r["src"] in a}
        assert to_central == {"S"}, f"{e['id']}: 엣지가 보낸 곳 {to_central}"
    return "모든 실험: 엣지 2개가 중앙 S 하나에만 보내고, 클라 6명이 엣지에 하나씩 배정"


def check_rest_fedavg(exps):
    """3. REST 로 모델 전달 + FedAvg 2단계 집계 (표본 수 가중), 모델 버전 섞임 없음"""
    for e in exps:
        R = e["config"]["rounds"]
        a = e["assignment"]["assignment"]
        n_clients = len(e["config"]["client_digits"])  # 설정이 바뀌어도 맞게 (클라 수를 숫자로 박지 않음)
        for r in range(1, R + 1):
            tr = [x for x in e["train"] if x["round"] == r]
            cm = [x for x in e["comm"] if x["round"] == r and x["kind"] != "injected"]
            clients = {x["target"]: x for x in tr if kind_of(x["target"]) == "client"}
            edges = {x["target"]: x for x in tr if kind_of(x["target"]) == "edge"}
            glob = next(x for x in tr if x["target"] == "global")
            assert len(clients) == n_clients and set(edges) == set(a), f"{e['id']} R{r}: 클라 {len(clients)} 엣지 {sorted(edges)}"
            assert all(x["model_version"] == r for x in clients.values()), f"{e['id']} R{r}: 클라 학습 시작 버전 ≠ {r}"
            assert glob["model_version"] == r + 1, f"{e['id']} R{r}: 집계 결과 버전 {glob['model_version']}"
            # 11/22 B(윤효연) 수정: 지연·중단 실험(심화 6.B, run_all --fault)은 제출 못 한 클라(participated false)를 빼고 엣지가 집계함
            for ed, rec in edges.items():  # 1차 집계 가중치 = 담당 클라 표본 수 (지연·중단 실험은 제출 못 한 클라 빼고)
                joined = [c for c in a[ed] if clients[c]["participated"]]
                assert sorted(rec["clients"]) == sorted(joined) and rec["n_samples"] == sum(clients[c]["n"] for c in joined), f"{e['id']} R{r} {ed}: 표본 수"
            assert glob["edge_n"] == {ed: edges[ed]["n_samples"] for ed in edges}, f"{e['id']} R{r}: 중앙 2차 집계 가중치 ≠ 엣지 표본 수"
            apis = {(x["src"][0], x["api"]) for x in cm}
            need = {("C", "GET /model"), ("C", "POST /client_update"), ("E", "GET /model"), ("E", "POST /edge_update")}
            assert need <= apis, f"{e['id']} R{r}: 빠진 요청 {need - apis}"
            assert all(x["ok"] for x in cm), f"{e['id']} R{r}: 실패 요청 있음"
            assert all(x["model_version"] == r for x in cm if x["api"] != "GET /status"), f"{e['id']} R{r}: 다른 버전 모델이 오감"
    inj = [e for e in exps if e["config"].get("inject")]
    for e in inj:  # 결함 주입: 지난 버전·배정 밖 엣지 제출이 409 로 거부
        bad = [x for x in e["comm"] if x["kind"] == "injected"]
        assert len(bad) == 2 and all(x["status"] == 409 for x in bad), f"{e['id']}: 주입 요청 {[(x['status']) for x in bad]}"
    return f"모든 라운드에서 REST 요청 4종 성공, 엣지·중앙 가중치 = 표본 수, 버전 섞임 0" + (f", 결함 주입 409 {2 * len(inj)}건 거부" if inj else "")


def check_compare(exps):
    """4. 선호 기반 배정 vs 무작위 배정 비교 (같은 조건)"""
    # 11/22 B(윤효연) 수정: fault_on 실험도 뺌 (안 빼면 선호 자리에 exp_pref_seed42_fault 가 들어감)
    by = {e["config"]["assign_method"]: e for e in exps if not e["config"].get("inject") and not e["config"].get("fault_on")}
    assert {"pref", "random"} <= set(by), f"실험 배정 방식: {sorted(by)}"
    keys = ("seed", "rounds", "local_epochs", "lr", "batch_size", "samples_per_client", "client_digits")
    assert all(by["pref"]["config"][k] == by["random"]["config"][k] for k in keys), "두 실험 학습 조건이 다름"
    assert by["pref"]["split"]["clients"] == by["random"]["split"]["clients"], "두 실험 데이터 분할이 다름"
    for m in ("pref", "random"):
        ck = by[m]["assignment"]["check"]
        assert not (ck["unassigned"] or ck["duplicated"] or ck["capacity_violation"]), f"{m}: 배정 제약 위반 {ck}"
    assert by["pref"]["assignment"]["assignment"] != by["random"]["assignment"]["assignment"], "두 배정이 같음"
    report = (BASE_DIR / "docs" / "report.md").read_text(encoding="utf-8")
    assert "| 선호(matching) |" in report and "| 무작위 |" in report, "docs/report.md 에 비교 표 없음 → python -m scripts.make_report"
    rp = by["pref"]["assignment"]["check"]["mean_pref_rank"]
    rr = by["random"]["assignment"]["check"]["mean_pref_rank"]
    return f"같은 분할·설정, 위반 0, 평균 선호 순위 선호 {rp:.2f} vs 무작위 {rr:.2f}, 보고서 표 있음"


def check_logs(exps):
    """5. 학습·데이터 분포·배정·통신 로그 저장 (log_format.md 필드)"""
    for e in exps:
        for x in e["train"]:
            k = kind_of(x["target"])
            assert set(x) == TRAIN_FIELDS[k], f"{e['id']} train {k}: {sorted(set(x) ^ TRAIN_FIELDS[k])}"
        for x in e["comm"]:
            assert set(x) == COMM_FIELDS, f"{e['id']} comm: {sorted(set(x) ^ COMM_FIELDS)}"
        assert all(0 <= x["acc"] <= 1 for x in e["train"] if "acc" in x) and all(x["latency_ms"] >= 0 for x in e["comm"])
        assert {"assignment", "check", "edge_composition", "client_prefs", "edge_prefs"} <= set(e["assignment"])
    return f"실험 {len(exps)}개 × 파일 5개, 필드가 log_format.md 와 일치, 정확도 0~1·지연 ms"


def check_dashboard(exps):
    """6. 저장된 로그를 화면 API 로 조회 (라운드·클라 연동은 tests/test_dashboard.py · 화면 시연으로 확인)"""
    c = app.test_client()
    listed = c.get("/api/experiments").get_json()
    base = [x for x in listed if not x.startswith("run-")]  # run-<시각>/… = 화면 '실험 실행' 탭에서 추가로 돌린 실험
    assert sorted(base) == sorted(e["id"] for e in exps), f"화면 실험 목록 {listed}"
    for e in exps:
        b = c.get(f"/api/{e['id']}/bundle").get_json()
        assert len(b["train"]) == len(e["train"]) and len(b["comm"]) == len(e["comm"]), f"{e['id']}: 화면이 받은 줄 수가 로그와 다름"
    assert c.get("/").status_code == 200
    return f"실험 {len(listed)}개 모두 화면 API 로 로그 전체 조회됨"


def main():
    log_root = BASE_DIR / load_config()["log_dir"]
    dirs = sorted(d for d in log_root.iterdir() if (d / "assignment.json").exists()) if log_root.exists() else []
    if not dirs:
        sys.exit(f"{log_root} 에 실험 로그가 없음 → 먼저 python -m scripts.run_all")
    exps = [load(d) for d in dirs]
    app.config["LOG_ROOT"] = log_root
    train_y = load_mnist(load_config())["train_y"]
    items = [
        ("1. 클라별 특정 숫자 보유 분할 (이미지 중복 없음)", lambda: check_split(exps, train_y)),
        ("2. 중앙 1 · 엣지 2 · 클라 6 구성", lambda: check_topology(exps)),
        ("3. Flask REST 모델 전달 + FedAvg 2단계 집계", lambda: check_rest_fedavg(exps)),
        ("4. 선호 기반 vs 무작위 배정 비교", lambda: check_compare(exps)),
        ("5. 학습·분포·배정·통신 로그 저장", lambda: check_logs(exps)),
        ("6. 저장된 로그 조회 (모니터링 API)", lambda: check_dashboard(exps)),
    ]
    sys.stdout.reconfigure(encoding="utf-8")
    failed = 0
    for name, fn in items:
        try:
            print(f"O  {name}\n   {fn()}")
        except AssertionError as err:
            failed += 1
            print(f"X  {name}\n   {err}")
    print(f"\n{len(items) - failed}/{len(items)} 통과 (실험: {', '.join(e['id'] for e in exps)})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
