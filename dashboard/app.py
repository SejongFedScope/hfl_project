"""모니터링 화면 서버 — 담당 C(김영헌), WBS 4.2

logs/ 의 실험 폴더를 읽어 화면에 JSON 으로 줌.
실행: python -m dashboard.app → http://127.0.0.1:5050
      python -m dashboard.app --sample → 실제 로그 대신 dashboard/sample_logs/ (화면 개발용)
"""
import argparse
import json

from flask import Flask, abort, jsonify, render_template

from hfl.common import BASE_DIR, load_config, read_json

SAMPLE_ROOT = BASE_DIR / "dashboard" / "sample_logs"

app = Flask(__name__)
app.config["LOG_ROOT"] = BASE_DIR / load_config()["log_dir"]  # --sample 이면 SAMPLE_ROOT 로 바뀜


def exp_names():
    """LOG_ROOT 아래에서 config.json 이 있는 폴더 이름 = 실험 ID"""
    root = app.config["LOG_ROOT"]
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "config.json").exists())


def read_jsonl(path):
    """JSONL → dict 리스트. 파일이 없으면 빈 리스트 (실행 도중 멈춘 실험)"""
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/experiments")
def experiments():
    """→ 실험 ID 목록"""
    return jsonify(exp_names())


@app.get("/api/<exp>/bundle")
def bundle(exp):
    """→ {"config", "split" (인덱스 제외), "assignment", "train", "comm"}
    목록에 없는 exp 는 404 (로그 폴더 밖 경로 차단)
    """
    if exp not in exp_names():
        abort(404)
    d = app.config["LOG_ROOT"] / exp
    split = read_json(d / "split.json")
    for c in split["clients"].values():
        c.pop("indices", None)  # 클라당 1,200개, 화면에서 안 씀
    return jsonify(
        config=read_json(d / "config.json"),
        split=split,
        assignment=read_json(d / "assignment.json"),
        train=read_jsonl(d / "train.jsonl"),
        comm=read_jsonl(d / "comm.jsonl"),
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5050)
    ap.add_argument("--sample", action="store_true", help="dashboard/sample_logs/ 의 시험 로그로 실행")
    a = ap.parse_args()
    if a.sample:
        app.config["LOG_ROOT"] = SAMPLE_ROOT
    app.run(host="127.0.0.1", port=a.port)
