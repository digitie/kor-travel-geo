# PR #20~#22 post-merge 리뷰 반영

## 배경

T-036이 PR #23으로 main에 merge된 뒤, 사용자 지시에 따라 다음 순서로 post-merge 리뷰 코멘트를 확인했다.

1. PR #22 `T035 MV refresh benchmark`
2. PR #21 `T034 road interval SHP copy tuning`
3. PR #20 `T033 full-load revalidation baseline`

세 PR 모두 merged 상태였고, conversation comment 1개씩만 있었다. formal review와 inline review thread는 없었다. 따라서 최신 `main`에서 새 follow-up PR로 반영한다.

## PR #22 반영

### 반영 완료

- `_rename_mv_next_indexes()` private helper 직접 import를 제거했다.
  - `postload.rename_mv_next_indexes_for_conn(conn)` public helper를 추가했다.
  - `scripts/benchmark_mv_refresh.py`와 production `shadow_swap_mv()`가 같은 public helper를 사용한다.
- `_optional_int()`의 broad `except Exception`을 `sqlalchemy.exc.ProgrammingError`로 좁혔다.
  - MV가 아직 없는 manual preflight 상황만 `None`으로 취급한다.
  - catch 후 `await conn.rollback()`을 호출해 같은 connection의 후속 stat query가 aborted transaction에 갇히지 않게 했다.
- benchmark JSON에 `schema_version=2`와 `metadata`를 추가했다.
  - `trial_index`
  - `cache_warm_hint`
  - `notes`
  - `concurrent_sessions_before/after`
  - `wait_events_before/after`
- `SET` phase 이름 분류를 세분화했다.
  - `SET search_path` → `rebuild.set_search_path`
  - `SET maintenance_work_mem` → `rebuild.set_maintenance_work_mem`
  - 기타 `SET` → `rebuild.set`
- `ANALYZE mv_geocode_target` transaction에도 `SET LOCAL lock_timeout = '2s'`를 적용했다.
  - production `shadow_swap_mv()`
  - benchmark `_analyze_mv()`와 `_shadow_swap_phases()`
- `docs/data-model.md`의 shadow swap 예시에 실제 `idx_mv_next_* → idx_mv_*` rename 단계를 명시했다.
- `docs/t035-mv-refresh-benchmark.md`에 JSON metadata, schema version, wait event snapshot의 한계를 기록했다.

### 후속으로 남긴 항목

- backend-local temp I/O counter는 현재 PostgreSQL 버전과 권한별 함수 차이가 있어 이번 PR에서는 유지했다. `pg_stat_database`가 DB 전역 누적값이라는 한계는 T-035 문서와 PR 본문에서 계속 명시한다.
- 운영 DB 보호 가드(`--allow-production-dsn`)는 실제 운영 DSN 판별 기준이 아직 없다. localhost 외부 DB를 전부 막으면 원격 staging benchmark도 막힐 수 있어, 운영 환경 정책 ADR 또는 CLI flag 설계와 함께 별도 PR로 다룬다.
- 실제 PostgreSQL 통합 테스트는 CI 비용과 Docker 의존성 때문에 이번 follow-up에서는 추가하지 않았다. 현재는 source-level/unit test와 실제 T-035 manual benchmark artifact로 검증한다.

## PR #21 반영

### 반영 완료

- `TL_SPRD_INTRVL` COPY row를 `RoadIntervalRow` dataclass로 표현했다.
  - `ROAD_INTERVAL_COPY_COLUMNS`와 `RoadIntervalRow.to_copy_tuple()`가 같은 projection 순서를 공유한다.
  - column list와 tuple shape가 코드에서 더 잘 드러난다.
- CP949 decode 실패 시 `LoaderError`에 파일 경로, record 번호, 필드명, byte slice를 포함한다.
- truncated DBF record 오류에 expected/actual byte 수, header `record_count`, file size를 포함한다.
- `psycopg.connect(..., autocommit=False)`를 명시하고, COPY 완료 뒤 explicit `conn.commit()`하는 의도를 주석으로 남겼다.
- deleted record(`record[:1] == b"*"`) skip 단위 테스트를 추가했다.
- CP949 decode error와 truncated record error 단위 테스트를 추가했다.
- `docs/t034-shp-append-tuning.md`에 row dataclass, 오류 문맥, deleted record 처리, `TL_SPBD_BULD` 후속 후보를 기록했다.

### 후속으로 남긴 항목

- `record_no`와 실제 `copied` 수를 운영 로그에 별도 출력하는 항목은 현재 progress callback 계약을 바꾸지 않기 위해 보류했다.
- `TL_SPBD_BULD` 튜닝은 T-037로 등록했다. geometry 포함 레이어는 DBF만 있는 `TL_SPRD_INTRVL`과 달리 geometry 변환과 winding 보정이 얽혀 있어 별도 실험이 필요하다.

## PR #20 반영

### 반영 완료

- `scripts/fullload_test.sh`에 phase별 timer를 추가했다.
  - DDL/init-db
  - `juso`
  - `locsum`
  - `navi`
  - text total
  - SHP
  - geometry link resolution
  - MV swap refresh
  - total elapsed
- preflight 출력에 `KTG_DB_PORT`가 `KTG_PG_DSN` 미설정 시에만 effective하다는 설명을 추가했다.
- `docs/t033-full-load-revalidation.md`에 SHP 시간 출처를 timestamp 기반으로 명시했다.
- T-033 측정이 단발 실행이며 cache/동시 프로세스 variance를 추정하지 않았다는 한계를 명시했다.
- C10 `OK 0`의 의미를 명확히 했다.
  - 현재 C10은 row-level source month 전수 비교가 아니라 `load_manifest` 대상 table의 `source_yyyymm` distinct count를 본다.
  - manual CLI 실행에서 manifest 비교 대상이 0건이면 `OK 0`이 될 수 있다.
- `tl_navi_entrc=12,830`은 원천 `match_rs_entrc.txt` row count와 loader 적재 row count cross-check가 필요하다고 기록했다.

### 후속으로 남긴 항목

- 기존 T-033 artifact 자체는 git ignore 대상이라 PR에 첨부하지 않는다. 다음 T-027 클린 로드에서 phase별 timer 출력과 핵심 log line을 문서에 직접 인용한다.
- DB size 24GB→26GB 차이 분해는 기존 T-027 DB와 T-033 DB가 동일 실행이 아니어서 이번 follow-up 범위에서 제외한다.

## 검증 범위

이번 follow-up은 실제 전국 full-load나 MV benchmark를 재실행하지 않는다. 변경 성격은 benchmark/script/loader 방어 로직과 문서 명확화다.

필수 검증:

- `pytest tests/unit/test_mv_refresh_benchmark.py tests/unit/test_postload_mv.py`
- `pytest tests/unit/test_shp_loader_gdal.py`
- 전체 `pytest -q`
- `ruff check .`
- `mypy src/kortravelgeo`
- `lint-imports`
- `git diff --check`
