"""엣지 서버 — 담당 B(윤효연), WBS 3.4.2

담당 클라 3명의 모델을 받아 1차 집계 → 중앙에 제출 → 버전 +1.
실행: python -m servers.edge --id E1 --port 5001. 요청·응답 형식은 docs/api.md.
"""
import argparse

from flask import Flask

app = Flask(__name__)


@app.post("/start")
def start():
    """{"exp_id", "clients"} → 담당 클라 저장, 버전 1"""
    raise NotImplementedError  # TODO 3.4.2


@app.get("/model")
def get_model():
    """이번 라운드 첫 요청이면 중앙 GET /model 로 받아 캐시 → {"round", "version", "weights"}
    409: 시작 전 / 502: 중앙 응답 없음
    """
    raise NotImplementedError  # TODO 3.4.2


@app.get("/status")
def status():
    """→ {"edge", "exp", "version", "clients", "received"}"""
    raise NotImplementedError  # TODO 3.4.2


@app.post("/client_update")
def client_update():
    """{"client_id", "version", "weights", "n_samples", "train_loss"}
    409: 배정 안 된 클라 / 버전 불일치
    담당 클라 다 모이면 weighted_average(클라 표본 수) → 중앙 POST /edge_update → train.jsonl (target 엣지 ID) → 버전 +1
    """
    raise NotImplementedError  # TODO 3.4.2, 3.4.3


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--port", type=int, required=True)
    a = ap.parse_args()
    app.config["EDGE_ID"] = a.id
    app.run(host="127.0.0.1", port=a.port, threaded=True)
