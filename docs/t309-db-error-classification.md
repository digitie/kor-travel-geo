# T-309 DB 오류 분류 정정 + UI 오류 표시 + 서빙 MV 빈 상태 readiness

## 배경

2026-09-28 공용 instance(`kor-travel-shared-postgres`, T-308) 이전 뒤 admin UI의 forward geocoding이
"KTG_PG_DSN 확인" 오류를 보였다. 실제 원인은 서빙 MV(`mv_geocode_target`, `mv_geocode_text_search`)가
비어 있어 느린 fallback 쿼리가 API `statement_timeout`(5s, `KTG_PG_STATEMENT_TIMEOUT_MS=5000`)에 걸린
것이었다. psycopg의 `QueryCanceled`(SQLSTATE 57014)는 `OperationalError` 하위 클래스라서
`api/responses.py`가 모든 `OperationalError`를 "DSN을 확인하라"는 503으로 바꾸고 있었고, UI는 v2
오류 envelope를 raw JSON 문자열로 보여 줘 그 힌트만 눈에 띄었다. `/v1/readyz`는 DB 연결만 봐서 MV가
빈 상태를 알리지 못했다.

## 결정 1 — 쿼리 시간 초과는 `E0504` + HTTP 504

`statement_timeout`(57014 + "statement timeout"), `lock_timeout`(55P03 `lock_not_available`), 그 밖의
서버 측 취소(57014)는 `DatabaseTimeoutError`(`DatabaseError` 하위, `code="E0504"`, `http_status=504`)로
반환한다.

- **504를 고른 이유**: 연결은 성공했고 upstream(DB)이 제시간에 답하지 못한 상황이라 RFC 9110의
  504 의미와 맞다. 503(연결 불가·용량 부족)과 access log·HTTP 상태 지표만으로 구분된다. 5xx이므로
  VWorld 호환 envelope는 그대로 `SYSTEM_ERROR`/level 3이고, 5xx 재시도 정책을 쓰는 클라이언트 동작도
  바뀌지 않는다. 503을 유지하는 안은 status만 보는 모니터링이 여전히 연결 장애와 섞으므로 버렸다.
- **코드 번호**: `E0501`~`E0503`이 이미 쓰여 다음 번호 `E0504`를 쓴다. `DatabaseError` 하위라 기존
  `except DatabaseError` 라이브러리 사용자는 그대로 잡는다.
- 사용자 요청 취소(`asyncio` 취소 → psycopg cancel)는 보통 `CancelledError`로 끝나 이 핸들러까지 오지
  않는다. 운영자가 `pg_cancel_backend`로 끊은 경우만 `query_canceled`로 분류된다.

## 결정 2 — 연결 오류는 E0500/503을 유지하되 원인별 메시지·힌트

psycopg는 연결 단계 실패를 SQLSTATE 없는(`sqlstate=None`) 일반 `OperationalError`로 올린다(실측:
`connection failed: ... Connection refused`, `failed to resolve host ...`, `FATAL:  role "..." does not
exist`). 그래서 SQLSTATE를 먼저 보고, 없으면 서버 메시지로 나눈다. 원문 메시지는 분류에만 쓰고 응답에
싣지 않는다.

| 분류(`error_type`) | 판별 | 힌트 |
|--------------------|------|------|
| `auth_failed` | 28xxx, password 인증 실패, `pg_hba.conf`, `permission denied for database`, role/database 없음 | `KTG_PG_DSN`의 user/password/database와 CONNECT 권한 |
| `too_many_connections` | 53300, "too many clients/connections", "remaining connection slots" | max_connections·role 한도, `KTG_PG_POOL_SIZE`/`KTG_PG_MAX_OVERFLOW` |
| `connection_failed` | SQLSTATE 없음, 08xxx, 57P01~57P03 | `KTG_PG_DSN` host/port, PostgreSQL 가용성, `/v1/readyz` |
| `mv_not_populated` | 55000 + "has not been populated" | MV refresh, `/v1/readyz` `components.serving` |
| (예외 클래스 이름) | 그 밖의 운영 오류(예: 53100 disk full) | PostgreSQL 상태와 `/v1/readyz` — DSN을 가리키지 않는다 |

`ProgrammingError`/`IntegrityError` 등 SQL·스키마·제약 오류는 T-178D대로 500 `database statement
failed`를 유지한다. 전체 표는 `docs/api-reference/library/error-codes.md`.

`ktg_api_db_errors_total{method,route,error_type}`의 `error_type`은 위 분류 이름이 된다. 분류되지 않은
오류는 예전처럼 예외 클래스 이름(`OperationalError`, `ProgrammingError` 등)이라 라벨 집합이 유계로
남는다. 이 배포 이후 시간 초과·연결 실패는 `OperationalError` 시계열 대신 새 라벨로 집계된다.
`kor-travel-docker-manager`에는 이 metric을 하드코딩한 대시보드·알림이 없음을 확인했다.

## 결정 3 — `/v1/readyz`는 서빙 MV가 비면 200 + `degraded`

`kor-travel-docker-manager`의 geo-api container healthcheck는 `/v1/healthz`(liveness)를 본다. 그래도
readiness 계약상 최초 적재 전 빈 DB는 정상 상태일 수 있으므로 `ready=false`/503으로 올리지 않고, 기존
pool 고부하·admission 포화와 같은 방식(HTTP 200, `ready=true`, `degraded=true`, `status="degraded"`)으로
알린다.

- DB probe가 성공한 뒤에만 `components.serving`을 확인한다. DB가 불가하면 `status="skipped"`.
- 카탈로그(`pg_class.relispopulated` via `to_regclass`)로 없음(`missing`)·populate 안 됨
  (`not_populated`, 이 MV를 SELECT하면 오류가 난다)을 먼저 가르고, populate된 MV만
  `EXISTS (SELECT 1 FROM mv)`로 비었는지(`empty`) 본다. `count(*)`는 쓰지 않는다.
- serving probe는 DB probe와 별개 connection·별개 `KTG_API_READINESS_TIMEOUT_MS` 예산으로 순차 실행한다.
  probe 자체가 실패·timeout이면 `status="unknown"`이고 `degraded`에 반영하지 않는다 — readiness는
  DB probe만으로 정한다.
- prod 확인(2026-09-29, 읽기 전용): 두 MV 모두 `relkind=m`, `relispopulated=true`, schema `public`.
  `EXPLAIN (ANALYZE, BUFFERS) SELECT EXISTS (SELECT 1 FROM mv_geocode_target), EXISTS (SELECT 1 FROM
  mv_geocode_text_search)`는 실행 4.9ms, `shared read=2`. 새 세션 첫 planning은 relcache 적재로 ~0.4s였고
  API의 pool connection은 재사용되므로 반복 probe에서는 이 비용이 없다.

응답 예:

```json
{
  "status": "degraded", "ready": true, "degraded": true,
  "components": {
    "database": {"status": "ok"},
    "pool": {"status": "ok"},
    "serving": {
      "status": "degraded",
      "detail": {"relations": {"mv_geocode_target": "empty", "mv_geocode_text_search": "not_populated"}}
    }
  }
}
```

## UI

- `lib/api.ts` `getErrorMessage`가 v2 envelope(`{status:"ERROR", query_id, error:{code,message,hint,field}}`),
  v1 비 VWorld·admin·GeoIP envelope(`{response:{errorCode,errorMessage,hint}}`), VWorld envelope
  (`{response:{error:{code,text}}}`)를 해석해 `DB 쿼리 시간 초과 [E0504]: database query timed out —
  힌트: ...` 형태 한 줄로 보여 준다. 기존 `{detail}`·BFF `{error:"AUTH_REQUIRED"}` 동작은 그대로다.
- `/debug/geocode`·`/debug/reverse`는 오류를 destructive 알림으로 보여 주고, JSON 패널에는 요약과 함께
  HTTP status와 원본 envelope를 남긴다.
- 관리 홈 "서빙 릴리스" 카드는 `/v1/readyz`의 `components.serving`이 degraded면 릴리스 원장이 active여도
  `degraded` 배지와 `서빙 MV 준비 안 됨: mv_... 비어 있음`을 먼저 보여 준다. readyz 조회 실패는 카드를
  막지 않는다.

## 검증

- `tests/unit/test_api_responses.py`: 시간 초과 3종(504/E0504, DSN 힌트 없음), VWorld 504 envelope, 연결
  실패 7종(메시지·힌트·원문 비노출), MV 미populate, 미분류 운영 오류, `ktg_api_db_errors_total` 라벨 증가.
- `tests/unit/test_health_readiness.py`: 서빙 MV empty/not_populated/missing이면 200 + degraded,
  `count(` 미사용·미populate MV EXISTS 제외, probe 실패는 unknown, DB 불가 시 skipped.
- `tests/unit/test_v1_vworld_compat.py`: `DatabaseTimeoutError` → 504 `SYSTEM_ERROR` level 3.
- UI: `tests/unit/api.test.ts`, `tests/unit/readiness.test.ts`, `tests/unit/debug-error-display.test.tsx`.
- 각 테스트는 구현을 되돌린 변형(분류 제거, 57014를 모두 cancel로, timeout을 503으로, 인증 marker 제거,
  serving degraded 무시, `count(*)` probe, 미populate 건너뛰기 제거, envelope 파싱 제거, 디버거 raw
  메시지, 힌트 누락, ok MV 포함)에서 실패함을 확인했다.
- `scripts/run_t159_db_fault_injection.py`의 `ok → down → slow → ok` 시나리오는 그대로 통과한다.
