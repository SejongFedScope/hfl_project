"""클라이언트 실행 프로그램 — 담당 B(윤효연), WBS 3.5

한 프로그램에서 클라 6개를 순서대로 학습·제출. 서버 3개가 떠 있어야 함.
실행: python -m runner.client_runner --method pref   (random, --inject)
"""
import argparse


def prepare(cfg, method, data, inject):
    """분할 → 배정 → 배정 검사 (위반 있으면 중단) → logs/<exp_id>/ 에 config.json, split.json, assignment.json
    exp_id = "exp_<method>_seed<seed>" (+ "_inject")
    → (exp_id, out_dir, split, assignment)
    """
    raise NotImplementedError  # TODO 3.5.1


def inject_faults(cfg, exp_id, comm_log, round_no, cid, edge, version, new_w, n):
    """지난 버전 모델 제출, 배정 안 된 엣지에 제출 → 둘 다 409 인지 확인 (kind "injected")"""
    raise NotImplementedError  # TODO 3.5.4


def run(method, inject):
    """서버 준비 대기 → /start → 라운드 반복:
    클라 순서대로 GET /model → train_local → evaluate → train.jsonl (update_norm 포함) → POST /client_update
    라운드 끝: 중앙 /status 로 버전 r+1 확인, train.jsonl 에 duration_ms
    """
    raise NotImplementedError  # TODO 3.5.2, 3.5.3


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", choices=["pref", "random"], default="pref")
    ap.add_argument("--inject", action="store_true", help="inject_round 에 거부돼야 할 요청 2건을 일부러 보냄")
    a = ap.parse_args()
    run(a.method, a.inject)
