"""C 검사 — 담당 C(김영헌), 로그 API 엣지 케이스. 실행: python -m tests.test_dashboard"""
import shutil
import tempfile
from pathlib import Path

from dashboard.app import SAMPLE_ROOT, app


def _logs_with_edge_cases():
    root = Path(tempfile.mkdtemp())
    shutil.copytree(SAMPLE_ROOT / "exp_pref_seed42", root / "exp_ok")
    (root / "exp_broken").mkdir()  # 설정만 있고 분할·배정이 없는 깨진 폴더
    shutil.copy(SAMPLE_ROOT / "exp_pref_seed42" / "config.json", root / "exp_broken" / "config.json")
    shutil.copytree(SAMPLE_ROOT / "exp_pref_seed42", root / "exp_cut")
    with open(root / "exp_cut" / "train.jsonl", "a", encoding="utf-8") as f:
        f.write('{"round": 9, "tar')  # 프로세스가 죽어서 잘린 마지막 줄
    shutil.copytree(SAMPLE_ROOT / "exp_pref_seed42", root / "exp_empty")
    (root / "exp_empty" / "train.jsonl").unlink()  # 시작 직후 죽어서 기록 없음
    (root / "exp_empty" / "comm.jsonl").unlink()
    return root


def test_edge_cases():
    root = _logs_with_edge_cases()
    app.config["LOG_ROOT"] = root
    c = app.test_client()
    try:
        assert c.get("/api/experiments").get_json() == ["exp_cut", "exp_empty", "exp_ok"]  # 깨진 폴더는 목록에서 빠짐
        assert c.get("/api/exp_broken/bundle").status_code == 404
        for bad in ("nope", "..", "..%2F..%2Fconfigs", "exp_ok%2F.."):  # 로그 폴더 밖으로 못 나감
            assert c.get(f"/api/{bad}/bundle").status_code == 404, bad

        ok = c.get("/api/exp_ok/bundle").get_json()
        cut = c.get("/api/exp_cut/bundle").get_json()
        assert len(cut["train"]) == len(ok["train"])  # 잘린 줄만 건너뜀
        assert all("indices" not in v for v in ok["split"]["clients"].values())  # 화면에 안 쓰는 인덱스는 뺌

        empty = c.get("/api/exp_empty/bundle").get_json()
        assert empty["train"] == [] and empty["comm"] == [] and empty["assignment"]["assignment"]

        app.config["LOG_ROOT"] = root / "없는_폴더"
        assert c.get("/api/experiments").get_json() == []
    finally:
        shutil.rmtree(root)


if __name__ == "__main__":
    test_edge_cases()
    print("PASS test_edge_cases")
