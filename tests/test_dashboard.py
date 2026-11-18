"""C 검사 — 담당 C(김영헌), 로그 API 엣지 케이스. 실행: python -m tests.test_dashboard"""
import shutil
import tempfile
from pathlib import Path

from dashboard.app import REGIONS, SAMPLE_ROOT, app


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

        html = c.get("/").get_data(as_text=True)  # Jinja 템플릿: 패널 8개·스크립트 6개가 목록대로 나오고 로그 출처가 보임
        assert all(f'id="{p["id"]}"' in html for r in REGIONS for p in r["panels"]) and html.count('<script src="/static/') == 7
        assert "실제 로그" in html and "{%" not in html and "{{" not in html

        app.config["LOG_ROOT"] = root / "없는_폴더"
        assert c.get("/api/experiments").get_json() == []
    finally:
        shutil.rmtree(root)


def test_make_report():
    """시험 로그로 보고서 생성: 표시 사이만 바뀌고 사람이 쓴 글은 그대로, 시험 요청은 성공률에서 빠짐"""
    from scripts import make_report
    root = Path(tempfile.mkdtemp())
    try:
        shutil.copytree(SAMPLE_ROOT / "exp_pref_seed42", root / "logs" / "exp_pref_seed42")
        shutil.copytree(SAMPLE_ROOT / "exp_random_seed42_inject", root / "logs" / "exp_random_seed42_inject")
        shutil.copytree(SAMPLE_ROOT / "exp_random_seed42_inject", root / "logs" / "exp_random_seed42")  # 결함 주입 없는 무작위 실험으로 씀
        cfg_path = root / "logs" / "exp_random_seed42" / "config.json"
        cfg_path.write_text(cfg_path.read_text(encoding="utf-8").replace('"inject": true', '"inject": false'), encoding="utf-8")
        report = root / "docs" / "report.md"
        report.parent.mkdir()
        report.write_text("손으로 쓴 머리말\n<!-- auto:conditions -->\n옛 표\n<!-- /auto:conditions -->\n손으로 쓴 해석\n"
                          + "".join(f"<!-- auto:{k} -->\n<!-- /auto:{k} -->\n" for k in ("preference", "edges", "performance", "comm")), encoding="utf-8")

        make_report.main(["--logs", str(root / "logs"), "--out", str(report)])
        text = report.read_text(encoding="utf-8")
        assert "손으로 쓴 머리말" in text and "손으로 쓴 해석" in text and "옛 표" not in text
        assert "| 시드 | 42 |" in text and "두 실험 학습 조건 동일 | 예" in text
        assert "엣지 간 숫자 분포 차이 (0 = 같음, 1 = 완전히 다름): 선호 **0.67**, 무작위 **0.00**" in text
        assert "| 선호 + 결함 주입 |" in text and "2 (409 2)" in text  # 시험 요청은 따로 셈
        assert (root / "docs" / "img" / "report_acc.svg").exists() and (root / "docs" / "img" / "report_edge_digits.svg").exists()

        report.write_text("표시 없음", encoding="utf-8")  # 표시가 없으면 덮어쓰지 않고 멈춤
        try:
            make_report.main(["--logs", str(root / "logs"), "--out", str(report)])
            raise AssertionError("표시가 없는데 멈추지 않음")
        except SystemExit:
            assert report.read_text(encoding="utf-8") == "표시 없음"
    finally:
        shutil.rmtree(root)


if __name__ == "__main__":
    for t in (test_edge_cases, test_make_report):
        t()
        print("PASS", t.__name__)
