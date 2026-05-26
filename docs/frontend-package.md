# 프론트엔드 패키지 사양서 — `kraddr-geo-ui`

본 문서는 첨부 사양서(2026-05-22 작성) Part A를 master 문서 체계로 옮긴 정리본이다. 디버깅 UI + DB 관리 UI를 한 Node.js 패키지로 통합 운영한다.

## A1. 개요

### A1.1 두 영역, 한 패키지

`kraddr-geo-ui`는 `python-kraddr-geo`(Python 패키지 `kraddr.geo`) 백엔드와 별도의 Node.js 패키지다. 사용자 대상 UI가 아니라 개발자·운영자가 라이브러리를 검증·관리하기 위한 내부 도구다.

- **디버깅 UI**: 지오코딩·역지오코딩·통합검색·정규화·SQL EXPLAIN을 지도와 함께 시각 검증
- **DB 관리 UI**: 테이블 통계, 적재 작업 큐, MV refresh, 사서함/다량배달처 갱신, 캐시 메트릭, 외부 API 키 관리, 로그 뷰어

두 영역 모두 같은 백엔드 REST API(`/v1/*` 및 `/v1/admin/*`)를 호출한다. 빌드 시 백엔드 `openapi.json`에서 TypeScript 타입과 schema 이름 목록을 생성한다. 폼 입력 Zod 스키마는 `lib/schemas.ts`에 수동 mirror로 둔다. 이 구조는 OpenAPI drift와 폼 입력 drift를 각각 분리해서 리뷰할 수 있게 한다.

### A1.2 핵심 결정 (요약)

| 영역 | 선택 |
|------|------|
| 프레임워크 | Next.js 16 (App Router) + TypeScript strict |
| UI | Tailwind 기반 자체 primitives (`Panel`, `PageHeader`, `JsonBlock`, `StatusBadge`), shadcn/ui 도입은 후속 |
| 폼 | controlled form + Zod helper |
| 지도 | MapLibre GL JS + VWorld WMTS + `maplibre-vworld` helper |
| 테이블 | PR #12는 native table, TanStack Table v8은 대량 필터/정렬 후속 |
| 데이터 패칭 | TanStack Query v5 |
| 타입 동기 | openapi-typescript + 수동 Zod mirror |
| 코드 표시 | 자체 `JsonBlock` 컴포넌트 |
| 테스트 | Vitest + @testing-library/react, Playwright는 e2e 후속 |

### A1.3 보안 모델 (내부 전용)

ADR-013에 명시 — 사내망/VPN 뒤에서만 접근. 별도 애플리케이션 인증 없음. 보안은 네트워크 레벨(nginx IP allowlist, 사내 SSO 게이트웨이)에서.

- 브라우저 → Next.js: 동일 origin. CORS 부재.
- Next.js → 백엔드: Route Handler가 서버 사이드에서 호출. CORS도 인증 헤더도 불필요.
- `/admin/*` 페이지: 일반 라우트와 동일. 별도 가드 없음.

외부 노출이 불가피해지면 (1) nginx/traefik basic auth, (2) 사내 SSO 게이트웨이, (3) 최후 수단으로 NextAuth — 그 결정은 새 ADR로 기록.

## A2. 프로젝트 구조

```
kraddr-geo-ui/
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
│   ├── admin/                     # tables/load/cache/logs/consistency
│   └── api/
│       └── proxy/[...path]/route.ts
├── components/
│   ├── layout/                    # AppShell
│   ├── ui/                        # Panel, PageHeader, JsonBlock, StatusBadge
│   ├── vworld/                    # CoordinateMap (MapLibre + VWorld WMTS + fallback preview)
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
KRADDR_GEO_API_INTERNAL_URL=http://localhost:8000           # 서버 사이드 전용
NEXT_PUBLIC_API_BASE_URL=/api/proxy                      # 브라우저 노출
NEXT_PUBLIC_VWORLD_API_KEY=your_vworld_api_key           # 브라우저 노출, VWorld 콘솔에서 도메인/IP 제한
```

`KRADDR_GEO_API_INTERNAL_URL`은 `NEXT_PUBLIC_` 접두사가 없어 서버 사이드에서만 접근 가능. 인증/시크릿은 두지 않는다(ADR-013).

`NEXT_PUBLIC_VWORLD_API_KEY` 발급은 `docs/external-apis.md` VWorld 프론트엔드 지도 항목 참조. 브라우저 번들에 포함되는 공개 키이므로 저장소에는 실제 값을 커밋하지 않고, VWorld 콘솔에서 로컬/스테이징/운영 도메인을 각각 제한한다.

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
  return trimmed.startsWith("/v1") ? trimmed : `/v1${trimmed}`;
}
export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> { ... }
export async function postJson<T>(path: string, body: unknown): Promise<T> { ... }
```

### A3.4 Next.js Route Handler 프록시

`app/api/proxy/[...path]/route.ts`가 백엔드로 전달한다. JSON 요청과 raw ZIP 업로드 요청을 같은 프록시로 처리하되, GET/HEAD가 아닌 요청 본문은 `request.body`(`ReadableStream`)를 그대로 `fetch`에 넘긴다. 대용량 ZIP을 Next.js Route Handler 메모리에 `arrayBuffer()`로 통째 적재하지 않기 위한 정책이며, Node.js fetch 스트림 전달 요건에 맞춰 `duplex: "half"`를 명시한다. Next.js 16에서는 Route Handler context의 `params`가 Promise이므로 `const params = await context.params` 형태를 사용한다.

프록시는 `/v1/` 하위 경로만 허용한다. `new URL()` 정규화 이후 `target.pathname`을 검사하므로 `/v1/../metrics` 같은 우회도 차단된다. 전달 헤더는 `accept`, `content-type`, `user-agent` allowlist만 사용하고 `authorization`/`cookie`/`x-forwarded-*` 등은 내부 백엔드로 넘기지 않는다.

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

`maplibre-gl`을 직접 사용해 VWorld WMTS raster style을 렌더링한다. 지도 URL, style 생성, 레이어별 maxZoom, CSS import는 `digitie/maplibre-vworld-js` package API를 사용한다. `kraddr-geo-ui/lib/vworld.ts`는 `maplibre-vworld`의 `getVWorldTileUrl()`, `getVWorldStyle()`, `getVWorldMaxZoom()`, `VWorldLayerType`를 재수출하는 얇은 경계다.

`CoordinateMap.tsx`는 실제 MapLibre 인스턴스, marker, click callback, tile error 처리를 담당한다. 상위 화면은 `components/vworld/LazyCoordinateMap.tsx`를 import한다. 이 wrapper는 `next/dynamic(..., { ssr: false })`로 MapLibre 번들을 클라이언트 런타임에만 불러오며, 로딩 중에는 같은 높이의 skeleton을 보여 준다. `maplibre-gl`은 브라우저 전역 객체와 WebGL에 의존하므로, 디버그 페이지에서 정적 import를 직접 늘리지 않는다.

`maplibre-vworld`는 `git+https://github.com/digitie/maplibre-vworld-js.git#c91c9f304669ce3f5fc4915f21186b23731d5816`로 고정한다. 이 upstream commit은 PR #6/#7 merge 이후 `dist/`, package `exports`, `types`, `style.css`, zod v4 peer dependency를 포함하고, PR #9에서 추가한 `onMapClick`/`onMapError`/`flyToOptions`와 tile error helper를 제공한다. 최신 helper 이름은 `redactVWorldUrl()`이며, `kraddr-geo-ui/lib/vworld.ts`는 기존 내부 컴포넌트 계약을 유지하기 위해 `redactVWorldUrl as redactVWorldTileUrl` alias를 둔다. CI에서 SSH key 없이 설치되어야 하므로 lockfile의 `resolved`도 `git+https`를 유지한다. 패키지 SHA를 바꿀 때는 WSL Linux Node/npm으로 `npm ci`, `npm run type-check`, `npm run test`, `npm run build`를 실행해 소비자 build가 유지되는지 먼저 확인한다.

지도 키는 `NEXT_PUBLIC_VWORLD_API_KEY`를 사용한다. 키가 없으면 같은 크기의 좌표 프리뷰로 대체한다. MapLibre/VWorld tile error는 일시적 네트워크 실패와 치명 오류를 구분한다. tile fetch 실패는 redacted URL로 `console.warn`만 남기고, 누적 임계치 이상이거나 style/WebGL 계열 오류일 때만 overlay를 보여 준다. 이 fallback 덕분에 CI, 내부망 테스트, VWorld 도메인 등록 전 개발 환경에서 화면이 비어 보이지 않는다.

VWorld raster layer는 레이어별 zoom 한계를 둔다. `Base`/`gray`/`midnight`는 z19까지, `Hybrid`/`Satellite`는 z18까지만 요청한다. `maplibre-vworld`의 style source id는 `vworld-${layerType}` 형식이고 `Hybrid`는 `vworld-satellite`와 `vworld-Hybrid`를 함께 쓰므로, tile error source 판별은 `vworld` prefix 기준으로 한다. marker 위치 갱신은 지도 클릭 후 되튐을 줄이기 위해 `flyTo({ animate: false, duration: 0 })`로 즉시 이동한다.

### A3.6.1 `digitie/maplibre-vworld-js` 보강 원칙

디버그 UI에서 VWorld/MapLibre 연동 문제가 발생하면 `kraddr-geo-ui`에서만 우회하지 않는다. 원인이 `digitie/maplibre-vworld-js`의 패키징, TypeScript 타입, CSS side-effect import, marker/cluster component, VWorld layer helper, Next.js 호환성에 있으면 해당 저장소도 적극 수정 대상에 포함한다.

현재 `kraddr-geo-ui`는 upstream helper와 CSS를 실제 package dependency로 소비하지만 `VWorldMap` 컴포넌트 전체를 곧바로 대체하지는 않는다. 대신 VWorld tile 오류 분류와 URL redaction은 upstream `isVWorldTileError()`/`redactVWorldUrl()` helper로 맞춘다. 내부 컴포넌트 import 이름은 `redactVWorldTileUrl` alias를 유지한다. 디버그 화면은 범용 지도 표시 외에 다음 동작을 보장해야 한다.

- 지도 클릭 시 `(lon, lat)` 순서의 `{ x, y }` 값을 reverse/geocode 디버그 입력으로 전달한다.
- `NEXT_PUBLIC_VWORLD_API_KEY`가 없으면 WebGL 지도를 만들지 않고 같은 크기의 좌표 preview fallback을 렌더링한다.
- VWorld tile 404/408/429/5xx와 네트워크 실패는 upstream helper로 분류한 뒤 즉시 치명 오류로 고정하지 않고 redacted warning과 누적 임계치로 처리한다.
- marker 갱신 시 애니메이션 되튐을 피하고, SSR 단계에서는 `next/dynamic(..., { ssr: false })`와 skeleton만 노출한다.

이 동작들은 T-044에서 `maplibre-vworld-js`의 재사용 가능한 props/hook/test로 옮긴다. 최종 목표는 `CoordinateMap.tsx`가 직접 `maplibregl.Map`, marker lifecycle, tile error classification을 소유하지 않고, upstream `VWorldMap` 또는 동등한 Hook/component를 감싸는 얇은 domain wrapper가 되는 것이다.

T-044 완전 포팅 원칙:

- `maplibre-vworld-js` public API가 click callback, marker 제어, `flyToOptions`, tile error hook/redaction, key 미설정 fallback, SSR-safe 사용법을 제공해야 한다.
- 해당 기능이 upstream에 없으면 `kraddr-geo-ui`에 임시 workaround를 추가하지 말고 `digitie/maplibre-vworld-js` 저장소를 직접 수정한다.
- upstream 수정은 별도 PR 또는 검증 가능한 commit으로 남긴 뒤, `kraddr-geo-ui/package.json`의 `maplibre-vworld` SHA와 lockfile을 갱신한다.
- upstream과 소비자 양쪽에서 test/build를 돌리고, PR 본문과 `docs/journal.md`에 upstream PR/commit, 검증 명령, 남은 차이를 기록한다.
- 포팅 후에도 `NEXT_PUBLIC_VWORLD_API_KEY` 미설정 fallback, `(lon, lat)` 좌표 순서, redacted logging, transient overlay 임계치, Next.js dynamic import skeleton은 유지해야 한다.

리뷰 기준:

- **패키징 문제**: GitHub 또는 npm install 후 `dist/`/`exports`/`types`가 없어서 소비자 build가 실패하면 `maplibre-vworld-js`의 배포 산출물 생성 또는 `files`/`exports` 구성을 고친다.
- **타입 문제**: React 18/19, MapLibre GL JS, Vite/Next.js에서 타입 오류가 나면 upstream 타입 선언과 테스트를 보강한다.
- **기능 문제**: VWorld `Base`/`gray`/`midnight`/`Hybrid`/`Satellite` layer, marker, click, clustering, attribution 중 공통 컴포넌트화할 수 있는 문제는 upstream에 반영한다.
- **의존성 선언 상태**: `maplibre-vworld`는 `git+https://github.com/digitie/maplibre-vworld-js.git#c91c9f304669ce3f5fc4915f21186b23731d5816`로 선언되어 있으며, `kraddr-geo-ui/lib/vworld.ts`는 upstream helper 재수출과 `redactVWorldUrl` 호환 alias만 담당한다.
- **컴포넌트 대체 조건**: click callback, marker 제어, tile error hook, fallback surface, SSR-safe 사용 방식이 upstream에서 같은 의미로 제공되고 테스트되면 `CoordinateMap.tsx`의 직접 MapLibre wiring을 제거하고 upstream 컴포넌트 또는 Hook을 사용한다.
- **보안·운영 조건**: 브라우저 노출 키는 VWorld 콘솔에서 origin/referrer 제한이 실제 WMTS에도 적용되는지 운영자가 확인한다. 향후 CSP를 켜면 `connect-src`와 `img-src`에 `https://api.vworld.kr`를 포함한다.

### A3.7 Provider 체인 (`app/providers.tsx`)

`QueryClientProvider` → children. ThemeProvider, Toaster, ReactQueryDevtools는 실제 사용 요구가 생기면 추가한다.

## A4. 공통 컴포넌트

- **CoordinateMap**: MapLibre GL JS와 VWorld WMTS raster style을 사용한다. `NEXT_PUBLIC_VWORLD_API_KEY`가 없거나 로딩 실패 시 좌표 프리뷰로 대체한다. 좌표 입력과 click callback은 모두 `(lon, lat)` 순서다.
- **GeocodeDebugger**: `address`, `type`, `fallback`을 받아 `/v1/address/geocode`를 호출하고 JSON 응답과 지도/좌표 프리뷰를 함께 표시한다.
- **TableStatsPanel**: `GET /v1/admin/tables` 결과를 native table로 보여준다. 수천 행 이상 필터·정렬이 필요해지면 TanStack Table로 승격한다.
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
| `/admin/load` | 다중 파일 업로드, source set 기준월 확인, 적재 작업 제출과 진행상황 모니터링 | `POST/PUT /v1/admin/uploads*`, `POST /v1/admin/load-sources/*`, `POST /v1/admin/loads`, `POST /v1/admin/maintenance/refresh-mv`, `GET /v1/admin/loads` |
| `/admin/cache` | 캐시 hit rate 시계열, 비우기 | `GET /v1/admin/cache/metrics` |
| `/admin/logs` | `load_jobs.log_tail` 최근 라인 조회 | `GET /v1/admin/logs` |
| `/admin/consistency` | C1~C10 정합성 리포트 조회·재검증 | `GET/POST /v1/admin/consistency*` |
| `/admin/backups` | DB 백업/복원 작업, 진행률, callback 상태, artifact 다운로드 | `POST/GET /v1/admin/backups`, `POST /v1/admin/restores`, `GET /v1/admin/jobs/{id}/events` |
| `/admin/performance` | 전국 DB query benchmark 결과, p95/p99 threshold, slow plan 조회 | `POST/GET /v1/admin/performance/benchmarks*` |

`/admin/postal`, `/admin/settings`, WebSocket log stream은 문서상 장기 후보였지만 PR #12 구현 범위에는 넣지 않았다. 후속 PR에서 별도 백엔드 표면을 먼저 확정한 뒤 추가한다.

### `/admin/load` 상태 머신

```
idle → selecting_files → uploading → upload_done → source_review
     → confirming_mismatch? → processing → finished → (reset) idle
```

원칙: "파일 업로드와 입력 처리는 각각 다 끝나면 다음 단계로". 파일이 서버에 모두 저장되고 source set 분석이 끝나기 전에는 적재 시작 버튼을 활성화하지 않는다. 업로드 중에는 처리 시작 버튼을 비활성화하고, 처리 중에는 새 파일 추가 영역을 닫는다.

- 파일 선택: `<input type="file" multiple>`과 drag and drop을 모두 지원한다. 디렉터리 drag가 가능한 브라우저에서는 `webkitRelativePath` 또는 동등한 relative path를 보존해 ZIP 묶음과 SHP sidecar 파일을 같은 upload set으로 보낸다.
- 업로드: T-045 구현은 upload set API를 사용한다. `POST /v1/admin/uploads`로 세션을 만들고, 각 파일은 `PUT /v1/admin/uploads/{upload_set_id}/files`에 raw stream으로 보낸다. 대용량 ZIP 업로드 진행률을 안정적으로 표시하기 위해 `XMLHttpRequest.upload.onprogress` 또는 동등한 업로드 progress wrapper를 사용한다. Next.js Route Handler는 파일 본문을 `arrayBuffer()`로 전체 버퍼링하지 않고 백엔드로 스트리밍한다.
- 업로드 진행률: 파일별 `uploaded_bytes / total_bytes`와 전체 `sum(uploaded_bytes) / sum(total_bytes)`를 별도 progress bar로 표시한다. 실패 파일은 재시도 버튼을 제공하고, 사용자가 전체 취소를 누르면 진행 중 요청을 abort한 뒤 서버 upload set cancel을 호출한다.
- source review: 모든 파일 저장이 완료되면 `POST /v1/admin/load-sources/discover`를 호출해 원천 후보, 기준월, 필수 원천 누락, 추천 source set을 표로 보여 준다.
- 기준월 mismatch 팝업: `mixed_yyyymm=true`이면 적재 시작 전에 modal을 띄운다. modal은 `juso`, `parcel_link`, `locsum`, `navi`, `shp`, `roadaddr_entrance`, `sppn_makarea`의 기준월과 경로를 보여 주고, C10 정합성 리포트에 혼합 기준월이 남는다는 점을 설명한다. 사용자가 계속 진행을 선택하면 서버가 요구하는 confirmation token 또는 문구를 `POST /v1/admin/load-sources/plan`에 함께 보낸다.
- 시도명 추론: `lib/sido.ts`의 `guessSido(filename)` (`서울→seoul`, `부산→busan`, …).
- 처리: `SourceSetPlan.batch_payload`가 확정된 뒤에만 `POST /v1/admin/loads kind=full_load_batch`를 호출한다. 큐가 직렬로 한 job씩 실행하며, UI는 root job과 child job을 폴링해 적재 진행률을 표시한다.
- 적재 진행률: 업로드 진행률과 분리한다. root `full_load_batch`의 `progress`, child job의 `current_stage`, `log_tail`을 함께 보여 주며, child별 가중 평균이 제공되면 전체 적재 퍼센트로 표시한다.
- 전체 취소: 업로드 단계에서는 upload set cancel + 브라우저 요청 abort를 수행한다. 적재 단계에서는 root job에 cancel 요청을 보내고, 서버는 실행 중 child의 협조적 cancel event와 대기 중 child의 `cancelled` 상태 전이를 담당한다. GDAL callback이 0 반환 → 즉시 중단.

UploadStage / SourceSetReviewStage / ProcessingStage 컴포넌트와 reducer 패턴은 T-045 구현 시 갱신한다. 테스트는 다중 파일 선택, DND, 기준월 mismatch modal, 업로드 취소, 적재 취소, 새로고침 후 진행률 복구를 포함해야 한다.

### `/admin/backups` 상태 머신 (ADR-030, T-046)

```
idle → configuring_backup → backup_preflight → backup_running
     → backup_done → artifact_ready → (reset) idle

idle → selecting_artifact → restore_preflight → restore_running
     → restore_done → validation_summary → (reset) idle
```

원칙: 백업/복원은 브라우저 요청 안에서 끝내지 않는다. UI는 작업 등록만 수행하고, 이후 `LoadJobStatus(kind="db_backup" | "db_restore")`와 `BackupArtifact` metadata를 통해 상태를 추적한다.

- 백업 생성 탭: 저장 위치 allowlist, 상대 경로, profile(`serving-ready`, `lean-serving`, `forensic`), jobs, compression level, callback URL을 입력한다. 저장 위치는 사용자의 로컬 다운로드 경로가 아니라 백엔드 서버가 접근 가능한 경로임을 UI 라벨에 명확히 표시한다.
- 진행 중 탭: `db_backup`, `db_restore` job을 함께 보여 준다. 우선 `GET /v1/admin/jobs/{job_id}/events` Server-Sent Events를 사용하고, 연결이 끊기면 TanStack Query polling으로 2초 간격 조회한다.
- 진행률: 백업은 `preflight → dump → archive → checksum → finalize`, 복원은 `preflight → extract → restore → analyze → validate → finalize` phase를 표시한다. `pg_dump`/`pg_restore` progress는 추정값이므로 stage label, elapsed time, 처리 object/file, archive 크기를 함께 보여 준다.
- 취소: 작업이 `queued` 또는 `running`일 때만 취소 버튼을 노출한다. 취소 후에는 서버가 partial dump dir, `.part` archive, 새 target DB를 어떻게 정리했는지 `log_tail`과 summary로 보여 준다.
- 백업 목록 탭: artifact id, 파일명, 크기, SHA256 앞 12자리, 생성일, profile, source set, callback 상태, 만료 예정일을 table로 표시한다. `done` artifact만 다운로드 버튼을 노출한다.
- 다운로드: 다운로드 링크는 브라우저 로컬 저장을 위한 보조 경로다. 백업 파일은 이미 서버 지정 경로에 저장되어 있으므로, UI는 서버 경로와 다운로드 링크를 구분해서 표시한다.
- 복원 탭: artifact 선택 또는 서버 경로 입력, target DB 이름, jobs, smoke test 여부, consistency 여부를 입력한다. 현재 연결 DB 이름과 같은 target은 클라이언트에서도 막고, 서버 preflight 실패 메시지도 그대로 보여 준다.
- 복원 안전장치: 기본 모드는 `new_database`만 노출한다. `replace_current`는 구현하더라도 별도 위험 모달, typed confirmation, 선행 백업 확인, maintenance mode 표시 없이는 실행하지 않는다.
- callback 상태: terminal callback이 성공하면 `callback_state=delivered`, 실패 후 재시도 중이면 `retrying`, 재시도 소진이면 `failed`로 표시한다. callback 실패는 백업 파일 성공 여부와 분리해서 보여 준다.

테스트는 backup form validation, SSE → polling fallback, 완료 후 다운로드 버튼 표시, callback 상태 badge, cancel flow, restore target DB 위험 입력 차단, corrupted artifact preflight 오류 표시를 포함해야 한다. 통합 검증은 대구광역시 부분 적재 DB를 대상으로 수행하고 전국 full-load는 실행하지 않는다.

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

## A7. DB 일관성 — 단일 엔진

프론트엔드는 자체 DB connection을 갖지 않는다. `/debug/*`(지오코딩/역지오코딩/정규화/EXPLAIN)와 `/admin/*`(테이블 통계/적재/MV refresh) 모두 백엔드 REST API를 호출하고, 백엔드는 `AsyncAddressClient.engine` 한 개의 SQLAlchemy 2 async engine으로 응답한다.

- **일관성**: 디버거 EXPLAIN과 운영 쿼리가 같은 search_path, 같은 statement_timeout, 같은 pool 옵션에서 평가됨.
- **관찰가능성**: structlog/Prometheus 카운터가 라이브러리·REST·디버거 호출을 한 곳에 집계.
- **권한·자원 통제**: DB pool 크기 단일 관리.

`kraddr-geo-ui`의 `package.json`에 `pg`/`prisma` 같은 DB 의존성이 들어오는 순간 ADR 위반이며 PR을 거절한다.

## A8. 외부 노출 정책 변경 시

내부망 가정이 깨질 때는 다음 순서를 따른다 — 코드 변경 없이 운영 변경으로 처리:

1. nginx/traefik 앞단에 basic auth 또는 OAuth proxy 배치
2. 사내 SSO 게이트웨이(Cloudflare Access, Tailscale, OpenVPN 등) 뒤로 이동
3. 마지막 수단으로 NextAuth 도입 — 그때도 `docs/decisions.md`에 새 ADR.
