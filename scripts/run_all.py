"""실험 일괄 실행 — 담당 B(윤효연), WBS 3.6

서버 3개(중앙, 엣지 E1·E2)를 띄우고 runner 로 실험 3개 실행 → logs/
  pref / random / pref + 결함 주입
끝나면 서버 종료. 실행: python -m scripts.run_all
      python -m scripts.run_all --methods pref,random [--inject] → 고른 배정 방식만 (화면 '실험 실행' 탭이 씀)
      python -m scripts.run_all --fault → 지연·중단 주입 실험 (심화 6.B, 기본 pref. --methods 와 같이 쓸 수 있음)
서버 출력(요청 로그·오류)은 logs/servers.log
"""
import argparse
import socket
import subprocess
import sys
from urllib.parse import urlsplit

from hfl.comm import wait_ready
from hfl.common import BASE_DIR, load_config
from runner.client_runner import run

EXPERIMENTS = [("pref", False), ("random", False), ("pref", True)]
START_TRIES = 600  # 0.5초 × 600 = 최대 5분 (첫 실행이면 중앙이 MNIST 를 받느라 오래 걸림)


def _in_use(url):
    """그 주소에 이미 뭔가 떠 있으면 True (지난 실행에서 안 꺼진 서버, 맥 AirPlay 5000번 등)"""
    u = urlsplit(url)
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex((u.hostname, u.port)) == 0


def _wait(proc, url):
    """서버가 /status 200 을 줄 때까지 대기. 그 사이 프로세스가 죽으면 바로 중단"""
    for _ in range(START_TRIES):
        if proc.poll() is not None:
            raise RuntimeError(f"서버가 시작하다 꺼짐: {url} (logs/servers.log 확인)")
        try:
            wait_ready(url, tries=1)
            return
        except RuntimeError:
            pass
    raise RuntimeError(f"서버가 응답하지 않음: {url}")


def main(experiments=EXPERIMENTS):
    cfg = load_config()
    servers = [(["servers.central"], cfg["central_url"])]
    servers += [(["servers.edge", "--id", e], url) for e, url in cfg["edge_urls"].items()]

    busy = [url for _, url in servers if _in_use(url)]
    if busy:
        raise SystemExit(f"포트가 이미 사용 중: {busy}. 떠 있는 서버를 끄거나 configs 의 주소를 바꾸세요")

    log_root = BASE_DIR / cfg["log_dir"]
    log_root.mkdir(parents=True, exist_ok=True)
    procs = []
    with open(log_root / "servers.log", "w", encoding="utf-8") as out:
        try:
            for args, url in servers:
                procs.append(subprocess.Popen([sys.executable, "-m", *args], cwd=BASE_DIR, stdout=out, stderr=subprocess.STDOUT))
            for proc, (_, url) in zip(procs, servers):
                _wait(proc, url)
            print("서버 3개 준비 완료:", ", ".join(url for _, url in servers))

            done = [run(*x) for x in experiments]  # (배정 방식, 결함 주입[, 지연·중단 주입])
            print(f"완료 ({log_root}):", ", ".join(done))
        finally:
            for p in procs:  # 실험이 중간에 실패해도 서버는 꼭 끔
                p.terminate()
            for p in procs:
                p.wait()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", help="쉼표로 구분한 배정 방식 (pref,random). 생략하면 기본 실험 3개")
    ap.add_argument("--inject", action="store_true", help="--methods 와 함께: 결함 주입을 켜고 실행")
    ap.add_argument("--fault", action="store_true", help="지연·중단 주입 실험 (설정 fault). --methods 없으면 pref 하나")
    a = ap.parse_args()
    if a.fault and not a.methods:
        main([("pref", a.inject, True)])
    elif not a.methods:
        main()
    else:
        methods = a.methods.split(",")
        if not methods or any(m not in ("pref", "random") for m in methods):
            ap.error("--methods 는 pref, random 중에서 (예: pref,random)")
        main([(m, a.inject, a.fault) for m in methods])
