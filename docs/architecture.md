# 아키텍처

본 문서는 `kraddr-geo` 백엔드와 `kraddr-geo-ui` 프론트엔드가 함께 구성하는 한 시스템의 큰 구조를 다룬다. 결정의 역사는 `decisions.md`(ADR)에서 별도로 관리한다.

## 두 패키지, 한 시스템

```
┌──────────────────────────┐      HTTP (내부망)      ┌──────────────────────────┐
│  kraddr-geo-ui              │ ──────────────────────▶ │  kraddr-geo (FastAPI)       │
│  Next.js 16 + Tailwind   │                         │  /v1/* + /v2/*           │
│  - /debug/*              │                         │  ─────────────────────── │
│  - /admin/*              │ ◀────────────────────── │  AsyncAddressClient      │
└──────────────────────────┘   OpenAPI → TS 타입     └──────────────────────────┘
                                                                 │
                                                                 ▼
                                                     ┌──────────────────────────┐
                                                     │  PostgreSQL + PostGIS    │
                                                     │  pg_trgm · master tables │
                                                     │  + mv_geocode_target     │
                                                     └──────────────────────────┘
```

- 한 코어(`core/`) 위에 두 인터페이스(Python 라이브러리, REST API)를 노출한다. 두 인터페이스는 같은 함수를 호출하므로 동작이 갈리지 않는다.
- 프론트엔드는 자체 DB 연결을 갖지 않는다. 모든 DB 접근은 `AsyncAddressClient.engine` 하나의 SQLAlchemy 2 async engine을 통과한다 — 디버거에서 본 EXPLAIN 결과가 운영 쿼리와 같은 환경에서 평가된다.

## 백엔드 계층 (`kraddr-geo`)

| 계층 | 위치 | 의존 대상 | 의존하지 않는 것 |
|------|------|-----------|------------------|
| dto | `src/kraddr/geo/dto/` | pydantic v2 | DB, FastAPI, 파일시스템 |
| core | `src/kraddr/geo/core/` | dto, 표준 라이브러리, Protocol | SQLAlchemy, FastAPI, 파일시스템 |
| infra | `src/kraddr/geo/infra/` | core/Protocol, SQLAlchemy 2 async, GeoAlchemy 2, psycopg async | FastAPI |
| loaders | `src/kraddr/geo/loaders/` | infra(엔진만), GeoPandas, GDAL Python binding | core, api |
| client | `src/kraddr/geo/client.py` | core, infra, dto | api, cli, loaders |
| api | `src/kraddr/geo/api/` | client, dto, FastAPI | loaders (admin 라우터만 예외) |
| cli | `src/kraddr/geo/cli/` | client, loaders, typer | api |

의존 방향은 **dto → core → infra → client → api/cli** 한 방향이다. `import-linter`가 `pyproject.toml`의 `[tool.importlinter]` 계약으로 강제한다. 단 하나의 예외(`api.routers.admin → loaders`)는 적재 트리거를 admin 라우터가 직접 호출하기 때문이며 ADR에 명시한다.

T-056 이후 `core/address/`는 시군구/법정동/도로명관리번호/도로명주소관리번호 같은 순수 주소 코드 helper만 맡는다. 도로명/지번 문자열 parser는 `core/normalize.py`에 남기고, 외부 Juso fallback adapter는 `infra`에서 이 helper를 호출해 provider 파라미터를 정규화한다.

## 프론트엔드 계층 (`kraddr-geo-ui`)

| 영역 | 선택 | 이유 |
|------|------|------|
| 프레임워크 | Next.js 16 (App Router) + TypeScript strict | RSC, 디렉토리=URL, 서버측 프록시 단순 |
| UI | Tailwind 기반 자체 primitives | 운영 콘솔에 필요한 작은 컴포넌트부터 소스 코드로 관리 |
| 폼 | controlled form + Zod helper | 초기 UI는 작은 폼 위주, Zod 스키마는 백엔드 pydantic v2와 미러 |
| 지도 | MapLibre GL JS + VWorld WMTS + 최신 `maplibre-vworld` helper | vworld 호환 검증 표면과 같은 공급자의 지도 타일 사용, 범용 VWorld/MapLibre 기능은 `digitie/maplibre-vworld-js` 보강 가능 |
| 테이블 | native table 우선, TanStack Table v8 후속 | 초기 관리 화면은 행 수가 작고, 대량 필터·정렬이 필요하면 승격 |
| 데이터 패칭 | TanStack Query v5 | 폴링·optimistic update |
| 타입 동기 | openapi-typescript + 수동 Zod mirror | 백엔드 `openapi.json`에서 TypeScript 타입 생성, 폼 스키마는 리뷰 가능한 수동 mirror |

자세한 디렉토리 구조, 컴포넌트 설계, 페이지별 화면은 `docs/frontend-package.md`를 본다.

VWorld 지도 연동은 `kraddr-geo-ui` 로컬 코드만의 책임으로 보지 않는다. `maplibre-vworld` package는 항상 최신 `main` 또는 stable release를 확인한 뒤 검증된 SHA로 소비한다. 2026-05-28 T-044에서는 `maplibre-vworld-js` `v0.1.0` tag commit `8559bf4f8d5a32011a51669552bb7e1aedd42cfb` 기준으로 public API를 문서-only로 재확인했고, upstream 코드는 직접 수정하지 않았다. MapLibre/VWorld 공통 컴포넌트나 패키징 문제가 발견되면 별도 upstream task/PR로 분리한다. 반대로 geocode/reverse 디버그 입력, 정합성/성능/적재 overlay, 관리 UI fallback처럼 이 프로젝트에만 의미가 있는 기능은 `kraddr-geo-ui` domain wrapper에서 구현한다.

T-044의 0.1.0 재확인 결론은 `kraddr-geo-ui/components/vworld/CoordinateMap.tsx`의 직접 MapLibre lifecycle 소유를 줄이고, 후속 구현 PR에서 upstream `VWorldMap` 또는 동등한 Hook/component를 감싸는 domain wrapper로 바꾸는 것이다. 필요한 click callback, marker 제어, tile error redaction, SSR-safe 사용법 같은 범용 기능이 upstream에 부족하면 이 저장소에서만 우회하지 않고 별도 upstream 작업으로 분리한다. key 미설정 fallback 문구와 layout, API 응답 overlay, 운영 콘솔 상태 연결은 이 저장소에 남긴다.

## 데이터 흐름 — 지오코딩

```
HTTP GET /v1/address/geocode?address=...
   │
   ▼
api.routers.geocode      ←  Pydantic 입력 검증
   │
   ▼
AsyncAddressClient._geocode_v1(...)
   │
   ▼
core.geocoder.geocode(repo, inp)
   │  ├ core.normalize.parse_address(...)         (순수 함수)
   │  ├ repo.lookup_by_road(...)                  (Protocol)
   │  └ (실패 시) repo.fuzzy_roads(...) → 재시도
   ▼
infra.geocode_repo.GeocodeRepository
   │  └ SQLAlchemy 2 async + raw SQL (mv_geocode_target)
   ▼
PostgreSQL + PostGIS (pg_trgm)
```

Python 공개 API의 `AsyncAddressClient.geocode()`는 위 내부 v1 호환 경로를 실행한 뒤 후보 목록 응답으로 투영한다. REST `/v1/address/geocode`만 vworld 호환 DTO를 그대로 반환한다.

## 데이터 흐름 — 쿼리 성능 벤치마크와 튜닝 (ADR-031, T-047)

```
전국 full-load 완료 DB
  ├─ row count/source_set/DB 설정 snapshot
  ├─ benchmark corpus 실행
  │   ├─ 도로명 exact / 지번 exact
  │   ├─ fuzzy geocode / 통합 search
  │   ├─ reverse nearest / reverse radius
  │   └─ zipcode / no-result / invalid
  ├─ EXPLAIN ANALYZE BUFFERS + pg_stat_statements 저장
  └─ p50/p95/p99/timeout/error/buffer report
        │
        ▼
  목표 초과 query군 분석
        │
        ├─ query rewrite / index / partial index 실험
        ├─ KNN·5179 공간 index·UNION ALL 분기 실험
        └─ 필요 시 read-only 보조 view/MV 도입
             ├─ mv_geocode_exact_key
             ├─ mv_geocode_text_search
             ├─ mv_reverse_point_5179
             └─ mv_zipcode_lookup
```

T-047의 보조 view/MV는 별도 source of truth가 아니다. master table 또는 `mv_geocode_target`에서 재생성 가능한 serving accelerator이며, API 응답 구조와 vworld 호환 계약은 그대로 유지한다. 새 보조 객체를 도입하면 refresh/swap 순서, index build time, disk size, `ANALYZE`, T-046 backup/restore 영향까지 함께 측정한다.

T-061에서 `mv_geocode_text_search`가 실제 read-only helper MV로 추가됐다. Q3 fuzzy geocode와 Q4 broad search fallback은 이 helper에서 `bd_mgt_sn` 후보를 먼저 추출한 뒤 `mv_geocode_target`에 join한다. Q4 exact preflight는 기존 target exact index를 유지한다. T-065 이후 helper에는 내비게이션용DB `시군구용건물명` 정규화 컬럼(`sigungu_buld_nm_nrm`)도 포함되어, 지역 문맥의 건물 별칭·동명 검색 후보 recall을 보강한다.

## 데이터 흐름 — 적재 (full-load batch)

```
Next.js /admin/load
  ├─ 다중 파일 선택/DND
  ├─ upload set 생성 ──POST /v1/admin/uploads──────────────────────▶ uploads/<upload_set_id>/
  ├─ 파일 저장 ───────PUT /v1/admin/uploads/{id}/files────────────▶ *.part → checksum → atomic rename
  ├─ source set 분석 ─POST /v1/admin/load-sources/discover────────▶ SourceSetDiscovery
  ├─ 기준월 mismatch 확인 ──POST /v1/admin/load-sources/plan──────▶ SourceSetPlan
  └─ batch 등록 ─────POST /v1/admin/loads kind=full_load_batch────▶ load_jobs root
                                                                    │
                                                                    ▼
                                                     필수 source child 5종 + 선택 child 직렬 실행
                               juso_text · juso_parcel_link · locsum · navi · shp_polygons
                               (+ roadaddr_entrance · pobox · bulk)
                                                                    │
                                                                    ▼
                                                     consistency_check (C1~C10)
                                                                    │
                                                                    ▼
                                            severity_max != ERROR 이면 mv_refresh swap enqueue
```

REST 큐와 `AsyncAddressClient.submit_load("full_load_batch", ...)`는 같은 `infra.batch.batch_children()` 검증 helper를 사용한다. 잘못된 payload는 root job을 만들기 전에 `InvalidInputError(E0100)`로 거절한다.

ADR-029/T-045부터 full-load 입력은 단일 `yyyymm`이 아니라 원천별 기준월을 가진 `source_set`으로 다룬다. CLI는 기준월이 서로 다른 source set을 발견하면 사용자에게 의도한 혼합 적재인지 확인하고, API/라이브러리는 prompt 없이 `discover_load_sources()`와 `build_full_load_source_set_plan()`을 분리 제공한다. UI는 모든 파일 저장이 끝난 뒤 source set을 분석하고, 기준월이 맞지 않으면 확인 modal을 거쳐 적재를 시작한다. 새 plan은 `payloads` mapping 대신 명시 `children` 배열을 만들어 선택 원천만 batch DAG에 포함한다.

`roadaddr_entrance_load`는 T-039부터 등록된 선택 child다. direct `bd_mgt_sn + EPSG:5179` 출입구를 `tl_roadaddr_entrc`에 적재한다. T-027 최종 클린 적재 재검증 이후 MV/정합성 serving CTE는 `tl_locsum_entrc`를 먼저 쓰고, direct 출입구는 `tl_roadaddr_entrc.source_yyyymm`이 `tl_juso_text.source_yyyymm`와 같은 기준월일 때만 fallback 후보로 사용한다. 현재 로컬 자료 기준월은 direct 출입구가 `202605`, 텍스트 정본이 `202603`이라 기본 full-load 6종에는 자동 포함하지 않고, 명시 child로 적재하더라도 serving 좌표에는 승격하지 않는다.

## 데이터 흐름 — DB 백업/복원 (ADR-030, T-046)

```
Next.js /admin/backups
  ├─ 백업 설정 입력
  │   ├─ 저장 위치: 서버 allowlist 하위 경로
  │   ├─ profile: serving-ready | lean-serving | forensic
  │   └─ callback URL: allowlist host만 허용
  ├─ 백업 등록 ─────POST /v1/admin/backups───────────────────────▶ load_jobs(kind=db_backup)
  │                                                                 │
  │                                                                 ▼
  │                                                  preflight → pg_dump -Fd --jobs
  │                                                                 │
  │                                                                 ▼
  │                                             manifest/checksum/log + tar.zst archive
  │                                                                 │
  │                                                                 ▼
  │                                            ops.artifacts metadata + callback
  │                                                                 │
  └─ 진행률 조회 ───GET /v1/admin/jobs/{id}/events 또는 polling────┘
      완료 후 ─────GET /v1/admin/backups/{artifact_id}/download────▶ streaming download
```

복원 흐름:

```
Next.js /admin/backups
  ├─ artifact와 target DB 선택
  ├─ 복원 등록 ─────POST /v1/admin/restores──────────────────────▶ load_jobs(kind=db_restore)
  │                                                                 │
  │                                                                 ▼
  │                                           archive 검증 → 새 빈 DB 확인 → extract
  │                                                                 │
  │                                                                 ▼
  │                                                pg_restore -Fd --jobs → ANALYZE
  │                                                                 │
  │                                                                 ▼
  │                                          row count/smoke 검증 → callback/finalize
  └─ 진행률 조회 ───GET /v1/admin/jobs/{id}/events 또는 polling────┘
```

plain SQL/DDL dump는 대용량 운영 기본값으로 사용하지 않는다. `pg_dump -Fd`와 `pg_restore -Fd`가 병렬성을 제공하고, `tar.zst` 단일 artifact는 UI 다운로드와 외부 보관에 적합하기 때문이다. 복원은 기본적으로 새 빈 DB에만 수행하고, 현재 운영 DB를 직접 덮어쓰는 경로는 maintenance mode와 명시 확인을 요구하는 별도 위험 경로로 둔다.

T-046 구현 검증은 전국 full-load를 다시 실행하지 않고 대구광역시 부분 적재 DB로 수행한다. 백업 원본 DB는 `kraddr_geo_t046_daegu`, 복원 target은 `kraddr_geo_t046_daegu_restore`로 분리하고, `mv_geocode_target` row count와 대구 geocode/reverse smoke test가 복원 후에도 유지되는지 확인한다.

## 데이터 흐름 — 운영 메타데이터와 릴리스 추적 (ADR-033, T-049)

```
full-load / daily / restore / mv_refresh / benchmark
  │
  ├─ load_jobs 상태 전환
  │      └─ ops.audit_events append-only 기록
  │
  ├─ source_set + row count + schema/code version capture
  │      └─ ops.dataset_snapshots
  │
  ├─ consistency / performance / backup / export 산출물
  │      └─ ops.artifacts(checksum, retention, callback, download token hash)
  │
  ├─ table/MV/index size와 통계 capture
  │      └─ ops.table_stats_snapshots
  │
  └─ MV shadow swap 성공
         └─ ops.serving_releases(active 1건, rollback lineage)
```

`ops` 스키마는 주소 원천 데이터가 아니라 운영 제어면이다. `public`의 master table과 serving MV는 조회 source of truth이고, `ops.dataset_snapshots`와 `ops.serving_releases`는 "어떤 source of truth 상태가 운영에 노출됐는가"를 설명한다. destructive restore, schema migration, full reset은 `ops.maintenance_windows`의 active window와 typed confirmation 없이는 실행하지 않는다.

T-046의 백업 artifact, T-047의 성능 리포트, C2/C4/C6/C7 data-quality export는 모두 `ops.artifacts`로 수렴한다. 이 공통 registry를 쓰면 checksum, 보존 기간, callback, download link, 관련 job/snapshot/release를 같은 방식으로 추적할 수 있다.

T-050 5차부터 `ops.table_stats_snapshots`는 수동 capture API뿐 아니라 API lifespan의 opt-in scheduler로도 쌓을 수 있다. 기본값은 비활성이라 개발 서버가 예기치 않은 write를 만들지 않고, interval을 켜면 주기 결과가 현재 active serving release snapshot에 자동 연결된다. 여러 API worker가 동시에 깨어나도 capture transaction은 advisory lock으로 한 번만 통과한다.

## 데이터 흐름 — 일변동 적용

```
운영자/스케줄러
  ├─ CLI: kraddr-geo load daily-juso data/juso/daily/20260401_dailyjusukrdata.zip
  └─ API: POST /v1/admin/loads kind=daily_juso_delta
                                                                    │
                                                                    ▼
                                                     daily_juso_loader.py
                                      TH_SGCO_RNADR_MST.TXT → tl_juso_text
                                      TH_SGCO_RNADR_LNBR.TXT → tl_juso_parcel_link
                                                                    │
                                                                    ▼
                                                     load_manifest daily watermark
                                                                    │
                                                                    ▼
                                            필요 시 resolve_text_geometry_links + mv_refresh
```

일변동은 full-load batch의 기본 child가 아니다. full-load가 끝난 운영 DB에 후속으로 적용하는 별도 작업이며, 적용 후 조회 표면에 반영하려면 운영자가 `refresh mv` 또는 `mv_refresh` job을 실행한다. `MST`는 `daily_juso_delta`, `LNBR`는 `juso_parcel_link_delta`로 분리 적용한다. 이 분리는 도로명주소 정본 변경과 보조 지번 1:N 변경의 실패/재시도 단위를 분리하기 위한 것이다.

## 개발 환경 (PC, WSL)

PC 개발은 WSL의 ext4 위에서 진행한다. NTFS 마운트에서 직접 `git`/`pip`/`uvicorn`을 실행하지 않는다.

```
~/dev/python-kraddr-geo/                              ← 코드, 가상환경, 테스트 (ext4, source of truth)
/mnt/<drive>/projects/python-kraddr-geo/              ← Windows에서도 보이는 카피본 (NTFS)
/mnt/<drive>/projects/python-kraddr-geo/data/         ← 도로명주소 ZIP/SHP, postal TXT, 외부 dump (NTFS)
```

- 작업이 완료되면 ext4 → NTFS 프로젝트 디렉토리로 카피한다.
- **데이터(`data/`)는 NTFS 측에만 둔다**. ext4 작업 디렉토리에는 심볼릭 링크(`ln -s /mnt/<drive>/projects/python-kraddr-geo/data data`) 또는 절대경로로만 참조한다.
- 통합/e2e 테스트, 전국 적재 검증, vworld 비교 등은 NTFS의 `data/`를 reference로 삼는다.

## 적재 ↔ 서빙은 단일 스키마 + MV로 분리한다

본 사양은 별도의 "서빙 어댑터 스키마"를 두지 않는다. 적재(`tl_spbd_*`, `tl_scco_*` 등 11개 마스터)와 서빙(`mv_geocode_target` 머티리얼라이즈드 뷰)이 **같은 DB·같은 search_path** 위에 있고, 라이브러리/REST API/디버거가 모두 `AsyncAddressClient.engine` 하나로 접근한다. 별도 `*_serving_*` 테이블을 만드는 패턴은 도입하지 않는다 — 동일 PK·동일 컬럼명에서 두 스키마가 갈라지면 회귀 시 침묵하기 쉽다. 평면화·denormalization이 필요하면 MV 또는 view로 표현하고, 컬럼명은 마스터 테이블과 일치시킨다(ADR-007 후속).

## 운영 환경

- DB: PostgreSQL 16 + PostGIS 3.4 (또는 호환 마이너 버전). `pg_trgm`, `unaccent` 확장 사용.
- 백엔드 런타임: Python 3.12, `uvicorn --workers 2 --proxy-headers` 권장. ARM 8GB 환경에서는 워커 수를 보수적으로.
- 프론트엔드: Node.js 20 LTS, Next.js 16. 사내망 또는 VPN 뒤에서만 접근 (별도 애플리케이션 인증 없음).
- 외부 노출이 필요하면 nginx/traefik의 basic auth, IP allowlist 또는 사내 SSO 게이트웨이 뒤에 둔다. 애플리케이션 코드에 인증 로직을 침투시키지 않는다(ADR-013).

## 관찰가능성

- 구조화 로그: `structlog` JSON. PR #12의 `/admin/logs`는 우선 `load_jobs.log_tail` 최근 라인을 조회하며, WebSocket tail은 후속 후보로 둔다.
- 메트릭: `prometheus-client`. `/metrics`에서 외부 API 호출 카운터, cache entries/hits/expired, 적재 작업 kind/state gauge를 노출한다.
- 트레이싱: (선택) OpenTelemetry. 도입은 ADR로 별도 결정.

## 참고

- 백엔드 사양서: `docs/backend-package.md`
- 프론트엔드 사양서: `docs/frontend-package.md`
- 데이터 모델: `docs/data-model.md`, `docs/address-db-schema.md`
- 결정 기록: `docs/decisions.md`
- 외부 API: `docs/external-apis.md`
