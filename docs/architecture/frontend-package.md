# 프론트엔드 패키지 사양서 — `kor-travel-geo-ui`

본 문서는 첨부 사양서(2026-05-22 작성) Part A를 `main` 문서 체계로 옮긴 정리본이다. 디버깅 UI + DB 관리 UI를 한 Node.js 패키지로 통합 운영한다.

## A1. 개요

### A1.1 두 영역, 한 패키지

`kor-travel-geo-ui`는 `kor-travel-geo`(Python 패키지 `kortravelgeo`) 백엔드와 별도의 Node.js 패키지다. 사용자 대상 UI가 아니라 개발자·운영자가 라이브러리를 검증·관리하기 위한 내부 도구다.

- **디버깅 UI**: 지오코딩·역지오코딩·통합검색·정규화·SQL EXPLAIN을 지도와 함께 시각 검증
- **DB 관리 UI**: 테이블 통계, 적재 작업 큐, MV refresh, 사서함/다량배달처 갱신, 캐시 메트릭, 외부 API 키 관리, 로그 뷰어

두 영역 모두 같은 백엔드 REST API를 호출한다. 지오코딩/역지오코딩 디버그 화면은 `/v2/geocode`, `/v2/reverse`를 쓰고, 운영·정규화·EXPLAIN 화면은 `/v1/admin/*`를 쓴다. 빌드 시 백엔드 `openapi.json`에서 TypeScript 타입과 schema 이름 목록을 생성한다. 폼 입력 Zod 스키마는 `lib/schemas.ts`에 수동 mirror로 둔다. 이 구조는 OpenAPI drift와 폼 입력 drift를 각각 분리해서 리뷰할 수 있게 한다.

### A1.2 핵심 결정 (요약)

| 영역 | 선택 |
|------|------|
| 프레임워크 | Next.js 16 (App Router) + TypeScript strict |
| UI | Tailwind 기반 자체 primitives + shadcn/ui source components |
| 폼 | React Hook Form + Zod helper |
| 지도 | MapLibre GL JS + VWorld WMTS + GitHub `maplibre-vworld-react` |
| 테이블 | TanStack React Table v8 + TanStack React Virtual |
| 상태 | Zustand는 디버그 UI의 초안/결과처럼 브라우저 화면 상태가 재사용될 때 사용 |
| 데이터 패칭 | TanStack Query v5 |
| 타입 동기 | openapi-typescript + 수동 Zod mirror |
| 코드 표시 | 자체 `JsonBlock` 컴포넌트 |
| 테스트 | Vitest + @testing-library/react, Playwright e2e |

### A1.3 보안 모델 (내부 전용)

ADR-013에 명시 — 사내망/VPN 뒤에서만 접근. 별도 애플리케이션 인증 없음. 보안은 네트워크 레벨(nginx IP allowlist, 사내 SSO 게이트웨이)에서.

- 브라우저 → Next.js: 동일 origin. CORS 부재.
- Next.js → 백엔드: Route Handler가 서버 사이드에서 호출. CORS도 인증 헤더도 불필요.
- `/admin/*` 페이지: 일반 라우트와 동일. 별도 가드 없음.

외부 노출이 불가피해지면 (1) nginx/traefik basic auth, (2) 사내 SSO 게이트웨이, (3) 최후 수단으로 NextAuth — 그 결정은 새 ADR로 기록.

## A2. 프로젝트 구조

```
kor-travel-geo-ui/
├── package.json, package-lock.json, tsconfig.json, next.config.mjs
├── tailwind.config.ts, postcss.config.mjs, eslint.config.mjs
├── .env.local.example
├── README.md, SKILL.md, CHANGELOG.md
├── docs/                          # ARCHITECTURE, DECISIONS, COMPONENTS, PAGES, TASKS, RESUME, JOURNAL
├── scripts/
│   ├── gen-types.mjs              # openapi.json → TypeScript types + schema name list
│   └── check-sync.sh
├── app/
│   ├── layout.tsx, page.tsx, globals.css, providers.tsx
│   ├── debug/                     # geocode/reverse/normalize/explain
│   ├── admin/                     # tables/load/cache/logs/consistency/backups/performance/ops
│   └── api/
│       └── proxy/[...path]/route.ts
├── components/
│   ├── layout/                    # AppShell
│   ├── ui/                        # Panel, PageHeader, JsonBlock, StatusBadge
│   ├── vworld/                    # CoordinateMap (MapLibre + VWorld WMTS + key-missing preview)
│   ├── debug/                     # Geocode/Reverse/Normalize/Explain debugger
│   └── admin/                     # Load/Table/Cache/Logs/Consistency panel
├── lib/
│   ├── api.ts                     # fetch 기반 REST helper
│   ├── schemas.ts                 # zod schemas (mirror of pydantic v2)
│   ├── schemas.gen.ts             # auto-generated schema name list, do not edit
│   ├── consistency.ts, format.ts, load-workflow.ts, proxy.ts, sido.ts
├── types/                         # api.gen.ts (openapi-typescript), domain.ts
└── tests/                         # unit (vitest), e2e (playwright)
```

### 환경변수 (`.env.local.example`)

```
KTG_API_INTERNAL_URL=http://localhost:12501           # 서버 사이드 전용
NEXT_PUBLIC_API_BASE_URL=/api/proxy                      # 브라우저 노출
NEXT_PUBLIC_VWORLD_API_KEY=your_vworld_api_key           # 선택 fallback. 기본은 Python API .env의 KTG_VWORLD_API_KEY
```

`KTG_API_INTERNAL_URL`은 `NEXT_PUBLIC_` 접두사가 없어 서버 사이드에서만 접근 가능. 인증/시크릿은 두지 않는다(ADR-013).

VWorld 키는 빌드 타임 상수로 직접 박지 않고 `/api/runtime-config`에서 런타임에 읽는다. 우선순위는 Python API의 `KTG_VWORLD_API_KEY` 환경변수, 저장소 루트 `.env`의 `KTG_VWORLD_API_KEY`, 마지막으로 UI 전용 `NEXT_PUBLIC_VWORLD_API_KEY`다. 저장소에는 실제 값을 커밋하지 않고, VWorld 콘솔에서 로컬/스테이징/운영 도메인을 각각 제한한다. `/admin/settings`는 `.env` 기본값을 보여 주고, 사용자가 저장한 값은 브라우저 localStorage override로 적용한다. 기본값 버튼은 override를 지우고 `.env` 값으로 되돌린다.

## A3. 공통 기반

### A3.1 백엔드 OpenAPI → TypeScript 타입 자동 생성

`scripts/gen-types.mjs`가 백엔드 `openapi.json`을 받아 `types/api.gen.ts`(openapi-typescript)와 `lib/schemas.gen.ts`(schema 이름 목록)를 생성한다. `npx`가 Windows/WSL 경계에서 spawn 문제를 일으킬 수 있으므로, 스크립트는 `process.execPath`로 local `node_modules/openapi-typescript/bin/cli.js`를 직접 실행한다.

CI에서 backend의 `python scripts/export_openapi.py` → frontend의 `npm run gen:types` → `git diff --exit-code types/api.gen.ts lib/schemas.gen.ts`로 drift 검출.

### A3.2 `lib/schemas.ts` (Zod — pydantic v2와 미러)

핵심 enum/모델은 백엔드 DTO와 1:1. 예시:

```ts
export const ZipSourceSchema = z.enum([
  "building_bsi_zon_no","bulk_delivery","kodis_bas_within","kodis_bas_centroid","pobox",
]);
export const GeocodeInputSchema = z.object({
  address:  z.string().min(1).max(200),
  type:     AddressTypeSchema.default("road"),
  crs:      z.string().default("EPSG:4326"),
  refine:   z.boolean().default(true),
  simple:   z.boolean().default(false),
  fallback: z.enum(["off","local_only","api"]).default("local_only"),
});
```

### A3.3 `lib/api.ts` — REST helper

```ts
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/proxy";
export function backendPath(path: string): string {
  const trimmed = path.startsWith("/") ? path : `/${path}`;
  return trimmed.startsWith("/v1") || trimmed.startsWith("/v2") ? trimmed : `/v1${trimmed}`;
}
export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> { ... }
export async function postJson<T>(path: string, body: unknown): Promise<T> { ... }
```

### A3.4 Next.js Route Handler 프록시

`app/api/proxy/[...path]/route.ts`가 백엔드로 전달한다. JSON 요청과 raw ZIP 업로드 요청을 같은 프록시로 처리하되, GET/HEAD가 아닌 요청 본문은 `request.body`(`ReadableStream`)를 그대로 `fetch`에 넘긴다. 대용량 ZIP을 Next.js Route Handler 메모리에 `arrayBuffer()`로 통째 적재하지 않기 위한 정책이며, Node.js fetch 스트림 전달 요건에 맞춰 `duplex: "half"`를 명시한다. Next.js 16에서는 Route Handler context의 `params`가 Promise이므로 `const params = await context.params` 형태를 사용한다.

프록시는 `/v1/`과 `/v2/` 하위 경로만 허용한다. `new URL()` 정규화 이후 `target.pathname`을 검사하므로 `/v1/../metrics` 같은 우회도 차단된다. 전달 헤더는 `accept`, `content-type`, `user-agent` allowlist만 사용하고 `authorization`/`cookie`/`x-forwarded-*` 등은 내부 백엔드로 넘기지 않는다.

### A3.5 `lib/queryClient.ts`

```ts
new QueryClient({
  defaultOptions: { queries: {
    staleTime: 60_000, refetchOnWindowFocus: false,
    retry: (n, err) => (err?.status >= 400 && err?.status < 500) ? false : n < 2,
  }}
});
```

### A3.6 `components/vworld/CoordinateMap.tsx`

GitHub `digitie/maplibre-vworld-react`의 web package가 제공하는 `VWorldMapView`/`Marker`/hook을 감싸 VWorld WMTS raster style을 렌더링한다. `kor-travel-geo-ui/lib/vworld.ts`는 `maplibre-vworld-react/packages/vworld-map-web/src/*`의 `getVWorldTileUrl()`, `getVWorldStyle()`, `getVWorldMaxZoom()`, `isVWorldTileError()`, `redactVWorldUrl()`, `VWorldMapView`, `Marker`, map hook, `VWorldLayerType`를 재수출하는 얇은 경계다.

`CoordinateMap.tsx`는 MapLibre lifecycle을 직접 소유하지 않고 upstream React `VWorldMapView`에 위임한다. 이 저장소에서는 click callback의 `{ x, y }` 변환, key 미설정 안내, tile error overlay 임계치, API 응답 geometry overlay만 domain wrapper로 담당한다. MapLibre를 대체하는 별도 지도 fallback 구현은 두지 않는다. 상위 화면은 `components/vworld/LazyCoordinateMap.tsx`를 import한다. 이 wrapper는 `next/dynamic(..., { ssr: false })`로 MapLibre 번들을 클라이언트 런타임에만 불러오며, 로딩 중에는 같은 높이의 skeleton을 보여 준다.

현재 UI dependency는 npm registry가 아니라 GitHub tarball로 고정한다. SHA는 `a7cb0f8f41ec00b44b1d106664506730b87033bd`이고, 의존성 spec은 `https://github.com/digitie/maplibre-vworld-react/archive/a7cb0f8f41ec00b44b1d106664506730b87033bd.tar.gz`다. SSH key 없이 `npm ci`가 재현되어야 하므로 `git@github.com:` 또는 `github:` shorthand를 쓰지 않는다. `maplibre-vworld-react` root tarball은 monorepo source를 포함하고, `vworld-map-web`은 bare import `vworld-map-core`를 사용하므로 `tsconfig.json`, `vitest.config.ts`, `next.config.mjs`에서 `vworld-map-core`와 `vworld-map-web` alias를 둔다. Next.js 16 build path는 Turbopack을 타므로 `turbopack.resolveAlias`도 webpack alias와 함께 유지한다.

지도 키는 `/api/runtime-config`가 반환한 VWorld 키를 사용한다. 기본값은 Python API `.env`의 `KTG_VWORLD_API_KEY`이며, UI 전용 `NEXT_PUBLIC_VWORLD_API_KEY`는 Python 키가 없을 때만 fallback이다. 키가 없으면 지도 대신 같은 크기의 좌표 프리뷰 UI를 보여 주지만, MapLibre/VWorld 타일 렌더링을 대체하는 별도 fallback 지도는 만들지 않는다. MapLibre/VWorld tile error는 upstream `isVWorldTileError()`와 `redactVWorldUrl()`로 일시적 네트워크 실패와 치명 오류를 구분한다. tile fetch 실패는 redacted URL로 `console.warn`만 남기고, 누적 임계치 이상이거나 style/WebGL 계열 오류일 때만 overlay를 보여 준다.

VWorld raster layer는 레이어별 zoom 한계를 둔다. `Base`/`gray`/`midnight`는 z19까지, `Hybrid`/`Satellite`는 z18까지만 요청한다. `maplibre-vworld-react` core의 style source id는 `Base`/`gray`/`midnight`에서 `vworld-base`이고, `Hybrid`는 `vworld-satellite`와 `vworld-base`를 함께 쓴다. tile error source 판별은 `vworld` prefix 기준으로 한다. marker와 카메라는 upstream `Marker`, `bbox`, `cameraTarget`, `cameraTransition="instant"` 조합으로 갱신한다.

T-067부터 `CoordinateMap`은 v2 geocode 후보의 `geometry`도 overlay로 표시한다. `point` marker는 항상 유지하고, polygon은 fill+outline, road line은 line layer, point geometry는 circle layer로 추가한다. 지도 viewport는 후보 `bbox`만 보지 않고 `point`도 함께 포함한다. 주소 대표점이나 출입구점이 건물 polygon 바깥 도로 쪽에 있을 수 있기 때문이다.

### A3.6.1 `digitie/maplibre-vworld-react` GitHub 패키지 소비와 책임 경계

디버그 UI에서 VWorld/MapLibre 연동 문제가 발생하면 먼저 문제가 범용 지도 기능인지, 이 프로젝트의 주소 디버그/관리 UX인지 분류한다. 원인이 `digitie/maplibre-vworld-react`의 패키징, TypeScript 타입, CSS side-effect import, marker component, VWorld layer helper, Next.js/Vitest 호환성처럼 다른 소비자도 재사용할 수 있는 범용 기능에 있으면 해당 저장소도 적극 수정 대상에 포함한다. 반대로 geocode/reverse 입력 연결, API 응답 좌표 표시, 정합성/성능/적재 overlay, 이 프로젝트 안내 문구와 layout은 `kor-travel-geo-ui`의 domain wrapper에서 구현한다.

디버그 화면은 범용 지도 표시 외에 다음 동작을 보장해야 한다.

- 지도 클릭 시 `(lon, lat)` 순서의 `{ x, y }` 값을 reverse/geocode 디버그 입력으로 전달한다.
- VWorld 키가 없으면 WebGL 지도를 만들지 않고 같은 크기의 좌표 preview UI를 렌더링한다. MapLibre를 대체하는 별도 fallback 지도는 두지 않는다.
- VWorld tile 404/408/429/5xx와 네트워크 실패는 upstream helper로 분류한 뒤 즉시 치명 오류로 고정하지 않고 redacted warning과 누적 임계치로 처리한다.
- marker 갱신 시 애니메이션 되튐을 피하고, SSR 단계에서는 `next/dynamic(..., { ssr: false })`와 skeleton만 노출한다.

리뷰 기준:

- **패키징 문제**: GitHub tarball 또는 향후 npm install 후 source subpath, alias, type declaration, CSS import 때문에 소비자 build가 실패하면 `maplibre-vworld-react`의 배포 산출물 또는 package export 구성을 고친다.
- **타입 문제**: React 18/19, MapLibre GL JS, Vite/Next.js에서 타입 오류가 나면 upstream 타입 선언과 테스트를 보강한다.
- **기능 문제**: VWorld `Base`/`gray`/`midnight`/`Hybrid`/`Satellite` layer, marker, click, attribution 중 공통 컴포넌트화할 수 있는 문제는 upstream에 반영한다.
- **프로젝트 특화 기능**: geocode/reverse form 상태, API 응답 overlay, 정합성/성능/적재 결과 표시, 이 프로젝트 안내 문구와 임계치는 `kor-travel-geo-ui`가 책임진다.
- **의존성 선언 상태**: `maplibre-vworld-react`는 GitHub tarball SHA `a7cb0f8f41ec00b44b1d106664506730b87033bd`로 선언되어 있다. npm registry release가 나오면 lockfile drift와 소비자 build를 확인한 뒤 전환한다.
- **보안·운영 조건**: 브라우저 노출 키는 VWorld 콘솔에서 origin/referrer 제한이 실제 WMTS에도 적용되는지 운영자가 확인한다. 향후 CSP를 켜면 `connect-src`와 `img-src`에 `https://api.vworld.kr`를 포함한다.

### A3.7 Playwright e2e

Playwright e2e는 `tests/e2e/`에 둔다. 현재 `debug-v2.spec.ts`는 브라우저 네트워크를 가로채 `/api/proxy/v2/geocode`, `/api/proxy/v2/reverse`, `/api/proxy/v2/regions/within-radius` 요청을 확인한다. 이 방식은 실제 DB 결과에 의존하지 않고, UI가 v2 REST body를 잘못 만들거나 v1 endpoint로 되돌아가면 즉시 실패한다. `vworld-map.spec.ts`는 runtime config를 mock하지 않고 Python API `.env`에서 확보한 VWorld 키로 MapLibre canvas와 VWorld WMTS 타일 응답을 확인한다.

프론트엔드 실행과 build/test는 WSL ext4 미러에서 Linux Node/npm으로 수행한다. Windows `npm`을 WSL 경로에서 실행하지 않는다. e2e 검증을 위한 Playwright 실행과 브라우저만 Windows에서 수행한다. WSL에서 UI 서버를 띄워 Windows Playwright를 붙일 때는 `next dev --hostname 0.0.0.0 --port 12505` 또는 production build 후 `next start --hostname 0.0.0.0 --port 12505`로 바인딩하고, Windows에서는 WSL IP를 `PLAYWRIGHT_BASE_URL`로 지정한다. PR 완료 전 e2e는 Chrome 기준 `chromium` project와 Firefox 기준 `firefox` project를 모두 실행한다. 실제 지도 로딩 e2e는 HMR origin 차단을 피하고 사용자 실행에 가깝게 production `next start` 서버에서 실행한다.

### A3.7.1 React Doctor

모든 프론트엔드 작업 뒤에는 `kor-travel-geo-ui`에서 React Doctor를 실행한다. 경고가 나오면 해당 React/Next.js 코드를 수정하고 같은 명령을 다시 실행해 새 경고가 남지 않았음을 확인한다.

```bash
npx react-doctor@latest . --offline --verbose --json
```

### A3.8 Provider 체인 (`app/providers.tsx`)

`QueryClientProvider` → children. ThemeProvider, Toaster, ReactQueryDevtools는 실제 사용 요구가 생기면 추가한다.

## A4. 공통 컴포넌트

- **CoordinateMap**: MapLibre GL JS와 VWorld WMTS raster style을 사용한다. VWorld 키가 없으면 지도 대신 좌표 프리뷰 UI를 보여 주고, MapLibre를 대체하는 별도 fallback 지도는 두지 않는다. 좌표 입력과 click callback은 모두 `(lon, lat)` 순서다. v2 후보의 `point` marker와 선택 `geometry` overlay를 함께 표시한다.
- **GeocodeDebugger**: `address`, `type`, `fallback`, `include_geometry`를 받아 `/v2/geocode`를 호출하고 JSON 응답과 지도/좌표·도형 프리뷰를 함께 표시한다.
- **RegionsWithinRadiusDebugger**: POI `(lon, lat)`와 `radius_km`, `levels`를 React Hook Form/Zod로 검증하고 `/v2/regions/within-radius`를 호출한다. 초안과 마지막 결과는 Zustand store에 저장하고, 요청은 TanStack Query mutation으로 실행한다. shadcn/ui `Card`, `Field`, `Input`, `Checkbox`, `Button`으로 구성한다.
- **VirtualTable**: 관리 UI 표면 공용 컴포넌트다. `@tanstack/react-table`로 컬럼 정의, 전역 필터, 정렬을 처리하고, 기본 `grid` 모드는 `@tanstack/react-virtual`로 row windowing을 적용한다. `as="table"` 모드는 작은 목록과 접근성 민감 화면에서 실제 `<table>` 구조를 렌더링한다.
- **TableStatsPanel**: `GET /v1/admin/tables` 결과를 `VirtualTable`로 보여준다.
- **JsonBlock**: JSON 응답과 EXPLAIN plan을 monospace pre 영역으로 표시. 별도 코드 표시 라이브러리는 production dependency로 두지 않는다.
- **ZipSourceBadge**: `ZipSource` enum별 색상/라벨 메타데이터로 시각화.

## A5. 디버깅 UI 페이지

| 경로 | 목적 | 주요 컴포넌트 |
|------|------|---------------|
| `/debug/geocode` | 주소 → 좌표 검증, VWorld 지도 마커 | GeocodeForm, CoordinateMap, JsonViewer, ZipSourceBadge |
| `/debug/reverse` | 지도 클릭 → 역지오코딩 | CoordinateMap(onClick), 결과 리스트 |
| `/debug/search` | 통합 검색 (address/place/district/road) | SearchForm, DataTable, CoordinateMap |
| `/debug/normalize` | 주소 정규화 디버거 (parts 시각화) | NormalizeForm, NormalizeViewer |
| `/debug/zipcode` | 우편번호 lookup 우선순위 시각화 | ZipcodeForm, ZipSourceBadge |
| `/debug/explain` | 임의 SELECT의 EXPLAIN plan | ExplainViewer (SELECT/WITH만 허용) |

**EXPLAIN 일관성**: 백엔드 `/v1/admin/explain`은 `AsyncAddressClient.engine`을 그대로 사용해 `EXPLAIN(FORMAT JSON [, ANALYZE, BUFFERS])`를 실행. 디버거 결과가 운영 쿼리와 같은 환경(search_path, statement_timeout, pool)에서 평가됨.

## A6. DB 관리 UI 페이지

| 경로 | 기능 | 주요 API |
|------|------|----------|
| `/admin/tables` | 테이블 통계 (행/디스크/인덱스/마지막 VACUUM) | `GET /v1/admin/tables` |
| `/admin/load` | 다중 파일 업로드, local/RustFS 저장소 선택, RustFS prefix import/local sync, source set 기준월 확인, 적재 작업 제출과 진행상황 모니터링 | `POST/PUT /v1/admin/uploads*`, `POST /v1/admin/storage/rustfs/*`, `POST /v1/admin/load-sources/*`, `POST /v1/admin/loads`, `POST /v1/admin/maintenance/refresh-mv`, `GET /v1/admin/loads` |
| `/admin/cache` | 캐시 hit rate 시계열, 비우기 | `GET /v1/admin/cache/metrics` |
| `/admin/logs` | `load_jobs.log_tail` 최근 라인 조회 | `GET /v1/admin/logs` |
| `/admin/consistency` | C1~C10 정합성 리포트 조회·재검증 | `GET/POST /v1/admin/consistency*` |
| `/admin/backups` | DB 백업/복원 작업, 진행률, callback 상태, artifact 다운로드 | `POST/GET /v1/admin/backups`, `POST /v1/admin/restores`, `GET /v1/admin/jobs/{id}/events` |
| `/admin/performance` | 전국 DB query benchmark 결과, p95/p99 threshold, slow plan 조회 | `POST/GET /v1/admin/performance/benchmarks*` |
| `/admin/settings` | VWorld 인증키 확인·브라우저 override 저장·기본값 복원, RustFS 업로드 저장소 설정·연결 확인 | `GET /api/runtime-config`, `GET/PATCH /v1/admin/storage/rustfs/config`, `POST /v1/admin/storage/rustfs/check` |

`/admin/postal`과 WebSocket log stream은 문서상 장기 후보였지만 PR #12 구현 범위에는 넣지 않았다. 후속 PR에서 별도 백엔드 표면을 먼저 확정한 뒤 추가한다.

### `/admin/load` 상태 머신

```
idle → uploading → source_review → plan_ready → processing → finished
                    └─ mixed yyyymm modal ─┘
     → cancelled / failed → (reset) idle
```

원칙: "파일 업로드와 입력 처리는 각각 다 끝나면 다음 단계로". 파일이 서버에 모두 저장되고 source set 분석이 끝나기 전에는 적재 시작 버튼을 활성화하지 않는다. 업로드 중에는 처리 시작 버튼을 비활성화하고, 처리 중에는 새 파일 추가 영역을 닫는다.

- 파일 선택: `<input type="file" multiple>`과 drag and drop을 모두 지원한다. 디렉터리 drag가 가능한 브라우저에서는 `webkitRelativePath` 또는 동등한 relative path를 보존해 ZIP 묶음과 SHP sidecar 파일을 같은 upload set으로 보낸다.
- 업로드: T-045 구현은 upload set API를 사용한다. T-076부터 `POST /v1/admin/uploads`는 `storage_kind="local" | "rustfs"`를 받을 수 있다. 각 파일은 `PUT /v1/admin/uploads/{upload_set_id}/files`에 raw stream으로 보낸다. 대용량 ZIP 업로드 진행률을 안정적으로 표시하기 위해 `XMLHttpRequest.upload.onprogress` 또는 동등한 업로드 progress wrapper를 사용한다. Next.js Route Handler는 파일 본문을 `arrayBuffer()`로 전체 버퍼링하지 않고 백엔드로 스트리밍한다.
- RustFS 원천 재사용: RustFS가 활성화된 경우 `/admin/load`는 기존 object prefix를 upload set으로 가져오는 `import-prefix`와, allowlist 하위 로컬 파일/디렉터리를 RustFS로 올리는 `sync-local` 입력을 제공한다. import된 upload set은 백엔드가 `materialized` cache로 내려받은 뒤 기존 source set discovery/plan 경로를 그대로 사용한다.
- 업로드 진행률: 파일별 `uploaded_bytes / total_bytes`와 전체 `sum(uploaded_bytes) / sum(total_bytes)`를 표시한다. 사용자가 전체 취소를 누르면 진행 중 요청을 abort한 뒤 서버 upload set cancel을 호출한다. 파일별 재시도 버튼은 후속 개선으로 남긴다.
- source review: 모든 파일 저장이 완료되면 `POST /v1/admin/load-sources/discover`를 호출해 원천 후보, 기준월, 필수 원천 누락, 추천 source set을 표로 보여 준다.
- 기준월 mismatch 팝업: `mixed_yyyymm=true`이면 적재 시작 전에 modal을 띄운다. modal은 `juso`, `parcel_link`, `locsum`, `navi`, `shp`, `roadaddr_entrance`, `sppn_makarea`의 기준월과 경로를 보여 주고, C10 정합성 리포트에 혼합 기준월이 남는다는 점을 설명한다. 사용자가 계속 진행을 선택하면 서버가 요구하는 confirmation token 또는 문구를 `POST /v1/admin/load-sources/plan`에 함께 보낸다.
- 처리: `SourceSetPlan.batch_payload`가 확정된 뒤에만 `POST /v1/admin/loads kind=full_load_batch`를 호출한다. 큐가 직렬로 한 job씩 실행하며, UI는 root job과 child job을 폴링해 적재 진행률을 표시한다.
- 적재 진행률: 업로드 진행률과 분리한다. root `full_load_batch`의 `progress`, child job의 `current_stage`, `log_tail`을 함께 보여 주며, child별 가중 평균이 제공되면 전체 적재 퍼센트로 표시한다.
- 전체 취소: 업로드 단계에서는 upload set cancel + 브라우저 요청 abort를 수행한다. 적재 단계에서는 root job에 cancel 요청을 보내고, 서버는 실행 중 child의 협조적 cancel event와 대기 중 child의 `cancelled` 상태 전이를 담당한다. GDAL callback이 0 반환 → 즉시 중단.

현재 구현은 `LoadConsole.tsx` 단일 컴포넌트와 `lib/load-workflow.ts` reducer/helper로 구성된다. 테스트는 상태 전이, 혼합 기준월 확인 문구, 진행률 계산을 우선 고정했고, 다중 파일/DND/modal/취소 흐름의 렌더링 테스트와 새로고침 후 진행률 복구는 후속 보강 후보로 남긴다.

### `/admin/backups` 상태 머신 (ADR-030, T-046)

```
idle → configuring_backup → backup_preflight → backup_running
     → backup_done → artifact_ready → (reset) idle

idle → selecting_artifact → restore_preflight → restore_running
     → restore_done → validation_summary → (reset) idle
```

원칙: 백업/복원은 브라우저 요청 안에서 끝내지 않는다. UI는 작업 등록만 수행하고, 이후 `LoadJobStatus(kind="db_backup" | "db_restore")`와 `BackupArtifact` metadata를 통해 상태를 추적한다. T-046 1차 UI는 `/admin/backups`에 백업 생성, 복원 등록, job 목록, cancel, artifact 다운로드/삭제를 구현했다.

- 백업 생성 탭: 저장 위치 allowlist, 상대 경로, profile(`serving-ready`, `lean-serving`, `forensic`), jobs, compression level, callback URL을 입력한다. 저장 위치는 사용자의 로컬 다운로드 경로가 아니라 백엔드 서버가 접근 가능한 경로임을 UI 라벨에 명확히 표시한다.
- 진행 중 영역: `db_backup`, `db_restore` job을 함께 보여 준다. 백엔드는 `GET /v1/admin/jobs/{job_id}/events` Server-Sent Events를 제공하지만, T-046 1차 UI는 안정성을 우선해 TanStack Query polling으로 상태를 갱신한다. SSE 연결과 polling fallback 전환 UI는 후속 고도화 후보로 남긴다.
- 진행률: 백업은 `preflight → dump → dump checksum → archive → checksum → finalize`, 복원은 `preflight → extract → restore → analyze → validate → finalize` phase를 표시한다. `pg_dump`/`pg_restore` progress는 추정값이므로 stage label, elapsed time, 처리 object/file, dump 디렉터리 크기, archive 입력/출력 byte, checksum byte를 함께 보여 준다.
- 취소: 작업이 `queued` 또는 `running`일 때만 취소 버튼을 노출한다. 취소 후에는 서버가 partial dump dir, `.part` archive, 새 target DB를 어떻게 정리했는지 `log_tail`과 summary로 보여 준다.
- 백업 목록 탭: artifact id, 파일명, 크기, SHA256 앞 12자리, 생성일, profile, source set, callback 상태, 만료 예정일을 table로 표시한다. `done` artifact만 다운로드 버튼을 노출한다.
- 다운로드: 다운로드 링크는 브라우저 로컬 저장을 위한 보조 경로다. 백업 파일은 이미 서버 지정 경로에 저장되어 있으므로, UI는 서버 경로와 다운로드 링크를 구분해서 표시한다.
- 복원 탭: artifact 선택 또는 서버 경로 입력, target DB 이름, jobs, smoke test 여부, consistency 여부를 입력한다. 현재 연결 DB 이름과 같은 target은 클라이언트에서도 막고, 서버 preflight 실패 메시지도 그대로 보여 준다.
- 복원 안전장치: 기본 모드는 `new_database`만 노출한다. `replace_current`는 별도 위험 모달, typed confirmation, 선행 백업 확인, maintenance mode 표시 없이는 실행하지 않는다. T-050 6차 이후 백엔드도 `RESTORE <현재 DB 이름>` 확인 문구와 active `restore` maintenance window가 없으면 이 모드를 거절한다. T-058 1차에서는 실제 hot-swap 실행 버튼을 바로 노출하지 않고, `/v1/admin/restores/hot-swap-plan`의 `typed_confirmation`, `rollback_confirmation`, `blockers`, `sql`을 먼저 보여 주는 검토 UI를 후속 후보로 둔다.
- callback 상태: terminal callback이 성공하면 `callback_state=delivered`, 재시도 소진 뒤 실패하면 `failed`, 아직 callback을 보내기 전이면 `pending`으로 표시한다. callback 실패는 백업 파일 성공 여부와 분리해서 보여 주고, 상세 drawer에서는 `manifest.callback_delivery.attempts`와 `callback_ids`를 확인할 수 있게 한다.

T-046에서 reducer/helper unit test와 Windows Playwright 렌더 검증을 수행했다. Windows Playwright는 API route를 mock해 `/admin/backups`에서 `Backup 시작`, `Restore 시작`, artifact download link 표시를 확인했다. 후속 UI 테스트는 SSE → polling fallback, callback 상태 badge, corrupted artifact preflight 오류 표시를 추가한다. 통합 검증은 대구광역시 부분 적재 DB를 대상으로 수행했고 전국 full-load는 실행하지 않았다.

### `/admin/performance` 후보 화면 (ADR-031, T-047)

T-047 1차 구현은 CLI와 artifact 중심으로도 충분하지만, 반복 튜닝이 길어지면 관리 UI에서 benchmark 결과를 바로 비교할 수 있어야 한다.

화면 구성:

- run 목록: run id, git commit, DB size, source set, corpus, iterations, concurrency, 시작/종료 시각.
- summary table: query군별 p50/p90/p95/p99, timeout, error, threshold 초과 여부.
- 전후 비교: baseline과 selected trial의 개선율, buffer read/temp write 변화, plan hash 변화.
- slow sample: case id, 입력값, 응답 상태, latency, rows, plan JSON 링크.
- plan viewer: `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, SETTINGS)` JSON을 tree/table로 표시한다.
- tuning note: 적용한 index/view/MV 후보, build time, size, refresh 영향.

UI 원칙:

- chart보다 table 우선. 운영자는 p95/p99, threshold 초과, slow sample을 빠르게 스캔해야 한다.
- threshold 초과는 색상 badge와 정렬로 드러내되, 과한 장식은 피한다.
- plan JSON은 크므로 기본 collapsed 상태로 열고, 필요한 node만 펼친다.
- 프론트엔드는 DB에 직접 연결하지 않는다. benchmark artifact metadata와 plan JSON은 백엔드 REST로만 가져온다.

테스트는 threshold badge, baseline/trial 비교 정렬, slow sample 클릭, 큰 plan JSON rendering, API 실패 상태를 포함한다.

### `/admin/ops` 화면 (ADR-033, T-049)

T-049 구현으로 관리 UI에 `/admin/ops` 화면을 추가했다. `/admin/load`, `/admin/backups`, `/admin/performance`가 각각 작업 실행 화면이라면 `/admin/ops`는 감사·스냅샷·릴리스·artifact를 묶어 보는 관제 화면이다. 첫 구현은 조회와 운영 메타데이터 capture/maintenance window 등록에 집중한다. backup/restore artifact의 세부 다운로드·삭제 action은 T-046 `/admin/backups`에서 제공하고, performance artifact 비교 UI는 T-047에서 확장한다.

화면 구성:

- dataset snapshot 목록: snapshot id, state, row count key 수를 표시한다. source set 상세 drilldown은 T-045에서 보강한다.
- serving release 목록: release id, active/superseded/pending 상태, release kind, serving MV 이름을 표시한다. T-050 4차 이후 full-load/MV refresh 성공은 active release로 자동 기록되고, restore 성공은 hot-swap 전 단계의 pending restore 후보로 자동 기록된다. active row는 DB partial unique index로 한 건만 허용된다.
- artifact 목록: `db_backup`, `db_restore_log`, `consistency_report`, `perf_report`, `source_inventory`, `schema_diff`를 같은 table에서 표시한다. `/admin/ops`는 전체 관제 목록을 유지하고, `db_backup` 다운로드/삭제 action은 `/admin/backups`의 작업 화면에서 수행한다.
- audit event 목록: action, outcome, 생성 시각을 표시한다. API key, DSN password, token, callback secret, 주소 원문은 backend redaction을 거친 payload만 받는다.
- maintenance window: `full_load`, `restore`, `schema_migration`, `mv_refresh`, `read_only`, `exclusive` window를 typed confirmation과 함께 생성한다. confirmation 원문은 DB에 저장하지 않고 hash만 저장한다.
- table stats snapshot: `POST /v1/admin/ops/table-stats/capture`로 table/MV/index size와 추정 row count snapshot을 수동 수집하고 최근 결과를 표시한다. 백엔드에서 `KTG_OPS_TABLE_STATS_CAPTURE_INTERVAL_MINUTES`를 켜면 같은 목록에 주기 capture 결과가 쌓이며, `snapshot_id` 미지정 결과는 현재 active serving release snapshot에 연결된다.

테스트는 현재 backend redaction/route contract와 frontend lint/type/build로 시작한다. 후속 UI 고도화 시 secret redaction 표시, active release 한 건 강조, artifact type filter, audit event pagination, maintenance window 만료 상태를 추가한다.

## A7. 관찰가능성

`kor-travel-geo-ui`는 Next.js 서버 프로세스에서 `/api/metrics`를 노출한다. Prometheus는 앱이 능동 연결하지 않는 pull 방식으로 이 endpoint를 scrape한다.

- route handler request total/duration: `/api/runtime-config`, `/api/proxy/[...path]`, `/api/metrics`, `/api/metrics/web-vitals`
- backend proxy upstream duration: `/v1/*`, `/v2/*` 백엔드 fetch를 method, backend route, status code 기준으로 집계
- Web Vitals: 브라우저에서 `useReportWebVitals`로 수집한 metric name, route, rating, value를 `/api/metrics/web-vitals`로 전송

동적 id나 긴 token은 metric label cardinality를 낮추기 위해 `:id`로 정규화한다. query string, 주소 원문, API key는 metric label에 넣지 않는다.

## A8. DB 일관성 — 단일 엔진

프론트엔드는 자체 DB connection을 갖지 않는다. `/debug/*`(지오코딩/역지오코딩/정규화/EXPLAIN)와 `/admin/*`(테이블 통계/적재/MV refresh) 모두 백엔드 REST API를 호출하고, 백엔드는 `AsyncAddressClient.engine` 한 개의 SQLAlchemy 2 async engine으로 응답한다.

- **일관성**: 디버거 EXPLAIN과 운영 쿼리가 같은 search_path, 같은 statement_timeout, 같은 pool 옵션에서 평가됨.
- **관찰가능성**: structlog/Prometheus 카운터가 라이브러리·REST·디버거 호출을 한 곳에 집계.
- **권한·자원 통제**: DB pool 크기 단일 관리.

`kor-travel-geo-ui`의 `package.json`에 `pg`/`prisma` 같은 DB 의존성이 들어오는 순간 ADR 위반이며 PR을 거절한다.

## A9. 외부 노출 정책 변경 시

내부망 가정이 깨질 때는 다음 순서를 따른다 — 코드 변경 없이 운영 변경으로 처리:

1. nginx/traefik 앞단에 basic auth 또는 OAuth proxy 배치
2. 사내 SSO 게이트웨이(Cloudflare Access, Tailscale, OpenVPN 등) 뒤로 이동
3. 마지막 수단으로 NextAuth 도입 — 그때도 `docs/decisions.md`에 새 ADR.
