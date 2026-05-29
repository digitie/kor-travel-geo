# RESUME — 작업 재개 가이드

새 에이전트 세션이 시작될 때 "지금 어디까지 했고, 다음은 뭐 하면 되나"를 한 화면에서 답한다.

## 현재 진척도 (2026-05-29 갱신, by codex)

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
- ✅ T-027 최종 실 데이터 클린 재적재 완료 — Docker PostGIS `localhost:15434`의 새 compose project/빈 pgdata에 실제 `data/juso` 원천과 `20260401_dailyjusukrdata.zip`을 처음부터 적재했다. 총 3,963초, `mv_geocode_target=6,416,642`, `mv_geocode_text_search=6,416,642`, `tl_sppn_makarea=24,204`, active serving release `faa1f42b-f5b9-4ef0-af0b-1a422d938ed3`, smoke `OK`를 확인했다. C1~C10은 실제 원천 품질 이슈(C2/C4/C6/C7)로 `severity_max=ERROR`이며, data-quality CSV 8개와 DB size snapshot을 남겼다. 상세: `docs/t027-fullload-plan.md`
- ✅ 최신 C1~C10 재검증 완료 — 2026-05-29 최종 재적재 후 C1~C10은 약 633초에 완료됐고 `severity_max=ERROR`다. C2 34,454건, C4 3,415건(`over_500m=16`), C6 803건, C7 6,817건은 기존 실제 데이터 품질 이슈로 유지된다. C10은 daily delta 반영으로 `tl_juso_text` 202603/202604 evidence를 함께 보고하며 `distinct_months=3` WARN이다.
- ✅ T-051 에이전트별 고정 worktree와 CodeGraph 운용 문서화 — ChatGPT Codex `~/dev/geo-codex`, Claude Code `~/dev/geo-claude`, Google Antigravity 2.0 `~/dev/geo-antigravity`를 고정 worktree로 두고 작업마다 branch만 새로 따도록 ADR-034와 개발 문서를 추가했다. CodeGraph `v0.9.6`을 WSL에 설치하고 세 worktree 모두 `codegraph init -i && codegraph status`까지 실행했다. `.codegraph/`는 ignore한다.
- ✅ T-047 1차 query benchmark harness와 지번 exact 튜닝 — `scripts/benchmark_query_performance.py`와 단위 테스트를 추가하고, T-027 최종 클린 DB에서 smoke 및 small concurrency benchmark를 실행했다. `idx_mv_jibun_name_exact`를 추가해 Q2 지번 exact 단일 샘플 client latency를 2830.59ms → 5.58ms로 줄였고, index build time 56.03초/size 761MiB를 기록했다. 상세: `docs/t047-query-performance-tuning.md`
- ✅ T-047 standard corpus와 pool 비교 — 1,100건 corpus로 동시성 1/4/16/64를 측정했다. 기본 pool에서 동시성 16까지는 모든 query군 p95가 목표 안에 들어왔고, 동시성 64 tail은 pool 대기와 DB 경합이 섞였다. `--pool-size 64 --max-overflow 0` 재측정에서는 Q2/Q8은 좋아졌지만 Q3/Q4는 악화되어 query split/text-search slim MV를 다음 후보로 남겼다. 상세: `docs/t047-query-performance-tuning.md`
- ✅ T-047 Q4 search exact preflight 튜닝 — `rn_nrm`/`buld_nm_nrm` exact btree index와 저장소 2단계 search 경로를 추가했다. Q4 standard 100건은 모두 exact preflight로 처리됐고, `Q4-search-038` broad trigram plan execution은 42.39ms에서 exact 0.56ms로 줄었다. Q4 p95는 default pool c1/c4/c16에서 62.12/70.62/116.06ms → 12.23/22.39/52.27ms, pool64 c64에서 481.22ms → 295.85ms로 개선됐다. 상세: `docs/t047-query-performance-tuning.md`
- ✅ PR #51/#52 post-merge 리뷰 audit/fixup — conversation/review/inline/thread를 다시 확인했다. 두 PR 모두 post-merge conversation review 1건씩, review 0건, review thread 0건이었다. Q4 search split은 PR #53에서 반영됐고, `pg_stat_statements`, T-047 index 운영 영향, stress corpus, pool wait/DB execution 분리, SQL 상수 public module, Q3 fuzzy/T-057 region hint는 후속 액션으로 정리했다. 상세: `docs/postmerge-review-fixups-pr51-pr52.md`
- ✅ T-047 관측성 benchmark 보강 — artifact schema 2에 measurement별 `checkout_ms`/`execute_ms`, summary별 `p95_checkout_ms`/`p95_execute_ms`를 추가했고, `pg_stat_statements` before/after/delta artifact와 reset 옵션을 추가했다. Docker fresh DB는 `shared_preload_libraries=pg_stat_statements`와 schema extension을 포함한다. 기존 T-027 DB smoke는 extension 미설치 상태를 artifact로 남겼고, 11개 query군 error 0으로 통과했다. 상세: `docs/t047-query-performance-tuning.md`
- ✅ T-047 active observability run — `kraddr-geo-t027-db-1`을 `pg_stat_statements` preload 상태로 재시작하고 extension을 활성화했다. 저장 corpus 1,100건 SHA `ef460f8...`로 `standard --iterations 3`를 실행했고 measurement 17,600건 error 0을 확인했다. 기본 pool c64 Q4 p95 330.80ms 중 checkout p95가 307.88ms라 tail 대부분이 pool 대기였고, pool64 c64 Q4 p95는 162.50ms로 낮아졌다. Alembic 33자 revision ID 문제도 32자 이하로 정정했다. 상세: `docs/t047-query-performance-tuning.md`
- ✅ T-047 인덱스 운영 영향 측정 — exact btree index 3개 포함 상태에서 MV refresh/swap, 디스크, 백업 envelope를 측정했다. `CONCURRENTLY` refresh는 T-035 기준 111.64초에서 133.28초, shadow `swap`은 137.15초에서 352.85초로 늘었다. exact index 3개 build phase 합계는 180.35초, exact index total size는 1.43GiB, `pg_dump -Fd --jobs=4` dump directory는 2분 21.60초/4.02GiB였다. 이 시점에는 로컬 `zstd` CLI 부재로 최종 `tar.zst` archive 측정이 남았지만, 이후 T-047 backup archive 압축 측정에서 완료했다. 상세: `docs/t047-query-performance-tuning.md`
- ✅ T-047 stress corpus benchmark — 11,000건 corpus SHA `2123e09...`와 88,000 measurement로 기본 pool `c1/c4/c16/c64`를 측정했다. error 0, c16 p95 34ms 이하였고, c64 tail은 대부분 checkout 대기였다. Q3 fuzzy c64는 p95 335.01ms 중 checkout p95 304.91ms/execute p95 32.07ms, Q4 search c64는 p95 302.21ms 중 checkout p95 280.41ms/execute p95 27.77ms였다. 상세: `docs/t047-query-performance-tuning.md`
- ✅ T-047 REST API e2e latency — `scripts/benchmark_api_latency.py`를 추가해 저장 corpus를 `/v1/address/*` 요청으로 변환하고, 1,000 REST case/8,000 measurement를 측정했다. error 0, c1 p95 6.95~16.18ms, c16 p95 43.79~97.13ms, c64 p95 479.65~810.53ms였다. 한국 밖 reverse 좌표가 내부 `pydantic.ValidationError`로 500을 반환하던 문제도 HTTP 400 `E0102`로 보정했다. 상세: `docs/t047-query-performance-tuning.md`
- ✅ T-047 REST API pool64 비교 — 같은 REST corpus를 uvicorn 단일 process에서 `KRADDR_GEO_PG_POOL_SIZE=64`, `KRADDR_GEO_PG_MAX_OVERFLOW=0`으로 재측정했다. error 0이었고 Q3 fuzzy c64 p95는 810.53ms → 557.25ms로 개선됐지만, Q1/Q2/Q4/Q5/Q7/Q8은 대부분 악화되어 운영 기본 pool을 64로 단순 상향하지 않기로 했다. 다음 비교는 API worker 수, pool size, admission control grid로 진행한다. 상세: `docs/t047-query-performance-tuning.md`
- ✅ T-047 REST worker/pool/admission grid — `/v1/address/*` 전용 optional admission control을 추가하고 `w1/p16/a16`, `w2/p8/a8`, `w4/p4/a4`를 같은 REST corpus로 측정했다. error는 모두 0이었다. `w4/p4/a4`는 Q4 search c64 p95를 753.25ms → 435.63ms, Q3 fuzzy를 810.53ms → 550.35ms로 낮췄지만 Q5 reverse/Q8 no-result는 악화됐다. 기본값은 admission 비활성으로 유지한다. 상세: `docs/t047-query-performance-tuning.md`
- ✅ T-047 REST admission candidate 반복 측정 — 기본 profile, `w2/p8/a8`, `w4/p4/a4`를 같은 REST corpus로 `iterations=3` 재측정했다. 세 run 모두 16,000 measurement/error 0이었다. `w2/p8/a8`은 Q1/Q4 p95와 Q1~Q4 p99가 더 안정적이었고, `w4/p4/a4`는 Q7/Q8/Q11에서 강했다. Q3 fuzzy는 p95 기준 기본 profile이 가장 낮아 worker/pool/admission만으로 확정 개선했다고 보지 않는다. 상세: `docs/t047-query-performance-tuning.md`
- ✅ T-047 backup archive 압축 측정 — `apt download zstd`로 로컬 `zstd v1.5.5`를 확보한 뒤 T-047 operational impact의 `pg_dump -Fd` directory를 실제 `tar.zst`로 포장했다. archive wall time은 33.31초, archive 크기는 4,308,457,630 bytes였고 SHA256은 `94f404bdf9a4a3956009f961f966e7bca3b90f42eecfc083e83add7b1ea87883`였다. dump 내부 `.dat.gz`가 이미 압축되어 있어 크기 감소는 작았다. 상세: `docs/t047-query-performance-tuning.md`
- ✅ T-057 행정구역 hint 기반 검색 가속 1차 구현과 실측 — `RegionHint(sig_cd,bjd_cd)`를 추가하고 `AsyncAddressClient.geocode/search/reverse_geocode`, `/v1/address/geocode`, `/v1/address/search`, `/v1/address/reverse`에 선택 hint를 연결했다. 응답 구조는 vworld 호환을 유지하고, 현재 MV에 물리 `sig_cd`가 없으므로 `bjd_cd` prefix filter로 적용한다. SQL standard run은 900 case/8,100 measurement/error 0, REST smoke는 320 case/1,920 measurement/error 0이었다. Q3 fuzzy c64 p95는 SQL에서 307.45ms → 267.99ms, REST smoke에서 651.62ms → 520.43ms로 개선됐지만 충분한 결정타는 아니어서 T-061 slim text-search 구조로 넘긴다. 상세: `docs/t057-region-hint-search.md`
- ✅ T-062 PR #53~#64 post-merge 리뷰 audit/fixup — PR #53부터 #64까지 conversation/review/inline/thread와 GraphQL `reviewThreads`를 재확인했고 unresolved thread 0건을 기록했다. 직접 반영 항목은 search exact preflight 정규화 문서화와 `search_fuzzy` benchmark case, `pg_stat_statements` schema prefix, reverse 좌표 validation의 structured error mapping, REST admission repeat 설명, backup archive checksum과 `tar.zst` 해석 보강이다. 상세: `docs/postmerge-review-fixups-pr53-pr64.md`
- ✅ T-044 `maplibre-vworld-js` 0.1.0 기준 문서-only 재확인 — GitHub tag `v0.1.0` commit `8559bf4f8d5a32011a51669552bb7e1aedd42cfb`의 package manifest, public export, `VWorldMap`, marker/layer primitive, VWorld helper를 확인했다. npm registry에는 아직 `maplibre-vworld@0.1.0`이 없어 dependency는 바꾸지 않았고, 사용자 지시에 따라 upstream 코드는 직접 수정하지 않았다. 상세: `docs/t044-maplibre-vworld-010-review.md`
- ✅ T-056 `python-kraddr-base` Address 코드 helper 정리 — 실제 `~/dev/python-kraddr-base`는 Git checkout이 아니고 `GPL-3.0-or-later`라 원본 코드를 복사하지 않았다. 대신 `core/address/codes.py`에 시군구/법정동/도로명관리번호/도로명주소관리번호 helper를 공개 주소 코드 규칙 기반 독립 구현으로 두고, Juso fallback 좌표 API 파라미터 정규화에 연결했다. 상세: `docs/t056-kraddr-base-address-merge.md`
- ✅ T-052/T-053 선행 정리 — PR #67 리뷰 후속으로 T-056의 라이선스 표현을 "공개 주소 코드 규칙 기반 독립 구현, GPL 원본 코드 미복사"로 바로잡았다. 사용자 확인에 따라 "조합/분리"가 코드 식별자 조합·분해·정규화 의도였음을 문서화했고, Juso 검색 결과에 좌표 API 필수 코드가 없으면 coord API를 호출하지 않는 회귀 테스트를 추가했다.
- ✅ T-052 외부 API 스타일 비교 + API v1/v2 분리 + AI-friendly 문서화 — v2는 Kakao/Naver/Google/VWorld 직접 wrapper가 아니라 각 API 스타일의 장점을 참고한 자체 candidate schema로 정리했다. `/v2/geocode`, `/v2/reverse`, `/v2/search`, `AsyncAddressClient.geocode_v2/reverse_v2/search_v2`, `docs/api-reference/`, OpenAPI와 frontend 생성 타입을 추가했다. 기존 v1 fallback은 ADR-019의 vworld/juso만 유지한다. 상세: `docs/t052-api-providers-v1-v2.md`
- ✅ T-053 Admin UI C1~C10 상세 분석/수동 판정 콘솔 — 사용자 재확인 의도를 먼저 문서화한 뒤 `ops.consistency_case_samples` row-per-sample 저장, case definition/sample list/summary/single·bulk decision/recheck/CSV admin API, OpenAPI/프론트 타입, `/admin/consistency/[report_id]` 상세 UI를 추가했다. UI는 TanStack Query, TanStack Table, Zustand와 `maplibre-vworld-js` wrapper 기반 지도 preview를 사용한다. 상세: `docs/t053-admin-ui-ops-statistics.md`
- ✅ T-061 Q3 fuzzy slim text-search 구조 — `mv_geocode_target`에서 재생성 가능한 `mv_geocode_text_search` helper MV를 추가해 Q3 fuzzy geocode와 Q4 broad search fallback 후보 추출을 분리했다. T-057 corpus 기준 Q3 fuzzy c64 p95는 359.25ms → 227.57ms, `sig_cd` hint는 193.36ms → 182.27ms, wide는 255.36ms → 200.69ms로 개선됐다. helper는 6,416,637행/2,426MiB이고 helper 포함 shadow swap은 497.54초였다. 상세: `docs/t061-slim-text-search.md`
- ✅ T-050 운영 hardening 1차 — upload set cleanup TTL, queued/running job 참조 보호, active grace, `kraddr-geo uploads cleanup` CLI를 완료했다. 상세: `docs/t050-ops-hardening.md`
- ✅ T-050 운영 hardening 2차 — backup/restore callback HMAC, retry/backoff, replay protection을 완료했다. callback payload는 timestamp/callback ID/body HMAC으로 서명하고, retry attempt와 최종 delivery 상태를 artifact manifest에 기록한다. 상세: `docs/t050-ops-hardening.md`
- ✅ T-050 운영 hardening 3차 — backup/restore file/archive size 기반 sub-progress를 완료했다. dump/archive/checksum/extract 구간에서 파일 크기 sampler를 사용해 기존 `load_jobs.progress/current_stage/log_tail`에 byte 기반 보조 진행률을 남긴다. 상세: `docs/t050-ops-hardening.md`
- ✅ T-050 운영 hardening 4차 — full-load/MV/restore 완료 hook의 `ops.dataset_snapshots`/`ops.serving_releases` 자동 생성을 완료했다. `mv_refresh` 성공 시 active release를 만들고, restore 성공 시 pending restore release 후보를 만든다. PR #75 리뷰 후속으로 load-batch ERROR gate를 MV swap 이전으로 옮기고 `mv_hash` 중복 count를 줄였다. 상세: `docs/t050-ops-hardening.md`
- ✅ PR #69~#75 post-merge 리뷰 audit/fixup — PR #69부터 최신 PR #75까지 formal review와 review thread를 재확인했고 unresolved thread 0건을 기록했다. 직접 반영 항목은 `maplibre-vworld` lockfile URL, consistency sample 조회 최적화, backup progress sample 캐시, release hook gate/count 보강, 운영 runbook 문서화다. 상세: `docs/postmerge-review-fixups-pr69-pr75.md`
- ✅ T-050 운영 hardening 5차 — API lifespan 기반 opt-in scheduler로 `ops.table_stats_snapshots` 주기 capture를 추가했다. 기본 interval은 0으로 비활성화하고, 수동/주기 capture에서 `snapshot_id`를 생략하면 현재 active serving release snapshot에 자동 연결한다. 상세: `docs/t050-ops-hardening.md`
- ✅ T-050 운영 hardening 6차 — `db_restore`의 `replace_current` 위험 경로를 active `restore` maintenance window와 typed confirmation에 연결했다. `target_dsn`은 허용하지 않고 target DB 이름은 현재 DB 이름과 같아야 하며 확인 문구는 `RESTORE <현재 DB 이름>`이다. 상세: `docs/t050-ops-hardening.md`
- ✅ T-050 운영 hardening 7차 — 실제 PostgreSQL FK/trigger/partial unique integration test를 추가했다. `KRADDR_GEO_TEST_PG_DSN` 기반 선택형 테스트가 `ops.audit_events.job_id` FK, append-only trigger, active release partial unique index, `ops.table_stats_snapshots.snapshot_id` FK를 실제 DB에서 검증한다. 별도 Docker DB `kraddr_geo_t050_ops_constraints`에서 `1 passed`를 확인했다. 상세: `docs/t050-ops-hardening.md`
- ✅ T-058 restore hot-swap plan/preflight — 같은 cluster 안 `ALTER DATABASE ... RENAME` 패턴을 1차 절차로 고정하고, `/v1/admin/restores/hot-swap-plan`과 `kraddr-geo serving hot-swap-plan`이 current DB, restore DB, previous alias, typed confirmation, rollback confirmation, blockers, SQL/steps를 산출하게 했다. 실제 rename 실행은 metadata 위치와 worker별 engine refresh 검증 뒤 후속 실행 표면으로 분리한다. 상세: `docs/t058-restore-hot-swap.md`
- ✅ PR #69~#80 post-merge 리뷰 audit/fixup — PR #69부터 최신 PR #80까지 formal review와 review thread를 재확인했고 unresolved thread 0건을 기록했다. 수동 table stats capture lock 충돌은 `409 E0409`로 구분하고, `replace_current` restore의 maintenance window 인가 통과는 `maintenance_window.authorize` audit event로 남긴다. 상세: `docs/postmerge-review-fixups-pr69-pr80.md`
- ✅ T-059 CLI/Job 동시 실행 보호 표준화 — `infra.concurrency`의 PostgreSQL session advisory lock helper를 추가하고, 주요 CLI 운영 명령과 FastAPI `JobQueue` handler가 같은 lock key를 공유하도록 했다. 중복 실행은 `E0409/HTTP 409` 또는 CLI exit code 2로 fail-fast한다. Docker PostgreSQL smoke에서 `MV_REFRESH` 중복 lock 차단을 확인했다. 상세: `docs/t059-concurrent-job-protection.md`
- ✅ PR #69~#82 post-merge 리뷰 audit/fixup — PR #69부터 최신 PR #82까지 formal review와 review thread를 재확인했고 unresolved thread 0건을 기록했다. PR #81 리뷰에서 발견된 `maintenance_window.authorize` audit의 `actor_type="job"` CHECK 위반을 `system`으로 고치고, table stats scheduler `skip_if_locked=True` 의도를 호출부에 명시했다. 상세: `docs/postmerge-review-fixups-pr69-pr82.md`
- ✅ T-054 한국 IP GeoIP gate — FastAPI middleware가 내부/loopback은 허용하고 외부 공용 IP는 GeoIP country `KR`만 통과시키게 했다. 기본 `strict` 모드에서는 GeoIP DB가 없으면 공용 IP를 `E0403/403`으로 차단하며, allow/deny CIDR, trusted proxy `X-Forwarded-For`, `geoip.denied` audit, `kraddr-geo geoip check`를 지원한다. 상세: `docs/t054-korea-only-geoip.md`
- ✅ T-055 N150/Odroid 운영 환경 비교 준비 — 실제 장비 도착 전 실행 가능한 준비를 완료했다. `scripts/capture_deployment_envelope.py`로 OS/CPU/메모리/NVMe/Docker/GDAL/PostgreSQL/fio/sysbench/zstd envelope를 캡처하고, T-027 full-load, T-047 SQL/REST benchmark, MV refresh/swap benchmark 실행 runbook과 산출물 구조를 `docs/t055-deployment-n150-odroid.md`에 고정했다. 실제 하드웨어 실측은 T-063으로 보류한다.
- ✅ PR #69~#86 post-merge 리뷰 audit/fixup — PR #69부터 최신 PR #86까지 formal review와 review thread를 재확인했고 thread 0건을 기록했다. PR #84 리뷰 후속으로 GeoIP gate를 admission control보다 먼저 실행하도록 순서를 바꾸고, `testclient` 특별 허용 제거와 `X-Forwarded-For` port 표기 파싱을 보강했다. 상세: `docs/postmerge-review-fixups-pr69-pr86.md`

## 다음 한 작업 (1시간 이내 분량)

즉시 실행 가능한 대기 task는 없다. T-055의 실제 N150/Odroid 실측은 장비가 있어야 의미가 있으므로 T-063으로 보류한다.

- 최신 T-027 실행 로그는 로컬 산출물 `artifacts/fullload/20260529_1643_final/` 아래에 있다. 이 경로는 git ignore 대상이다.
- 최신 실제 DB 정합성은 `severity_max=ERROR`다. 남은 주요 항목은 C2 34,454건, C4 500m 초과 16건, C6 803건, C7 6,817건이다. C10은 `tl_juso_text=202603/202604`, `tl_locsum_entrc`/`tl_navi_*`/`tl_spbd_buld_polygon=202604`, `tl_roadaddr_entrc`/`tl_sppn_makarea=202605`를 row-level evidence로 보고 `WARN` 처리한다.
- `maplibre-vworld-js` 0.1.0 기준 확인 결과는 `docs/t044-maplibre-vworld-010-review.md`에 있다. `v0.1.0` tag commit은 `8559bf4f8d5a32011a51669552bb7e1aedd42cfb`이고, 현재 `kraddr-geo-ui` dependency는 아직 `7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`에 고정되어 있다. npm registry에는 아직 `maplibre-vworld@0.1.0`이 없으므로 실제 dependency 갱신은 별도 PR에서 GitHub tag/commit 기준으로 검증해야 한다. upstream 코드는 T-044에서 직접 수정하지 않는다.
- T-046 백업/복원은 1차 구현과 대구 부분 DB 실제 backup → restore 검증을 완료했다. 전국 T-027 DB의 `serving-ready` 백업 생성은 운영 보존 절차로 별도 실행한다.
- T-047 쿼리 성능 튜닝은 지번 exact/Q4 search exact preflight, 관측성, stress, REST e2e, REST pool/admission 반복 측정, `tar.zst` archive 측정, T-057 region hint 비교, T-061 slim text-search helper까지 완료했다. c64 tail은 여전히 checkout 대기 영향이 커서 `/admin/performance`와 운영 hardening에서 checkout/execute 분리 표시를 이어간다.
- PR #69~#86 리뷰 후속에서 남긴 보류 항목은 v2 `distance_m`/confidence/precision, C1~C10 전수 export, callback receiver 예제, release ledger repair, table 단위 shared lock이다.
- T-055 N150/Odroid 비교는 runbook과 envelope 캡처 준비만 완료했다. 실제 장비가 생기면 T-063에서 `scripts/capture_deployment_envelope.py`, `scripts/fullload_test.sh`, `scripts/benchmark_query_performance.py`, `scripts/benchmark_api_latency.py`, `scripts/benchmark_mv_refresh.py`를 같은 SHA/데이터 snapshot으로 실행한다.

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
- **VWorld debug map**: 실제 키는 `NEXT_PUBLIC_VWORLD_API_KEY`로 로컬 `.env.local`에만 둔다. `maplibre-vworld`는 현재 `git+https://github.com/digitie/maplibre-vworld-js.git#7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`로 고정되어 있지만, T-044에서 `v0.1.0` commit `8559bf4...`의 `VWorldMap`, marker/layer primitive, tile error helper를 문서-only로 재확인했다. SHA/tag를 바꾸면 먼저 최신 `main` 또는 stable release를 확인하고 Linux Node/npm으로 `npm ci`/`lint`/`type-check`/`test`/Next.js build를 다시 확인한다. Windows `npm`은 WSL ext4 경로에서 UNC cleanup 오류를 낼 수 있으므로 사용하지 않는다. `VWorldMap` 컴포넌트 대체는 범용 지도 primitive를 upstream API로 소비하고, key 미설정 fallback 문구, API 응답 overlay, transient overlay 임계치 같은 `kraddr-geo-ui` 특화 동작을 domain wrapper에 남기는 방식으로 진행한다.
- **PR 리뷰 확인 루틴**: PR 리뷰를 반영할 때는 `gh pr view <번호> --json comments,reviews,latestReviews`와 GitHub review thread fetch 스크립트를 함께 확인한다. conversation comment와 formal review body가 따로 존재할 수 있으므로, 제목이 비슷하더라도 마지막 코멘트까지 읽고 merge condition을 문서/코드 체크리스트로 옮긴다.
- **CodeGraph/Windows npm shim**: WSL에서 `codegraph`가 `/mnt/c/Users/.../npm/codegraph`를 가리키고 `node: not found`로 실패하면 Windows npm shim이 PATH에 앞선 것이다. WSL에서는 Linux installer 또는 Linux Node/npm 설치를 사용하고, worktree별 `.codegraph/`가 있으면 `codegraph sync`로 갱신한다.
- **CodeGraph MCP 재시작 필요**: 프로젝트 루트 `.codex/config.toml`에 CodeGraph MCP 설정을 추가했지만 Codex Desktop 재시작 전에는 현재 세션 도구로 노출되지 않을 수 있다. 재시작 후 `codegraph_explore`가 보이면 컴포넌트 수정 전 영향도 확인에 우선 사용한다.

## 작업 후 의무사항

1. `docs/journal.md`에 항목 추가 (날짜·요약·관련 파일·결정·다음 작업)
2. 본 `docs/resume.md`의 진척도 토글 갱신
3. 변경된 결정이 있다면 `docs/decisions.md`에 ADR 추가
4. 사용자 가시 변경이면 `CHANGELOG.md` 갱신
5. 스키마 변경이면 `scripts/export_openapi.py` 재실행 → 프론트엔드 `gen:types`
