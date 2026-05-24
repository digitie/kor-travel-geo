# JOURNAL — 작업 일지

새 항목은 항상 파일 맨 위에 추가(역시간순). 기존 항목은 절대 수정하지 않는다 — 잘못된 결정조차 기록으로 남는 것이 가치다.

## 2026-05-25 (PR #14 리뷰 반영 — schema migration, SHP natural key, 리뷰 확인 프로토콜)

**작업**: PR #14의 정식 review body(`# PR #14 리뷰 — T-027 actual full-load execution fixes`)와 마지막 Optional conversation comment를 모두 확인하고 반영했다.

**반영 상세**:
- H1: `alembic/versions/0002_t027_shp_schema_fixups.py`를 추가했다. 기존 DB에 `tl_spbd_buld_polygon` natural key 컬럼, `tl_sprd_manage.geom`, `tl_sprd_rw.geom` `MULTIPOLYGON` 타입 변경을 적용한다.
- H2: `tl_spbd_buld_polygon.bjd_cd` generated column은 `LI_CD=''`를 `00`으로 보정하고, `rncode_full`은 빈 문자열을 NULL로 취급하도록 `SCHEMA_SQL`과 `sql/ddl/001_schema.sql`을 수정했다.
- M1: stale 운영 MV index가 남아 있어 새 `idx_mv_next_*`를 drop하는 복구 경로에서 `warnings.warn`을 남기도록 했다.
- M2: SHP full reset은 `TRUNCATE` 직전 대상 테이블별 approximate row count snapshot을 출력한다. 문서에는 full mode 중단 시 9개 SHP 테이블이 비거나 일부만 적재된 상태일 수 있음을 명시했다.
- M3/L7: 내비 loader의 `limit`은 좌표 결측 skip 이후 yield row 기준임을 docstring으로 명시하고, C4 SQL에는 `resolve_text_geometry_links()` 선행 의존성을 주석으로 남겼다.
- Optional: Docker 포트 환경변수를 저장소 prefix 규칙에 맞춰 `KRADDR_DB_PORT`에서 `KRADDR_GEO_DB_PORT`로 변경했다.
- 반복 방지: `docs/agent-guide.md`에 PR 리뷰 확인 프로토콜을 추가했다. 앞으로 PR 리뷰 반영 시 conversation comments뿐 아니라 `reviews[].body`와 `review_threads[]`를 반드시 확인한다.

**검증**:
- `pytest tests/unit/test_alembic_migrations.py tests/unit/test_infra_engine_pnu_sql.py tests/unit/test_shp_loader_gdal.py tests/unit/test_postload_mv.py tests/unit/test_navi_loader.py tests/unit/test_consistency_sql.py -q` → 17 passed.
- `ruff check .` → 통과.
- `mypy src/kraddr/geo` → 통과.
- `lint-imports` → Layered architecture kept.
- `bash -n scripts/fullload_test.sh` → 통과.
- `PATH="$PWD/.venv/bin:$PATH" DATA_DIR=/home/digitie/kraddr-geo-data KRADDR_GEO_DB_PORT=15432 PLAN_ONLY=1 bash scripts/fullload_test.sh` → 통과. 출력 DSN은 `localhost:15432`.
- `pytest -q` → 80 passed, 7 skipped.
- 임시 DB `kraddr_geo_pr14_review`에서 `alembic upgrade head` → 0001, 0002 적용 성공. `LI_CD=''` 샘플 insert 시 generated `bjd_cd=1111010100`, `rncode_full=111103100012` 확인.
- 실제 T-027 DB 영향 조회: `empty_li=0`, `empty_rn=0`, `empty_rds_sig=0`, `bjd_8=0`, `bjd_10=10,687,732`.

## 2026-05-25 (PR #14/T-027 — 실제 전국 SHP 재적재와 정합성 재검증)

**작업**: `data/juso/도로명주소 전자지도` 실제 전국 SHP 17개 시도 × 9개 레이어를 새 natural-key 스키마로 Docker PostGIS에 재적재하고, C1~C10 정합성 검증을 실제 DB에서 재실행했다.

**실행 로그**:
- 상세 로그: `artifacts/fullload/20260524_173115/execution-log.md` (git ignore 산출물)
- 환경: WSL2 Ubuntu 24.04, AMD Ryzen 7 7840HS 16 vCPU, 메모리 29GiB, Docker 29.5.2, Python 3.12.3, GDAL 3.8.4
- DB: `kraddr-geo-t027-db-1`, `localhost:15432`, `kraddr_geo`
- SHP 재적재 경과: 3시간 10분 4초, exit status 0, 최대 RSS 187,100KB
- 종료 직후 DB 크기: 24GB
- 디스크 여유: ext4 약 796GB, C: 약 682GB, F: 약 264GB

**확정 row count**:
- `tl_scco_ctprvn`: 17
- `tl_scco_sig`: 255
- `tl_scco_emd`: 5,067
- `tl_scco_li`: 15,161
- `tl_kodis_bas`: 34,516
- `tl_sprd_manage`: 875,221
- `tl_sprd_rw`: 1,482,679
- `tl_sprd_intrvl`: 16,993,167
- `tl_spbd_buld_polygon`: 10,687,732

**발견한 문제**:
- `TL_SPBD_BULD` natural key(`rncode_full`, `bjd_cd`, 건물구분, 본번, 부번)는 중복 polygon을 많이 가진다. 같은 natural key에 polygon이 여러 개인 경우 C4/C5가 모든 후보와 다대다 거리값을 만들며 180km급 이상치를 대량 보고했다.
- `rds_sig_cd`/`rncode_full`이 NULL인 SHP 건물 polygon이 581건 있었다. 나머지 natural-key 컬럼과 geometry는 전 건 채워졌다.
- `source_file` 컬럼은 현재 GDAL append 경로에서 전 건 NULL이다. 적재 추적성 보강 후보로 남긴다.
- 대부분 시도 `TL_SPRD_RW.shp`, 일부 `TL_SPBD_BULD.shp`/행정구역 polygon에서 GDAL ring winding order 자동 보정 경고가 반복됐다. 적재는 실패 없이 완료됐다.
- 실제 smoke test에서 `geocode` SQL의 `:si IS NULL` 선택 필터가 psycopg `AmbiguousParameter`를 일으켰다. PostgreSQL은 `IS NULL`에 먼저 등장한 바인딩 파라미터의 타입을 추론하지 못할 수 있다.

**보강 상세**:
- C4는 같은 natural key SHP polygon 후보 중 `e.geom <-> p.geom` 기준 가장 가까운 polygon 1개만 평가하도록 `JOIN LATERAL ... LIMIT 1`로 수정했다.
- C5는 같은 natural key SHP polygon 후보 중 `n.centroid_5179 <-> p.geom` 기준 가장 가까운 polygon 1개만 평가하도록 수정했다.
- 단위 테스트는 C4/C5가 LATERAL nearest 후보를 사용함을 확인하도록 보강했다.
- `geocode`, `zipcode`, `pobox` raw SQL의 optional filter는 `CAST(:param AS text/integer/boolean)`로 명시해 psycopg 타입 추론 실패를 막았다.

**정합성 결과**:
- 1차 재검증: 4분 59.41초, `severity_max=ERROR`
  - C4: 257,783건, `over_500m=11,649`
  - C5: 3,277,327건
- C4/C5 nearest 보강 후 2차 재검증: 6분 27.54초, `severity_max=ERROR`
  - C1 WARN: 32,531건
  - C2 ERROR: 34,699건
  - C3 WARN: 3,510,265건
  - C4 ERROR: 3,415건, `over_500m=16`, `p95=3.82m`, `p99=15.50m`
  - C5 WARN: 202건
  - C6 ERROR: 803건
  - C7 ERROR: 6,817건
  - C8 WARN: 24,471건
  - C9 OK: 0건
  - C10 OK: 0건

**검증**:
- `ruff check src/kraddr/geo/loaders/consistency.py tests/unit/test_consistency_sql.py` 통과.
- `pytest tests/unit/test_consistency_sql.py -q`는 pytest capture 임시파일 `FileNotFoundError`로 테스트 실행 전 실패.
- `pytest -s tests/unit/test_consistency_sql.py -q` → 2 passed.
- SHP 9개 테이블 `ANALYZE` → 4.14초, 성공.
- `ruff check src/kraddr/geo/infra/geocode_repo.py src/kraddr/geo/infra/zip_repo.py src/kraddr/geo/infra/pobox_repo.py tests/unit/test_infra_repo_sql.py` 통과.
- `pytest -s tests/unit/test_infra_repo_sql.py tests/unit/test_consistency_sql.py -q` → 12 passed.
- smoke test: `서울특별시 종로구 필운대로 93` geocode OK, reverse OK(10건), search 3건, zipcode OK(3건).

**다음 작업**: C4/C5 nearest 보강을 커밋·푸시하고 PR #14에 실제 전수 적재/정합성 결과를 코멘트한다. 이어서 MV/클라이언트 smoke와 전체 테스트를 가능한 범위까지 수행하고, 남은 C2/C4/C6/C7 원천 데이터 품질 항목은 후속 분석 후보로 분리한다.

## 2026-05-24 (PR #14/T-027 — 실제 SHP 적재 중 GDAL/PostGIS 스키마 보강)

**작업**: 실제 `data/juso/도로명주소 전자지도`를 Docker PostGIS에 적재하는 과정에서 SHP 로더의 GDAL 옵션, geometry 타입, full-load overwrite 전략 문제를 확인하고 보강했다.

**발견한 문제**:
- GDAL 3.8 Python binding은 `VectorTranslateOptions(openOptions=...)`를 받지 않아 SHP 적재가 `TypeError`로 중단되었다.
- `openOptions` 제거 후에는 `accessMode="overwrite"`가 운영 테이블을 원천 DBF 스키마로 재생성하면서 `tl_scco_ctprvn.geom`이 `Polygon`으로 바뀌었고, 실제 `MultiPolygon` 삽입에서 실패했다.
- `shp-all --mode full`은 17개 시도 디렉터리를 순회하는데, 각 시도마다 overwrite/full을 그대로 적용하면 앞 시도 데이터가 뒤 시도 적재 때 사라질 수 있다.
- 실제 2026년 전자지도 17개 시도 파일을 확인한 결과 `TL_SPRD_RW.shp`는 모두 `Polygon` 레이어다. 기존 `tl_sprd_rw.geom geometry(MultiLineString, 5179)` 정의와 맞지 않았다.
- 실패 후 복구를 위해 `init-db`를 다시 실행하자, 이미 대량 텍스트 데이터가 들어간 상태에서는 MV 생성이 5초 statement timeout에 걸렸고 같은 트랜잭션의 앞선 DDL까지 롤백될 수 있음을 확인했다.

**보강 상세**:
- SHP 로더는 CP949를 `gdal.config_options({"SHAPE_ENCODING": "CP949"})`로 지정한다.
- full 모드는 대상 9개 테이블을 명시적으로 `TRUNCATE`한 뒤 GDAL은 항상 기존 PostgreSQL 테이블에 `append`한다. 원천 DBF 전체 컬럼으로 운영 테이블을 재생성하지 않는다.
- `SQLStatement`는 JOIN 키와 필요한 속성 컬럼만 alias한다. OGR SQL 결과가 geometry를 유지하므로 `GEOMETRY AS geom` 같은 가짜 문자열 필드를 만들지 않는다.
- `shp-all --mode full`과 `load all-sidos --shp-root`는 첫 시도만 full, 이후 시도는 append로 바꿔 전국 적재가 누적되도록 했다.
- `tl_sprd_rw.geom`은 실제 SHP 헤더에 맞춰 `MULTIPOLYGON 5179`로 조정하고 문서도 도로면 polygon 기준으로 갱신했다.
- `init-db`는 schema/index/MV statement를 별도 트랜잭션으로 실행해 MV 경고가 schema DDL을 롤백하지 않게 했다. 경고가 있으면 개수를 출력한다.
- `refresh mv --swap`은 복구 중 기존 `mv_geocode_target`이 없어도 `mv_geocode_target_next`를 바로 운영 이름으로 승격한다. swap 후 `ANALYZE mv_geocode_target`도 수행한다.
- `scripts/fullload_test.sh`는 기본 `KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS`를 30분으로 높인다. 대량 링크 해소와 shadow MV 빌드가 운영 기본값 5초에 막히지 않도록 하기 위함이다.
- 실제 MV 빌드 후 `pt_source='centroid'`가 0건인 것을 확인했다. 원인은 내비게이션용DB의 `bd_mgt_sn`이 25자리이고 정본 `tl_juso_text.bd_mgt_sn`은 26자리라 직접 조인이 불가능한 점이었다. 또한 내비 `bjd_cd`는 리 코드가 `00`인 경우가 많아 10자리 법정동 완전 일치도 부적합했다. MV fallback을 `rncode_full + 건물구분 + 본번/부번 + left(bjd_cd, 8)` 대표 centroid 조인으로 변경했다.
- 두 번째 MV swap에서 `idx_mv_next_geocode_target_next_pk`가 이미 존재한다는 충돌을 확인했다. 첫 swap 때 shadow MV 인덱스명이 운영 MV에 그대로 남았기 때문이다. swap 전후에 `idx_mv_next_*` 이름을 운영명 `idx_mv_*`로 정규화하도록 보강했다. 이어 실제 재시도에서 old MV의 운영명 인덱스가 아직 있는 상태로 next 인덱스를 rename하려 하면 next 인덱스가 drop되는 것을 확인해, old MV를 먼저 drop한 뒤 next 인덱스를 rename하도록 순서를 조정했다.
- 실제 C1~C10 정합성 검증에서 C1/C2가 전량 불일치했다. `TL_SPBD_BULD.BD_MGT_SN`도 25자리이고 정본은 26자리라 건물 polygon도 직접 `bd_mgt_sn` 조인이 불가능했다. `tl_spbd_buld_polygon`에 `RDS_SIG_CD`, `RN_CD`, `BULD_SE_CD`, `BULD_MNNM`, `BULD_SLNO`, `SIG_CD`, `EMD_CD`, `LI_CD`를 함께 적재하고 C1/C2/C4/C5를 natural key 기준으로 바꿨다. C8은 `TL_SPRD_RW`에 `rds_man_no`가 없어 전량 WARN이 나므로, `TL_SPRD_MANAGE` LineString geometry를 적재해 도로 인접성 검증에 사용하도록 바꿨다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_shp_loader_gdal.py tests/unit/test_cli_contract.py -q` → 6 passed.
- `.venv/bin/python -m ruff check src/kraddr/geo/loaders/shp/polygons_loader.py src/kraddr/geo/cli/main.py tests/unit/test_shp_loader_gdal.py tests/unit/test_cli_contract.py` → 통과.
- 실패로 오염된 SHP 보조 테이블 9개만 drop 후 `KRADDR_GEO_PG_DSN=...15432 .venv/bin/kraddr-geo init-db` 재실행. MV 생성은 timeout 경고가 났지만 SHP 테이블 스키마는 `MULTIPOLYGON 5179`로 복구됨을 확인했다.
- `세종특별자치시` 실제 SHP 9개 레이어 적재 성공: 59.09초, 최대 RSS 약 128MiB, `tl_spbd_buld_polygon` 55,819행, `tl_sprd_intrvl` 100,009행 등 9개 테이블 row count 확인.
- 전국 SHP 153개 레이어 적재 성공: 3시간 1분 34초, 최대 RSS 약 181MiB. 정확한 row count는 `tl_spbd_buld_polygon` 10,687,732행, `tl_sprd_intrvl` 16,993,167행, `tl_sprd_rw` 1,482,679행 등으로 확인했다.

**다음 작업**: 변경분을 PR #14에 푸시하고, 같은 Docker DB에서 전국 `shp-all --mode full`을 재실행한다. 이후 pobox/bulk optional 단계, 링크 해소, MV swap, C1~C10 정합성, smoke test를 순서대로 계속 진행한다.

## 2026-05-24 (PR #14/T-027 — 실제 데이터로드 실행 중 포트 충돌 방지)

**작업**: PR #13이 main에 머지된 뒤 `codex/t027-fullload-execution` 브랜치에서 실제 데이터로드를 시작했다. WSL ext4 클론(`~/dev/python-kraddr-geo`)에서 Python/GDAL 환경을 만들고, `F:\dev\python-kraddr-geo\data` 원본을 `~/kraddr-geo-data` 작업 사본으로 복사했다.

**실행 로그**:
- 상세 실행 로그는 로컬 산출물 `artifacts/fullload/20260524_173115/execution-log.md`에 기록한다.
- 환경: WSL2 Ubuntu 24.04, AMD Ryzen 7 7840HS 16 vCPU, 메모리 29GiB, Docker 29.5.2, Docker Compose v5.1.4, Python 3.12.3, GDAL 3.8.4.
- `--copy-data` 시작 `2026-05-24T17:31:15+09:00`, 종료 `2026-05-24T18:35:47+09:00`, 경과 약 1시간 4분 32초.
- 복사 결과: `~/kraddr-geo-data/juso` 약 25GB, 파일 683개. `epost`는 현재 원본 파일이 없어 빈 디렉터리다.

**발견한 문제**:
- 로컬 5432 포트가 기존 `airflow-postgres-1` 컨테이너에서 이미 사용 중이었다.
- T-027 기본 compose/스크립트가 `localhost:5432`를 그대로 사용하면 기존 DB에 DDL/적재를 실행할 위험이 있다.

**보강 상세**:
- `docker-compose.yml`의 외부 포트를 `${KRADDR_GEO_DB_PORT:-5432}:5432`로 파라미터화했다.
- `scripts/fullload_test.sh`는 `KRADDR_GEO_PG_DSN`이 없을 때 `KRADDR_GEO_DB_PORT`를 반영한 DSN을 만든다.
- `docs/t027-fullload-plan.md`, `docs/dev-environment-recovery.md`, `CLAUDE.md`에 `KRADDR_GEO_DB_PORT=15432` 사용 예와 포트 충돌 주의사항을 추가했다.

**검증**:
- `bash -n scripts/fullload_test.sh` 통과.
- `DATA_DIR=/home/digitie/kraddr-geo-data KRADDR_GEO_DB_PORT=15432 PLAN_ONLY=1 bash scripts/fullload_test.sh` 통과. 출력 DSN이 `localhost:15432`로 바뀌는 것을 확인했다.
- `git diff --check` 통과.

**다음 작업**: PR 생성 후 `KRADDR_GEO_DB_PORT=15432`로 Docker PostGIS를 기동하고 실제 적재를 계속 진행한다. 이후 발견되는 문제는 같은 PR에 누적한다.

## 2026-05-24 (PR #13/T-027 — Windows 재설치·Codex 세션 복구 문서화)

**작업**: Windows 재설치 후 `git pull`로 PR #13 작업을 문제없이 이어갈 수 있도록 복구 절차를 문서화했다. 실제 Docker 전체 적재와 `PLAN_ONLY=1` 실행은 하지 않았다.

**보강 상세**:
- `docs/windows-reinstall-recovery.md`를 추가했다. Git branch/PR을 영속 상태의 기준으로 두고, `data/`·`.env`·API 키·WSL distro·Docker volume의 백업 여부를 구분했다.
- 재설치 후 WSL/GDAL/Python 환경 복구, PR #13 브랜치 checkout, `docs/t027-fullload-plan.md` 확인, `PLAN_ONLY=1 bash scripts/fullload_test.sh` preflight 순서를 명시했다.
- Codex 레벨 복구는 repo에 넣을 내용과 로컬 세션 편의 기능을 분리했다. 문서에는 일반적인 `codex resume`, `codex fork`, `codex doctor`, `codex cloud` 확인 명령과 `CODEX_HOME`/`.codex` 백업 주의사항만 남겼다.
- `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/dev-environment.md`, `docs/dev-environment-recovery.md`, `docs/resume.md`에서 새 복구 문서를 참조하도록 연결하고, 실제 적재는 사용자 명시 전 실행하지 않는 금지선을 맞췄다.

**다음 작업**: PR #13 리뷰 후에도 실제 전체 적재는 바로 실행하지 않는다. 먼저 문서와 스크립트 syntax 확인을 거친 뒤, 사용자가 허용하면 `PLAN_ONLY=1` preflight 결과를 PR에 공유한다.

## 2026-05-24 (PR #13/T-027 — Docker full-load 계획 보강)

**작업**: 사용자 지시에 따라 실제 Docker 전체 적재 실행은 중단하고, `F:\dev\python-kraddr-geo\data\juso` 전체를 대상으로 한 계획/문서/스크립트 preflight 보강만 진행했다. 로컬 파일 시스템은 목록과 용량만 확인했고 DB 적재·Docker 실행은 하지 않았다.

**확인한 데이터 인벤토리**:
- `data/juso` 전체는 약 28GB다.
- 현재 full-load에 바로 쓸 수 있는 자료는 `202603_도로명주소 한글_전체분`, `202604_위치정보요약DB_전체분.zip`, `202604_내비게이션용DB_전체분`, `도로명주소 전자지도`다.
- `daily/*.zip`, `jibun_rnaddrkor_*`, `건물군 내 상세주소 동 도형`, `구역의 도형`, `도로명주소 건물 도형`, `도로명주소 출입구 정보`는 현재 로더의 직접 적재 대상이 아니므로 후속 태스크로 분리했다.

**보강 상세**:
- `docs/t027-fullload-plan.md`를 실행 전 리뷰 가능한 계획서로 재작성했다. 실행 금지선, Docker project/volume 안전장치, 기준월 분리, phase별 중단·재개, 산출물 경로, 미지원 자료 후속 태스크를 명시했다.
- `scripts/fullload_test.sh`는 실행 산출물로 남기되 `PLAN_ONLY=1` preflight를 추가했다. 단일 `YYYYMM` 대신 `JUSO_YYYYMM`/`LOCSUM_YYYYMM`/`NAVI_YYYYMM`을 분리하고, CLI 호출은 `kraddr-geo` console script로 맞췄다.
- 초안 스크립트의 DDL inline SQL 실행을 `alembic upgrade head`로 바꾸고, 별도 적재 명령 뒤 누락될 수 있는 `resolve_text_geometry_links()`를 명시적으로 수행하도록 정리했다. MV 갱신은 full-load에 맞게 `refresh mv --swap`을 기본으로 둔다.
- smoke test는 실제 DTO 구조(`GeocodeResponse.result.point`, `ReverseResponse.result`, `SearchResponse.result`, `ZipcodeResponse.result`)에 맞게 보정했다.

**검증**:
- `bash -n scripts/fullload_test.sh` → 통과. 실제 DB/Docker 적재 실행은 하지 않았다.

**다음 작업**: PR #13 리뷰 후 `PLAN_ONLY=1 bash scripts/fullload_test.sh`만 먼저 실행한다. 전체 적재는 Docker 볼륨/로그 경로/중단 기준을 확인한 뒤 별도 지시가 있을 때 진행한다.

## 2026-05-24 (PR #12 리뷰 보강 — 보안·CI·에러 처리)

**작업**: PR #12 top-level 리뷰 코멘트를 확인했다. inline review thread는 없었고, GitHub 기준 mergeable 상태라 Git 충돌은 없었다. 다만 backend CI가 `scripts.export_openapi` import 실패로 깨졌고, 리뷰의 C/H/M 항목과 추가 코멘트의 프록시 스트리밍 항목을 모두 코드로 반영했다.

**구현 상세**:
- C1/C2: `/v1/admin/upload/sido-zip`에서 `sido`와 `filename`을 path token으로 정규화하고, resolved path가 `loader_data_dir/uploads` 밖으로 나가면 `InvalidInputError(E0100)`로 거절한다. `api_max_upload_bytes`(기본 2GiB)를 추가해 초과 업로드는 partial file 삭제 후 실패시킨다.
- H1/L1: Next.js 프록시는 `new URL()` 정규화 이후 `/v1/` 하위 경로만 허용하고, 전달 헤더를 `accept`/`content-type`/`user-agent`로 제한한다.
- 추가 코멘트: Next.js 프록시는 더 이상 `request.arrayBuffer()`로 업로드 본문 전체를 메모리에 올리지 않는다. GET/HEAD 외 요청은 `request.body` `ReadableStream`을 그대로 넘기고 Node.js fetch 요건에 맞춰 `duplex: "half"`를 설정한다.
- H2: `ApiError`를 추가해 HTTP status를 보존하고, React Query retry가 4xx를 재시도하지 않게 했다.
- H3: `/v1/admin/explain`은 실행 전 `set_config('statement_timeout', ..., true)`를 호출한다. 기본 timeout은 `api_explain_timeout_ms=3000`.
- M1~M3/L2/L3: `LoadConsole`, `ReverseDebugger`, `ConsistencyPanel` 에러 처리를 보강하고 빈 jobs 배열 finished 전이를 막았다.
- M4: Prometheus gauge 이름을 `kraddr_geo_cache_hits_total`에서 `kraddr_geo_cache_hits`로 변경했다.
- M5: `ExplainDebugger`가 `explainFormSchema`를 사용해 SELECT/WITH와 세미콜론 금지를 클라이언트에서도 검증한다.
- CI: `scripts/__init__.py`를 추가하고 pytest `pythonpath`에 repository root를 명시해 GitHub Actions의 pytest 수집 환경에서도 `scripts.export_openapi` import가 안정적으로 동작하게 했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kraddr/geo scripts/export_openapi.py` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json` → drift 없음
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 70 passed, 1 skipped
- 임시 DB `kraddr_geo_codex_pr12_review`에서 `KRADDR_GEO_TEST_PG_DSN=... pytest tests/integration/test_optional_real_postgres_load.py -q` → 실제 `data/juso` 샘플 COPY + MV 생성 1 passed
- `cd kraddr-geo-ui && npm run lint && npm run type-check && npm run test && npm run build` → 통과, Vitest 12 passed
- `cd kraddr-geo-ui && npm audit --omit=dev --audit-level=high && npm audit --audit-level=high` → high 기준 통과, moderate advisory만 잔여

**다음 작업**: PR #12 CI 재확인과 리뷰어 코멘트 답변.

## 2026-05-23 (PR #12 — T-021~T-026 프론트엔드·관측·CI 구현)

**작업**: PR #11을 main에 머지한 뒤, PR #11 후속 의견을 PR #12로 이관했다. PR #12 범위는 T-018~T-020이 main에 이미 포함된 상태에서 T-021~T-026을 실제 코드와 테스트로 마무리하는 것이다.

**구현 상세**:
- T-021: `kraddr-geo-ui` 패키지를 추가했다. Next.js 16(App Router), React 18, Tailwind, TanStack Query, `react-kakao-maps-sdk`, OpenAPI 타입 생성 스크립트(`npm run gen:types`)를 포함한다.
- T-022: `/debug/geocode`, `/debug/reverse`, `/debug/normalize`, `/debug/explain` 페이지를 구현했다. 모든 요청은 `/api/proxy/[...path]` Route Handler를 통해 백엔드 `/v1/*`로 전달한다. Kakao JS key가 없으면 지도는 좌표 프리뷰로 fallback한다.
- T-023: `/admin/load`, `/admin/tables`, `/admin/cache`, `/admin/logs` 페이지를 구현했다. full-load batch payload 등록, raw ZIP 업로드, MV refresh enqueue, 테이블 통계, 캐시 메트릭, `load_jobs.log_tail` 조회를 확인할 수 있다.
- T-024: 루트 `.pre-commit-config.yaml`과 `.github/workflows/ci.yml`을 추가했다. backend lint/type/import/test와 frontend type generation drift/lint/type/test/build를 분리된 job으로 검증한다.
- T-025: `infra/metrics.py`와 `/metrics` endpoint를 추가했다. 외부 API 호출 결과, cache entries/hits/expired, load job kind/state 분포를 Prometheus 포맷으로 노출한다.
- T-026: `/admin/consistency` 페이지를 추가했다. C1~C10 report 목록, 상세 case grid, 원본 JSON, 재검증 enqueue를 제공한다.
- FastAPI admin 라우터와 `AsyncAddressClient`에 `/v1/admin/tables`, `/v1/admin/explain`, `/v1/admin/cache/metrics`, `/v1/admin/logs`, `/v1/admin/upload/sido-zip`, `/v1/admin/maintenance/refresh-mv` 표면을 연결했다.

**결정**:
- ADR-019를 추가했다. 신규 프론트엔드는 Next.js 14가 아니라 Next.js 16을 보안 하한선으로 둔다. `npm audit --omit=dev --audit-level=high`가 통과해야 한다.
- `/v1/admin/upload/sido-zip`은 `python-multipart` 의존을 피하기 위해 multipart가 아닌 raw request body stream + query `filename` 형태로 구현했다. Next.js 프록시는 body를 `arrayBuffer()`로 읽어 그대로 전달한다.
- `ruff format --check`는 기존 파일 포맷 churn이 커서 PR #12 CI 범위에서 제외했다. 이번 PR은 `ruff check`, `mypy`, `lint-imports`, `pytest`를 품질 게이트로 삼는다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kraddr/geo scripts/export_openapi.py`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q`
- `KRADDR_GEO_TEST_PG_DSN=... .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` — 실제 `data/juso` 샘플 COPY와 MV 생성 검증
- `cd kraddr-geo-ui && npm ci && npm run gen:types && npm run lint && npm run type-check && npm run test && npm run build`
- `cd kraddr-geo-ui && npm audit --omit=dev --audit-level=high`

**다음 작업**: PR #12 리뷰 대기. 후속 후보는 `/admin/load` 업로드 진행률(XHR progress), `/admin/logs` streaming tail, `/debug/reverse` 지도 클릭 즉시 조회 UX다.

## 2026-05-23 (PR #11 follow-up — batch payload fail-fast 검증)

**작업**: PR #11 후속 확인 결과 GitHub review thread/comment는 없었지만, 원격 브랜치에 `AsyncAddressClient.submit_load("full_load_batch", ...)`를 `insert_load_batch`로 라우팅하는 보강 커밋이 추가되어 있었다. 해당 방향은 REST와 라이브러리 표면을 일치시키므로 타당하다고 판단했고, 그 위에 잘못된 batch payload가 `load_jobs`에 root + 빈 child를 먼저 남기는 문제를 추가로 막았다.

**구현 상세**:
- `infra.batch.batch_children()`에서 enqueue 전 payload 검증을 수행한다. 기본 `payloads` 경로는 ADR-017 source child 5종(`juso_text_load`, `locsum_load`, `navi_load`, `shp_polygons_load`, `pobox_load`) 모두에 `path` 또는 `source_path`가 있어야 한다.
- 명시 `children`/`child_jobs` 배열은 더 이상 잘못된 entry를 조용히 버리지 않는다. entry object, non-empty `kind`, object `payload`를 요구하고, 경로 기반 로더(`bulk_load` 포함)는 `path`/`source_path`가 없으면 `InvalidInputError(E0100)`를 던진다.
- `AsyncAddressClient.submit_load("full_load_batch", ...)`는 검증 실패 시 `AdminRepository.insert_load_batch`와 `insert_load_job` 어느 쪽도 호출하지 않으므로, 불완전한 batch root가 DB에 영속되지 않는다.
- `docs/backend-package.md`에 `full_load_batch` payload 예시와 검증 정책을 자세히 추가했다. REST와 라이브러리 표면이 같은 helper를 공유한다는 점을 명시했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_infra_batch.py tests/unit/test_client_submit_load_batch.py -q` → 14 passed.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 65 passed, 1 skipped.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kraddr/geo scripts/export_openapi.py` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json` → drift 없음.
- 임시 DB `kraddr_geo_codex_pr11_followup`에서 `KRADDR_GEO_TEST_PG_DSN=... pytest tests/integration/test_optional_real_postgres_load.py -q` 실행 → 실제 `data/juso` 샘플 COPY + MV 생성 1 passed.

**다음 작업**: PR #11에 후속 의견과 검증 결과를 남긴 뒤, 리뷰어가 원하면 payload schema를 OpenAPI DTO 수준에서 더 좁히는 작업을 별도 PR로 분리한다.

## 2026-05-23 (PR #11 리뷰 fixup — 라이브러리 batch DAG 비대칭 해소)

**작업**: PR #11 리뷰에서 발견된 라이브러리/REST 비대칭 이슈를 해결했다. `AsyncAddressClient.submit_load("full_load_batch", ...)`가 `AdminRepository.insert_load_job`을 직접 호출하던 경로를 `insert_load_batch`로 라우팅하여, 라이브러리 사용자도 REST `/v1/admin/loads`와 동일하게 root + 5종 child + DAG가 즉시 적재되도록 한다.

**구현 상세**:
- `src/kraddr/geo/infra/batch.py` 신규 모듈에 `BATCH_SOURCE_KINDS`와 `batch_children()`을 이동했다. `api/_jobs.py`의 동명 private 헬퍼는 제거하고 새 모듈을 import한다.
- `AsyncAddressClient.submit_load`는 `kind == "full_load_batch"`일 때 `batch_children(payload)`로 child 구성을 결정해 `AdminRepository.insert_load_batch`를 호출한다. 비-batch kind는 종전대로 `insert_load_job`을 사용한다.
- `infra/batch.py`는 `core/dto` 의존 없는 순수 모듈이라 client / api / loaders 어느 레이어에서도 import 가능. import-linter "Layered architecture" 컨트랙트 유지.

**검증**:
- `tests/unit/test_infra_batch.py` 신규 — default kind 순서, `payloads` 매핑 키, 명시 `children` 우선, 잘못된 entry drop을 검증.
- `tests/unit/test_client_submit_load_batch.py` 신규 — `AsyncMock`으로 `insert_load_batch` / `insert_load_job` 호출 분기를 검증.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp python -m pytest tests/unit/ -q` → 51 passed.
- `python -m ruff check`, `mypy --strict src/kraddr/geo/api/_jobs.py src/kraddr/geo/infra/batch.py src/kraddr/geo/client.py`, `lint-imports` 모두 통과.
- `python scripts/export_openapi.py --check` → drift 없음 (DTO 변경 없음).

**다음 작업**: T-021 프론트엔드 패키지 `kraddr-geo-ui` 부트스트랩.

## 2026-05-23 (codex, T-018~T-020 구현 + 신규 PR 준비)

**작업**: PR #10 리뷰 fixup 위에서 T-018~T-020을 추가 구현하고, 사용자 요청대로 P1/P2 리뷰 반영 사항과 T-005~T-020 완료 범위를 하나의 신규 PR로 등록할 준비를 진행했다.

**구현 상세**:
- T-018: CLI 운영 명령을 확장했다. `kraddr-geo load all-sidos`는 juso/locsum/navi 필수 경로와 선택 SHP/epost 보조 경로를 받아 직접 적재 → 링크 해소 → C1~C10 정합성 검증 → optional MV refresh까지 묶는다. `load shp`, `load shp-all`, `load pobox`, `load bulk`, `load epost --kind=full`, `refresh mv --swap`, `validate consistency --cases/--scope`도 추가했다.
- T-019: `infra/external_api.py`를 추가했다. `AsyncAddressClient.geocode(..., fallback="api")`는 로컬 DB 결과가 `NOT_FOUND`일 때만 외부 폴백을 호출한다. 호출 순서는 vworld 주소 좌표 API → juso 검색 API + 좌표 API다. 외부 응답은 기존 `GeocodeResponse`로 변환하며 공급자 출처는 `x_extension.source`에만 둔다.
- T-020: `scripts/export_openapi.py`를 추가해 `create_app().openapi()`를 `openapi.json`으로 내보낸다. `--check` 모드는 committed schema와 생성 결과가 다르면 실패한다. `.github/workflows/openapi.yml`은 PR마다 `.[api]` extra 설치 후 drift 검사를 실행한다.

**문서**:
- `docs/tasks.md`에서 T-018~T-020을 완료로 이동했다.
- `docs/resume.md`의 다음 작업을 T-021 프론트엔드 부트스트랩으로 갱신했다.
- `docs/backend-package.md`에 외부 API fallback 흐름과 OpenAPI export/CI drift 절차를 명시했다.
- `docs/external-apis.md`에 구현 위치, 호출 순서, 응답 매핑 정책을 보강했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 51 passed, 1 skipped. skipped 1건은 `KRADDR_GEO_TEST_PG_DSN` 미설정 시 건너뛰는 선택형 실제 PostgreSQL COPY 테스트다.
- `KRADDR_GEO_TEST_PG_DSN='postgresql+psycopg://postgres:postgres@localhost:5432/kraddr_geo_codex_t020_verify' .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` → 1 passed. 검증 후 `kraddr_geo_codex_t020_verify` DB는 삭제했다.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kraddr/geo scripts/export_openapi.py` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json` → 통과

## 2026-05-23 (codex, PR #10 리뷰 코멘트 반영)

**작업**: PR #10 상위 리뷰 코멘트의 P1/P2 항목을 반영했다. P1은 ADR-017 batch DAG, C1~C10 정합성 검증, PNU NULL guard이고, P2는 reverse `both`, 텍스트 인코딩 fallback, `load_jobs` 진행률/log_tail, `x_extension` ADR 문서화를 중심으로 처리했다.

**주요 변경**:
- `load_jobs`에 `load_batch_id`, `parent_job_id`를 추가하고 `full_load_batch` root job 아래 source load child 5종 → `consistency_check` → `mv_refresh(strategy='swap')` 순서로 이어지는 batch DAG를 구현했다.
- `JobQueue` handler 시그니처를 `(payload, cancel_event, progress_cb)`로 확장했다. `progress_cb`는 `progress`, `current_stage`, `heartbeat_at`, `log_tail`을 DB에 갱신한다.
- FastAPI lifespan에서 기본 handler를 등록한다. `juso_text_load`, `locsum_load`, `navi_load`, `shp_polygons_load`, `pobox_load`, `bulk_load`, `consistency_check`, `mv_refresh`가 큐에서 실제 실행된다.
- `loaders/consistency.py`를 C1~C10 전체 케이스로 확장했다. 각 케이스는 `count`, `ratio`, `threshold`, `metric`, `sample`을 채운다. C4/C6/C7/C9는 `ERROR` 판정 근거가 명시되어 batch swap gate로 쓸 수 있다.
- `tl_juso_text.pnu` generated column에 `mntn_yn IS NULL` 가드를 추가했다. 실제 `rnaddrkor_seoul.txt` 524,678건은 `bd_mgt_sn` 길이가 모두 26자리였으므로, 체크 제약은 `BETWEEN 25 AND 26`으로 좁혔다.
- reverse `type="both"`가 도로명과 지번 결과를 모두 반환하도록 보정했다.
- 텍스트 인코딩 감지는 BOM → CP949 검증 → UTF-8 검증 순서로 바꿨다.
- ADR-017(batch DAG)과 ADR-018(`x_extension` 스키마 격리)을 `docs/decisions.md`에 추가했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 47 passed, 1 skipped. skipped 1건은 `KRADDR_GEO_TEST_PG_DSN`이 없을 때만 건너뛰는 선택형 실제 PostgreSQL COPY 테스트다.
- `KRADDR_GEO_TEST_PG_DSN='postgresql+psycopg://postgres:postgres@localhost:5432/kraddr_geo_codex_pr10_fix' .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` → 1 passed. 검증 후 `kraddr_geo_codex_pr10_fix` DB는 삭제했다.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kraddr/geo` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept

**다음**: PR #10에 반영 요약과 검증 결과를 코멘트로 남긴다.

## 2026-05-23 (codex, T-005~T-017 일괄 구현 + 실제 파일/DB 검증)

**작업**: PR #7이 닫힌 뒤 최신 `origin/main`(`fa276dd`)에서 새 브랜치 `codex/t017-text-primary-load`를 만들고, ADR-012/ADR-016 기준으로 T-005부터 T-017까지 백엔드 1차 구현을 진행했다. 사용자의 추가 지시대로 `data/juso` 실제 파일을 반드시 열어 검증했고, 로컬 PostGIS에 별도 테스트 DB를 만들어 실제 샘플 COPY 적재와 MV 생성까지 확인했다.

**변경 파일(주요)**:
- 신규: `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_text_primary_postgis_schema.py`
- 신규: `src/kraddr/geo/infra/engine.py`, `infra/sql.py`, `infra/pnu.py`, `infra/geocode_repo.py`, `infra/reverse_repo.py`, `infra/search_repo.py`, `infra/zip_repo.py`, `infra/pobox_repo.py`, `infra/admin_repo.py`
- 신규: `src/kraddr/geo/core/protocols.py`, `core/normalize.py`, `core/geocoder.py`, `core/reverse_geocoder.py`, `core/searcher.py`, `core/zipcoder.py`, `core/poboxer.py`, `core/responses.py`
- 갱신: `src/kraddr/geo/client.py`, `src/kraddr/geo/__init__.py`, `src/kraddr/geo/dto/admin.py`, `src/kraddr/geo/cli/main.py`
- 신규: `src/kraddr/geo/api/app.py`, `api/_jobs.py`, `api/deps.py`, `api/responses.py`, `api/routers/*`
- 신규: `src/kraddr/geo/loaders/text/juso_hangul_loader.py`, `locsum_loader.py`, `navi_loader.py`, `loaders/shp/polygons_loader.py`, `shp/delta_loader.py`, `loaders/postload.py`, `loaders/consistency.py`, `loaders/pobox_loader.py`, `loaders/bulk_loader.py`, `loaders/manifest.py`
- 신규 테스트: `tests/unit/test_infra_engine_pnu_sql.py`, `test_core_geocoder.py`, `test_infra_repo_sql.py`, `test_api_app_contract.py`, `tests/integration/test_real_juso_text_loaders.py`, `test_optional_real_postgres_load.py`
- 갱신 문서: `docs/tasks.md`, `docs/resume.md`, `docs/data-model.md`, `docs/backend-package.md`, `CHANGELOG.md`

**구현 상세**:
- T-005: `make_async_engine()`은 `Settings.pg_dsn` 보정을 신뢰하고, statement timeout과 `search_path=public,x_extension`를 연결 옵션에 넣는다. PostGIS/pg_trgm/unaccent는 `x_extension` 스키마에 설치한다.
- T-006/T-007: DDL은 텍스트 4 + SHP polygon/폴리라인 9 + 우편번호 보조 2 + 메타 5 = 20개 테이블을 만든다. `mv_geocode_target`은 `pt_5179`, `pt_4326`, `pt_source`를 노출하고 `pt_5179 IS NOT NULL` partial GiST index를 둔다. `tl_juso_text.pnu`는 `COALESCE(lnbr_mnnm, 0)` 없이 필수 필드 결측 시 `NULL`을 반환한다.
- T-008~T-010: 주소 정규화(`parse_address`)와 geocode core/repo를 구현했다. 도로명 fuzzy는 트랜잭션 안에서만 `SET LOCAL pg_trgm.similarity_threshold`를 사용한다.
- T-011/T-016: `AsyncAddressClient`가 실제 raw SQL repo를 연결해 geocode/reverse/search/zipcode/pobox를 호출한다. load job과 consistency report 조회/등록/취소 표면도 추가했다.
- T-012/T-015: FastAPI 앱과 `/v1/address/*`, `/v1/admin/loads`, `/v1/admin/consistency/*` 라우터를 추가했다. `JobQueue`는 DB `load_jobs`를 기준으로 상태를 영속화하고 startup에서 잔존 `running`을 `failed` 처리한다. 실행 직전 `pg_try_advisory_xact_lock` + `FOR UPDATE SKIP LOCKED`로 다중 워커 중복 실행을 막는다.
- T-013a~c: 텍스트 로더는 실제 파일 기반 인덱스를 박아 `psycopg.copy()`로 적재한다. 위치정보요약DB 실제 ZIP은 `bd_mgt_sn`을 직접 제공하지 않으므로 natural key를 보관하고 후처리에서 `tl_juso_text`와 조인해 해소한다. 일부 위치정보요약DB 행은 X/Y가 비어 있어 `geom NOT NULL` 적재에서 제외한다.
- T-013d/T-014: SHP 보조 로더는 ADR-012 대상 9개 레이어만 load plan으로 만들며, GDAL Python binding은 실제 호출 시에만 import한다. delta merge는 `settings.mvm_res_code_actions` 또는 DB `load_codes`에서 온 action map을 받도록 설계했다.
- T-017: epost 보조 우편번호용 `postal_pobox`, `postal_bulk_delivery` COPY 로더를 추가했다.

**실제 파일 검증**:
- `data/juso/202603_도로명주소 한글_전체분/rnaddrkor_seoul.txt` 첫 25행을 실제 CP949로 읽어 `bd_mgt_sn`, `rncode_full`, 건물번호, 우편번호, PNU 매핑을 검증했다.
- `data/juso/202604_위치정보요약DB_전체분.zip`의 `entrc_seoul.txt` ZIP member를 직접 스트리밍해 `sig_cd`, `ent_man_no`, `rncode_full`, `ent_se_cd`, EPSG:5179 X/Y를 검증했다.
- `data/juso/202604_내비게이션용DB_전체분/match_build_seoul.txt`와 `match_rs_entrc.txt`를 읽어 centroid/진입점 좌표와 kind 매핑을 검증했다.
- `data/juso/도로명주소 전자지도/강원특별자치도`의 SHP/DBF 파일로 ADR-012 보조 9개 레이어 load plan을 검증했다.
- 로컬 PostgreSQL(PostGIS)에서 `kraddr_geo_codex_t017` 테스트 DB를 생성해 DDL 적용 → 실제 파일 샘플 COPY 적재 → `resolve_text_geometry_links()` → `mv_geocode_target` 생성까지 통과 확인 후 DB를 삭제했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 43 passed, 1 skipped. skipped 1건은 `KRADDR_GEO_TEST_PG_DSN`이 없을 때만 건너뛰는 선택형 실제 PostgreSQL COPY 테스트다.
- `KRADDR_GEO_TEST_PG_DSN='postgresql+psycopg://postgres:postgres@localhost:5432/kraddr_geo_codex_t017' .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` → 1 passed.
- `.venv/bin/python -m ruff check .` → 통과
- `.venv/bin/python -m mypy src/kraddr/geo` → 통과
- `.venv/bin/lint-imports` → Layered architecture kept

**다음**:
- T-018 CLI를 운영 워크플로 수준으로 완성한다. 이번 작업에서 `load juso/locsum/navi`, `refresh mv`, `validate consistency`, `jobs` 기본 명령은 추가했지만 `load all-sidos`, `load shp-all`, `load epost`, 업로드 batch CLI는 후속이다.
- T-020 OpenAPI export 전에 FastAPI optional extra가 설치되지 않은 환경의 import 실패 정책을 정리한다.

---

## 2026-05-23 (claude, 텍스트 정본 + SHP polygon 하이브리드 전환)

**작업**: ADR-005를 부분 supersede하고 ADR-012(텍스트 정본 1차 + SHP polygon 보조 하이브리드), ADR-016(적재 진행도/정합성 API), ADR-007 복원·재정의를 묶어 사양 단계에서 전환. 사용자 지시: NTFS의 `data/juso` 텍스트 자료 3종(도로명주소 한글_전체분, 위치정보요약DB_전체분, 내비게이션용DB_전체분) 활용으로 완성도 ↑.

**변경 파일**:
- `docs/decisions.md` — ADR-005에 partial supersede 표시 / ADR-007 복원(위치정보요약DB ent_se_cd 기반) / ADR-012 신규 / ADR-016 신규
- `docs/data-model.md` — 마스터 14개 구조로 전면 재작성. 텍스트 1차 4종(`tl_juso_text`, `tl_locsum_entrc`, `tl_navi_buld_centroid`, `tl_navi_entrc`)과 SHP polygon 7종으로 분리. 텍스트 파일 포맷·컬럼 매핑 명시. MV 정의를 텍스트 정본 + 대표 출입구 + centroid fallback + `pt_source` 컬럼으로 재정의. 정합성 케이스 C1~C10 분류표와 `load_consistency_reports` 테이블 추가.
- `docs/backend-package.md` §9 — `loaders/text/`, `loaders/shp/`, `loaders/consistency.py` 분리. `juso_hangul_loader.py` 구현 예시(stdlib csv + `psycopg.copy()`, 인코딩 감지, 진행률 callback). `tl_spbd_buld_polygon` 분리 적재 전략. §9.8(진행도 API), §9.9(정합성 API), §9.10(로그/리포트 정책) 신규.
- `docs/backend-package.md` §10 CLI — `kraddr-geo load juso/locsum/navi/shp`, `kraddr-geo validate consistency`, `kraddr-geo jobs list/status/cancel` 추가.
- `docs/tasks.md` — T-006(18개 테이블), T-007(MV 재정의), T-011(`AsyncAddressClient` 진행도 API), T-013을 T-013a~d로 분할. T-026(정합성 검증) 신규.
- `docs/resume.md` — ADR 확인 목록 갱신 (~ADR-016).
- `CHANGELOG.md` — 정책 전환 기록.

**결정**:
- ADR-012: 적재는 행안부 텍스트 정본 1차 + SHP polygon 보조 하이브리드. GDAL은 polygon 적재에만 사용. ADR-005의 GDAL Python binding 결정은 partial supersede.
- ADR-007 재정의: 대표 출입구 선택은 위치정보요약DB의 `ent_se_cd='0'` 기반. 출입구가 0개인 건물은 내비게이션용DB centroid fallback (MV의 `pt_source` 컬럼으로 출처 노출).
- ADR-016: 적재 진행도(`load_status`/`list_load_jobs`/`submit_load`/`cancel_load`)와 정합성 리포트(`run_consistency_check`/`consistency_report`)를 라이브러리·REST·디버그 UI에 일급으로 노출. C1~C10 케이스를 `load_consistency_reports` JSONB로 영속화.
- MV `mv_geocode_target` 컬럼명: `ent_pt_5179` → `pt_5179`, `ent_pt_4326` → `pt_4326` + `pt_source ∈ {entrance, centroid}` 추가.
- PNU 매핑(`mntn_yn 0→1, 1→2`, ADR-010)을 `tl_juso_text.pnu` generated stored column으로 박음.

**검증**: 문서 전용 변경. T-013a~T-013d(텍스트/SHP 분리 로더), T-026(정합성) 구현 시 reference.

**다음**: T-005 (`infra/engine.py`). 이후 T-006(DDL)부터 ADR-012의 14개 테이블 구조로 진행.

---

## 2026-05-23 (claude, 사양 리뷰 종합 반영)

**작업**: 두 차례 리뷰 의견(v1 기반 5건 + master 기반 5건)에 사용자 보완을 더해 사양 단계에서 미리 묶어 반영.

**변경 파일**:
- `SKILL.md` — §4 DO NOT 11~13 추가: (11) 공간 술어 형변환 금지·반경은 5179 meter, (12) bulk param 한도, (13) 작업 큐 영속화.
- `docs/data-model.md` — MV에 `idx_mv_geom5179` 추가 / "MV 갱신 모드" 절 (평시 CONCURRENTLY vs 분기 shadow MV swap, lock_timeout/인덱스 이름/권한/prepared statement invalidation 주의) / "공간 쿼리 가이드" (5179 meter 기준 CTE 예시, ent_pt_4326 응답 전용) / 행정 polygon 4326 변환 view (`v_kodis_bas_4326`, `v_scco_emd_4326`) / "PNU 조립" (mntn_yn 0/1 → 1/2, infra/generated column 위치) / "MVM_RES_CD 한 배치당 PK 단일화 가정" + 깨질 시 dedup CTE.
- `docs/architecture.md` — "적재 ↔ 서빙 단일 스키마 + MV" 강조 절.
- `docs/backend-package.md` §7.1 — engine factory DSN 보정 제거, settings.pg_dsn 신뢰. §9.7 — `load_jobs` 영속 테이블, lifespan recovery, advisory lock + FOR UPDATE SKIP LOCKED 패턴.
- `docs/decisions.md` — ADR-010(PNU 매핑 + 조립 위치 infra), ADR-011(작업 큐 `load_jobs` 영속화 + 다중 워커 안전성).
- `docs/tasks.md` — T-006/T-007/T-015에 본 ADR 인용.
- `docs/resume.md` — ADR 확인 목록 갱신.
- `CHANGELOG.md` — 정책 변경 기록.

**결정**:
- ADR-010: PNU 11번째 자리 매핑은 `0→1, 1→2`. 조립은 `infra/`(또는 generated stored column). `core/`는 의미론적 `mntn_yn`만 보관.
- ADR-011: `load_jobs` 별도 테이블에 작업 상태 영속화. lifespan startup에서 잔존 running→failed, queued는 payload 존재 여부에 따라 재큐잉/failed. 다중 워커 안전성은 `pg_try_advisory_lock` + `FOR UPDATE SKIP LOCKED`.
- 공간 쿼리: 반경/nearest는 5179(meter) 기준, 4326은 응답 전용. 술어 안에 `ST_Transform(t.geom, ...)` 금지.
- MV 갱신: 평시 CONCURRENTLY, 분기 풀로드는 shadow MV + RENAME swap (lock_timeout, prepared plan invalidation 명시).

**참고**: 본 변경은 모두 문서/사양 보강이며 코드 변경 없음. T-006/T-007/T-013/T-015 진행 시 본 ADR과 가이드를 reference로 적용.

**다음**: T-005 (`infra/engine.py`). 사양상 settings.pg_dsn을 그대로 신뢰하므로 구현 비용이 줄어듦.

---

## 2026-05-23 (codex, T-004 + 실제 SHP/DBF 검사)

**작업**: T-004 DTO 6종 구현 및 `data/juso/도로명주소 전자지도` 실제 파일 읽기 테스트 추가

**변경 파일**:
- 신규: `src/kraddr/geo/dto/geocode.py`, `src/kraddr/geo/dto/reverse.py`, `src/kraddr/geo/dto/search.py`, `src/kraddr/geo/dto/zipcode.py`, `src/kraddr/geo/dto/pobox.py`, `src/kraddr/geo/dto/admin.py`
- 신규: `src/kraddr/geo/loaders/juso_map.py`
- 신규: `tests/unit/test_dto_geocode.py`, `tests/unit/test_dto_reverse.py`, `tests/unit/test_dto_search_zipcode_pobox_admin.py`
- 신규: `tests/integration/test_juso_map_files.py`
- 갱신: `src/kraddr/geo/dto/__init__.py`, `pyproject.toml`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`

**결정**:
- DTO는 `docs/backend-package.md` §4의 wire contract를 우선해 pydantic v2 frozen model로 작성했다.
- `type` 필드는 vworld/API wire field이므로 DTO 파일별로 `A003` ruff ignore를 한정 적용했다.
- pydantic runtime이 nested DTO 타입을 해석해야 하므로 `GeocodeResponse`, `ReverseResultItem`, `SearchResultItem`의 address DTO imports는 runtime import로 유지하고 해당 파일에만 `TC001` ignore를 한정 적용했다.
- GDAL 적재 구현은 T-013 범위로 남긴다. 다만 이번 작업에서 순수 Python으로 SHP/DBF 헤더를 직접 열어 `강원특별자치도/51000`의 11개 마스터 레이어와 `TL_SPBD_BULD` 필드(`BD_MGT_SN`, `BULD_MNNM`, `MVM_RES_CD`, `RN_CD`, `SIG_CD` 등)를 검증했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 28 passed. 실제 파일 경로 `data/juso/도로명주소 전자지도/강원특별자치도/51000/*.shp|*.dbf|*.shx`를 열어 검사함.
- `.venv/bin/python -m ruff check .` → 통과
- `.venv/bin/python -m mypy src/kraddr/geo` → 통과
- `.venv/bin/lint-imports` → Layered architecture kept

**다음**: T-005 — `infra/engine.py` async engine factory + 통합 테스트 준비.

---

## 2026-05-23 (claude, epost 데이터셋 정책)

**작업**: 우편번호 외부 API 활용 정책을 ADR-009로 확정하고 관련 문서 보강.

**변경 파일**:
- `docs/decisions.md` — ADR-009 추가 (epost 15000302, `downloadKnd=1` 분기 1회 전체 적재. 실시간 lookup 15056971 미도입).
- `docs/external-apis.md` — epost 절 보강: 데이터셋 ID 15000302, `downloadKnd` 4종 표, 분기 1회 전체 적재 흐름, 미도입 API(15056971) 명시. 한눈에 표에도 데이터셋 ID + ADR 인용.
- `docs/data-model.md` — `postal_pobox`/`postal_bulk_delivery` 위에 epost 15000302 ZIP 적재 출처와 ADR-009 인용.
- `.env.example` — `KRADDR_GEO_EPOST_API_KEY` 위 주석에 데이터셋 ID + ADR-009 표기.
- `CHANGELOG.md` — `### Added`에 ADR-009 요약.

**결정**:
- ADR-009: 우편번호 매칭은 epost 데이터셋 15000302의 전체 ZIP(`downloadKnd=1`)을 **분기 1회** 받아 `postal_pobox`/`postal_bulk_delivery`를 TRUNCATE → INSERT. 변경분 누적 미운영. 실시간 lookup API(데이터셋 15056971) 미도입.

**검증**:
- 본 실행 환경(원격 컨테이너)은 `openapi.epost.go.kr` 외부망이 차단되어 직접 호출은 못 했다. 데이터셋 ID와 `downloadKnd` 4종 정의는 공공데이터포털 검색 결과로 확정. 사용자 WSL 환경에서 키 재발급 후 `curl ... -G --data-urlencode "downloadKnd=1"`로 응답을 마지막 점검 권장.
- 사용자가 채팅에 노출한 서비스 키는 즉시 재발급(또는 활용중지) 권장. 본 PR/문서/`.env.example`에 평문 커밋 없음.

**다음**: T-017(`pobox_loader.py`, `bulk_loader.py`) 구현 시 본 ADR을 reference로 적용. CLI에 `kraddr-geo load epost --kind=full` 같은 entry를 두고 운영은 systemd timer로 분기 트리거.

---

## 2026-05-23 (claude, GDAL 셋업 문서)

**작업**: PR #3 마무리 — GDAL 시스템 의존성을 문서로 못박는다.

**변경 파일**:
- 신규: `docs/dev-environment.md` (WSL ext4 기준 셋업, conda/Docker 대안)
- 갱신: `docs/geocoding-readiness.md` (체크리스트 0번 항목 — 시스템 GDAL 설치)
- 갱신: `docs/resume.md` ("알려진 함정"에 GDAL 버전 미스매치, `libgdal-dev` 누락)
- 갱신: `SKILL.md` §2 (빠른 시작에 `apt install libgdal-dev` + `gdal==$(gdal-config --version)` 핀 추가)
- 갱신: `pyproject.toml` (`loaders` extra 위 주석 — 시스템 의존성/Docker 권장)
- 갱신: `docs/decisions.md` (ADR-008 — 시스템 GDAL과 동일 버전 핀)

**결정**:
- ADR-008: `loaders` extra는 `pip install "gdal==$(gdal-config --version)"`로 시스템과 동일 버전 핀. 운영·CI는 `osgeo/gdal:*` Docker 베이스 표준화. ADR-005 보강.

**검증**: 문서 전용 변경이라 코드 테스트 영향 없음. T-013 진행 시 실제 GDAL 환경에서 `dev-environment.md` 절차로 재현 가능.

**다음**: T-004 (DTO 6종).

---

## 2026-05-23 (codex, 리뷰 3차 반영)

**작업**: PR 리뷰 반영 — 설정 싱글톤 helper 역할 분리

**변경 파일**:
- 갱신: `src/kraddr/geo/settings.py`, `tests/unit/test_settings.py`, `docs/backend-package.md`

**결정**:
- `reset_settings()`는 인자 없이 싱글톤을 비우는 역할만 맡는다.
- 테스트나 명시 주입이 필요할 때는 `set_settings(settings)`를 사용한다.

**다음**: 기존 다음 작업 유지 — T-004 나머지 DTO 작성.

---

## 2026-05-23 (codex, 리뷰 2차 반영)

**작업**: PR 리뷰 항목 5~10 반영 — DTO 필수성, validator 범위, CLI exit, ruff ignore, 예외명, namespace package 정리

**변경 파일**:
- 갱신: `src/kraddr/geo/dto/address.py`, `src/kraddr/geo/cli/main.py`, `src/kraddr/geo/exceptions.py`, `pyproject.toml`
- 갱신: `tests/unit/test_dto_address.py`, `tests/unit/test_exceptions.py`
- 갱신: `docs/backend-package.md`, `docs/decisions.md`
- 삭제: `src/kraddr/__init__.py`

**결정**:
- `RefinedAddress.structure`는 사양대로 필수 `AddressStructure`로 둔다.
- 빈 문자열 → `None` 변환 validator는 optional address fields에만 적용하고, `level0`은 빈 문자열을 명시적으로 거부한다.
- `typer.Exit`는 인스턴스(`raise typer.Exit()`)로 raise한다.
- `N815` ruff ignore는 vworld 호환 필드가 있는 `dto/address.py`에만 한정한다.
- base 예외명은 `KraddrGeoError`로 확정한다(ADR-014).
- `kraddr` parent는 PEP 420 implicit namespace package로 둔다(ADR-015).

**다음**: 기존 다음 작업 유지 — T-004 나머지 DTO 작성.

---

## 2026-05-23 (codex)

**작업**: PR 리뷰 반영 — 설정 기본값을 사양과 맞추고 README에 법적·데이터 사용 한계 추가

**변경 파일**:
- 갱신: `src/kraddr/geo/settings.py`, `.env.example`, `tests/unit/test_settings.py`, `README.md`

**결정**:
- `epost_download_url` 기본값은 브라우저 다운로드 페이지가 아니라 공공데이터포털 OpenAPI endpoint(`http://openapi.epost.go.kr/postal/downloadAreaCodeService/downloadAreaCodeService/getAreaCodeInfo`)로 둔다.
- `pg_statement_timeout_ms` 기본값은 사양값 5초(`5000`)로 둔다. 별도 ADR 없이 사양에 맞춘다.
- `api_default_radius_m` 기본값은 역지오코딩 hit rate를 위해 사양값 `200`으로 둔다.
- `api_cors_origins` 기본값은 빈 tuple로 둔다. localhost 허용은 `.env` override에서만 명시한다.
- README에 MIT 라이선스가 코드/문서에만 적용되고 외부 데이터/API 응답은 각 제공처 약관을 따른다는 한계를 명시했다.

**다음**: 기존 다음 작업 유지 — T-004 나머지 DTO 작성.

---

## 2026-05-22 (codex)

**작업**: T-001~T-003 구현 — Python 패키지 스캐폴드, 설정, 공통/주소 DTO와 단위 테스트 추가

**변경 파일**:
- 신규: `pyproject.toml`, `.env.example`
- 신규: `src/kraddr/__init__.py`, `src/kraddr/geo/__init__.py`, `src/kraddr/geo/version.py`, `src/kraddr/geo/py.typed`
- 신규: `src/kraddr/geo/settings.py`, `src/kraddr/geo/exceptions.py`, `src/kraddr/geo/client.py`, `src/kraddr/geo/cli/main.py`
- 신규: `src/kraddr/geo/dto/common.py`, `src/kraddr/geo/dto/address.py`
- 신규: `tests/unit/test_settings.py`, `tests/unit/test_dto_common.py`, `tests/unit/test_dto_address.py`
- 갱신: `CHANGELOG.md`, `docs/tasks.md`, `docs/resume.md`

**결정**:
- import-linter는 도구 제약상 `root_package = "kraddr"`와 `containers = ["kraddr.geo"]` 조합으로 설정한다. 이는 문서의 `kraddr.geo` 계층 계약과 같은 의미이며 실제 도구 실행이 통과하는 형태다.
- `AsyncAddressClient`와 CLI는 이번 범위에서 import/install 검증을 위한 자리표시자로만 둔다. 실제 지오코딩 기능은 T-010/T-011에서 구현한다.
- 사용자가 지정한 SHP 기준 경로 `data/juso/도로명주소 전자지도`를 확인했다. 강원도 샘플의 11개 DBF 필드는 문서의 마스터 레이어(`TL_SPBD_BULD`, `TL_SPBD_ENTRC`, `TL_SPRD_MANAGE` 등)와 맞는다.

**검증**:
- `pip install -e ".[dev]"` 통과
- `pip install -e ".[api,dev]"` 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 10 passed
- `.venv/bin/python -m ruff check .` → 통과
- `.venv/bin/python -m mypy src/kraddr/geo` → 통과
- `.venv/bin/lint-imports` → Layered architecture kept

**참고**:
- 현재 작업 디렉토리가 `/mnt/f` NTFS 위라 문서의 WSL/NTFS 경고가 그대로 적용된다. 기본 `TMP`/`TEMP`가 Windows Temp(`/mnt/c/...`)를 가리키면 pytest 캡처가 시작 전 실패하므로 검증 시 Linux `/tmp`를 명시했다.
- `loaders` extra는 현재 환경에 `gdal-config`가 없어 설치 검증하지 않았다. T-013에서 GDAL Python binding 설치 환경과 함께 별도 검증한다.

**다음**: T-004 — 나머지 DTO(`geocode`, `reverse`, `search`, `zipcode`, `pobox`, `admin`)와 단위 테스트 작성.

---

## 2026-05-22 (human, 추가 명시)

**작업**: 사용자 추가 지시 반영 — 프로젝트/패키지 식별자 정정, WSL/NTFS 개발 정책, 데이터 위치(NTFS의 `data/`) 명시

**변경 파일**:
- 갱신: `README.md`, `AGENTS.md`, `SKILL.md`, `CHANGELOG.md`, `docs/architecture.md`, `docs/backend-package.md`, `docs/code-guide-for-beginners.md`, `docs/geocoding-readiness.md`, `docs/reflection-summary.md` 외 일괄 치환 대상 전부

**결정**:
- 식별자 통일: GitHub 저장소 = `python-kraddr-geo`, Python import = `kraddr.geo`, CLI = `kraddr-geo`, env prefix = `KRADDR_GEO_`, PostgreSQL DB = `kraddr_geo`, 프론트엔드 패키지 = `kraddr-geo-ui`
- PC 개발은 WSL ext4 위에서, 작업 완료 시 NTFS로 카피. 데이터(`data/`)는 NTFS 측에만 두고 ext4 작업 디렉토리는 심볼릭 링크/절대경로로 참조
- 테스트(특히 통합/e2e/전국 검증)는 NTFS의 `data/`를 reference로 삼는다

**참고**: 이번 변경은 코드를 새로 만들기 전 사양 단계에서의 명확화이며, ADR은 추가하지 않음(향후 결정이 뒤집힐 때 ADR로 별도 기록).

**다음**: T-001 (`pyproject.toml` 신규 작성). pyproject.toml의 `name = "python-kraddr-geo"`, scripts `kraddr-geo = "kraddr.geo.cli.main:app"`, importlinter `root_package = "kraddr.geo"`로 시작.

---

## 2026-05-22 (human)

**작업**: 신규 사양(`kraddr.geo` 패키지의 PostgreSQL+PostGIS 재구현 + `kraddr-geo-ui` 프론트엔드)을 master 문서에 반영

**변경 파일**:
- 신규: `SKILL.md`, `CHANGELOG.md`
- 신규 (`docs/`): `architecture.md`, `decisions.md`, `data-model.md`, `tasks.md`, `resume.md`, `journal.md`, `backend-package.md`, `frontend-package.md`, `agent-guide.md`, `external-apis.md`
- 갱신: `AGENTS.md`, `README.md`, `docs/address-db-schema.md`, `docs/code-guide-for-beginners.md`, `docs/geocoding-readiness.md`, `docs/reverse-geocoding.md`, `docs/spatialite-vworld-implementation.md`
- 신규: `docs/reflection-summary.md` (반영 내용 요약)

**결정**:
- ADR-001 ~ ADR-006, ADR-013을 `docs/decisions.md`에 초기 기록
- 응답 구조는 vworld와 1:1 호환, 자체 확장은 `x_extension`만 (ADR-003)
- 라이브러리 API는 async-only (ADR-002)
- 로더는 GDAL Python binding 사용, `ogr2ogr` subprocess 폐기 (ADR-005)

**참고**: 첨부받은 두 docx 사양서가 우선이며, 기존 SpatiaLite 문서와 충돌하는 부분은 모두 PostgreSQL + PostGIS / `kraddr-geo` 기준으로 갱신함.

**다음**: T-001 (`pyproject.toml` 신규 작성).

---

## 2026-05-22 (human, 이전)

**작업**: 기존 SpatiaLite 기반 구현(`kraddr.geo`)을 `v1` 브랜치로 이관하고 master를 문서·repo 설정만 남도록 정리

**변경 파일**: 삭제 — `alembic/`, `alembic.ini`, `debug-ui/`, `pyproject.toml`, `src/`, `tests/`

**메모**: master는 새 사양으로 처음부터 다시 구현한다. 이전 구현은 `v1` 브랜치에서 참조 가능.
