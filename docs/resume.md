# RESUME — 작업 재개 가이드

새 에이전트 세션이 시작될 때 "지금 어디까지 했고, 다음은 뭐 하면 되나"를 한 화면에서 답한다.

## 현재 진척도 (2026-05-27 갱신, by codex)

- ✅ 이전 SpatiaLite 기반 `kraddr.geo` 구현을 `v1` 브랜치로 이관
- ✅ `main` 브랜치를 문서·repo 설정만 남도록 정리
- ✅ 신규 사양(`kraddr.geo` 패키지의 PostgreSQL+PostGIS 재구현 + `kraddr-geo-ui` 프론트엔드) 문서 골격을 `main`에 반영
- ✅ 식별자 정정 및 WSL/NTFS 개발 정책, NTFS의 `data/` 정책을 모든 문서에 명시
- ✅ `pyproject.toml` 신규 작성 — `name = "python-kraddr-geo"`, scripts `kraddr-geo = "kraddr.geo.cli.main:app"`
- ✅ 기본 패키지 스캐폴드 작성 — `src/kraddr/geo/`, 계층별 빈 패키지, `AsyncAddressClient` 자리표시자, Typer CLI 진입점
- ✅ `Settings` + `.env.example` 작성 — `KRADDR_GEO_` prefix, DB/API/외부 API/cache/log/loader 설정
- ✅ `dto/common.py`, `dto/address.py` 작성 — CRS 정규화, 불변 DTO, vworld 주소 구조 + 단위 테스트
- ✅ 나머지 DTO(`geocode`, `reverse`, `search`, `zipcode`, `pobox`, `admin`) 구현
- ✅ `data/juso/도로명주소 전자지도` 실제 SHP/DBF 파일 헤더·필드 검사 테스트 추가 (`강원특별자치도/51000`)
- ✅ DDL/Alembic 적용 (`sql/ddl/`, `alembic/versions/0001_text_primary_postgis_schema.py`)
- ✅ `infra/engine.py`, raw SQL repo(`geocode/reverse/search/zip/pobox/admin`) 구현
- ✅ `core/normalize.py`, `core/geocoder.py`, `reverse/search/zipcode/pobox` 코어 구현
- ✅ `AsyncAddressClient` 실제 기능 연결 — geocode/reverse/search/zipcode/pobox, load job 조회/등록/취소, consistency report 조회
- ✅ FastAPI 앱/라우터 구현 — `/v1/address/*`, `/v1/admin/loads`, `/v1/admin/consistency/*`
- ✅ 텍스트 정본 로더 구현 — `juso_hangul_loader.py`, `locsum_loader.py`, `navi_loader.py`
- ✅ SHP 보조 로더/후처리 구현 — `polygons_loader.py`, `delta_loader.py`, `postload.py`, `consistency.py`
- ✅ epost 보조 우편번호 로더 구현 — `pobox_loader.py`, `bulk_loader.py`
- ✅ 실제 `data/juso` 파일 검증 — 도로명주소 한글 서울 파일, 위치정보요약DB ZIP member, 내비게이션용DB 서울 파일, 강원 SHP load plan
- ✅ 실제 PostgreSQL(PostGIS) 샘플 적재 검증 — 별도 테스트 DB에서 DDL 적용 → 실제 파일 COPY 샘플 load → 링크 해소 → MV 생성 확인
- ✅ PR #10 리뷰 반영 — `load_jobs` batch DAG(`load_batch_id`, `parent_job_id`, `full_load_batch`), C1~C10 정합성 검증, PNU NULL guard, reverse `both`, 인코딩 fallback, `log_tail` 갱신 경로 구현
- ✅ ADR-017(batch DAG + 정합성 게이트)과 ADR-018(`x_extension` 스키마 격리) 문서화
- ✅ T-018 CLI 운영 명령 구현 — `load all-sidos`, `load shp/shp-all`, `load epost --kind=full`, `refresh mv --swap`, `validate consistency --cases/--scope`
- ✅ T-019 외부 API 폴백 구현 — `fallback="api"`일 때 로컬 `NOT_FOUND` 후 vworld → juso 검색+좌표 순서로 호출
- ✅ T-020 OpenAPI export 구현 — `scripts/export_openapi.py`, committed `openapi.json`, `.github/workflows/openapi.yml` drift 검사
- ✅ PR #11 후속 반영 — `full_load_batch` REST/라이브러리 공유 DAG 경로 확인, enqueue 전 child payload fail-fast 검증, PR 코멘트용 검증 근거 정리
- ✅ PR #12 기반 보강 — PR #11을 main에 머지하고, 후속 의견은 PR #12로 이관
- ✅ T-021 프론트엔드 패키지 `kraddr-geo-ui` 부트스트랩 — Next.js 16 + React 18 + Tailwind + TanStack Query. 지도는 MapLibre GL JS + VWorld WMTS를 사용하며, 범용 `digitie/maplibre-vworld-js` 문제도 적극 수정 대상으로 둔다.
- ✅ T-022 디버그 페이지 구현 — `/debug/geocode`, `/debug/reverse`, `/debug/normalize`, `/debug/explain`
- ✅ T-023 관리 페이지 구현 — `/admin/load`, `/admin/tables`, `/admin/cache`, `/admin/logs`
- ✅ T-024 품질 게이트 추가 — 루트 `pre-commit`, 통합 CI, frontend `gen:types` drift 검사, lint/type/test/build
- ✅ T-025 Prometheus 메트릭 구현 — `/metrics`, 외부 API 호출 counter, cache/load job gauge
- ✅ T-026 정합성 UI 구현 — `/admin/consistency`에서 C1~C10 report 목록·상세·재검증 enqueue 확인
- ✅ FastAPI admin 보강 — `/v1/admin/tables`, `/v1/admin/explain`, `/v1/admin/cache/metrics`, `/v1/admin/logs`, `/v1/admin/upload/sido-zip`, `/v1/admin/maintenance/refresh-mv`
- ✅ PR #12 리뷰 보강 — 업로드 path traversal/크기 제한, 프록시 `/v1` 제한과 스트리밍 전달, React Query retry, EXPLAIN timeout, LoadConsole/Explain/Reverse/Consistency 에러 처리, CI `scripts` import 실패 수정
- ✅ PR #15 리베이스/리뷰 보강 — PR #14 merge 이후 최신 `main` 위로 rebase하고, `maplibre-vworld`를 upstream main commit `a5b3c65`로 고정해 helper/CSS를 실제 package에서 소비한다. 이후 후속 PR에서는 upstream PR #9 commit `11321fe`로 동기화해 VWorld tile error/redaction helper까지 공유한다.
- ✅ PR #13/T-027 계획 보강 — `data/juso` 전체 인벤토리, Docker full-load 실행 금지선, 기준월 분리(`JUSO_YYYYMM`/`LOCSUM_YYYYMM`/`NAVI_YYYYMM`), `PLAN_ONLY=1` preflight, 미지원 자료 후속 태스크를 문서화
- 🟡 Windows 재설치/새 Codex 세션 복구 문서화 — `docs/windows-reinstall-recovery.md`에 Git/PR handoff, `data/`·`.env` 백업, WSL 복구, Codex `resume`/`fork`/로컬 백업 명령을 정리하고 `CLAUDE.md`/`docs/dev-environment-recovery.md`의 실제 적재 금지선을 동기화
- 🟡 PR #14/T-027 실제 전체 적재 실행 — WSL ext4 작업 사본 `~/kraddr-geo-data`와 Docker PostGIS(`localhost:15432`)에서 텍스트/NAVI/SHP/MV 적재를 수행
- ✅ 실제 SHP 17개 시도 × 9개 레이어 재적재 완료 — 153 레이어, 3시간 10분 4초, `tl_spbd_buld_polygon` 10,687,732행, `tl_sprd_intrvl` 16,993,167행, `tl_sprd_rw` 1,482,679행
- ✅ 실제 SHP natural key 스키마 검증 — `bjd_cd`/건물번호/geometry 전 건 채움, `rds_sig_cd`/`rncode_full` NULL 581건 확인
- ✅ C4/C5 정합성 SQL 보강 — natural key 중복 polygon 다대다 거리 오염을 막기 위해 nearest polygon 1개만 평가하도록 수정
- ✅ 실제 smoke test 보강 — psycopg optional filter 타입 추론 오류를 `CAST(:param AS ...)`로 수정하고 geocode/reverse/search/zipcode smoke 통과
- ✅ PR #14 리뷰 반영 — Alembic `0002_t027_shp_schema_fixups`, SHP generated column 빈 문자열 보정, `KRADDR_GEO_DB_PORT` 네이밍, MV index 경고, SHP truncate row snapshot, PR 리뷰 확인 프로토콜 문서화
- ✅ PR #14 추가 리뷰 반영 — `tl_sprd_rw` migration non-polygon row guard, MV index rename live catalog 유도, locsum `staging_seq`, navi zero-coordinate skip, GDAL `connect_timeout`, C6/C7 `ST_Covers` 전환
- ✅ 실제 C2/C4/C6/C7 선택 재검증 — C2 `missing_text=34,118`/`missing_resolve_key=581`, C4 `over_500m=16`, C6 803/C7 6,817 유지 확인
- ✅ T-031 데이터 품질 후속 분석 PR 분리 — PR #14 close 이후 이어갈 C2/C4/C6/C7 sample/지도/원천 파일 역추적 계획을 `docs/t027-data-quality-followup.md`에 정리
- ✅ PR #17/T-031 보강 — `kraddr-geo validate data-quality-samples` CLI와 C2/C4/C6/C7 CSV export SQL을 추가하고, SHP loader가 `source_file`/`source_yyyymm`을 적재하도록 보강
- ✅ PR #17 실제 Docker DB 검증 — `localhost:15432`에서 CSV 8개 export 성공(2분 52.45초, RSS 79,956KB). C2 `missing_resolve_key` 581건은 전부 `rds_sig_cd` 결측, C4 500m+ 상위 7건은 출입구 경도 약 `+2.0`도 이상치 패턴 확인
- ✅ PR #18 VWorld debug helper sync — T-032 성능 튜닝 전에 `maplibre-vworld-js` PR #9 commit `11321fe`와 `kraddr-geo-ui` helper 소비 상태를 최신 main 위에서 정리하고 frontend lint/type/test/build 재검증
- ✅ T-032 성능 튜닝 완료 — C4/C6/C7 export 중복 공간 스캔 제거, 정합성 CTE materialization, SHP 다중 시도 적재의 마지막 1회 `ANALYZE`, postload timeout 보강을 반영했다. 사용자 지시에 따라 실제 실행 검증은 세종특별시·경상남도 축소 데이터 1회만 수행했고, 전국 full test와 반복 trial은 T-033~T-035로 분리했다. 상세: `docs/t032-performance-tuning.md`
- ✅ PR #19 리뷰 반영 — temp table prepare/export를 명시적 transaction으로 고정하고, SQL splitter를 `infra.sql.iter_sql_statements()`로 통합했다. postload timeout docstring/`None` 옵션, SHP `ANALYZE` table별 transaction, T-033~T-035 후속 ID, migration lock 주석을 추가했다.
- ✅ T-033 전국 full-load 재검증 — 빈 DB `kraddr_geo_t033`에 실제 전국 데이터를 적재해 4시간 8분 2초 기준선, SHP 153 layers, MV 6,416,637행, smoke test 통과, data-quality CSV 8개 export 결과를 확보했다. `TL_SPRD_INTRVL` GDAL INSERT 병목이 재확인되어 T-034 우선 튜닝 대상으로 둔다. 상세: `docs/t033-full-load-revalidation.md`
- ✅ T-034 SHP append 병목 튜닝 — geometry 없는 `TL_SPRD_INTRVL`을 GDAL append 대신 DBF 직접 scan + `psycopg COPY` 경로로 분리했다. 세종 단일 레이어는 36.12초 → 1.59초, 경기도 2,677,715행은 새 경로 15.88초, 세종 9개 SHP 레이어 전체는 31.69초로 검증했다. 상세: `docs/t034-shp-append-tuning.md`
- ✅ T-035 MV refresh/swap 벤치마크 — `scripts/benchmark_mv_refresh.py`를 추가하고 전국 DB에서 `CONCURRENTLY` 1분 49.64초, shadow swap 2분 16.28초를 측정했다. swap rename/index rename 구간은 약 0.016초였고, `ANALYZE`를 별도 transaction으로 분리했다. 상세: `docs/t035-mv-refresh-benchmark.md`
- ✅ T-036 `maplibre-vworld-js` main 동기화 — `kraddr-geo-ui`의 `maplibre-vworld` dependency를 upstream main commit `c91c9f304669ce3f5fc4915f21186b23731d5816`로 갱신했다. 최신 upstream은 `redactVWorldUrl()`와 redaction 표기 `***`를 쓰므로, UI 내부 경계에서는 `redactVWorldUrl as redactVWorldTileUrl` alias로 기존 컴포넌트 계약을 유지하고 테스트를 갱신했다. 상세: `docs/t036-maplibre-vworld-sync.md`
- ✅ PR #20~#22 post-merge 리뷰 반영 — T-036 merge 이후 사용자 지시 순서대로 PR #22, #21, #20 리뷰 코멘트를 thread-aware로 확인하고, benchmark metadata/public helper, DBF COPY 오류 문맥, full-load phase timer/doc 명확화를 PR #24로 반영했다. 상세: `docs/postmerge-review-fixups-pr20-pr22.md`
- ✅ T-028 일변동 ZIP 로더 — `data/juso/daily/*.zip`의 `TH_SGCO_RNADR_MST.TXT`를 `tl_juso_text`에 적용하는 daily delta loader, CLI `load daily-juso`, API job kind `daily_juso_delta`를 추가했다. `TH_SGCO_RNADR_LNBR.TXT`는 T-038 전까지 manifest에 미지원 행 수로 기록한다. 실제 `20260401_dailyjusukrdata.zip` MST 422행과 `20260404` `No Data` member를 검증했다. 상세: `docs/t028-daily-juso-delta.md`
- ✅ T-029 `jibun_rnaddrkor_*` 활용 결정 — 실제 전국 `jibun_rnaddrkor_*` 1,769,370행과 daily `LNBR` 구조를 확인했다. 둘 다 대표 PNU가 아니라 건물↔지번 1:N 관계로 보고, `tl_juso_text.pnu`에 덮어쓰지 않고 후속 `tl_juso_parcel_link` 테이블로 분리하기로 ADR-022에서 확정했다. 상세: `docs/t029-jibun-rnaddrkor-decision.md`
- ✅ T-030 별도 도형/출입구 자료 검토 — `건물군 내 상세주소 동 도형`, `구역의 도형`, `도로명주소 건물 도형`, `도로명주소 출입구 정보` 세종 ZIP을 열어 layer/geometry/text 구조를 확인했다. 기본 full-load에는 즉시 섞지 않고 T-039~T-041로 분리하기로 ADR-023에서 확정했다. 상세: `docs/t030-extra-shape-sources.md`
- ✅ T-038 `tl_juso_parcel_link` DDL/로더 — `jibun_rnaddrkor_*` full snapshot과 daily `TH_SGCO_RNADR_LNBR.TXT` delta를 별도 1:N 테이블에 적재한다. CLI/API job kind/full-load batch/UI 기본 payload를 연결했고, Docker DB `kraddr_geo_t038`에서 실제 서울 `jibun` 2행과 daily LNBR 5행 적재를 검증했다. 상세: `docs/t038-parcel-link-loader.md`
- ✅ T-039 `도로명주소 출입구 정보` direct entrance loader — `RNENTDATA_2605_*.txt`를 `tl_roadaddr_entrc`에 별도 적재한다. T-027 최종 클린 적재 보강 이후 MV 대표 좌표는 `tl_locsum_entrc` → same-month `tl_roadaddr_entrc` → `tl_navi_buld_centroid` 순서로 선택한다. 실제 전국 17개 ZIP 6,418,169행 구조, 세종 유효 좌표 27,779행, Docker DB `kraddr_geo_t039` 샘플 적재와 T-027 same-month gate를 검증했다. 상세: `docs/t039-roadaddr-entrance-loader.md`
- ✅ T-040 `도로명주소 건물 도형` bundle 비교 — 세종/경남 실제 address building bundle을 전자지도 `TL_SPBD_BULD`/`TL_SPBD_ENTRC`와 비교했다. address polygon key 교집합은 세종 15,339/27,792, 경남 345,290/656,230으로 단순 중복이 아니어서 serving loader는 보류하고 분석 후보로 분리했다. 상세: `docs/t040-building-shape-bundle.md`
- ✅ T-041 상세주소 동 도형/구역 추가 레이어 검토 — 세종/경남 실제 `건물군 내 상세주소 동 도형`이 전자지도 `TL_SPBD_BULD`의 부분집합임을 확인했다. `구역의 도형`의 기존 행정/기초구역 5개 레이어는 전자지도와 key 기준 완전 중복이다. `TL_SCCO_GEMD`는 별도 overlay/분석 후보로 남기고, `TL_SPPN_MAKAREA`는 ADR-027에서 국가지점번호 보조 geocode/reverse 데이터 후보로 승격했다. 상세: `docs/t041-detail-zone-shape-layers.md`
- ✅ T-037 geometry 포함 SHP 대형 레이어 적재 튜닝 — `TL_SPBD_BULD`를 projection staging table + 운영 테이블 insert-select 경로로 분기했다. 세종 단일 레이어는 기존 append 38.36초에서 18.59초로 줄었고, 경기도 1,649,975행 단일 레이어는 40분 17.15초에 성공했다. 세종 SHP 9개 레이어 public CLI 적재도 Docker DB에서 확인했다. 상세: `docs/t037-shp-geometry-tuning.md`
- ✅ T-048 `maplibre-vworld-js` 최신 동기화와 책임 경계 재정의 — upstream `main` 최신 commit `7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`을 확인하고 `kraddr-geo-ui` dependency/lockfile을 갱신했다. ADR-032를 추가해 범용 VWorld/MapLibre 기능은 upstream, 지오코딩/역지오코딩/관리 UI 특화 기능은 이 저장소 domain wrapper에서 구현하는 원칙을 확정했다.
- ✅ T-049 운영 메타데이터·감사·릴리스 스키마 구현 — `ops` 스키마 6개 테이블, append-only audit trigger, active release partial unique index, redacted audit payload/hash helper, `/v1/admin/ops/*` API, `/admin/ops` UI, table stats snapshot capture, typed maintenance confirmation hash를 추가했다. 상세: `docs/t049-ops-metadata-schema.md`
- ✅ T-045 원천 자료 기준월 선택과 대용량 업로드/적재 UX 구현 — source set 탐지/계획 DTO와 helper, JSON manifest 기반 upload set 저장소, `/v1/admin/uploads/*` 및 `/v1/admin/load-sources/*`, `AsyncAddressClient` 메서드, `kraddr-geo load full-set`, `/admin/load` 다중 파일/DND 업로드·기준월 확인 modal·업로드/적재 진행률·취소 UX를 추가했다. 혼합 기준월은 정확한 확인 문구가 있어야 plan을 만들 수 있고, batch payload는 명시 `children`과 source set 감사 필드를 남긴다. 상세: `docs/t045-source-set-load-ux.md`
- ✅ T-046 적재 완료 DB 백업/복원 및 UI 구현 — `pg_dump -Fd --jobs` directory dump + `tar.zst` archive, `ops.artifacts` metadata, `/v1/admin/backups`, `/v1/admin/restores`, `/v1/admin/jobs/{job_id}/events`, `kraddr-geo backup/restore`, `/admin/backups` UI를 추가했다. 대구광역시 부분 DB 실제 적재 후 83MiB archive 백업, 새 DB 복원, row count 일치, geocode/reverse smoke `OK`를 확인했다. 상세: `docs/t046-db-backup-restore.md`
- ✅ T-042 `TL_SPPN_MAKAREA` 국가지점번호 보조 데이터 적재/조회 구현 — `tl_sppn_makarea` DDL/Alembic, GDAL loader, `kraddr-geo load sppn-makarea`, API job kind, source set optional child, 국가지점번호 parser/formatter, geocode/reverse `x_extension.sppn_makarea`를 추가했다. Docker PostGIS에서 세종 실제 ZIP 146행을 적재했고, `금이산` polygon 내부 점을 `다바 7363 4856`으로 formatter → geocode/reverse 조회까지 검증했다. 상세: `docs/t042-sppn-makarea.md`
- ✅ README 법적 고지 보강 — 프로젝트가 AI 활용 방식과 개발 워크플로를 학습·검증하기 위한 기술 연구 프로젝트이며, 외부 원천 데이터/API는 제공 기관의 조건을 준수하는 것을 전제로 사용한다고 명시했다.
- ✅ 문서 정합성 재검토 — `master`/`main` 표현, README/SKILL quick start CLI 예시, `kraddr-geo-ui` 소유 설명, T-046 artifact registry 명칭, README ADR 목록, 후속 task 순서를 현재 코드와 ADR에 맞춰 정리했다. 상세: `docs/doc-consistency-audit-20260527.md`
- ✅ T-043 PR #23~#41 리뷰 코멘트 audit/fixup — conversation/review/inline/thread 표면을 모두 확인하고 unresolved review thread 0개를 기록했다. VWorld alias/test, daily delta 운영 문서와 `--limit-per-file` 경고, `TL_SPBD_BULD` staging advisory lock/skip metric, ADR-027 위험 섹션 등을 보강했다. 상세: `docs/postmerge-review-fixups-pr23-latest.md`
- ✅ PR #34~#47 리뷰 코멘트 audit/fixup — conversation/review/inline/thread 표면을 다시 확인했고 unresolved current thread 0개를 기록했다. `source_set` DTO/OpenAPI/TS 타입을 nested JSON 보존으로 보강하고, `ops.audit_events.job_id` FK를 `ON DELETE NO ACTION`으로 바꿨으며, `maplibre-vworld-js` 최신 `7947b2e` 동기화와 WSL frontend 검증 helper를 추가했다. 상세: `docs/postmerge-review-fixups-pr34-latest.md`
- ✅ T-027 최종 실 데이터 클린 적재 1회 완료 — Docker PostGIS `localhost:15432`의 빈 DB에 실제 `data/juso` 원천을 처음부터 적재했다. 총 3,934초, `mv_geocode_target=6,416,637`, `tl_sppn_makarea=24,204`, smoke `OK`를 확인했다. direct `tl_roadaddr_entrc=202605`를 `juso=202603` 세트에 바로 serving 승격하면 C4/C6/C7이 증가해, MV/정합성 serving CTE는 `tl_locsum_entrc` 우선 + same-month direct fallback으로 보정했다.
- ✅ 실제 C1~C10 재검증 완료 — 보정 후 C1~C10은 611.71초에 완료됐고 `severity_max=ERROR`다. C2 34,699건, C4 3,415건(`over_500m=16`), C6 803건, C7 6,817건은 기존 실제 데이터 품질 이슈로 유지된다. C10은 row-level 기준월 집계로 `distinct_months=3` WARN을 보고한다.
- ✅ T-051 에이전트별 고정 worktree와 CodeGraph 운용 문서화 — ChatGPT Codex `~/dev/geo-codex`, Claude Code `~/dev/geo-claude`, Google Antigravity 2.0 `~/dev/geo-antigravity`를 고정 worktree로 두고 작업마다 branch만 새로 따도록 ADR-034와 개발 문서를 추가했다. CodeGraph `v0.9.6`을 WSL에 설치하고 세 worktree 모두 `codegraph init -i && codegraph status`까지 실행했다. `.codegraph/`는 ignore한다.

## 다음 한 작업 (1시간 이내 분량)

다음 작업은 T-047 전국 적재 후 쿼리 성능 벤치마크와 튜닝이다. 이미 T-027 최종 클린 적재 DB의 row count와 정합성 기준선이 있으므로, 같은 데이터 상태에서 exact/fuzzy geocode, reverse nearest/radius, search, zipcode, no-result 경로를 반복 측정한다. p50/p95/p99, `EXPLAIN ANALYZE`, `pg_stat_statements`, 동시성 결과, 튜닝 전후 차이를 문서화하고 목표 초과 query군은 index/query rewrite/read-only 보조 MV까지 적극 실험한다. 그 다음 후보는 T-044 최신 `maplibre-vworld-js` 기반 domain wrapper 경계화와 T-050 운영 hardening이다.

- 상세 실행 로그는 로컬 산출물 `artifacts/fullload/20260524_173115/execution-log.md`에 있다. 이 경로는 git ignore 대상이다.
- 현재 실제 DB 정합성은 `severity_max=ERROR`다. 남은 주요 항목은 C2 34,699건, C4 500m 초과 16건, C6 803건, C7 6,817건이다. C10은 `tl_juso_text=202603`, `tl_locsum_entrc`/`tl_navi_*`/`tl_spbd_buld_polygon=202604`, `tl_roadaddr_entrc`/`tl_sppn_makarea=202605`를 row-level evidence로 보고 `WARN` 처리한다.
- T-034에서 `TL_SPRD_INTRVL` 전용 COPY 경로를 검증했고, T-037에서 `TL_SPBD_BULD` projection staging 경로도 검증했다. 전국 전체 SHP 시간은 T-027 최종 클린 로드에서 다시 확인한다.
- T-035에서 `kraddr_geo_t033` MV는 여러 번 refresh/swap됐고 최종 상태는 `mv_geocode_target=6,416,637`, `mv_geocode_target_next/old` 없음, index 이름 `idx_mv_*` 정상이다.
- `maplibre-vworld-js` upstream main 확인 커밋은 `7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`이고, 현재 `kraddr-geo-ui`는 이 SHA에 맞춰져 있다. 최신 upstream은 `redactVWorldTileUrl()`가 아니라 `redactVWorldUrl()`를 export하므로 `kraddr-geo-ui/lib/vworld.ts`에서 기존 내부 이름으로 alias한다. T-044에서는 이 helper 소비 상태를 넘어서 `VWorldMap`/Hook 기반으로 경계화하되, 범용 지도 primitive만 upstream에 두고 지오코딩/역지오코딩/관리 UI 특화 기능은 이 저장소 wrapper에 남긴다.
- PR #17 이전에 적재된 실제 T-027 DB의 SHP `source_file`은 전 건 NULL이다. PR #17 이후 SHP를 재적재하면 `source_file=<시도>/<시군구코드>/<레이어>.shp`와 `source_yyyymm`가 채워진다.
- `daily/*.zip`는 T-028 이후 MST를 `tl_juso_text`에 적용할 수 있고, T-038 이후 `LNBR`를 `tl_juso_parcel_link`에 별도 delta로 적용할 수 있다. `도로명주소 출입구 정보`는 T-039 이후 `tl_roadaddr_entrc`에 적재할 수 있으며, 같은 기준월 세트에서만 MV fallback 후보가 된다. `도로명주소 건물 도형`은 T-040 이후 분석 helper로 비교 가능하지만 serving loader는 보류한다. T-041 상세주소 동/구역 추가 레이어도 `scripts/compare_extra_shape_layers.py`로 비교 가능하다. `TL_SPPN_MAKAREA`는 T-042 이후 `tl_sppn_makarea` 별도 loader/조회 경로가 있으며, source set에서는 optional `sppn_makarea_load` child로 연결된다.
- 원천별 업데이트 시점은 서로 다를 수 있다. ADR-029/T-045 구현에 따라 새 full-load UX는 단일 `yyyymm`이 아니라 `source_set.yyyymm_by_kind`를 사용하며, 기준월이 섞이면 CLI/UI에서 정확한 `YYYYMM/... 혼합 적재 확인` 문구를 받아야 한다. API/라이브러리는 prompt 없이 `discover_load_sources()`와 `build_full_load_source_set_plan()`을 분리 제공한다. `/admin/load`는 업로드가 끝난 뒤 source set을 분석하고 `full_load_batch`의 명시 `children` payload를 등록한다.
- T-046 백업/복원은 1차 구현과 대구 부분 DB 실제 backup → restore 검증을 완료했다. 남은 hardening은 callback retry/backoff, restore 취소 시 target DB drop/quarantine 정책, 디스크 여유 공간 사전 추정, PostgreSQL/PostGIS major mismatch hard-fail이다. 전국 full-load 재실행은 후속 T-027에서 수행한다.
- T-049 운영 메타데이터는 1차 구현 상태다. 현재 구현은 DDL/API/UI와 redacted audit event, maintenance window 생성/종료, table stats snapshot capture를 제공한다. T-045/T-046/T-047을 진행할 때 source set 확정, backup/restore artifact, 성능 리포트, MV swap 성공 지점을 `ops.dataset_snapshots`, `ops.artifacts`, `ops.serving_releases`에 실제로 연결하는 보강이 이어져야 한다.
- T-050은 PR #34~#47 리뷰 audit에서 남긴 운영 hardening 묶음이다. upload set cleanup TTL과 참조 lock, callback HMAC/retry/replay protection, size 기반 backup/restore sub-progress, snapshot/release 자동 생성 hook, table stats cron, destructive confirmation flow, 실제 PostgreSQL constraint integration test를 포함한다.
- T-047 쿼리 성능 튜닝도 설계 상태다. 전국 full-load DB에서 exact/fuzzy geocode, reverse, search, zipcode, no-result 경로를 다수 반복 측정하고, 목표를 초과하면 index/query rewrite뿐 아니라 `mv_geocode_exact_key`, `mv_geocode_text_search`, `mv_reverse_point_5179` 같은 read-only 보조 MV 후보를 실험한다.

## 작업 시작 전 확인할 것

- [ ] `AGENTS.md`의 "식별자" 표와 "개발 환경 정책" 다시 읽기
- [ ] 자기 에이전트 고정 worktree에서 작업 중인지 확인하고, 새 작업 branch를 만든 뒤 `codegraph sync` 실행
- [ ] `SKILL.md` §4 "DO NOT" 룰 다시 읽기
- [ ] `docs/architecture.md`의 의존 방향 확인
- [ ] `docs/decisions.md`의 ADR-001 ~ ADR-020 확인 (특히 **ADR-012 텍스트 정본 + SHP polygon 하이브리드**, ADR-017 batch DAG, ADR-018 `x_extension` 스키마, ADR-019 Next.js 16 보안 하한선, ADR-020 VWorld MapLibre 지도)
- [ ] 마지막 `docs/journal.md` 엔트리 읽기
- [ ] Windows 재설치/새 Codex 세션에서 이어받는 경우 `docs/windows-reinstall-recovery.md` 읽기
- [ ] NTFS의 `data/` 디렉토리가 준비되어 있고 ext4에서 심볼릭 링크 또는 절대경로로 접근 가능한지

## 알려진 함정

- **WSL/NTFS 분리**: ext4 작업 디렉토리에서 NTFS의 `data/`로 심볼릭 링크를 둘 때 권한/inotify 이슈 발생 가능. 절대경로 사용을 권장.
- `pg_trgm.similarity_threshold`는 트랜잭션 단위로만 `SET LOCAL` — 전역 변경 금지 (SKILL.md §4-3)
- 좌표 입력은 `(lon, lat)` 순서. `(lat, lon)`으로 받으면 한국 밖으로 가서 `InvalidCoordinateError` 발생
- `ogr2ogr -append`와 `-overwrite`를 같이 쓰지 말 것 (GDAL Python binding으로 대체)
- `MVM_RES_CD` 매핑은 코드 상수가 아닌 settings 또는 DB `load_codes` 테이블에서 읽는다
- PostgreSQL DB 이름은 `kraddr_geo` (dot 불가). 환경변수 prefix는 `KRADDR_GEO_`.
- 현재 셸처럼 `TMP`/`TEMP`가 Windows Temp(`/mnt/c/...`)를 가리키면 pytest 캡처가 `FileNotFoundError`로 실패할 수 있다. WSL에서는 `TMPDIR=/tmp TMP=/tmp TEMP=/tmp python -m pytest`처럼 Linux `/tmp`를 지정한다.
- **GDAL 버전 미스매치**: Python `gdal` 패키지가 시스템 GDAL과 다른 버전이면 `ImportError: undefined symbol`. `pip install "gdal==$(gdal-config --version)"`로 핀(ADR-008, `docs/dev-environment.md`).
- **`libgdal-dev` 누락**: `pip install -e ".[loaders]"`가 `gdal-config: command not found`로 실패. WSL에서는 `sudo apt install libgdal-dev gdal-bin` 후 재시도.
- **위치정보요약DB에는 `bd_mgt_sn`이 직접 없다**: 실제 `entrc_*.txt`는 `sig_cd`, `ent_man_no`, `bjd_cd`, `rncode_full`, 건물번호, 우편번호, 좌표를 제공한다. 로더는 원본 키를 보존하고 `postload.resolve_text_geometry_links()`에서 `tl_juso_text`와 조인해 `bd_mgt_sn`을 해소한다.
- **일부 위치정보요약DB 행은 좌표가 비어 있다**: `tl_locsum_entrc.geom`은 `NOT NULL`이므로 로더는 X/Y가 모두 있는 행만 적재한다. 좌표 결측 비율은 정합성 리포트(C3 확장)에서 별도 집계할 수 있다.
- **실제 DB 적재 검증**: 로컬 PostGIS가 준비되어 있으면 `KRADDR_GEO_TEST_PG_DSN=... pytest tests/integration/test_optional_real_postgres_load.py -q`로 실제 `data/juso` 샘플 COPY와 MV 생성을 확인한다.
- **프론트엔드 TypeScript 캐시**: `kraddr-geo-ui/tsconfig.tsbuildinfo`는 생성물이다. `.gitignore` 대상이며 PR에 포함하지 않는다.
- **Next.js 16 Route Handler context**: `app/api/proxy/[...path]/route.ts`의 `params`는 Promise다. Next.js 14 예시처럼 동기 객체로 받으면 type-check가 실패한다.
- **VWorld debug map**: 실제 키는 `NEXT_PUBLIC_VWORLD_API_KEY`로 로컬 `.env.local`에만 둔다. `maplibre-vworld`는 현재 `git+https://github.com/digitie/maplibre-vworld-js.git#7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`로 고정되어 있고 `dist`/`exports`/`types`/`style.css`, click/error/flyTo hook, tile error helper가 포함됨을 확인했다. SHA를 바꾸면 먼저 최신 `main` 또는 stable release를 확인하고 Linux Node/npm으로 `npm ci`/`lint`/`type-check`/`test`/Next.js build를 다시 확인한다. Windows `npm`은 WSL ext4 경로에서 UNC cleanup 오류를 낼 수 있으므로 사용하지 않는다. `VWorldMap` 컴포넌트 대체는 범용 지도 primitive를 upstream 최신 API로 소비하고, key 미설정 fallback 문구, API 응답 overlay, transient overlay 임계치 같은 `kraddr-geo-ui` 특화 동작을 domain wrapper에 남기는 방식으로 진행한다.
- **PR 리뷰 확인 루틴**: PR 리뷰를 반영할 때는 `gh pr view <번호> --json comments,reviews,latestReviews`와 GitHub review thread fetch 스크립트를 함께 확인한다. conversation comment와 formal review body가 따로 존재할 수 있으므로, 제목이 비슷하더라도 마지막 코멘트까지 읽고 merge condition을 문서/코드 체크리스트로 옮긴다.
- **CodeGraph/Windows npm shim**: WSL에서 `codegraph`가 `/mnt/c/Users/.../npm/codegraph`를 가리키고 `node: not found`로 실패하면 Windows npm shim이 PATH에 앞선 것이다. WSL에서는 Linux installer 또는 Linux Node/npm 설치를 사용하고, worktree별 `.codegraph/`가 있으면 `codegraph sync`로 갱신한다.

## 작업 후 의무사항

1. `docs/journal.md`에 항목 추가 (날짜·요약·관련 파일·결정·다음 작업)
2. 본 `docs/resume.md`의 진척도 토글 갱신
3. 변경된 결정이 있다면 `docs/decisions.md`에 ADR 추가
4. 사용자 가시 변경이면 `CHANGELOG.md` 갱신
5. 스키마 변경이면 `scripts/export_openapi.py` 재실행 → 프론트엔드 `gen:types`
