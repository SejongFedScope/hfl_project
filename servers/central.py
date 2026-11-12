"""중앙 서버 — 담당 B(윤효연), WBS 3.4.1

엣지 2개의 모델을 받아 2차 집계 → 공통 시험 데이터로 평가 → train.jsonl 기록 → 버전 +1.
요청·응답 형식은 docs/api.md.
"""
import argparse

from flask import Flask

app = Flask(__name__)


@app.post("/start")
def start():
    """{"exp_id", "edges"} → 모델 0 으로 초기화, 버전 1"""
    raise NotImplementedError  # TODO 3.4.1


@app.get("/model")
def get_model():
    """→ {"round", "version", "weights"}"""
    raise NotImplementedError  # TODO 3.4.1


@app.get("/status")
def status():
    """→ {"exp", "round", "version", "submitted", "last_eval"}"""
    raise NotImplementedError  # TODO 3.4.1


@app.post("/edge_update")
def edge_update():
    """{"edge_id", "version", "weights", "n_samples"}
    409: 시작 전 / 모르는 엣지 / 버전 불일치
    엣지 다 모이면 weighted_average(엣지 표본 수) → evaluate → train.jsonl (target "global") → 버전 +1
    """
    raise NotImplementedError  # TODO 3.4.1, 3.4.3


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5000)
    app.run(host="127.0.0.1", port=ap.parse_args().port, threaded=True)
