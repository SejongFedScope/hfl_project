"""모니터링 화면 서버 — 담당 C(김영헌), WBS 4.2

logs/ 의 실험 폴더를 읽어 화면에 JSON 으로 줌.
실행: python -m dashboard.app → http://127.0.0.1:5050  ('실험 실행' 탭에서 설정 바꿔 실험 실행: dashboard/runs.py)
      python -m dashboard.app --sample → 실제 로그 대신 dashboard/sample_logs/ (화면 개발용)
"""
import argparse
import json

from flask import Flask, abort, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from dashboard.runs import SAMPLE_ROOT, done_rounds, is_live
from dashboard.runs import bp as runs_bp
from hfl.common import BASE_DIR, load_config, read_json


app = Flask(__name__)
app.config["LOG_ROOT"] = BASE_DIR / load_config()["log_dir"]  # --sample 이면 SAMPLE_ROOT 로 바뀜
app.register_blueprint(runs_bp)  # '실험 실행' 탭 API (dashboard/runs.py)


def exp_names():
    """LOG_ROOT 아래에서 설정·분할·배정 파일이 다 있는 폴더 이름 = 실험 ID
    (runner 가 시작할 때 세 파일을 같이 씀 → 하나라도 없으면 깨진 폴더라 뺌)
    화면에서 돌린 실험은 run-<시각>/exp_… → ID 'run-<시각>/exp_…' (기본 실험 뒤, 최근 것이 아래)"""
    root = app.config["LOG_ROOT"]
    if not root.exists():
        return []
    need = ("config.json", "split.json", "assignment.json")
    is_exp = lambda p: all((p / f).exists() for f in need)
    base = sorted(p.name for p in root.iterdir() if is_exp(p))
    runs = sorted((r.name, p.name) for r in root.glob("run-*") if r.is_dir() for p in r.iterdir() if is_exp(p))  # (실행, 실험) 순 → 같은 초의 '-2' 도 뒤로
    return base + [f"{r}/{p}" for r, p in runs]


def read_jsonl(path):
    """JSONL → dict 리스트. 파일이 없으면 빈 리스트 (실행 도중 멈춘 실험)
    쓰다가 끊긴 줄(프로세스가 죽은 경우)은 건너뜀"""
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 빈 줄·잘린 줄
    return rows


# 화면 구성 (영역 4개 × 패널 2개). templates/index.html 이 이 목록으로 영역·패널 HTML 을 만듦
REGIONS = [
    {"no": 1, "title": "계층 구조·배정", "question": "누가 어느 엣지에 붙었고, 배정이 잘 됐나", "panels": [
        {"id": "p_tree", "title": "계층 트리", "tag": "구조", "desc": "중앙–엣지–클라 연결, 엣지 색, 참여·실패 상태"},
        {"id": "p_assign", "title": "선호·배정 행렬", "tag": "배정", "desc": "클라 × 엣지 양측 선호 순위와 실제 배정, 위반 수"}]},
    {"no": 2, "title": "통신 상태", "question": "어느 요청이 느리거나 실패했나", "panels": [
        {"id": "p_comm_heatmap", "title": "통신 히트맵", "tag": "링크", "desc": "링크 × 라운드 지연, 빨강 = 실패·409"},
        {"id": "p_requests", "title": "요청 목록", "tag": "요청", "desc": "선택 라운드의 요청·상태 코드·모델 버전"}]},
    {"no": 3, "title": "데이터·클라 학습", "question": "숫자 분포 차이가 클라 학습으로 어떻게 이어지나", "panels": [
        {"id": "p_data", "title": "데이터 분포", "tag": "데이터", "desc": "클라 × 숫자 표본 수, 엣지별 합, 숫자 쏠림"},
        {"id": "p_clients", "title": "클라 로그", "tag": "클라", "desc": "클라별 학습 손실·정확도·지연 추이, 실패 수"}]},
    {"no": 4, "title": "공동 모델·실험 비교", "question": "공동 모델 성능과 실험 조건(배정·결함·지연) 차이", "panels": [
        {"id": "p_trend", "title": "학습 추세", "tag": "공동 모델", "desc": "라운드별 정확도·손실, 라운드 × 숫자 정확도"},
        {"id": "p_compare", "title": "실험 비교", "tag": "비교", "desc": "이 실험 vs 비교 실험: 정확도·선호 충족도·엣지 구성 (결함·지연 실험은 같은 배정의 기본 실험과)"}]},
]
ANALYSIS = [  # '심층 분석' 탭: 큰 패널 4개 (2×2)
    {"id": "p_local", "title": "클라 모델 vs 공동 모델", "tag": "연합 효과", "desc": "숫자별 정확도: 클라가 자기 데이터로 학습한 직후 모델과 공동 모델"},
    {"id": "p_traffic", "title": "트래픽 흐름", "tag": "통신량", "desc": "클라 → 엣지 → 중앙으로 오간 바이트 (선택 라운드까지 누적, 요청+응답)"},
    {"id": "p_rank", "title": "클라 정확도 순위 변화", "tag": "순위", "desc": "라운드마다 클라 모델 정확도 순위 (1 = 가장 높음)"},
    {"id": "p_sim", "title": "클라 유사도", "tag": "군집", "desc": "숫자별 정확도가 얼마나 비슷한가 (코사인 유사도, 1 = 같음)"},
]
ALGO = [  # '알고리즘 비교' 탭 (담당 A 심화 결과 logs/algo_compare 를 읽기만 함): 큰 패널 4개
    {"id": "p_algo_curve", "title": "공동 모델 정확도", "tag": "라운드", "desc": "단일 중앙 집계에서 알고리즘별 라운드마다 공동 정확도"},
    {"id": "p_algo_table", "title": "최종 지표", "tag": "비교", "desc": "마지막 라운드 기준, 시드 평균 (최소~최대). 열마다 가장 좋은 값 굵게"},
    {"id": "p_algo_tradeoff", "title": "변화량과 정확도", "tag": "trade-off", "desc": "클라 모델이 공동 모델에서 벗어난 크기(평균 변화량)와 최종 정확도, 점 = 알고리즘 × epoch"},
    {"id": "p_algo_digits", "title": "숫자별 정확도", "tag": "숫자", "desc": "마지막 라운드 공동 모델의 숫자별 정확도 (선택한 epoch·시드)"},
]
SCRIPTS = ["state.js", "kpi.js", "structure.js", "comm.js", "data.js", "global.js", "analysis.js", "run.js", "algo.js"]  # state.js 가 먼저 (나머지가 subscribe 함)


@app.errorhandler(HTTPException)
def api_error(e):
    """/api 아래 오류는 HTML 대신 {"message"} JSON (수업 5장: 에러 본문 통일, 상태 코드 그대로). 화면 주소는 Flask 기본 페이지"""
    if not request.path.startswith("/api/"):
        return e
    msg = {404: "없는 주소이거나 목록에 없는 실험", 405: "이 주소가 받지 않는 메소드"}.get(e.code, e.description)
    return jsonify(message=msg), e.code


@app.errorhandler(Exception)
def api_crash(e):
    """예상 못 한 오류: 쓰는 쪽에는 짧게만, 자세한 내용은 서버 출력에 (수업 5장: 500 에 내부 경로·구조를 싣지 않음)"""
    app.logger.exception("처리 중 오류: %s", request.path)
    if request.path.startswith("/api/"):
        return jsonify(message="서버 내부 오류 (대시보드 서버 출력 확인)"), 500
    return "서버 내부 오류", 500


def log_source():
    """머리말에 보여 줄 로그 출처 (시험 로그인지 실제 로그인지 헷갈리지 않게)"""
    root = app.config["LOG_ROOT"]
    if root == SAMPLE_ROOT:
        return "시험 로그 (dashboard/sample_logs)"
    try:
        return f"실제 로그 ({root.relative_to(BASE_DIR).as_posix()})"
    except ValueError:
        return f"실제 로그 ({root})"


@app.get("/")
def index():
    return render_template("index.html", regions=REGIONS, analysis=ANALYSIS, algo=ALGO, scripts=SCRIPTS, log_source=log_source())


@app.get("/api/algo")
def algo():
    """알고리즘 비교 결과 (scripts/compare_algorithms.py 가 만든 logs/algo_compare/summary.json)
    + 실험마다 마지막 라운드 공동 모델의 숫자별 정확도. 없으면 404 + 만드는 명령"""
    root = app.config["LOG_ROOT"] / "algo_compare"
    if not (root / "summary.json").exists():
        return jsonify(message="알고리즘 비교 결과가 없음",
                       hint="python -m scripts.compare_algorithms --seeds 42 7 123 --epochs 1 5 10 --q 1 5 --q-epochs 1"), 404
    try:
        summary = read_json(root / "summary.json")
        results = summary["results"]
    except (ValueError, KeyError, TypeError):  # 쓰는 도중이거나 깨진 파일
        return jsonify(message="알고리즘 비교 결과 파일을 읽지 못함 (만드는 중이면 끝난 뒤 다시)",
                       hint="python -m scripts.compare_algorithms … 를 다시 실행"), 500
    for x in results:
        name = str(x.get("exp_id", ""))
        ok = name.startswith("alg_") and "/" not in name and "\\" not in name and ".." not in name  # summary 안 이름으로 폴더 밖을 읽지 않게
        last = [r for r in read_jsonl(root / name / "train.jsonl") if r.get("target") == "global"] if ok else []
        x["final_by_digit"] = last[-1]["acc_by_digit"] if last else None
    return jsonify(summary)


@app.get("/api/experiments")
def experiments():
    """→ 실험 ID 목록"""
    return jsonify(exp_names())


@app.get("/api/<path:exp>/bundle")
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
        ended=ended_of(exp, d),
    )


def ended_of(exp, d):
    """화면에서 돌린 실험이 중간에 멈췄으면 {"reason"} (중지·실패·대시보드가 꺼져서 끊김), 아니면 None
    → 화면이 '실행 중'으로 착각해 계속 다시 받지 않게"""
    if (d / "ended.json").exists():
        return read_json(d / "ended.json")
    if exp.startswith("run-") and not is_live(exp) and done_rounds(d) < read_json(d / "config.json")["rounds"]:
        return {"reason": "interrupted"}
    return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5050)
    ap.add_argument("--sample", action="store_true", help="dashboard/sample_logs/ 의 시험 로그로 실행")
    a = ap.parse_args()
    if a.sample:
        app.config["LOG_ROOT"] = SAMPLE_ROOT  # 실험 실행 탭은 미리보기만 (runs.run_allowed)
    app.run(host="127.0.0.1", port=a.port)
