"""공통 함수 — 담당 B(윤효연), WBS 3.1

설정 파일 읽기, 로그 파일(JSON / JSONL) 쓰기. 모든 파일이 가져다 씀.
"""
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # 프로젝트 루트
DEFAULT_CONFIG = BASE_DIR / "configs" / "default.json"


def load_config():
    """configs/default.json 을 dict 로 반환. 환경변수 HFL_CONFIG 가 있으면 그 파일."""
    return read_json(os.environ.get("HFL_CONFIG") or DEFAULT_CONFIG)


def exp_dir(cfg, exp_id):
    """logs/<exp_id>/ 폴더 Path 반환 (없으면 만듦).
    cfg["log_dir"] 가 상대 경로면 실행 위치와 상관없이 프로젝트 루트 기준.
    """
    d = BASE_DIR / cfg["log_dir"] / exp_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _to_builtin(o):
    """json 이 모르는 numpy 값(int64, float32, 배열)을 파이썬 기본 값으로 바꿈."""
    if hasattr(o, "tolist"):
        return o.tolist()
    raise TypeError(f"JSON 으로 바꿀 수 없는 값: {type(o).__name__}")


def write_json(path, obj):
    """obj 를 JSON 파일로 저장 (덮어씀). 변환에 실패하면 파일을 건드리지 않음."""
    text = json.dumps(obj, ensure_ascii=False, indent=2, default=_to_builtin)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read_json(path):
    """JSON 파일 → dict / list"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def append_jsonl(path, record):
    """dict 하나를 JSON 한 줄로 파일 끝에 추가."""
    line = json.dumps(record, ensure_ascii=False, default=_to_builtin) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
