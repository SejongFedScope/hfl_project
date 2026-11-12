# hfl_project

계층적 연합학습 환경 + 학습·통신 모니터링 (웹기반시스템 Project 1)

중앙 서버 1 · 엣지 서버 2 · 가상 클라이언트 6, MNIST 숫자별 분할(non-IID), FedAvg 2단계 집계, 선호(matching)·무작위 배정 비교, 학습·배정·통신 로그, 4영역 모니터링 화면.

> 지금은 **뼈대 + 함수 틀**만 있음. 파일 맨 위 설명과 함수 docstring에 담당·할 일(WBS 번호)·입출력이 있고, 본문은 `NotImplementedError`. WBS 번호·일정은 팀 Notion.

## 담당

| 역할 | 담당 | 파일 |
|---|---|---|
| A 학습·집계 | 이건 | `hfl/data_split.py` `hfl/model.py` `hfl/aggregate.py` `tests/test_learning.py` `docs/aggregation_check.md` |
| B 서버·배정 | 윤효연 | `configs/` `hfl/common.py` `hfl/assign.py` `hfl/comm.py` `servers/` `runner/` `scripts/run_all.py` `tests/test_server.py` `docs/api.md` `docs/log_format.md` `README.md` `requirements.txt` |
| C 모니터링 화면 | 김영헌 | `dashboard/` `scripts/make_report.py` `docs/usability_test.md` |
| 실험·검증 | 전원 | `docs/report.md`, 교차 검증 |

## 규칙

- 파일마다 주인 1명. 남의 파일 고칠 땐 주인에게 먼저 말하기.
- `docs/api.md`, `docs/log_format.md` 는 3명 합의 없이 변경 금지.
- 브랜치·PR 없이 `main` 에 바로 push.
  - push 전에 `git pull --rebase` 로 최신 `main` 받기.
  - 실행 안 되는 코드(import 오류 등)는 올리지 않기. 다른 사람이 받자마자 깨짐.

## 실행 (구현 후)

Python 3.11 이상.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python -m tests.test_learning      # 집계 손계산 · 분할 중복
python -m tests.test_server        # 배정 위반 · 409
python -m scripts.run_all          # 서버 3개 + 실험 3개 (pref, random, pref+결함 주입) → logs/
python -m dashboard.app            # http://127.0.0.1:5050
```

서버를 따로 띄울 때 (터미널 4개):

```powershell
python -m servers.central --port 5000
python -m servers.edge --id E1 --port 5001
python -m servers.edge --id E2 --port 5002
python -m runner.client_runner --method pref        # random, 또는 --inject
```

- 주소는 `localhost` 말고 `127.0.0.1` (Windows 에서 localhost 는 요청마다 약 2초 지연)
- MNIST 는 첫 실행 때 `data/` 에 자동 다운로드

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
├─ tests/test_learning.py (A), test_server.py (B)
└─ docs/
   ├─ api.md                    B   ★약속
   ├─ log_format.md             B   ★약속
   ├─ aggregation_check.md      A
   ├─ usability_test.md         C
   └─ report.md                 공동
```
