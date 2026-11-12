"""공통 함수 — 담당 B(윤효연), WBS 3.1

설정 파일 읽기, 로그 파일(JSON / JSONL) 쓰기. 모든 파일이 가져다 씀.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # 프로젝트 루트


def load_config():
    """configs/default.json 을 dict 로 반환. 환경변수 HFL_CONFIG 가 있으면 그 파일."""
    raise NotImplementedError  # TODO 3.1


def exp_dir(cfg, exp_id):
    """logs/<exp_id>/ 폴더 Path 반환 (없으면 만듦)."""
    raise NotImplementedError  # TODO 3.1


def write_json(path, obj):
    raise NotImplementedError  # TODO 3.1


def read_json(path):
    raise NotImplementedError  # TODO 3.1


def append_jsonl(path, record):
    """dict 하나를 JSON 한 줄로 파일 끝에 추가."""
    raise NotImplementedError  # TODO 3.1
