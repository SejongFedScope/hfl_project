# 로그 형식 설명서 (담당 B · ★약속 문서 — 3명 합의 없이 변경 금지)

실험 1개 = `logs/<exp_id>/` 폴더 1개, 파일 5개. `exp_id` = `exp_<배정방식>_seed<시드>[_inject]`.
정확도는 0~1, 시간·지연은 ms.

## config.json — 설정 (`kind: config`)

`configs/default.json` 전체 + `exp_id`, `algorithm`(fedavg), `assign_method`(pref / random), `inject`(bool).

## split.json — 데이터 분할

```json
{"seed": 42, "clients": {"C1": {"n": 1200, "digit_counts": [400,400,400,0,0,0,0,0,0,0], "indices": [MNIST train 인덱스 1200개]}, "...": {}}}
```

## assignment.json — 배정

| 필드 | 뜻 |
|---|---|
| `method` | pref / random |
| `capacity` | 엣지 정원 |
| `client_prefs`, `edge_prefs` | 양측 선호 순위 |
| `assignment` | `{"E1": [...], "E2": [...]}` 실제 배정 |
| `check.unassigned` / `duplicated` / `capacity_violation` | 제약 위반 목록 (정상이면 빈 리스트) |
| `check.client_pref_rank` | 클라별 배정 엣지의 선호 순위 (1 = 1순위) |
| `check.mean_pref_rank` | 평균 선호 순위 |
| `edge_composition` | 엣지별 클라, 클라 수, 표본 수 n, 숫자별 표본 수 |

## train.jsonl — 학습 (한 줄 = 기록 1개, `target` 으로 구분)

| target | 기록하는 곳 | 필드 |
|---|---|---|
| `global` | 중앙 | round, model_version(집계 결과 버전), eval_data(test), acc, loss, acc_by_digit[10], edge_n |
| `C1`~`C6` | runner | round, model_version(학습 시작 버전), edge, n, train_loss, eval_data, acc, loss, acc_by_digit, participated |
| `E1`, `E2` | 엣지 | round, model_version, clients, client_n, n_samples |
| `round` | runner | round, duration_ms (라운드 시작~중앙 집계 확인) |

모든 줄에 `exp`, `kind`(measured) 포함. 평가 대상 모델(`target`)과 평가 데이터(`eval_data`)를 같이 기록.

## comm.jsonl — 통신 (요청 1건 = 1줄)

| 필드 | 뜻 |
|---|---|
| `exp`, `round`, `model_version` | 실험, 라운드, 요청에 실린/요청한 모델 버전 (시작 설정 요청은 round 0) |
| `src`, `dst` | 보낸 쪽 / 받는 쪽 (`runner`, `C1`~`C6`, `E1`, `E2`, `S`) |
| `api` | 예: `POST /client_update` |
| `latency_ms` | 보낸 쪽에서 잰 요청~응답 시간 |
| `ok`, `status`, `error` | 성공 여부(200), HTTP 상태 코드, 연결 실패 시 예외 이름 |
| `req_bytes` | 요청 본문 크기 (화면 누적 통신량용) |
| `bytes` | 응답 본문 크기 |
| `kind` | `config`(시작 설정) / `measured`(실제 측정) / `injected`(일부러 넣은 시험 요청) |
