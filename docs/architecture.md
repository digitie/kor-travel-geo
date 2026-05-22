# 아키텍처

본 문서는 `addr-kr` 백엔드와 `addr-kr-ui` 프론트엔드가 함께 구성하는 한 시스템의 큰 구조를 다룬다. 결정의 역사는 `decisions.md`(ADR)에서 별도로 관리한다.

## 두 패키지, 한 시스템

```
┌──────────────────────────┐      HTTP (내부망)      ┌──────────────────────────┐
│  addr-kr-ui              │ ──────────────────────▶ │  addr-kr (FastAPI)       │
│  Next.js 14 + shadcn/ui  │                         │  /v1/* + /v1/admin/*     │
│  - /debug/*              │                         │  ─────────────────────── │
│  - /admin/*              │ ◀────────────────────── │  AsyncAddressClient      │
└──────────────────────────┘   OpenAPI → 타입·Zod    └──────────────────────────┘
                                                                 │
                                                                 ▼
                                                     ┌──────────────────────────┐
                                                     │  PostgreSQL + PostGIS    │
                                                     │  pg_trgm · 11 master MV  │
                                                     └──────────────────────────┘
```

- 한 코어(`core/`) 위에 두 인터페이스(Python 라이브러리, REST API)를 노출한다. 두 인터페이스는 같은 함수를 호출하므로 동작이 갈리지 않는다.
- 프론트엔드는 자체 DB 연결을 갖지 않는다. 모든 DB 접근은 `AsyncAddressClient.engine` 하나의 SQLAlchemy 2 async engine을 통과한다 — 디버거에서 본 EXPLAIN 결과가 운영 쿼리와 같은 환경에서 평가된다.

## 백엔드 계층 (`addr-kr`)

| 계층 | 위치 | 의존 대상 | 의존하지 않는 것 |
|------|------|-----------|------------------|
| dto | `src/addr_kr/dto/` | pydantic v2 | DB, FastAPI, 파일시스템 |
| core | `src/addr_kr/core/` | dto, 표준 라이브러리, Protocol | SQLAlchemy, FastAPI, 파일시스템 |
| infra | `src/addr_kr/infra/` | core/Protocol, SQLAlchemy 2 async, GeoAlchemy 2, psycopg async | FastAPI |
| loaders | `src/addr_kr/loaders/` | infra(엔진만), GeoPandas, GDAL Python binding | core, api |
| client | `src/addr_kr/client.py` | core, infra, dto | api, cli, loaders |
| api | `src/addr_kr/api/` | client, dto, FastAPI | loaders (admin 라우터만 예외) |
| cli | `src/addr_kr/cli/` | client, loaders, typer | api |

의존 방향은 **dto → core → infra → client → api/cli** 한 방향이다. `import-linter`가 `pyproject.toml`의 `[tool.importlinter]` 계약으로 강제한다. 단 하나의 예외(`api.routers.admin → loaders`)는 적재 트리거를 admin 라우터가 직접 호출하기 때문이며 ADR에 명시한다.

## 프론트엔드 계층 (`addr-kr-ui`)

| 영역 | 선택 | 이유 |
|------|------|------|
| 프레임워크 | Next.js 14 (App Router) + TypeScript strict | RSC, 디렉토리=URL, 서버측 프록시 단순 |
| UI | shadcn/ui (Radix + Tailwind) | 소스 코드로 컴포넌트가 들어와 커스터마이즈 자유 |
| 폼 | React Hook Form + Zod | Zod 스키마는 백엔드 pydantic v2와 미러 |
| 지도 | react-kakao-maps-sdk | 한국 좌표·지명에 가장 풍부 |
| 테이블 | TanStack Table v8 | 헤드리스, 정렬·필터·페이지네이션 |
| 데이터 패칭 | TanStack Query v5 | 폴링·optimistic update |
| 타입 동기 | openapi-typescript + openapi-fetch + ts-to-zod | 백엔드 `openapi.json`에서 자동 생성 |

자세한 디렉토리 구조, 컴포넌트 설계, 페이지별 화면은 `docs/frontend-package.md`를 본다.

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

## 데이터 흐름 — 적재 (시도별)

```
Next.js 업로드 폼  ──POST /v1/admin/upload/sido-zip──▶  api/routers/admin.upload_sido_zip
                                                              │
                                                              ▼
                                                        디스크에 ZIP 저장 (uploads/)
                                                              │
모든 업로드 완료 → POST /v1/admin/load/sido-batch ──▶  api._jobs.queue.enqueue(...)
                                                              │
                                                              ▼
                                          asyncio.Semaphore(1) — 직렬 처리
                                                              │
                                                              ▼
                            loaders.sido_loader.SidoLoader.load_sido(...)
                              │  ├ ZIP 해제 → SHP 디렉토리
                              │  ├ gdal.VectorTranslate(..., open_options=["ENCODING=CP949"])
                              │  ├ 진행률 callback → Job.progress
                              │  └ (delta) loaders.delta_loader.apply_delta(...)
                              ▼
                          PostgreSQL (master tables) → REFRESH MATERIALIZED VIEW
```

## 운영 환경

- DB: PostgreSQL 16 + PostGIS 3.4 (또는 호환 마이너 버전). `pg_trgm`, `unaccent` 확장 사용.
- 백엔드 런타임: Python 3.12, `uvicorn --workers 2 --proxy-headers` 권장. ARM 8GB 환경에서는 워커 수를 보수적으로.
- 프론트엔드: Node.js 20 LTS, Next.js 14. 사내망 또는 VPN 뒤에서만 접근 (별도 애플리케이션 인증 없음).
- 외부 노출이 필요하면 nginx/traefik의 basic auth, IP allowlist 또는 사내 SSO 게이트웨이 뒤에 둔다. 애플리케이션 코드에 인증 로직을 침투시키지 않는다(ADR-013).

## 관찰가능성

- 구조화 로그: `structlog` JSON. 디버그 UI의 `/admin/logs`가 WebSocket으로 tail.
- 메트릭: `prometheus-client`. 외부 API 호출 카운터, 캐시 hit rate, 적재 작업 상태.
- 트레이싱: (선택) OpenTelemetry. 도입은 ADR로 별도 결정.

## 참고

- 백엔드 사양서: `docs/backend-package.md`
- 프론트엔드 사양서: `docs/frontend-package.md`
- 데이터 모델: `docs/data-model.md`, `docs/address-db-schema.md`
- 결정 기록: `docs/decisions.md`
- 외부 API: `docs/external-apis.md`
