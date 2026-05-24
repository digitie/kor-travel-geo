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
| 지도 | MapLibre GL JS + VWorld WMTS (`digitie/maplibre-vworld-js` 연동 대상) |
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

`maplibre-gl`을 직접 사용해 VWorld WMTS raster style을 렌더링한다. 지도 URL과 style 생성 규칙은 `digitie/maplibre-vworld-js`의 `getVWorldTileUrl()` / `getVWorldStyle()` 계약과 맞춘다.

현재 `digitie/maplibre-vworld-js` GitHub 의존성은 `package.json`에 추적하지만, GitHub install 결과물에는 `dist/`가 포함되지 않아 패키지 root를 직접 import하면 Next.js build가 깨진다. 따라서 `kraddr-geo-ui/lib/vworld.ts`에 같은 WMTS style helper를 임시 bridge로 둔다. 이 bridge는 장기 fork가 아니라 upstream 패키징 보강 전까지의 안전장치다.

지도 키는 `NEXT_PUBLIC_VWORLD_API_KEY`를 사용한다. 키가 없거나 MapLibre/VWorld tile 로딩에 실패하면 같은 크기의 좌표 프리뷰 또는 loading overlay로 대체한다. 이 fallback 덕분에 CI, 내부망 테스트, VWorld 도메인 등록 전 개발 환경에서 화면이 비어 보이지 않는다.

### A3.6.1 `digitie/maplibre-vworld-js` 보강 원칙

디버그 UI에서 VWorld/MapLibre 연동 문제가 발생하면 `kraddr-geo-ui`에서만 우회하지 않는다. 원인이 `digitie/maplibre-vworld-js`의 패키징, TypeScript 타입, CSS side-effect import, marker/cluster component, VWorld layer helper, Next.js 호환성에 있으면 해당 저장소도 적극 수정 대상에 포함한다.

리뷰 기준:

- **패키징 문제**: GitHub 또는 npm install 후 `dist/`/`exports`/`types`가 없어서 소비자 build가 실패하면 `maplibre-vworld-js`의 배포 산출물 생성 또는 `files`/`exports` 구성을 고친다.
- **타입 문제**: React 18/19, MapLibre GL JS, Vite/Next.js에서 타입 오류가 나면 upstream 타입 선언과 테스트를 보강한다.
- **기능 문제**: VWorld `Base`/`gray`/`midnight`/`Hybrid`/`Satellite` layer, marker, click, clustering, attribution 중 공통 컴포넌트화할 수 있는 문제는 upstream에 반영한다.
- **로컬 bridge 제거 조건**: `maplibre-vworld` 패키지가 install 직후 `import { VWorldMap, Marker, getVWorldStyle } from "maplibre-vworld"` 형태로 안정 빌드되면 `kraddr-geo-ui/lib/vworld.ts`와 직접 MapLibre wiring을 줄이고 upstream 컴포넌트를 사용한다.

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
| `/admin/load` | 적재 작업 제출과 진행상황 모니터링 | `POST /v1/admin/upload/sido-zip`, `POST /v1/admin/loads`, `POST /v1/admin/maintenance/refresh-mv`, `GET /v1/admin/loads` |
| `/admin/cache` | 캐시 hit rate 시계열, 비우기 | `GET /v1/admin/cache/metrics` |
| `/admin/logs` | `load_jobs.log_tail` 최근 라인 조회 | `GET /v1/admin/logs` |
| `/admin/consistency` | C1~C10 정합성 리포트 조회·재검증 | `GET/POST /v1/admin/consistency*` |

`/admin/postal`, `/admin/settings`, WebSocket log stream은 문서상 장기 후보였지만 PR #12 구현 범위에는 넣지 않았다. 후속 PR에서 별도 백엔드 표면을 먼저 확정한 뒤 추가한다.

### `/admin/load` 상태 머신

```
idle → uploading → upload_done → processing → finished → (reset) idle
```

원칙: "파일 업로드와 입력 처리는 각각 다 끝나면 다음 단계로". 업로드 중 처리 시작 버튼 비활성, 처리 중 새 파일 추가 영역 닫힘.

- 업로드: PR #12 구현은 raw request body를 `fetch`로 전송한다. `python-multipart` 의존을 피하고 backend stream 처리와 맞추기 위한 결정이다. 브라우저 → Next.js → FastAPI 경로에서 파일 본문은 스트림으로 전달하고, Next.js Route Handler는 `arrayBuffer()`로 전체 파일을 버퍼링하지 않는다. 실패 시 `upload_done`으로 상태를 풀고 JSON 영역에 에러를 표시한다. 대용량 ZIP 업로드 진행률이 필요해지면 `XMLHttpRequest` 기반 progress bar를 후속으로 추가한다.
- 시도명 추론: `lib/sido.ts`의 `guessSido(filename)` (`서울→seoul`, `부산→busan`, …).
- 처리: 큐가 직렬로 한 job씩. UI는 사용자가 새로고침 버튼을 누르거나 후속 polling 구현으로 갱신한다. 모든 job이 종료 상태(`done`/`cancelled`/`failed`)면 `finished`.
- 전체 취소: 모든 미종료 job에 cancel 요청. GDAL callback이 0 반환 → 즉시 중단.

UploadStage / ProcessingStage 컴포넌트와 reducer 패턴은 첨부 §A6.3.4 ~ §A6.3.7 참조.

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
