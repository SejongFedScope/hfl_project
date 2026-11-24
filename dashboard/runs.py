"""화면에서 설정 바꿔 실험 실행 — 담당 C(김영헌)

'실험 실행' 탭이 보낸 값 → 검사 → logs/run-<시각>/run_config.json → scripts.run_all 을 그 설정으로 실행 (HFL_CONFIG).
명세 구조(클라 6·엣지 2·정원 3)와 서버 주소는 고정, 나머지(시드·라운드·학습 설정·초기 모델·데이터 분할·양측 선호·배정 방식·결함 주입)만 바꿈.
새 실험은 logs/run-<시각>/exp_… 에 쌓여 원래 실험 로그를 덮어쓰지 않음. 한 번에 하나만 실행 (서버 포트가 하나라서).
"""
import json
import math
import pathlib
import os
import signal
import subprocess
import sys
import threading
import time

from flask import Blueprint, current_app, jsonify, request

from hfl.assign import check_assignment, make_assignment
from hfl.common import BASE_DIR, load_config, write_json
from runner.client_runner import check_fault, make_exp_id

bp = Blueprint("runs", __name__)
SAMPLE_ROOT = BASE_DIR / "dashboard" / "sample_logs"  # 화면 개발용 시험 로그 (git 에 있음 → 여기에 실행 결과를 쓰면 안 됨)

CLIENTS = [f"C{i}" for i in range(1, 7)]  # 명세 고정
EDGES = ["E1", "E2"]
METHODS = ["pref", "random"]
INIT_MODELS = ["zeros", "normal"]  # hfl.model.init_weights
NUMBERS = {  # 이름: (화면 라벨, 최소, 최대, 형)
    "seed": ("시드", 0, 2**31 - 1, int),
    "rounds": ("라운드 수", 1, 100, int),
    "local_epochs": ("학습 횟수", 1, 20, int),
    "lr": ("학습률", 0.0001, 1.0, float),
    "batch_size": ("배치 크기", 1, 5000, int),
    "samples_per_client": ("클라당 이미지 수", 10, 5000, int),
    "inject_round": ("결함 주입 라운드", 1, 100, int),
}
FAULT_NUMBERS = {  # 지연·중단 주입 (설정 fault, 담당 B 심화 6.B)
    "round": ("지연·중단 라운드", 1, 100, int),
    "delay_sec": ("지연 시간(초)", 0.1, 30.0, float),
    "deadline_sec": ("엣지 대기 제한(초)", 0.1, 30.0, float),
}
MNIST_TRAIN_PER_DIGIT = [5923, 6742, 5958, 6131, 5842, 5421, 5918, 6265, 5851, 5949]  # MNIST 학습 6만 장의 숫자별 장수 (고정)
lock = threading.Lock()
job = {"proc": None, "tag": None, "dir": None, "exps": [], "log": None, "stopped": False, "marked": False, "rounds": 0}


def defaults():
    """화면 처음 값 = configs/default.json"""
    c = load_config()
    return {**{k: c[k] for k in NUMBERS}, "init_model": c.get("init_model", "zeros"), "client_digits": c["client_digits"], "client_prefs": c["client_prefs"],
            "edge_prefs": c["edge_prefs"], "methods": METHODS, "inject": False, "edge_capacity": c["edge_capacity"], "fault_on": False, "fault": c["fault"],
            "limits": {k: [lo, hi] for k, (_, lo, hi, _) in NUMBERS.items()}, "run_allowed": run_allowed()}


def run_allowed():
    """시험 로그 폴더를 보고 있으면 실행 금지 (--sample 이든 다른 방법이든)"""
    return pathlib.Path(current_app.config["LOG_ROOT"]).resolve() != SAMPLE_ROOT.resolve()


def _number(v, lo, hi, typ):
    """JSON 값이 범위 안 숫자면 그 값, 아니면 None (참·거짓, NaN·무한대, 정수 자리에 소수 거부)"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    if isinstance(v, int) and not lo <= v <= hi:  # 아주 큰 정수는 float 로 못 바꾸니 범위부터 거름
        return None
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if typ is int and v != int(v):
        return None
    return typ(v) if lo <= v <= hi else None


def _ranking(v, items):
    """items 전부를 한 번씩 담은 순위 목록이면 True (동점·빠짐·다른 값 없음)"""
    return isinstance(v, list) and len(v) == len(items) and all(isinstance(x, str) for x in v) and sorted(v) == sorted(items)


def min_deadline(cfg):
    """지연·중단 실험의 엣지 대기 제한 최솟값(초). 담당 B 엣지는 이 제한을 '모든 라운드'에 걸고, 라운드 첫 GET /model 부터 잼
    → 평소 라운드에도 클라 3명이 학습·제출하는 시간보다 짧으면 정상 클라가 빠져 실행이 멈춤 (409 deadline passed)
    ponytail: 실측(클라당 1,200장·epoch 1 → 라운드 6명 약 0.7초)에서 클라 1명 ≈ 0.11초 × 장수/1200 × epoch + 0.05초 로 어림, 여유 2배"""
    t = 0.11 * cfg["samples_per_client"] / 1200 * cfg["local_epochs"] + 0.05
    return max(1.0, round(2 * 3 * t, 1))


def fault_msg(e):
    """check_fault(담당 B) 오류 문구의 설정 키 이름 → 화면 라벨"""
    s = str(e)
    for k, v in (("fault.delay_sec, fault.deadline_sec", "지연 시간·대기 제한"), ("fault.delay_client", "지연 클라"),
                 ("drop_client", "중단 클라"), ("fault.round", "라운드"), ("fault: ", "")):
        s = s.replace(k, v)
    return s


def validate(body):
    """→ (설정 dict, 배정 방식 목록, 결함 주입 여부, 오류 목록 [{"field", "msg"}]). 화면에서 온 값이라 모두 다시 검사"""
    cfg, errors = dict(load_config()), []
    err = lambda field, msg: errors.append({"field": field, "msg": msg})
    if not isinstance(body, dict):
        err("", "요청 형식이 잘못됨 (JSON 객체여야 함)")
        return cfg, [], False, errors
    inject = body.get("inject") is True
    for k, (label, lo, hi, typ) in NUMBERS.items():
        if k == "inject_round" and not inject:
            continue  # 결함 주입을 끄면 주입 라운드는 안 씀
        v = _number(body.get(k), lo, hi, typ)
        if v is None:
            err(k, f"{label}: {lo}~{hi} 사이 {'정수' if typ is int else '숫자'}")
        else:
            cfg[k] = v
    if inject and "inject_round" not in [e["field"] for e in errors] and cfg["inject_round"] > cfg["rounds"]:
        err("inject_round", f"결함 주입 라운드: 1~{cfg['rounds']} (라운드 수 안)")

    if body.get("init_model") not in INIT_MODELS:
        err("init_model", "초기 모델: 전부 0 / 정규분포 중 하나")
    else:
        cfg["init_model"] = body["init_model"]

    digits = body.get("client_digits")
    if not isinstance(digits, dict) or sorted(map(str, digits)) != CLIENTS:
        err("client_digits", "데이터 분할: 클라 C1~C6 모두 필요")
    else:
        n = cfg["samples_per_client"] if "samples_per_client" not in [e["field"] for e in errors] else None
        ok_digits = {}
        for c in CLIENTS:
            ds = digits[c]
            if not isinstance(ds, list) or not ds or not all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 9 for d in ds) or len(set(ds)) != len(ds):
                err(f"client_digits.{c}", f"{c}: 숫자를 1개 이상 고르세요")
            elif n is not None and n % len(ds):
                err(f"client_digits.{c}", f"{c}: 클라당 {n}장을 숫자 {len(ds)}개로 똑같이 나눌 수 없음")
            else:
                ok_digits[c] = sorted(ds)
        if len(ok_digits) == len(CLIENTS):
            cfg["client_digits"] = ok_digits
            if n is not None:  # 같은 숫자를 가진 클라끼리 겹치지 않게 나누므로 그 숫자 이미지가 모자라면 안 됨
                for d in range(10):
                    owners = [c for c in CLIENTS if d in ok_digits[c]]
                    need = sum(n // len(ok_digits[c]) for c in owners)
                    if need > MNIST_TRAIN_PER_DIGIT[d]:
                        err("client_digits", f"숫자 {d}: {'·'.join(owners)} 에 {need}장이 필요한데 MNIST 에 {MNIST_TRAIN_PER_DIGIT[d]}장뿐 (클라당 이미지 수를 줄이거나 숫자를 나눠 가지게)")

    cp, ep = body.get("client_prefs"), body.get("edge_prefs")
    if not isinstance(cp, dict) or sorted(map(str, cp)) != CLIENTS or not all(_ranking(cp[c], EDGES) for c in CLIENTS):
        err("client_prefs", "클라 선호: 클라마다 E1·E2 순위 (동점 없이 둘 다)")
    else:
        cfg["client_prefs"] = {c: cp[c] for c in CLIENTS}
    if not isinstance(ep, dict) or sorted(map(str, ep)) != EDGES or not all(_ranking(ep[e], CLIENTS) for e in EDGES):
        err("edge_prefs", "엣지 선호: 엣지마다 C1~C6 순위 (동점 없이 모두)")
    else:
        cfg["edge_prefs"] = {e: ep[e] for e in EDGES}

    fault_on = body.get("fault_on") is True
    if fault_on:
        f, ok = body.get("fault"), True
        if not isinstance(f, dict):
            err("fault", "지연·중단 설정이 없음")
            ok = False
        else:
            fault = {}
            for k, (label, lo, hi, typ) in FAULT_NUMBERS.items():
                v = _number(f.get(k), lo, hi, typ)
                if v is None:
                    err(f"fault.{k}", f"{label}: {lo}~{hi} 사이 {'정수' if typ is int else '숫자'}")
                    ok = False
                fault[k] = v
            for k in ("delay_client", "drop_client"):
                v = f.get(k)
                if v is not None and v not in CLIENTS:
                    err(f"fault.{k}", f"{'지연' if k == 'delay_client' else '중단'} 클라: C1~C6 또는 없음")
                    ok = False
                fault[k] = v
        if ok:
            cfg["fault"] = fault
            try:
                check_fault(cfg)  # 라운드 범위, 같은 클라 둘 다 지정 등 (B 의 검사 그대로)
            except ValueError as e:
                err("fault.round" if "fault.round" in str(e) else "fault", f"지연·중단: {fault_msg(e)}")
            need = min_deadline(cfg)
            if "samples_per_client" not in [x["field"] for x in errors] and fault["deadline_sec"] < need:
                err("fault.deadline_sec", f"엣지 대기 제한: 지연·중단 실험은 모든 라운드에 대기 제한이 걸림. 이 학습량(클라당 {cfg['samples_per_client']}장 × "
                                          f"epoch {cfg['local_epochs']})이면 평소 라운드에도 엣지에 3명이 모이는 데 시간이 걸려 {need}초 이상 필요")

    methods = body.get("methods")
    if not isinstance(methods, list) or not methods or not all(isinstance(m, str) and m in METHODS for m in methods) or len(set(methods)) != len(methods):
        err("methods", "배정 방식: 선호·무작위 중 1개 이상")
        methods = []
    if fault_on and not [e for e in errors if e["field"].startswith(("fault", "client_prefs", "edge_prefs"))]:
        for m in [m for m in METHODS if m in (methods or [])]:
            try:
                check_fault(cfg, make_assignment(cfg, m))  # 엣지마다 제출할 클라가 남는지 (배정을 알아야 봄)
            except ValueError as e:
                err("fault", f"지연·중단 ({'선호' if m == 'pref' else '무작위'} 배정): {fault_msg(e)}")
    cfg["fault_on"] = fault_on
    return cfg, [m for m in METHODS if m in methods], inject, errors


def preview(cfg):
    """두 배정 방식의 결과 미리보기 (학습 없이 배정만): 엣지별 클라·숫자, 평균 선호 순위"""
    out = {}
    for m in METHODS:
        a = make_assignment(cfg, m)
        chk = check_assignment(a, cfg)
        per_digit = {c: cfg["samples_per_client"] // len(cfg["client_digits"][c]) for c in CLIENTS}
        out[m] = {
            "assignment": a,
            "mean_pref_rank": chk["mean_pref_rank"],
            "violations": len(chk["unassigned"]) + len(chk["duplicated"]) + len(chk["capacity_violation"]),
            "edge_digits": {e: [sum(per_digit[c] for c in cs if d in cfg["client_digits"][c]) for d in range(10)] for e, cs in a.items()},
        }
        if cfg.get("fault_on"):  # 지연·중단 라운드에 엣지마다 확실히 집계에 들어가는 클라 + 늦게 내는 클라
            f = cfg["fault"]  # 지연 클라는 다른 클라를 다 처리한 뒤 제출 → 엣지 대기 제한(첫 GET 부터)에 걸리면 빠짐: 미리 장담 못 함
            out[m]["fault_edges"] = {e: {"sure": [c for c in cs if c not in (f["drop_client"], f["delay_client"])],
                                         "late": [c for c in cs if c == f["delay_client"]]} for e, cs in a.items()}

    return out


def _mark_ended(reason):
    """중지·실패한 실험 폴더에 ended.json → 화면이 '실행 중'으로 착각해 계속 다시 받지 않게 (app.py bundle 의 ended)"""
    if job["marked"] or job["dir"] is None:
        return
    job["marked"] = True
    for exp in job["exps"]:
        d = job["dir"].parent / exp
        if d.is_dir() and done_rounds(d) < job["rounds"]:  # 다 끝난 실험(2개 중 첫 번째 등)은 표시 안 함
            write_json(d / "ended.json", {"reason": reason, "tag": job["tag"]})


def done_rounds(d):
    """실험 폴더에서 중앙 집계까지 끝난 라운드 수"""
    path = d / "train.jsonl"
    if not path.exists():
        return 0
    done = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            x = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(x, dict) and x.get("target") == "global":
            done = max(done, x.get("round", 0))
    return done


def is_live(exp):
    """지금 이 대시보드가 돌리고 있는 실험인가"""
    return job["proc"] is not None and job["proc"].poll() is None and exp in job["exps"]


def _body():
    """요청 JSON (깨졌거나 너무 깊게 중첩되면 None → 검사에서 400)"""
    try:
        return request.get_json(silent=True)
    except RecursionError:
        return None


def _status():
    p = job["proc"]
    code = None if p is None else p.poll()
    if code not in (None, 0):
        _mark_ended("stopped" if job["stopped"] else "failed")
    tail = []
    if job["log"] and job["log"].exists():
        tail = job["log"].read_text(encoding="utf-8", errors="replace").splitlines()[-12:]
    return {"running": p is not None and code is None, "tag": job["tag"], "exps": job["exps"], "returncode": code,
            "stopped": job["stopped"], "log_tail": tail}


def _kill_tree(p):
    """run_all 과 그 밑의 서버 3개까지 끔 (run_all 만 끄면 서버가 포트를 잡은 채 남음)"""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
    else:
        os.killpg(p.pid, signal.SIGTERM)  # start_new_session=True 로 띄워서 프로세스 그룹 = run_all
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass  # 상태 조회 때 다시 확인


@bp.before_request
def same_origin_only():
    """다른 사이트가 사용자 브라우저로 실행·중지를 보내지 못하게: 주소는 이 PC(127.0.0.1·localhost)만, POST 는 JSON 만
    (JSON 요청은 브라우저가 다른 사이트에서 보낼 때 사전 확인(CORS preflight)을 거쳐 막힘)"""
    if request.host.rsplit(":", 1)[0] not in ("127.0.0.1", "localhost"):
        return jsonify(errors=[{"field": "", "msg": "이 PC 주소(127.0.0.1)로만 쓸 수 있음"}]), 403
    if request.method == "POST" and not request.is_json:
        return jsonify(errors=[{"field": "", "msg": "JSON 요청만 받음"}]), 415


@bp.get("/api/run/defaults")
def run_defaults():
    return jsonify(defaults())


@bp.post("/api/run/preview")
def run_preview():
    cfg, _, _, errors = validate(_body())
    if errors:
        return jsonify(errors=errors), 400
    return jsonify(errors=[], preview=preview(cfg))


@bp.get("/api/run/status")
def run_status():
    with lock:
        return jsonify(_status())


@bp.post("/api/run")
def run_start():
    """→ 202 {"tag", "exps"} / 400 {"errors"} / 409 실행 중·시험 로그 모드"""
    if not run_allowed():
        return jsonify(errors=[{"field": "", "msg": "시험 로그 모드(--sample)에서는 실행하지 않음 (시험 로그를 덮어쓰지 않게)"}]), 409
    cfg, methods, inject, errors = validate(_body())
    if errors:
        return jsonify(errors=errors), 400
    with lock:
        if _status()["running"]:
            return jsonify(errors=[{"field": "", "msg": f"이미 실행 중: {job['tag']}"}]), 409
        base = time.strftime("run-%Y%m%d-%H%M%S")  # '_' 없음 (화면이 실험 이름의 '_' 로 배정 방식을 읽음), 연도 포함 → 이름순 = 시간순
        tag, k = base, 1
        while (current_app.config["LOG_ROOT"] / tag).exists():  # 같은 초에 다시 누름 (앞 실행이 바로 실패한 경우)
            k += 1
            tag = f"{base}-{k}"
        out = current_app.config["LOG_ROOT"] / tag
        out.mkdir(parents=True)
        cfg["log_dir"] = str(out)  # 절대 경로 → BASE_DIR / 절대 경로 = 그대로
        write_json(out / "run_config.json", cfg)  # config.json 이 아님 → 이 폴더 자체는 실험 목록에 안 나옴
        fault = cfg["fault_on"]
        cmd = [sys.executable, "-m", "scripts.run_all", "--methods", ",".join(methods)] + (["--inject"] if inject else []) + (["--fault"] if fault else [])
        log = out / "run.log"
        env = {**os.environ, "HFL_CONFIG": str(out / "run_config.json"), "PYTHONIOENCODING": "utf-8",
               "PYTHONUNBUFFERED": "1"}  # 출력을 바로 파일에 → 실행 기록 칸에 진행이 보이고, 중지해도 안 사라짐
        with open(log, "w", encoding="utf-8") as f:  # 자식 프로세스가 핸들을 물려받음
            proc = subprocess.Popen(cmd, cwd=BASE_DIR, env=env, stdout=f, stderr=subprocess.STDOUT,
                                    start_new_session=os.name != "nt")  # 셸 안 거침, 인자는 검사한 값만
        job.update(proc=proc, tag=tag, dir=out, log=log, stopped=False, marked=False, rounds=cfg["rounds"],
                   exps=[f"{tag}/{make_exp_id(cfg, m, inject, fault)}" for m in methods])
        return jsonify(tag=tag, exps=job["exps"]), 202


@bp.post("/api/run/stop")
def run_stop():
    """실행 중이면 끔 → 200 {status}. 끈 실험은 거기까지의 로그만 남음 (화면은 '끝난 라운드'까지 표시)"""
    with lock:
        if not _status()["running"]:
            return jsonify(errors=[{"field": "", "msg": "실행 중인 실험 없음"}]), 409
        _kill_tree(job["proc"])
        job["stopped"] = job["proc"].poll() != 0  # 끄는 사이에 정상으로 끝났으면 '중지'가 아님
        return jsonify(_status())
