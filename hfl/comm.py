"""통신 + 통신 기록 — 담당 B(윤효연), WBS 3.3

서버·runner 의 모든 HTTP 요청은 call() 로 보냄. 요청 1건 = comm.jsonl 1줄 (필드는 docs/log_format.md).
"""
import json
import time

import numpy as np
import requests

from hfl.common import _to_builtin, append_jsonl

READY_INTERVAL_SEC = 0.5  # wait_ready 재시도 간격 (tries=60 이면 최대 약 30초)


def to_wire(w):
    """numpy 배열 → JSON 숫자 리스트"""
    return np.asarray(w, dtype=np.float64).tolist()


def from_wire(lst):
    """JSON 숫자 리스트 → numpy float64 배열"""
    return np.asarray(lst, dtype=np.float64)


def call(method, base_url, path, src, dst, log_path, exp_id, round_no, version, body=None, timeout=30, kind="measured"):
    """requests 로 요청 → 지연(ms)·성공·상태 코드·요청/응답 바이트·kind 를 log_path 에 1줄 기록
    → requests.Response, 연결 실패면 None
    kind: "config"(시작 설정) / "measured"(실제) / "injected"(일부러 넣은 시험 요청)
    """
    # 본문을 여기서 한 번만 글자로 바꿔서 보냄 → 보낸 크기(req_bytes)를 정확히 잴 수 있음
    data = None if body is None else json.dumps(body, default=_to_builtin).encode("utf-8")
    headers = {"Content-Type": "application/json"} if data is not None else {}

    resp, error = None, None
    t0 = time.perf_counter()
    try:
        resp = requests.request(method, base_url + path, data=data, headers=headers, timeout=timeout)
    except requests.RequestException as e:  # 연결 거부, 시간 초과 등 — 응답 자체가 없음
        error = type(e).__name__
    latency_ms = (time.perf_counter() - t0) * 1000

    append_jsonl(log_path, {
        "exp": exp_id,
        "round": round_no,
        "model_version": version,
        "src": src,
        "dst": dst,
        "api": f"{method} {path}",
        "latency_ms": round(latency_ms, 3),
        "ok": resp is not None and resp.status_code == 200,
        "status": resp.status_code if resp is not None else None,
        "error": error,
        "req_bytes": len(data) if data is not None else 0,
        "bytes": len(resp.content) if resp is not None else 0,
        "kind": kind,
    })
    return resp


def wait_ready(url, tries=60):
    """GET url/status 가 200 될 때까지 대기, 끝내 안 되면 RuntimeError
    서버가 뜨는지 확인하는 준비 단계라 comm.jsonl 에는 기록하지 않음 (아직 실험 전).
    """
    for _ in range(tries):
        try:
            if requests.get(url + "/status", timeout=1).status_code == 200:
                return
        except requests.RequestException:
            pass  # 아직 안 떴음 → 잠깐 쉬고 다시
        time.sleep(READY_INTERVAL_SEC)
    raise RuntimeError(f"서버가 응답하지 않음: {url} ({tries}번 시도)")
