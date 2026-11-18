# hfl_project

[![검사](https://github.com/SejongFedScope/hfl_project/actions/workflows/check.yml/badge.svg)](https://github.com/SejongFedScope/hfl_project/actions/workflows/check.yml)  push 마다 단위 검사 → 실험 실행 → 보고서 → 필수 6항목 점검을 자동으로 돌림 (`.github/workflows/check.yml`)

계층적 연합학습 환경 + 학습·통신 모니터링 (웹기반시스템 Project 1)

중앙 서버 1 · 엣지 서버 2 · 가상 클라이언트 6, MNIST 숫자별 분할(non-IID), FedAvg 2단계 집계, 선호(matching)·무작위 배정 비교, 학습·배정·통신 로그, 4영역 모니터링 화면.

> 파일 맨 위 설명과 함수 docstring에 담당·할 일(WBS 번호)·입출력이 있음. WBS 번호·일정은 팀 Notion.

## 담당

| 역할 | 담당 | 파일 |
|---|---|---|
| A 학습·집계 | 이건 | `hfl/data_split.py` `hfl/model.py` `hfl/aggregate.py` `tests/test_learning.py` `docs/aggregation_check.md` `docs/third_party.md` |
| B 서버·배정 | 윤효연 | `configs/` `hfl/common.py` `hfl/assign.py` `hfl/comm.py` `servers/` `runner/` `scripts/run_all.py` `tests/test_server.py` `docs/api.md` `docs/log_format.md` `README.md` `requirements.txt` |
| C 모니터링 화면 | 김영헌 | `dashboard/` `scripts/make_report.py` `tests/test_dashboard.py` `tests/test_ui.py` `docs/usability_test.md` |
| 실험·검증 | 전원 | `docs/report.md`, 교차 검증 |

## 규칙

- 파일마다 주인 1명. 남의 파일 고칠 땐 주인에게 먼저 말하기.
- `docs/api.md`, `docs/log_format.md` 는 3명 합의 없이 변경 금지.
- 브랜치·PR 없이 `main` 에 바로 push.
  - push 전에 `git pull --rebase` 로 최신 `main` 받기.
  - 실행 안 되는 코드(import 오류 등)는 올리지 않기. 다른 사람이 받자마자 깨짐.

## 실행

Python 3.11 이상. **3.11·3.12 권장**: `numpy==1.26.4` 는 3.13 용 설치 파일이 없어서, 3.13 에서는 소스 빌드로 설치돼 오래 걸림 (macOS 는 Xcode Command Line Tools 필요).

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

가상환경을 켠 뒤에는 두 OS 모두 같은 명령:

```bash
python -m tests.test_learning      # 집계 손계산 · 분할 중복
python -m tests.test_server        # 배정 위반 · 409
python -m tests.test_dashboard     # 로그 API 엣지 케이스 · 보고서 생성
python -m tests.test_ui            # 화면 클릭·키보드 동작 (playwright 있을 때만, 없으면 SKIP)
python -m scripts.run_all          # 서버 3개 + 실험 3개 (pref, random, pref+결함 주입) → logs/
python -m scripts.make_report      # logs/ → docs/report.md 표 + docs/img/ 그래프
python -m tests.test_requirements  # 명세 필수 6항목 O/X (run_all 다음에)
python -m dashboard.app            # http://127.0.0.1:5050
python -m dashboard.app --sample   # 실제 로그 대신 dashboard/sample_logs/ 시험 로그로 화면 보기
```

- `run_all` 은 약 10초 (첫 실행은 MNIST 다운로드로 더 걸림). 서버 출력은 `logs/servers.log`
- 같은 실험을 다시 돌리면 그 실험 폴더의 로그를 지우고 새로 씀. 시드 고정이라 결과는 같음
- 포트(5003, 5001, 5002)가 이미 사용 중이면 시작하지 않음 → 떠 있는 서버를 끄거나 `configs/default.json` 주소 변경

서버를 따로 띄울 때 (터미널 4개, 각각 가상환경 켜고):

```bash
python -m servers.central --port 5003
python -m servers.edge --id E1 --port 5001
python -m servers.edge --id E2 --port 5002
python -m runner.client_runner --method pref        # random, 또는 --inject
```

- 주소는 `localhost` 말고 `127.0.0.1` (Windows 에서 localhost 는 요청마다 약 2초 지연)
- MNIST 는 첫 실행 때 `data/` 에 자동 다운로드
- 중앙 기본 포트가 5000 이 아닌 5003 인 이유: macOS 는 AirPlay 수신 기능이 5000번을 씀

## 폴더

```
hfl_project/
├─ configs/default.json         B   시드·분할·선호 순위·정원·서버 주소
├─ hfl/
│  ├─ data_split.py             A   MNIST 로드, 숫자별 중복 없는 분할
│  ├─ model.py                  A   모델, 로컬 학습, 평가(숫자별 정확도)
│  ├─ aggregate.py              A   weighted_average (엣지·중앙 공통)
│  ├─ common.py                 B   설정 읽기, JSON/JSONL 쓰기
│  ├─ assign.py                 B   선호(matching)·무작위 배정, 제약 검사
│  └─ comm.py                   B   HTTP 요청 + 통신 기록
├─ servers/central.py, edge.py  B   Flask REST 서버
├─ runner/client_runner.py      B   클라 6개 순차 학습·제출
├─ scripts/
│  ├─ run_all.py                B   서버 3개 띄우고 실험 일괄 실행
│  └─ make_report.py            C   logs → 비교 표·그래프
├─ dashboard/                   C
│  ├─ app.py                        로그 읽기 API
│  ├─ templates/index.html          상단 KPI + 4영역 격자
│  ├─ static/                       state.js(선택 상태) kpi.js structure.js comm.js data.js global.js style.css vendor/echarts.min.js
│  └─ sample_logs/                  손으로 만든 시험 로그
├─ tests/test_learning.py (A), test_server.py (B), test_dashboard.py · test_ui.py (C), test_requirements.py (공동, 필수 6항목)
└─ docs/
   ├─ api.md                    B   ★약속
   ├─ log_format.md             B   ★약속
   ├─ aggregation_check.md      A   손계산 예제
   ├─ third_party.md            A   공개 코드(FedProx) 사용 기록·수정 사항·원본 실행 기록
   ├─ usability_test.md         C
   └─ report.md                 공동
```
