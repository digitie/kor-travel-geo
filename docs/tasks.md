# TASKS — 백로그

작업 항목은 `T-NNN` 형식의 ID로 관리한다. 새 작업은 "대기"의 우선순위 순서대로 들어가고, 진행 중이 되면 담당자를 표시한다. 완료된 작업은 "완료" 섹션 상단에 누적한다.

## 진행 중
- 없음

## 대기 (우선순위 순)

2026-05-27 문서 정합성 재검토 기준 우선순위다. 운영 메타데이터(T-049)를 먼저 세워 T-045/T-046/T-047 산출물을 같은 감사·artifact·snapshot 축에 연결하고, 원천 선택/백업/보조 데이터/최종 적재/성능 gate를 처리한 뒤 지도 UI 경계화(T-044)를 진행한다.

- T-046 적재 완료 DB 백업/복원 및 UI — 전국 full-load를 매번 다시 돌리지 않고 검증된 DB 상태를 보존할 수 있도록 `pg_dump -Fd --jobs` directory dump를 임시 디렉터리에 만들고, metadata와 함께 `tar.zst` 압축 아카이브로 저장한다. plain SQL/DDL 덤프는 대용량 운영 기본값에서 제외한다. `db_backup`, `db_restore`는 백그라운드 job으로 실행하고, 사용자가 지정한 allowlist 하위 서버 경로에 저장하며, 진행률·log tail·취소·terminal callback·다운로드 링크를 `/admin/backups` UI에서 제공한다. 복원은 기본적으로 새 빈 DB에만 허용하고, 운영 DB 덮어쓰기는 maintenance mode와 명시 확인을 요구한다. 구현 검증은 전국 full-load가 아니라 대구광역시 부분 적재 DB로 backup → restore → row count/smoke test를 수행한다. 설계 문서: ADR-030, `docs/t046-db-backup-restore.md`
- T-042 `TL_SPPN_MAKAREA` 국가지점번호 보조 데이터 적재/조회 — `구역의 도형`의 지점번호표기 의무지역 polygon을 `tl_sppn_makarea` 별도 테이블로 적재한다. reverse geocode는 좌표 포함 여부를 `sppn_area` 보조 후보 또는 `x_extension.sppn_makarea`로 노출하고, geocode는 국가지점번호 문자열 parser/generator가 계산한 좌표를 의무지역 polygon으로 검증한다. 구현 전 문서 설계: ADR-027, `docs/t041-detail-zone-shape-layers.md`
- T-027 최종 실 데이터 클린 적재 검증 — 남은 튜닝/증분/보조 로더 작업을 모두 머지한 뒤 Docker DB를 삭제하고 처음부터 다시 적재한다. C1~C10 정합성, geocode/reverse/search/zipcode smoke test, data-quality export, 성능 로그를 최종 회귀 기준으로 남긴다. 상세: `docs/t027-fullload-plan.md`
- T-047 전국 적재 후 쿼리 성능 벤치마크와 튜닝 — T-027 클린 full-load DB에서 도로명 exact, 지번 exact, fuzzy geocode, 통합 search, reverse nearest/radius, zipcode, no-result 경로를 다수 반복 측정한다. p50/p95/p99, timeout, buffer, `EXPLAIN ANALYZE`, `pg_stat_statements`, 동시성 4/16/64 결과를 기록하고, 목표를 초과하면 인덱스, SQL 재작성, query split, KNN, 보조 view/materialized view를 적극 실험한다. 보조 객체는 source of truth가 아니라 read-only serving accelerator로만 허용하며, refresh/swap·디스크·백업 영향까지 기록한다. 설계 문서: ADR-031, `docs/t047-query-performance-tuning.md`
- T-044 디버그 UI를 최신 `maplibre-vworld-js` 기반 domain wrapper로 경계화 — `kraddr-geo-ui/components/vworld/CoordinateMap.tsx`의 직접 MapLibre wiring을 upstream `digitie/maplibre-vworld-js`의 최신 `VWorldMap` 또는 동등한 재사용 컴포넌트/Hook으로 대체한다. upstream에는 VWorld layer/style, marker primitive, click/error/flyTo hook, tile error redaction, package export/type/CSS처럼 다른 소비자도 재사용할 수 있는 범용 기능만 둔다. `(lon, lat)` 디버그 입력 연결, key 미설정 fallback 문구와 layout, 정합성/성능/적재 overlay, transient overlay 임계치처럼 `python-kraddr-geo` 특화 기능은 이 저장소의 domain wrapper에서 구현한다. upstream에 부족한 범용 기능·타입·패키징·Next.js 호환 문제가 있으면 `maplibre-vworld-js` 저장소를 직접 수정하고 별도 PR을 올린 뒤, 항상 최신 `main` 또는 stable release를 확인해 검증된 SHA로 dependency를 갱신한다. 완료 시 `kraddr-geo-ui` lint/type/test/build와 upstream test/build 결과, 변경 SHA, 책임 경계, 남은 차이를 문서화한다.

## 완료
- [x] T-045 원천 자료 기준월 선택과 대용량 업로드/적재 UX. `SourceCandidate`/`SourceSetDiscovery`/`SourceSetPlan`/`UploadSetStatus`/`UploadFileStatus` DTO, `infra.source_set` 탐지·계획 helper, JSON manifest 기반 upload set 저장소, `/v1/admin/uploads/*`와 `/v1/admin/load-sources/*` REST API, `AsyncAddressClient` 메서드, `kraddr-geo load full-set`, `/admin/load` 다중 파일/DND 업로드와 기준월 확인 modal을 구현했다. 혼합 기준월은 정확한 token 없이는 plan 생성이 실패하고, batch payload에는 source set 감사 필드와 명시 child job 목록이 남는다. 상세: `docs/t045-source-set-load-ux.md` (2026-05-27)
- [x] T-049 운영 메타데이터·감사·릴리스 스키마 구현. `ops` 스키마와 `ops.audit_events`, `ops.dataset_snapshots`, `ops.serving_releases`, `ops.artifacts`, `ops.maintenance_windows`, `ops.table_stats_snapshots` DDL/Alembic migration을 추가했다. `/v1/admin/ops/*` API, `AsyncAddressClient` 메서드, `/admin/ops` 관리 UI, audit redaction/hash helper, active release partial unique index, append-only audit trigger, table stats snapshot capture, typed maintenance confirmation hash를 함께 구현했다. secret/DSN/token/address 원문이 audit payload에 남지 않는 테스트를 추가했다. 상세: `docs/t049-ops-metadata-schema.md` (2026-05-27)
- [x] T-043 PR #23~#41 리뷰 코멘트 일괄 audit/fixup. GitHub conversation comment, formal review body, flat inline comment, GraphQL reviewThreads를 모두 재확인했고 unresolved thread가 0개임을 기록했다. PR #23/#24/#25/#28/#32/#33의 소규모 반영 가능 항목을 코드/문서에 직접 반영하고, 나머지는 T-049/T-045/T-042/T-027/T-047/T-044 후속으로 이관했다. 상세: `docs/postmerge-review-fixups-pr23-latest.md` (2026-05-27)
- [x] T-048 `maplibre-vworld-js` 최신 동기화와 책임 경계 재정의. `kraddr-geo-ui`의 `maplibre-vworld` dependency를 upstream `main` 최신 commit `1a28b1099ab6c9c03e892e469974aee8c07deda1`로 갱신하고, ADR-032로 "공용 VWorld/MapLibre 기능은 upstream, 지오코딩/역지오코딩/관리 UI 특화 기능은 이 저장소" 원칙을 확정했다. 최신성 확인 명령과 frontend 검증 기준을 문서화했다. (2026-05-27)
- [x] T-037 geometry 포함 SHP 대형 레이어 적재 튜닝. `TL_SPBD_BULD`를 운영 테이블 직접 append 대신 projection staging table + 운영 테이블 insert-select 경로로 분기했다. 세종 단일 레이어는 기존 38.36초에서 18.59초로 줄었고, 경기도 1,649,975행은 40분 17.15초에 성공했다. 상세: `docs/t037-shp-geometry-tuning.md` (2026-05-26)
- [x] T-041 상세주소 동 도형/구역 추가 레이어 검토. 세종/경남 실제 `건물군 내 상세주소 동 도형`이 전자지도 `TL_SPBD_BULD`의 부분집합임을 확인했고, `구역의 도형` 중 기존 행정/기초구역 5개 레이어는 전자지도와 key 기준 완전 중복임을 확인했다. `TL_SCCO_GEMD`는 별도 overlay/분석 후보로 보류하고, `TL_SPPN_MAKAREA`는 ADR-027에서 국가지점번호 보조 데이터 후보로 승격했다. 상세: `docs/t041-detail-zone-shape-layers.md` (2026-05-26)
- [x] T-040 `도로명주소 건물 도형` bundle 비교. 세종/경남 실제 `TL_SGCO_RNADR_MST`, `TL_SPBD_ENTRC`, `TL_SPOT_CNTC`를 전자지도 `TL_SPBD_BULD`/`TL_SPBD_ENTRC`와 natural key로 비교했고, 단순 중복이 아니므로 현행 serving table에는 섞지 않기로 ADR-025에서 결정했다. 비교 helper/script와 실제 파일 테스트를 추가했다. 상세: `docs/t040-building-shape-bundle.md` (2026-05-26)
- [x] T-039 `도로명주소 출입구 정보` direct entrance loader 구현. `RNENTDATA_2605_*.txt`를 `tl_roadaddr_entrc`에 별도 적재하고, MV 대표 좌표는 `tl_roadaddr_entrc` → `tl_locsum_entrc` → `tl_navi_buld_centroid` 순서로 선택한다. 실제 전국 17개 ZIP 6,418,169행 구조, 세종 유효 좌표 27,779행, Docker DB 샘플 적재와 MV 우선순위를 검증했다. 상세: `docs/t039-roadaddr-entrance-loader.md` (2026-05-26)
- [x] T-038 `tl_juso_parcel_link` DDL/로더 구현. `jibun_rnaddrkor_*` full snapshot과 daily `TH_SGCO_RNADR_LNBR.TXT` delta를 별도 1:N 테이블에 적재하고, CLI/API job kind/full-load batch/UI 기본 payload를 연결했다. 실제 Docker DB에서 `jibun_rnaddrkor_seoul.txt`와 `20260401_dailyjusukrdata.zip` LNBR 샘플 적재를 검증했다. 상세: `docs/t038-parcel-link-loader.md` (2026-05-26)
- [x] T-030 상세주소 동 도형/별도 건물 도형 로더 검토. 세종 실제 ZIP 기준으로 `건물군 내 상세주소 동 도형`, `구역의 도형`, `도로명주소 건물 도형`, `도로명주소 출입구 정보`의 layer/geometry/text 구조를 확인하고, 기본 full-load에 즉시 섞지 않고 T-039~T-041로 분리하기로 ADR-023에서 확정했다. 상세: `docs/t030-extra-shape-sources.md` (2026-05-26)
- [x] T-029 `jibun_rnaddrkor_*` 활용 여부 결정. 실제 전국 `jibun_rnaddrkor_*` 1,769,370행과 daily `LNBR` 구조를 확인하고, `tl_juso_text.pnu`에 덮어쓰지 않고 후속 `tl_juso_parcel_link` 1:N 테이블로 분리하기로 ADR-022에서 확정했다. 상세: `docs/t029-jibun-rnaddrkor-decision.md` (2026-05-26)
- [x] T-028 일변동 ZIP 로더. `data/juso/daily/*.zip`의 `TH_SGCO_RNADR_MST.TXT`를 `tl_juso_text`에 UPSERT/DELETE로 적용하고, `TH_SGCO_RNADR_LNBR.TXT`는 T-038 전까지 manifest에 미지원 행 수로 기록한다. 실제 `20260401_dailyjusukrdata.zip` MST 422행과 `20260404` `No Data` member를 검증했다. 상세: `docs/t028-daily-juso-delta.md` (2026-05-26)
- [x] PR #20~#22 post-merge 리뷰 반영. PR #22 → PR #21 → PR #20 순서로 리뷰 코멘트를 확인하고, T-035 benchmark metadata/public helper/lock timeout, T-034 DBF COPY 오류 문맥/row dataclass/deleted record test, T-033 full-load phase timer/C10 설명을 보강했다. 상세: `docs/postmerge-review-fixups-pr20-pr22.md` (2026-05-26)
- [x] T-036 `maplibre-vworld-js` main 동기화. `kraddr-geo-ui`의 `maplibre-vworld` dependency를 upstream main commit `c91c9f304669ce3f5fc4915f21186b23731d5816`로 갱신하고, `redactVWorldUrl()` helper를 기존 내부 이름 `redactVWorldTileUrl`로 alias해 디버그 UI 계약을 유지했다. 최신 upstream redaction 표기 `***`를 테스트로 고정하고 frontend `npm ci`/lint/type/test/build를 검증했다. 상세: `docs/t036-maplibre-vworld-sync.md` (2026-05-26)
- [x] T-035 MV refresh/swap 벤치마크. `scripts/benchmark_mv_refresh.py`로 전국 DB `kraddr_geo_t033`에서 `CONCURRENTLY`와 shadow swap을 비교했다. `CONCURRENTLY`는 1분 49.64초, shadow swap은 2분 16.28초였고, swap rename/index rename 구간은 약 0.016초였다. `shadow_swap_mv()`는 `ANALYZE`를 별도 transaction으로 분리했다. 상세: `docs/t035-mv-refresh-benchmark.md` (2026-05-26)
- [x] T-034 SHP GDAL append 병목 튜닝. `TL_SPRD_INTRVL`은 geometry 없는 DBF 속성 레이어라 GDAL append 대신 직접 DBF scan + `psycopg COPY` 경로로 분기했다. 세종 단일 레이어는 36.12초에서 1.59초로 줄었고, 경기도 2,677,715행은 새 경로에서 15.88초에 적재됐다. 상세: `docs/t034-shp-append-tuning.md` (2026-05-26)
- [x] T-033 전국 full-load 성능 재검증. PR #20에서 `kraddr_geo_t033` 빈 DB에 실제 전국 데이터 full-load를 수행했다. 전체 4시간 8분 2초, SHP 153 layers, MV 6,416,637행, smoke test 통과, data-quality CSV 8개 export를 기록했다. 상세: `docs/t033-full-load-revalidation.md` (2026-05-26)
- [x] T-032 full-load/정합성 성능 튜닝. PR #19에서 C4/C6/C7 중복 공간 스캔 제거, 정합성 CTE materialization, SHP 다중 시도 적재 마지막 1회 `ANALYZE`, postload timeout 보강, 세종특별시·경상남도 축소 검증 1회를 완료했다. 전국 full test와 반복 trial은 T-033~T-035로 분리했다. 상세: `docs/t032-performance-tuning.md` (2026-05-25)
- [x] T-031 T-027 데이터 품질 후속 분석. PR #17에서 C2/C4/C6/C7 CSV export CLI, SHP `source_file` 추적성, 실제 Docker DB 1차 실행 결과를 정리했다. 상세: `docs/t027-data-quality-followup.md` (2026-05-25)
- [x] T-026 디버그 UI `/admin/consistency` 페이지 구현. `GET /v1/admin/consistency`, `GET /v1/admin/consistency/{report_id}`, `POST /v1/admin/consistency/run`을 사용해 C1~C10 리포트 목록, 케이스별 severity/count, 원본 JSON을 확인한다 (2026-05-23)
- [x] T-025 `prometheus-client` 메트릭 구현. 외부 API 호출 success/failure counter, `geo_cache` entries/hits/expired gauge, `load_jobs` kind/state gauge를 `/metrics`에서 노출한다. 라이브러리 단독 설치 환경에서는 no-op fallback으로 import 실패를 피한다 (2026-05-23)
- [x] T-024 `pre-commit`, `import-linter`, `mypy` CI 정착. 루트 `.pre-commit-config.yaml`과 `.github/workflows/ci.yml`을 추가하고 backend/frontend lint·type-check·test·build·OpenAPI type drift 검사를 묶었다 (2026-05-23)
- [x] T-023 프론트엔드 `/admin/load`, `/admin/tables`, `/admin/cache`, `/admin/logs` 구현. full-load batch payload 입력, raw ZIP 업로드, MV refresh enqueue, 테이블 통계, 캐시 메트릭, `load_jobs.log_tail` 조회를 제공한다 (2026-05-23)
- [x] T-022 프론트엔드 `/debug/geocode`, `/debug/reverse`, `/debug/normalize`, `/debug/explain` 구현. 지오코딩/역지오코딩/정규화/EXPLAIN 요청을 Next.js Route Handler 프록시로 백엔드에 전달하고 JSON 응답을 즉시 확인한다 (2026-05-23)
- [x] T-021 프론트엔드 패키지 `kraddr-geo-ui` 부트스트랩. Next.js 16 + React 18 + Tailwind + TanStack Query + MapLibre GL JS + VWorld WMTS + OpenAPI 타입 생성 스크립트 기반의 별도 Node.js 패키지를 추가했다. `digitie/maplibre-vworld-js`는 범용 VWorld/MapLibre 문제 발생 시 적극 수정 대상으로 둔다 (2026-05-23, 2026-05-25 갱신)
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
