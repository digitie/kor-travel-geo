# RESUME — 작업 재개 가이드

새 에이전트 세션이 시작될 때 "지금 어디까지 했고, 다음은 뭐 하면 되나"를 한 화면에서 답한다.

## 현재 진척도 (2026-05-26 갱신, by codex)

- ✅ 이전 SpatiaLite 기반 `kraddr.geo` 구현을 `v1` 브랜치로 이관
- ✅ master 브랜치를 문서·repo 설정만 남도록 정리
- ✅ 신규 사양(`kraddr.geo` 패키지의 PostgreSQL+PostGIS 재구현 + `kraddr-geo-ui` 프론트엔드) 문서 골격을 master에 반영
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
- ✅ T-021 프론트엔드 패키지 `kraddr-geo-ui` 부트스트랩 — Next.js 16 + React 18 + Tailwind + TanStack Query. 지도는 MapLibre GL JS + VWorld WMTS를 사용하며, `digitie/maplibre-vworld-js` 문제도 적극 수정 대상으로 둔다.
- ✅ T-022 디버그 페이지 구현 — `/debug/geocode`, `/debug/reverse`, `/debug/normalize`, `/debug/explain`
- ✅ T-023 관리 페이지 구현 — `/admin/load`, `/admin/tables`, `/admin/cache`, `/admin/logs`
- ✅ T-024 품질 게이트 추가 — 루트 `pre-commit`, 통합 CI, frontend `gen:types` drift 검사, lint/type/test/build
- ✅ T-025 Prometheus 메트릭 구현 — `/metrics`, 외부 API 호출 counter, cache/load job gauge
- ✅ T-026 정합성 UI 구현 — `/admin/consistency`에서 C1~C10 report 목록·상세·재검증 enqueue 확인
- ✅ FastAPI admin 보강 — `/v1/admin/tables`, `/v1/admin/explain`, `/v1/admin/cache/metrics`, `/v1/admin/logs`, `/v1/admin/upload/sido-zip`, `/v1/admin/maintenance/refresh-mv`
- ✅ PR #12 리뷰 보강 — 업로드 path traversal/크기 제한, 프록시 `/v1` 제한과 스트리밍 전달, React Query retry, EXPLAIN timeout, LoadConsole/Explain/Reverse/Consistency 에러 처리, CI `scripts` import 실패 수정
- ✅ PR #15 리베이스/리뷰 보강 — PR #14 merge 이후 최신 `main` 위로 rebase하고, `maplibre-vworld`를 upstream main commit `a5b3c65`로 고정해 helper/CSS를 실제 package에서 소비한다. 이후 후속 PR에서는 upstream PR #9 commit `11321fe`로 동기화해 VWorld tile error/redaction helper까지 공유한다.
- 🟡 PR #13/T-027 계획 보강 — `data/juso` 전체 인벤토리, Docker full-load 실행 금지선, 기준월 분리(`JUSO_YYYYMM`/`LOCSUM_YYYYMM`/`NAVI_YYYYMM`), `PLAN_ONLY=1` preflight, 미지원 자료 후속 태스크를 문서화
- 🟡 Windows 재설치/새 Codex 세션 복구 문서화 — `docs/windows-reinstall-recovery.md`에 Git/PR handoff, `data/`·`.env` 백업, WSL 복구, Codex `resume`/`fork`/로컬 백업 명령을 정리하고 `CLAUDE.md`/`docs/dev-environment-recovery.md`의 실제 적재 금지선을 동기화
- 🟡 PR #14/T-027 실제 전체 적재 실행 — WSL ext4 작업 사본 `~/kraddr-geo-data`와 Docker PostGIS(`localhost:15432`)에서 텍스트/NAVI/SHP/MV 적재를 수행
- ✅ 실제 SHP 17개 시도 × 9개 레이어 재적재 완료 — 153 레이어, 3시간 10분 4초, `tl_spbd_buld_polygon` 10,687,732행, `tl_sprd_intrvl` 16,993,167행, `tl_sprd_rw` 1,482,679행
- ✅ 실제 SHP natural key 스키마 검증 — `bjd_cd`/건물번호/geometry 전 건 채움, `rds_sig_cd`/`rncode_full` NULL 581건 확인
- ✅ C4/C5 정합성 SQL 보강 — natural key 중복 polygon 다대다 거리 오염을 막기 위해 nearest polygon 1개만 평가하도록 수정
- ✅ 실제 smoke test 보강 — psycopg optional filter 타입 추론 오류를 `CAST(:param AS ...)`로 수정하고 geocode/reverse/search/zipcode smoke 통과
- ✅ PR #14 리뷰 반영 — Alembic `0002_t027_shp_schema_fixups`, SHP generated column 빈 문자열 보정, `KRADDR_GEO_DB_PORT` 네이밍, MV index 경고, SHP truncate row snapshot, PR 리뷰 확인 프로토콜 문서화
- ✅ PR #14 추가 리뷰 반영 — `tl_sprd_rw` migration non-polygon row guard, MV index rename live catalog 유도, locsum `staging_seq`, navi zero-coordinate skip, GDAL `connect_timeout`, C6/C7 `ST_Covers` 전환
- ✅ 실제 C2/C4/C6/C7 선택 재검증 — C2 `missing_text=34,118`/`missing_resolve_key=581`, C4 `over_500m=16`, C6 803/C7 6,817 유지 확인
- 🟡 T-031 데이터 품질 후속 분석 PR 분리 — PR #14 close 이후 이어갈 C2/C4/C6/C7 sample/지도/원천 파일 역추적 계획을 `docs/t027-data-quality-followup.md`에 정리
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
- 🟡 실제 C1~C10 재검증 완료 — C4/C5는 크게 개선됐지만 C2/C4/C6/C7은 실제 데이터 기준 `ERROR`가 남아 후속 분석 필요

## 다음 한 작업 (1시간 이내 분량)

T-029 PR을 열어 약 20분 리뷰 코멘트를 기다린 뒤, 코멘트가 있으면 최대한 반영하고 없으면 main에 merge한다. 그 다음 구현 작업은 T-030 상세주소 동 도형/별도 건물 도형 로더 검토다.

- 상세 실행 로그는 로컬 산출물 `artifacts/fullload/20260524_173115/execution-log.md`에 있다. 이 경로는 git ignore 대상이다.
- 현재 실제 DB 정합성은 `severity_max=ERROR`다. 남은 주요 항목은 C2 34,699건, C4 500m 초과 16건, C6 803건, C7 6,817건이다.
- T-034에서 `TL_SPRD_INTRVL` 전용 COPY 경로는 검증했지만, `TL_SPBD_BULD`는 여전히 GDAL append 경로다. 전국 전체 SHP 시간은 T-027 최종 클린 로드에서 다시 확인한다.
- T-035에서 `kraddr_geo_t033` MV는 여러 번 refresh/swap됐고 최종 상태는 `mv_geocode_target=6,416,637`, `mv_geocode_target_next/old` 없음, index 이름 `idx_mv_*` 정상이다.
- `maplibre-vworld-js` upstream main 확인 커밋은 `c91c9f304669ce3f5fc4915f21186b23731d5816`이고, 현재 `kraddr-geo-ui`는 이 SHA에 맞춰져 있다. 최신 upstream은 `redactVWorldTileUrl()`가 아니라 `redactVWorldUrl()`를 export하므로 `kraddr-geo-ui/lib/vworld.ts`에서 기존 내부 이름으로 alias한다.
- PR #17 이전에 적재된 실제 T-027 DB의 SHP `source_file`은 전 건 NULL이다. PR #17 이후 SHP를 재적재하면 `source_file=<시도>/<시군구코드>/<레이어>.shp`와 `source_yyyymm`가 채워진다.
- `daily/*.zip`는 T-028 이후 MST만 적용 가능하다. `jibun_rnaddrkor_*`와 daily `LNBR`는 ADR-022에 따라 후속 `tl_juso_parcel_link`로 분리한다. `건물군 내 상세주소 동 도형`, `도로명주소 출입구 정보`는 현재 full-load 스크립트의 적재 대상이 아니며 T-030에서 중복·보완 관계를 조사한다.

## 작업 시작 전 확인할 것

- [ ] `AGENTS.md`의 "식별자" 표와 "개발 환경 정책" 다시 읽기
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
- **VWorld debug map**: 실제 키는 `NEXT_PUBLIC_VWORLD_API_KEY`로 로컬 `.env.local`에만 둔다. `maplibre-vworld`는 현재 `git+https://github.com/digitie/maplibre-vworld-js.git#c91c9f304669ce3f5fc4915f21186b23731d5816`로 고정되어 있고 `dist`/`exports`/`types`/`style.css`, click/error/flyTo hook, tile error helper가 포함됨을 확인했다. SHA를 바꾸면 Linux Node/npm으로 `npm ci`/`type-check`/`test`/Next.js build를 다시 확인한다. Windows `npm`은 WSL ext4 경로에서 UNC cleanup 오류를 낼 수 있으므로 사용하지 않는다. `VWorldMap` 컴포넌트 전체 대체는 click callback, key 미설정 fallback, transient tile error redaction/overlay, SSR-safe wrapper 동작을 upstream과 맞추는 후속 PR에서 진행한다.
- **PR 리뷰 확인 루틴**: PR 리뷰를 반영할 때는 `gh pr view <번호> --json comments,reviews,latestReviews`와 GitHub review thread fetch 스크립트를 함께 확인한다. conversation comment와 formal review body가 따로 존재할 수 있으므로, 제목이 비슷하더라도 마지막 코멘트까지 읽고 merge condition을 문서/코드 체크리스트로 옮긴다.

## 작업 후 의무사항

1. `docs/journal.md`에 항목 추가 (날짜·요약·관련 파일·결정·다음 작업)
2. 본 `docs/resume.md`의 진척도 토글 갱신
3. 변경된 결정이 있다면 `docs/decisions.md`에 ADR 추가
4. 사용자 가시 변경이면 `CHANGELOG.md` 갱신
5. 스키마 변경이면 `scripts/export_openapi.py` 재실행 → 프론트엔드 `gen:types`
