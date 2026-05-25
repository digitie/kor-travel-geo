# TASKS — 백로그

작업 항목은 `T-NNN` 형식의 ID로 관리한다. 새 작업은 "대기"의 우선순위 순서대로 들어가고, 진행 중이 되면 담당자를 표시한다. 완료된 작업은 "완료" 섹션 상단에 누적한다.

## 진행 중
- 없음

## 대기 (우선순위 순)
- T-034 SHP GDAL append 병목 튜닝 — 두 시도 축소 검증에서도 시간을 지배한 `TL_SPRD_INTRVL`, `TL_SPBD_BULD` 적재를 별도로 계측한다. `PG_USE_COPY=YES`가 실제 COPY 경로로 적용되는지 로그와 `pg_stat_activity`로 확인하고, 필요하면 `TL_SPRD_INTRVL` 전용 COPY 로더 또는 GDAL 옵션 분리를 검토한다.
- T-035 MV refresh/swap 벤치마크 — `REFRESH MATERIALIZED VIEW CONCURRENTLY`와 shadow MV build + rename swap을 같은 데이터셋에서 비교한다. lock wait, 임시 파일/I/O, index build 시간, `idx_mv_*` rename 복구 경로를 함께 기록해 운영 점검 창 기준을 만든다.
- T-036 `maplibre-vworld-js` main 동기화 — 현재 `kraddr-geo-ui`는 `digitie/maplibre-vworld-js#11321fe`에 고정되어 있으나 upstream main은 `1d87eca`까지 진행됐다. 최신 main을 확인하고, dependency SHA 갱신·타입/테스트/문서 반영을 별도 PR로 진행한다.
- T-028 일변동 ZIP 로더 — `data/juso/daily/*.zip`를 full-load 이후 증분 적용할 수 있도록 파일 구조 분석, `MVM_RES_CD` 매핑, 재실행 안전성을 설계한다.
- T-029 `jibun_rnaddrkor_*` 활용 여부 결정 — 도로명주소 한글 전체분에 같이 배포되는 지번 매핑 텍스트를 현재 `tl_juso_text`와 어떻게 조화시킬지 ADR로 확정한다.
- T-030 상세주소 동 도형/별도 건물 도형 로더 검토 — `건물군 내 상세주소 동 도형`, `구역의 도형`, `도로명주소 건물 도형`, `도로명주소 출입구 정보`의 전자지도 SHP와 중복·보완 관계를 조사한다.
- T-027 최종 실 데이터 클린 적재 검증 — 남은 튜닝/증분/보조 로더 작업을 모두 머지한 뒤 Docker DB를 삭제하고 처음부터 다시 적재한다. C1~C10 정합성, geocode/reverse/search/zipcode smoke test, data-quality export, 성능 로그를 최종 회귀 기준으로 남긴다. 상세: `docs/t027-fullload-plan.md`

## 완료
- [x] T-033 전국 full-load 성능 재검증. PR #20에서 `kraddr_geo_t033` 빈 DB에 실제 전국 데이터 full-load를 수행했다. 전체 4시간 8분 2초, SHP 153 layers, MV 6,416,637행, smoke test 통과, data-quality CSV 8개 export를 기록했다. 상세: `docs/t033-full-load-revalidation.md` (2026-05-26)
- [x] T-032 full-load/정합성 성능 튜닝. PR #19에서 C4/C6/C7 중복 공간 스캔 제거, 정합성 CTE materialization, SHP 다중 시도 적재 마지막 1회 `ANALYZE`, postload timeout 보강, 세종특별시·경상남도 축소 검증 1회를 완료했다. 전국 full test와 반복 trial은 T-033~T-035로 분리했다. 상세: `docs/t032-performance-tuning.md` (2026-05-25)
- [x] T-031 T-027 데이터 품질 후속 분석. PR #17에서 C2/C4/C6/C7 CSV export CLI, SHP `source_file` 추적성, 실제 Docker DB 1차 실행 결과를 정리했다. 상세: `docs/t027-data-quality-followup.md` (2026-05-25)
- [x] T-026 디버그 UI `/admin/consistency` 페이지 구현. `GET /v1/admin/consistency`, `GET /v1/admin/consistency/{report_id}`, `POST /v1/admin/consistency/run`을 사용해 C1~C10 리포트 목록, 케이스별 severity/count, 원본 JSON을 확인한다 (2026-05-23)
- [x] T-025 `prometheus-client` 메트릭 구현. 외부 API 호출 success/failure counter, `geo_cache` entries/hits/expired gauge, `load_jobs` kind/state gauge를 `/metrics`에서 노출한다. 라이브러리 단독 설치 환경에서는 no-op fallback으로 import 실패를 피한다 (2026-05-23)
- [x] T-024 `pre-commit`, `import-linter`, `mypy` CI 정착. 루트 `.pre-commit-config.yaml`과 `.github/workflows/ci.yml`을 추가하고 backend/frontend lint·type-check·test·build·OpenAPI type drift 검사를 묶었다 (2026-05-23)
- [x] T-023 프론트엔드 `/admin/load`, `/admin/tables`, `/admin/cache`, `/admin/logs` 구현. full-load batch payload 입력, raw ZIP 업로드, MV refresh enqueue, 테이블 통계, 캐시 메트릭, `load_jobs.log_tail` 조회를 제공한다 (2026-05-23)
- [x] T-022 프론트엔드 `/debug/geocode`, `/debug/reverse`, `/debug/normalize`, `/debug/explain` 구현. 지오코딩/역지오코딩/정규화/EXPLAIN 요청을 Next.js Route Handler 프록시로 백엔드에 전달하고 JSON 응답을 즉시 확인한다 (2026-05-23)
- [x] T-021 프론트엔드 패키지 `kraddr-geo-ui` 부트스트랩. Next.js 16 + React 18 + Tailwind + TanStack Query + MapLibre GL JS + VWorld WMTS + OpenAPI 타입 생성 스크립트 기반의 별도 Node.js 패키지를 추가했다. `digitie/maplibre-vworld-js`는 문제 발생 시 적극 수정 대상으로 둔다 (2026-05-23, 2026-05-25 갱신)
- [x] T-020 OpenAPI export 스크립트 + `openapi.json` 생성 + GitHub Actions drift 검사 (`scripts/export_openapi.py`, `.github/workflows/openapi.yml`) 구현 (2026-05-23)
- [x] T-019 외부 API 폴백(`fallback="api"`) — vworld 주소 좌표 API와 juso 검색+좌표 API 어댑터 구현. 로컬 `NOT_FOUND`일 때만 호출하고 `x_extension.source`에 공급자 출처 기록 (2026-05-23)
- [x] T-018 CLI 운영 명령 구현 — `load all-sidos`, `load shp`, `load shp-all`, `load pobox`, `load bulk`, `load epost --kind=full`, `refresh mv --swap`, `validate consistency --cases/--scope` (2026-05-23)
- [x] PR #10 리뷰 fixup: ADR-017 batch DAG(`load_batch_id`, `parent_job_id`, `full_load_batch`), C1~C10 정합성 검증, PNU `mntn_yn IS NULL` guard, reverse `both`, 인코딩 fallback, `load_jobs.log_tail` 갱신 경로, ADR-018 문서화 (2026-05-23)
- [x] T-017 `loaders/pobox_loader.py`, `loaders/bulk_loader.py` (epost 보조 우편번호 COPY 로더) 구현 (2026-05-23)
- [x] T-016 reverse / search / zipcode / pobox 코어와 raw SQL repo, REST 라우터 구현 (2026-05-23)
- [x] T-015 `api/_jobs.py` 작업 큐(`load_jobs` 영속화, startup running 복구, advisory lock + `FOR UPDATE SKIP LOCKED`)와 `/v1/admin/loads`, `/v1/admin/consistency/*` 표면 구현 (2026-05-23)
- [x] T-014 `loaders/shp/delta_loader.py` (settings/DB 기반 `MVM_RES_CD` action 매핑을 받는 polygon delta merge helper) 구현 (2026-05-23)
- [x] T-013d `loaders/shp/polygons_loader.py` (GDAL `VectorTranslate`, ADR-012 보조 SHP 9종 load plan) 구현 + 실제 강원 SHP load plan 검증 (2026-05-23)
- [x] T-013c `loaders/text/navi_loader.py` (내비게이션용DB centroid + 진입점 parser/COPY) 구현 + 실제 서울 파일 검증 (2026-05-23)
- [x] T-013b `loaders/text/locsum_loader.py` (위치정보요약DB 출입구 좌표 parser/COPY, `bd_mgt_sn` 후해소 구조) 구현 + 실제 ZIP member 검증 (2026-05-23)
- [x] T-013a `loaders/text/juso_hangul_loader.py` (도로명주소 한글_전체분 parser/COPY, NULL-safe PNU 검증) 구현 + 실제 서울 파일 검증 (2026-05-23)
- [x] T-012 `api/app.py`, geocode/reverse/search/zipcode/pobox/admin 라우터 구현 (2026-05-23)
- [x] T-011 `AsyncAddressClient` 실제 engine/repo 연결, geocode/reverse/search/zipcode/pobox/load/consistency 메서드 구현 (2026-05-23)
- [x] T-010 `core/geocoder.py` 구현 + Fake repo 단위 테스트 (2026-05-23)
- [x] T-009 `core/normalize.py` 주소 정규화 순수 함수 구현 (2026-05-23)
- [x] T-008 `infra/geocode_repo.py` 및 reverse/search/zip/pobox/admin raw SQL repo 구현 (2026-05-23)
- [x] T-007 `mv_geocode_target` MV 정의(`pt_5179`/`pt_4326`/`pt_source`, partial GiST index) + 실제 PostgreSQL 샘플 load/MV 생성 검증 (2026-05-23)
- [x] T-006 텍스트 4 + SHP polygon/폴리라인 9 + 보조 2 + 메타 5 = 20개 테이블 DDL + Alembic 0001 작성. `tl_juso_text.pnu` NULL-safe generated column, `load_jobs`, `load_consistency_reports` 포함 (2026-05-23)
- [x] T-005 `infra/engine.py` async engine factory 작성 (`Settings.normalize_pg_dsn` 신뢰, `x_extension` search_path, statement timeout) (2026-05-23)
- [x] T-004 `dto/geocode.py`, `dto/reverse.py`, `dto/search.py`, `dto/zipcode.py`, `dto/pobox.py`, `dto/admin.py` 작성 (2026-05-23)
- [x] T-003 `dto/common.py`, `dto/address.py` 작성 + 단위 테스트 (2026-05-22)
- [x] T-002 `Settings` (pydantic-settings) + `.env.example` 작성 (2026-05-22)
- [x] T-001 `pyproject.toml` 작성 (`kraddr-geo` 패키지, optional extras `api`/`loaders`/`dev`) (2026-05-22)

## 사양 참조
- 백엔드 세부: `docs/backend-package.md`
- 프론트엔드 세부: `docs/frontend-package.md`
- 데이터 모델: `docs/data-model.md`
- 외부 API: `docs/external-apis.md`
