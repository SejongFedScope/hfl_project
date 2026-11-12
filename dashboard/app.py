"""모니터링 화면 서버 — 담당 C(김영헌), WBS 4.2

logs/ (개발 중엔 dashboard/sample_logs/) 의 실험 폴더를 읽어 화면에 JSON 으로 줌.
실행: python -m dashboard.app → http://127.0.0.1:5050
"""
import argparse

from flask import Flask, render_template

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/experiments")
def experiments():
    """→ 실험 ID 목록"""
    raise NotImplementedError  # TODO 4.2


@app.get("/api/<exp>/bundle")
def bundle(exp):
    """→ {"config", "split" (인덱스 제외), "assignment", "train", "comm"}
    목록에 없는 exp 는 404 (로그 폴더 밖 경로 차단)
    """
    raise NotImplementedError  # TODO 4.2


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5050)
    app.run(host="127.0.0.1", port=ap.parse_args().port)
