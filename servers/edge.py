"""엣지 서버 — 담당 B(윤효연), WBS 3.4.2

담당 클라 3명의 모델을 받아 1차 집계 → 중앙에 제출 → 버전 +1.
실행: python -m servers.edge --id E1 (--port 생략 시 설정 파일 edge_urls 의 포트). 요청·응답 형식은 docs/api.md.
"""
import argparse
import threading
from urllib.parse import urlsplit

from flask import Flask, jsonify, request

from hfl.aggregate import weighted_average
from hfl.comm import call, from_wire, to_wire
from hfl.common import append_jsonl, exp_dir, load_config

app = Flask(__name__)
cfg = load_config()

# 서버 상태 (중앙과 같은 방식: lock 안에서만 읽고 씀)
lock = threading.Lock()
state = {
    "exp": None,
    "clients": [],      # 담당 클라 ID 목록
    "version": 0,       # 지금 받는 라운드의 모델 버전
    "model": None,      # 이번 라운드 공동 모델 (중앙에서 받은 숫자 리스트. 담당 클라 모두에게 같은 것)
    "received": {},     # 이번 라운드에 받은 클라 모델 {"C1": (모델, 표본 수)}
}


def _edge_id():
    return app.config["EDGE_ID"]


def _reject(msg, code=409, **extra):
    return jsonify(ok=False, error=msg, **extra), code


def _log_path(name):
    return exp_dir(cfg, state["exp"]) / name


@app.post("/start")
def start():
    """{"exp_id", "clients"} → 담당 클라 저장, 버전 1"""
    body = request.get_json()
    with lock:
        state.update(exp=body["exp_id"], clients=list(body["clients"]), version=1, model=None, received={})
        return jsonify(ok=True, edge=_edge_id(), clients=state["clients"])


@app.get("/model")
def get_model():
    """이번 라운드 첫 요청이면 중앙 GET /model 로 받아 캐시 → {"round", "version", "weights"}
    409: 시작 전 / 502: 중앙 응답 없음
    """
    with lock:
        if state["exp"] is None:
            return _reject("not started")
        v = state["version"]
        if state["model"] is None:  # 이번 라운드 첫 요청 → 중앙에서 받아 둠
            resp = call("GET", cfg["central_url"], "/model", _edge_id(), "S", _log_path("comm.jsonl"),
                        state["exp"], v, v, timeout=cfg["request_timeout_sec"])
            if resp is None or resp.status_code != 200:
                return _reject("central unavailable", 502)
            got = resp.json()
            if got["version"] != v:  # 중앙이 다른 라운드 모델을 주면 받지 않음
                return _reject("central version mismatch", 502, central_version=got["version"])
            state["model"] = got["weights"]
        return jsonify(round=v, version=v, weights=state["model"])


@app.get("/status")
def status():
    """→ {"edge", "exp", "version", "clients", "received"}"""
    with lock:
        return jsonify(edge=_edge_id(), exp=state["exp"], version=state["version"],
                       clients=state["clients"], received=list(state["received"]))


@app.post("/client_update")
def client_update():
    """{"client_id", "version", "weights", "n_samples", "train_loss"}
    409: 배정 안 된 클라 / 버전 불일치
    담당 클라 다 모이면 weighted_average(클라 표본 수) → 중앙 POST /edge_update → train.jsonl (target 엣지 ID) → 버전 +1
    """
    body = request.get_json()
    with lock:
        if state["exp"] is None:
            return _reject("not started")
        if body["client_id"] not in state["clients"]:
            return _reject("client not assigned to this edge")
        if body["version"] != state["version"]:
            return _reject("version mismatch")

        # 같은 클라가 같은 라운드에 또 내면 덮어씀
        state["received"][body["client_id"]] = (from_wire(body["weights"]), body["n_samples"])
        received, expected = len(state["received"]), len(state["clients"])
        if received < expected:
            return jsonify(ok=True, received=received, expected=expected, edge_submitted=False)

        # 담당 클라 전원 제출 → 1차 집계 (클라 순서 고정) → 중앙 제출
        v, clients = state["version"], state["clients"]
        ns = [state["received"][c][1] for c in clients]
        edge_w = weighted_average([state["received"][c][0] for c in clients], ns)
        resp = call("POST", cfg["central_url"], "/edge_update", _edge_id(), "S", _log_path("comm.jsonl"),
                    state["exp"], v, v, timeout=cfg["request_timeout_sec"],
                    body={"edge_id": _edge_id(), "version": v, "weights": to_wire(edge_w), "n_samples": sum(ns)})
        if resp is None:
            return _reject("central unavailable", 502)
        if resp.status_code != 200:
            return _reject("central rejected", 502, central_status=resp.status_code)

        append_jsonl(_log_path("train.jsonl"), {
            "exp": state["exp"],
            "round": v,
            "model_version": v,  # 이 엣지가 받은 모델 = 클라가 학습을 시작한 버전
            "target": _edge_id(),
            "clients": clients,
            "client_n": dict(zip(clients, ns)),
            "n_samples": sum(ns),
            "kind": "measured",
        })
        state.update(version=v + 1, model=None, received={})
        return jsonify(ok=True, received=received, expected=expected, edge_submitted=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, choices=list(cfg["edge_urls"]))
    ap.add_argument("--port", type=int)  # 생략하면 설정 파일 edge_urls 의 포트
    a = ap.parse_args()
    url = urlsplit(cfg["edge_urls"][a.id])
    app.config["EDGE_ID"] = a.id
    app.run(host=url.hostname, port=a.port or url.port, threaded=True)
