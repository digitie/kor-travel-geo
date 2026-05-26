# 아키텍처

본 문서는 `kraddr-geo` 백엔드와 `kraddr-geo-ui` 프론트엔드가 함께 구성하는 한 시스템의 큰 구조를 다룬다. 결정의 역사는 `decisions.md`(ADR)에서 별도로 관리한다.

## 두 패키지, 한 시스템

```
┌──────────────────────────┐      HTTP (내부망)      ┌──────────────────────────┐
│  kraddr-geo-ui              │ ──────────────────────▶ │  kraddr-geo (FastAPI)       │
│  Next.js 16 + Tailwind   │                         │  /v1/* + /v1/admin/*     │
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

## 프론트엔드 계층 (`kraddr-geo-ui`)

| 영역 | 선택 | 이유 |
|------|------|------|
| 프레임워크 | Next.js 16 (App Router) + TypeScript strict | RSC, 디렉토리=URL, 서버측 프록시 단순 |
| UI | Tailwind 기반 자체 primitives | 운영 콘솔에 필요한 작은 컴포넌트부터 소스 코드로 관리 |
| 폼 | controlled form + Zod helper | 초기 UI는 작은 폼 위주, Zod 스키마는 백엔드 pydantic v2와 미러 |
| 지도 | MapLibre GL JS + VWorld WMTS + `maplibre-vworld` helper | vworld 호환 검증 표면과 같은 공급자의 지도 타일 사용, `digitie/maplibre-vworld-js` 보강 가능 |
| 테이블 | native table 우선, TanStack Table v8 후속 | 초기 관리 화면은 행 수가 작고, 대량 필터·정렬이 필요하면 승격 |
| 데이터 패칭 | TanStack Query v5 | 폴링·optimistic update |
| 타입 동기 | openapi-typescript + 수동 Zod mirror | 백엔드 `openapi.json`에서 TypeScript 타입 생성, 폼 스키마는 리뷰 가능한 수동 mirror |

자세한 디렉토리 구조, 컴포넌트 설계, 페이지별 화면은 `docs/frontend-package.md`를 본다.

VWorld 지도 연동은 `kraddr-geo-ui` 로컬 코드만의 책임으로 보지 않는다. `maplibre-vworld` package는 검증된 GitHub SHA로 소비하고, MapLibre/VWorld 공통 컴포넌트나 패키징 문제가 발견되면 `digitie/maplibre-vworld-js`도 적극 수정 대상에 포함한다. 이 원칙은 디버그 UI가 장기적으로 재사용 가능한 VWorld MapLibre wrapper 위에 얹히도록 하기 위한 것이다.

T-044부터는 이 원칙을 더 강하게 적용한다. `kraddr-geo-ui/components/vworld/CoordinateMap.tsx`의 직접 MapLibre wiring을 유지하는 것이 아니라, upstream `maplibre-vworld-js`의 `VWorldMap` 또는 동등한 Hook/component로 완전히 포팅한다. 필요한 click callback, marker 제어, tile error overlay, key fallback, SSR-safe 사용법이 upstream에 부족하면 이 저장소에서만 우회하지 않고 upstream을 수정한 뒤 검증된 SHA를 다시 소비한다.

## 데이터 흐름 — 지오코딩

```
HTTP GET /v1/address/geocode?address=...
   │
   ▼
api.routers.geocode      ←  Pydantic 입력 검증
   │
   ▼
AsyncAddressClient.geocode(...)
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
                                                     source child 6종 직렬 실행
                       juso_text · juso_parcel_link · locsum · navi · shp_polygons · pobox
                                                                    │
                                                                    ▼
                                                     consistency_check (C1~C10)
                                                                    │
                                                                    ▼
                                            severity_max != ERROR 이면 mv_refresh swap enqueue
```

REST 큐와 `AsyncAddressClient.submit_load("full_load_batch", ...)`는 같은 `infra.batch.batch_children()` 검증 helper를 사용한다. 잘못된 payload는 root job을 만들기 전에 `InvalidInputError(E0100)`로 거절한다.

ADR-029/T-045부터 full-load 입력은 단일 `yyyymm`이 아니라 원천별 기준월을 가진 `source_set`으로 다룬다. CLI는 기준월이 서로 다른 source set을 발견하면 사용자에게 의도한 혼합 적재인지 확인하고, API/라이브러리는 prompt 없이 `discover_load_sources()`와 `build_full_load_source_set_plan()`을 분리 제공한다. UI는 모든 파일 저장이 끝난 뒤 source set을 분석하고, 기준월이 맞지 않으면 팝업 확인을 거쳐 적재를 시작한다.

`roadaddr_entrance_load`는 T-039부터 등록된 선택 child다. direct `bd_mgt_sn + EPSG:5179` 출입구를 `tl_roadaddr_entrc`에 적재하고 MV 대표 좌표 1순위 후보로 사용하지만, 현재 로컬 자료 기준월이 `202605`라 기본 full-load 6종에는 자동 포함하지 않는다. 같은 기준월의 전체분을 확보했거나 C10 기준월 불일치를 의도적으로 감수하는 검증에서는 `children` 또는 `child_jobs`에 명시해 batch에 포함한다.

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
