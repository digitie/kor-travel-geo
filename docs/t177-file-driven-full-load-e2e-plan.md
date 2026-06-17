# T-177 파일 기반 full-load e2e 테스트 계획

## 목적

T-177은 T-073 계열 shell script에 맞춰 재실행하는 작업이 아니다. 실제 Juso 원천 파일을
pytest opt-in 통합/e2e 테스트가 직접 읽고, 이미 동작 중인 PostgreSQL/PostGIS scratch DB에
schema 적용부터 적재, 후처리, MV, smoke, consistency, benchmark까지 재현하는 테스트
트랙이다.

이 계획은 T-177 구현 전에 먼저 검토한 테스트 전략과 Task 분해를 고정한다. 각 Task는 별도
PR로 머지하고, 다음 Task로 넘어가기 전 2026-06-16 이후 PR의 Claude Code 코멘트 후속이
새로 생겼는지 확인한다. 리뷰 반영만을 위한 PR은 이 조사 대상에서 제외한다.

## 검토 기준

| 기준 | 결정 |
|------|------|
| 실행 방식 | pytest opt-in integration/e2e. `scripts/fullload_test.sh`에 테스트를 맞추지 않는다. |
| DB 생명주기 | 저장소가 PostgreSQL을 구동/정지/재시작하지 않는다. `KTG_TEST_PG_DSN`으로 이미 떠 있는 scratch DB에 접속한다. |
| 안전장치 | `KTG_TEST_FULL_LOAD_E2E=1`, `KTG_TEST_FULL_LOAD_E2E_CONFIRM="RUN-T177-E2E <database>"`, DB 이름 allowlist(`t177`, `test`, `scratch` 포함)를 모두 요구한다. |
| 데이터 루트 | 기본은 `data/juso`이며, WSL 미러에서는 `data -> /mnt/f/dev/geodata` symlink를 통해 `F:\dev\geodata\juso`를 본다. |
| 기준월 | 원천별 기준월을 분리한다. 현재 보존 원천은 `roadname=202605`, `locsum=202604`, `navi=202604`, `electronic_map=202604`, `roadaddr_entrance=202604`, `sppn_makarea=202603/202604 fallback` 조합을 명시한다. `roadaddr_entrance` row-level 기준월은 ZIP 내부 `RNENTDATA_*` 파일명에서 loader가 추론할 수 있다. |
| 적재 표면 | loader Python API를 직접 호출한다. CLI는 최종 smoke나 사용자 runbook 확인에만 제한적으로 쓴다. |
| 범위 확대 | 세종/시도 단위 fast e2e에서 시작해 전국 long-run e2e로 확장한다. 전국 실행은 별도 opt-in과 긴 timeout을 요구한다. |
| 산출물 | `artifacts/t177/<run_id>/` 아래 JSON/Markdown/CSV를 쓰되 Git에는 커밋하지 않는다. 문서에는 핵심 요약과 재현 명령만 남긴다. |

## 입력 파일 계획

| 원천 | 파일 discovery | 적재 대상 | 우선 Task |
|------|----------------|-----------|-----------|
| 도로명주소 한글 전체분 | `discover_juso_hangul_files`, `discover_jibun_rnaddrkor_files` | `tl_juso_text`, `tl_juso_parcel_link` | T-177C |
| 일변동 ZIP | `discover_daily_juso_sources`, `discover_daily_lnbr_sources` | `tl_juso_text`, `tl_juso_parcel_link` delta | T-177C |
| 위치정보요약DB | `discover_locsum_files` | `tl_locsum_entrc` | T-177C |
| 내비게이션용DB | `discover_navi_build_files`, `discover_navi_entrance_files` | `tl_navi_buld_centroid`, `tl_navi_entrc` | T-177C |
| 도로명주소 전자지도 | `build_shp_load_plan` | 9개 SHP serving 보조 테이블 | T-177D |
| 도로명주소 출입구 정보 | `discover_roadaddr_entrance_sources` | `tl_roadaddr_entrc` | T-177E |
| 구역의 도형 `TL_SPPN_MAKAREA` | `load_sppn_makarea` | `tl_sppn_makarea` | T-177E |

## 테스트 하니스 구조

새 테스트는 `tests/integration/test_t177_file_driven_full_load_e2e.py` 계열로 분리한다.
기본 CI에서는 skip된다.

1. 환경 preflight
   - `KTG_TEST_FULL_LOAD_E2E=1` 확인
   - `KTG_TEST_PG_DSN` 확인
   - `SELECT current_database()` 후 confirmation 문자열 비교
   - DB 이름 allowlist 검증
   - PostGIS/pg_trgm/unaccent extension 확인 또는 schema 적용 중 생성 확인
   - data root 존재와 필수 파일 discovery 결과를 JSON plan으로 저장

2. DB 초기화
   - scratch DB에 `SCHEMA_SQL`, `INDEX_SQL`을 적용한다.
   - 기존 row가 있으면 destructive confirmation 없이는 실패한다.
   - Task별 fast e2e는 필요한 테이블만 clean slate로 만들고, 전국 e2e는 DB 전체를 새로 준비한다.

3. 파일 적재
   - 각 loader API를 직접 호출한다.
- fast e2e는 `limit_per_file` 또는 시도 subset을 사용해 수분 내 완료를 목표로 한다.
- T-177C 텍스트 fast-sample의 기본 `limit_per_file`은 2이며
  `KTG_TEST_FULL_LOAD_E2E_SAMPLE_LIMIT`로 조정한다.
- T-177D SHP fast-sample은 전자지도 월 폴더에서 세종(없으면 이름순 첫 시도) ZIP 또는
  디렉터리를 선택한다. ZIP 원천은 artifact 작업 디렉터리에 materialize한 뒤 공개
  `load_shp_polygons()` API로 serving 9개 레이어를 모두 적재한다.
- long-run e2e는 전국 원천 전체를 읽으며 별도 marker와 긴 timeout을 요구한다.

4. 후처리와 serving 구축
   - `resolve_text_geometry_links()`
   - `MV_SQL` 또는 `refresh_mv(strategy="swap")` 표면
   - `ops.dataset_snapshots`/`load_manifest`/source 기준월 요약 기록

5. 검증
   - row count, source_yyyymm, manifest kind
   - geometry validity/SRID
   - geocode/reverse/search/zipcode smoke
   - C1~C10 consistency fast subset 또는 full scope
   - T-047 계열 SQL/REST benchmark hook

## Task 분해

### T-177A Plan/Task 등록

이 문서와 `docs/tasks.md`에 상세 Task를 등록한다. 코드 변경은 하지 않는다.

완료 조건:

- T-177의 실행 원칙, 환경 gate, 데이터 파일 범위, 산출물 위치가 문서화되어 있다.
- T-177B 이후 Task가 PR 단위로 쪼개져 있다.

### T-177B opt-in e2e 하니스와 destructive preflight

`tests/integration/_t177_full_load_harness.py`의 공통 helper와
`tests/integration/test_t177_file_driven_full_load_e2e.py` opt-in 테스트를 만든다.

완료 조건:

- opt-in env가 없으면 skip한다.
- `KTG_TEST_PG_DSN` DB 이름과 typed confirmation을 확인한다.
- 기존 row가 있으면 typed confirmation 외에 `KTG_TEST_FULL_LOAD_E2E_ALLOW_NONEMPTY=1`을
  요구한다.
- data root discovery plan을 JSON artifact로 저장한다.
- schema/index 적용 smoke와 빈 DB/기존 DB guard 테스트가 있다.

### T-177C 텍스트 정본과 daily delta DB 구축 e2e

도로명주소 한글, 지번 연결, daily MST/LNBR, 위치정보요약DB, 내비게이션용DB를 실제 파일에서
읽어 scratch DB에 적재한다.

완료 조건:

- loader API를 직접 호출한다.
- fast sample mode에서 row count와 `load_manifest`를 검증한다.
- daily delta가 snapshot 이후 upsert/delete manifest를 남긴다.
- `resolve_text_geometry_links()` 전후 핵심 링크 수치를 artifact에 저장한다.
- 지번 링크 FK parent sample seed와 `t177c-text-delta-fast-sample-load.json` artifact가 있다.

### T-177D 전자지도 SHP/PostGIS geometry e2e

도로명주소 전자지도 SHP 9개 레이어를 selected 시도 단위로 읽고 PostGIS 테이블에 적재한다.

완료 조건:

- 실제 전자지도 root에서 selected 시도 ZIP 또는 dataset을 자동 선택한다(세종 우선, 없으면
  이름순). ZIP 원천은 artifact 작업 디렉터리에 materialize한다.
- GDAL Python binding이 없으면 skip한다.
- `build_shp_load_plan()` discovery 결과와 실제 `load_shp_polygons(mode="full")` 적재 layer 수를
  검증한다.
- SRID, geometry validity, 주요 table row count, source file/source yyyymm을 검증한다.
- `refresh_region_radius_parts()` 후 `region_radius_parts`의 SRID/validity도 함께 검증한다.
- `t177d-shp-geometry-fast-sample-load.json` artifact를 남긴다.
- 전국 장기 실행과 대형 레이어 전체 소요시간은 T-177G long-run에서 분리 검증한다.

### T-177E 선택 보강 원천 e2e

도로명주소 출입구 정보와 `TL_SPPN_MAKAREA`를 실제 파일에서 읽어 선택 보강 테이블에 적재한다.

완료 조건:

- roadaddr entrance는 같은 기준월 gate와 source_yyyymm 기록을 검증한다.
- SPPN makarea는 polygon validity와 geocode/reverse repository SPPN smoke를 검증한다.
  serving MV가 필요한 core reverse smoke는 T-177F에서 검증한다.
- 기준월 혼합은 C10/manifest에서 의도된 warning으로 드러난다.

### T-177F post-load serving, smoke, consistency e2e

T-177C~E의 loaded DB를 바탕으로 serving MV와 API-level smoke를 검증한다.

완료 조건:

- 현재 보존 원천에 daily ZIP 또는 materialize된 navi TXT가 없으면, T-177F fast-sample은
  도로명주소 한글 snapshot과 위치정보요약DB를 직접 적재하는 전용 helper로 텍스트 정본을
  구성한다. daily/navi 전체 조합은 T-177G long-run에서 다시 다룬다.
- fresh scratch DB에서 `resolve_text_geometry_links()` 뒤 `rebuild_mv()`로 serving MV를 구축한다.
- `mv_geocode_target`, `mv_geocode_text_search` row count와 핵심 index 존재를 검증한다.
- `region_radius_parts`는 T-177D SHP helper가 갱신한 serving object로 row count를 함께 검증한다.
- geocode/reverse/search/zipcode smoke가 local DB만으로 통과한다.
- smoke는 `geo_cache`를 비우고 cache disabled client로 실행하며, sample이 위치정보요약DB 링크
  기반 serving row에서 나왔음을 artifact와 assertion으로 남긴다.
- C1~C10 consistency subset report를 artifact로 남긴다.
- fast-sample C1~C10 `severity_max`는 acceptance gate가 아니다. 제한된 row 수와 기준월 혼합을
  드러내는 smoke 산출물로 보고, 전국 acceptance 판정은 T-177G/T-177H에서 수행한다.
- 실패 sample은 CSV/JSON으로 저장한다.

### T-177G 전국 long-run full-load e2e

fast sample이 아니라 전국 실제 원천 전체를 읽어 DB를 구축하는 장기 opt-in e2e다.

완료 조건:

- 별도 env `KTG_TEST_FULL_LOAD_E2E_LONGRUN=1`을 요구한다.
- 전체 phase별 wall time, row count, DB size, source month summary를 artifact로 남긴다.
- 실패 시 재개 가능 phase와 cleanup 절차를 report에 남긴다.

### T-177H T-047 benchmark와 최종 acceptance report

전국 long-run DB를 기준으로 SQL/REST benchmark와 최종 acceptance report를 생성한다.

완료 조건:

- T-047 계열 SQL benchmark를 연결한다.
- REST benchmark는 API 서버가 명시적으로 제공될 때만 실행한다.
- p95/p99, error count, slow plan, `pg_stat_statements` snapshot을 report로 남긴다.
- `docs/resume.md`와 `docs/tasks-done.md`가 최종 결과를 가리킨다.

## PR 운영 순서

1. 각 Task는 독립 branch와 PR로 처리한다.
2. PR 머지 전, 2026-06-16 이후 PR에서 새 Claude Code 코멘트가 있는지 확인한다. 리뷰 반영 PR은 제외한다.
3. 새 문제가 발견되면 GitHub issue와 Task를 만들고, 문제 해결 PR을 먼저 머지한 뒤 T-177을 계속한다.
4. T-177B 이후 구현 PR은 최소한 focused pytest, Ruff, mypy, `git diff --check`를 통과해야 한다.
5. 프론트엔드가 포함되는 Task가 생기면 WSL ext4 Linux Node 검증과 Windows Playwright 원칙을 따른다.
