"""중앙 서버 — 담당 B(윤효연), WBS 3.4.1

엣지 2개의 모델을 받아 2차 집계 → 공통 시험 데이터로 평가 → train.jsonl 기록 → 버전 +1.
요청·응답 형식은 docs/api.md. 라운드 r 은 모델 버전 r 로 시작 (라운드 번호 = 현재 버전).
"""
import argparse
import threading
from urllib.parse import urlsplit

from flask import Flask, jsonify, request

from hfl.aggregate import weighted_average
from hfl.comm import from_wire, to_wire
from hfl.common import append_jsonl, exp_dir, load_config
from hfl.data_split import load_mnist
from hfl.model import evaluate, init_weights

app = Flask(__name__)
cfg = load_config()

# 서버 상태: 요청과 요청 사이에 기억하는 값. 요청이 동시에 와도 꼬이지 않게 lock 안에서만 읽고 씀
lock = threading.Lock()
state = {
    "exp": None,        # 실험 ID (POST /start 전에는 None)
    "edges": [],        # 이번 실험의 엣지 ID 목록
    "version": 0,       # 현재 공동 모델 버전
    "weights": None,    # 현재 공동 모델 (numpy 7,850개)
    "submitted": {},    # 이번 라운드에 받은 엣지 모델 {"E1": (모델, 표본 수)}
    "last_eval": None,  # 최근 평가 {"round", "acc", "loss"}
}
_test = {}  # 공통 시험 데이터 (처음 필요할 때 한 번 읽어 둠)


def _load_test():
    if not _test:
        d = load_mnist(cfg)
        _test["x"], _test["y"] = d["test_x"], d["test_y"]
    return _test["x"], _test["y"]


def _reject(msg):
    return jsonify(ok=False, error=msg), 409


@app.post("/start")
def start():
    """{"exp_id", "edges"} → 모델 0 으로 초기화, 버전 1"""
    body = request.get_json()
    with lock:
        state.update(exp=body["exp_id"], edges=list(body["edges"]), version=1,
                     weights=init_weights(), submitted={}, last_eval=None)
    return jsonify(ok=True, version=1)


@app.get("/model")
def get_model():
    """→ {"round", "version", "weights"}"""
    with lock:
        if state["exp"] is None:
            return _reject("not started")
        v = state["version"]
        return jsonify(round=v, version=v, weights=to_wire(state["weights"]))


@app.get("/status")
def status():
    """→ {"exp", "round", "version", "submitted", "last_eval"}"""
    with lock:
        return jsonify(exp=state["exp"], round=state["version"], version=state["version"],
                       submitted=list(state["submitted"]), last_eval=state["last_eval"])


@app.post("/edge_update")
def edge_update():
    """{"edge_id", "version", "weights", "n_samples"}
    409: 시작 전 / 모르는 엣지 / 버전 불일치
    엣지 다 모이면 weighted_average(엣지 표본 수) → evaluate → train.jsonl (target "global") → 버전 +1
    """
    body = request.get_json()
    with lock:
        if state["exp"] is None:
            return _reject("not started")
        if body["edge_id"] not in state["edges"]:
            return _reject("unknown edge")
        if body["version"] != state["version"]:
            return _reject("version mismatch")  # 다른 라운드 모델이 섞이지 않게 (PDF 5쪽)

        # 같은 엣지가 같은 라운드에 또 내면 덮어씀
        state["submitted"][body["edge_id"]] = (from_wire(body["weights"]), body["n_samples"])
        received = len(state["submitted"])
        aggregated = received == len(state["edges"])
        if aggregated:
            _aggregate()
        return jsonify(ok=True, received=received, aggregated=aggregated, version=state["version"])


def _aggregate():
    """2차 집계: 엣지 모델을 엣지별 전체 표본 수로 가중 평균 → 시험 데이터 평가 → 기록 → 버전 +1
    edge_update 의 lock 안에서만 부름.
    """
    r = state["version"]
    edges = state["edges"]  # 늘 같은 순서로 더해야 실행마다 결과가 같음
    ns = [state["submitted"][e][1] for e in edges]
    new_w = weighted_average([state["submitted"][e][0] for e in edges], ns)

    x, y = _load_test()
    acc, loss, acc_by_digit = evaluate(new_w, x, y)
    append_jsonl(exp_dir(cfg, state["exp"]) / "train.jsonl", {
        "exp": state["exp"],
        "round": r,
        "model_version": r + 1,  # 집계 결과 버전
        "target": "global",
        "eval_data": "test",
        "acc": acc,
        "loss": loss,
        "acc_by_digit": acc_by_digit,
        "edge_n": dict(zip(edges, ns)),
        "kind": "measured",
    })
    state.update(version=r + 1, weights=new_w, submitted={},
                 last_eval={"round": r, "acc": acc, "loss": loss})


if __name__ == "__main__":
    url = urlsplit(cfg["central_url"])
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=url.port)  # 기본값은 설정 파일 central_url 의 포트
    port = ap.parse_args().port
    _load_test()  # 시험 데이터를 미리 읽어 둠 → 첫 집계 요청이 느려지지 않게
    app.run(host=url.hostname, port=port, threaded=True)
