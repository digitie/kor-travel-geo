# JOURNAL — 작업 일지

새 항목은 항상 파일 맨 위에 추가(역시간순). 기존 항목은 절대 수정하지 않는다 — 잘못된 결정조차 기록으로 남는 것이 가치다.

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
