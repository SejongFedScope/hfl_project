"""통신 + 통신 기록 — 담당 B(윤효연), WBS 3.3

서버·runner 의 모든 HTTP 요청은 call() 로 보냄. 요청 1건 = comm.jsonl 1줄 (필드는 docs/log_format.md).
"""


def to_wire(w):
    """numpy 배열 → JSON 숫자 리스트"""
    raise NotImplementedError  # TODO 3.3


def from_wire(lst):
    """JSON 숫자 리스트 → numpy float64 배열"""
    raise NotImplementedError  # TODO 3.3


def call(method, base_url, path, src, dst, log_path, exp_id, round_no, version, body=None, timeout=30, kind="measured"):
    """requests 로 요청 → 지연(ms)·성공·상태 코드·요청/응답 바이트·kind 를 log_path 에 1줄 기록
    → requests.Response, 연결 실패면 None
    kind: "config"(시작 설정) / "measured"(실제) / "injected"(일부러 넣은 시험 요청)
    """
    raise NotImplementedError  # TODO 3.3


def wait_ready(url, tries=60):
    """GET url/status 가 200 될 때까지 대기, 끝내 안 되면 RuntimeError"""
    raise NotImplementedError  # TODO 3.3
