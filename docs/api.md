# API 설명서 (담당 B · ★약속 문서 — 3명 합의 없이 변경 금지)

모든 요청·응답 본문은 JSON. 모델 파라미터 `weights` = 숫자 7,850개 리스트 (`W` 784×10 을 행 순서로 편 뒤 `b` 10개).
라운드 r 은 모델 버전 r 로 시작하고, 2차 집계가 끝나면 버전 r+1 이 된다.
오류 응답 본문은 `{"ok": false, "error": "<아래 오류 문구>"}`. 같은 라운드에 같은 클라·엣지가 다시 제출하면 마지막 제출로 덮어쓴다.
중앙 기본 포트가 5000 이 아닌 이유: macOS 는 AirPlay 수신 기능이 5000번을 씀.

## 중앙 서버 (`servers/central.py`, 기본 :5003)

| 요청 | 본문 | 응답 200 | 오류 |
|---|---|---|---|
| `POST /start` | `{"exp_id": str, "edges": ["E1","E2"]}` | `{"ok": true, "version": 1}` — 모델 0 으로 초기화 | |
| `GET /model` | | `{"round": r, "version": r, "weights": [...]}` | 409 `not started` |
| `POST /edge_update` | `{"edge_id": "E1", "version": r, "weights": [...], "n_samples": N_E}` | `{"ok": true, "received": k, "aggregated": bool, "version": v}` — 모든 엣지 제출 시 2차 집계 → 시험 데이터 평가 → train.jsonl 기록 → 버전 +1 | 409 `not started` / `unknown edge` / `version mismatch` |
| `GET /status` | | `{"exp", "round", "version", "submitted": [...], "last_eval": {"round", "acc", "loss"}}` | |

## 엣지 서버 (`servers/edge.py --id E1 --port 5001`)

| 요청 | 본문 | 응답 200 | 오류 |
|---|---|---|---|
| `POST /start` | `{"exp_id": str, "clients": ["C1","C2","C4"]}` | `{"ok": true, "edge", "clients"}` | |
| `GET /model` | | `{"round", "version", "weights"}` — 이번 라운드 첫 요청이면 중앙 `GET /model` 로 받아 캐시 | 409 `not started`, 502 `central unavailable` / `central version mismatch` (중앙 모델 버전이 엣지와 다름, `central_version` 같이 보냄) |
| `POST /client_update` | `{"client_id", "version", "weights", "n_samples", "train_loss"}` | `{"ok", "received", "expected", "edge_submitted": bool}` — 담당 클라 전원 제출 시 1차 집계 → 중앙 `POST /edge_update` → 버전 +1 | 409 `not started` / `client not assigned to this edge` / `version mismatch`, 502 `central unavailable` / `central rejected` (`central_status` 같이 보냄) |
| `GET /status` | | `{"edge", "exp", "version", "clients", "received"}` | |

## 모니터링 (`dashboard/app.py`, 기본 :5050)

| 요청 | 응답 |
|---|---|
| `GET /` | 모니터링 화면 |
| `GET /api/experiments` | 실험 ID 목록 |
| `GET /api/<exp>/bundle` | config, split(인덱스 제외), assignment, train, comm 한 번에 |

## 한 라운드 호출 순서

```
runner → E1  GET  /model            (C1 차례)
E1     → S   GET  /model            (E1 이번 라운드 첫 요청)
runner        C1 로컬 학습 + 시험 평가
runner → E1  POST /client_update    (C1)
... C2, C4 반복 (모델은 E1 캐시)
E1     → S   POST /edge_update      (3/3 → 1차 집계 결과)
... E2 쪽 C3, C5, C6 같은 순서 → S 2차 집계, 평가, 버전 +1
runner → S   GET  /status           (버전이 r+1 인지 확인)
```

요청 하나마다 보낸 쪽이 `logs/<exp>/comm.jsonl` 에 한 줄 기록 (`hfl/comm.py` 의 `call`).
