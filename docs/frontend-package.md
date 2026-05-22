# 프론트엔드 패키지 사양서 — `kraddr-geo-ui`

본 문서는 첨부 사양서(2026-05-22 작성) Part A를 master 문서 체계로 옮긴 정리본이다. 디버깅 UI + DB 관리 UI를 한 Node.js 패키지로 통합 운영한다.

## A1. 개요

### A1.1 두 영역, 한 패키지

`kraddr-geo-ui`는 `python-kraddr-geo`(Python 패키지 `kraddr.geo`) 백엔드와 별도의 Node.js 패키지다. 사용자 대상 UI가 아니라 개발자·운영자가 라이브러리를 검증·관리하기 위한 내부 도구다.

- **디버깅 UI**: 지오코딩·역지오코딩·통합검색·정규화·SQL EXPLAIN을 지도와 함께 시각 검증
- **DB 관리 UI**: 테이블 통계, 적재 작업 큐, MV refresh, 사서함/다량배달처 갱신, 캐시 메트릭, 외부 API 키 관리, 로그 뷰어

두 영역 모두 같은 백엔드 REST API(`/v1/*` 및 `/v1/admin/*`)를 호출한다. 빌드 시 백엔드 `openapi.json`에서 Zod 스키마와 TypeScript 타입을 자동 생성하므로 두 패키지가 어긋나면 즉시 빌드 실패.

### A1.2 핵심 결정 (요약)

| 영역 | 선택 |
|------|------|
| 프레임워크 | Next.js 14 (App Router) + TypeScript strict |
| UI | shadcn/ui (Radix + Tailwind) |
| 폼 | React Hook Form + Zod |
| 지도 | react-kakao-maps-sdk |
| 테이블 | TanStack Table v8 |
| 데이터 패칭 | TanStack Query v5 |
| 타입 동기 | openapi-typescript + openapi-fetch + ts-to-zod |
| 코드 표시 | @uiw/react-json-view, react-syntax-highlighter |
| 테스트 | Vitest + @testing-library/react + Playwright |

### A1.3 보안 모델 (내부 전용)

ADR-013에 명시 — 사내망/VPN 뒤에서만 접근. 별도 애플리케이션 인증 없음. 보안은 네트워크 레벨(nginx IP allowlist, 사내 SSO 게이트웨이)에서.

- 브라우저 → Next.js: 동일 origin. CORS 부재.
- Next.js → 백엔드: Route Handler가 서버 사이드에서 호출. CORS도 인증 헤더도 불필요.
- `/admin/*` 페이지: 일반 라우트와 동일. 별도 가드 없음.

외부 노출이 불가피해지면 (1) nginx/traefik basic auth, (2) 사내 SSO 게이트웨이, (3) 최후 수단으로 NextAuth — 그 결정은 새 ADR로 기록.

## A2. 프로젝트 구조

```
kraddr-geo-ui/
├── package.json, tsconfig.json, next.config.mjs
├── tailwind.config.ts, postcss.config.mjs, components.json
├── .env.local.example
├── README.md, SKILL.md, CHANGELOG.md
├── docs/                          # ARCHITECTURE, DECISIONS, COMPONENTS, PAGES, TASKS, RESUME, JOURNAL
├── scripts/
│   ├── gen-types.ts               # openapi.json → types + zod
│   └── check-sync.sh
├── app/
│   ├── layout.tsx, page.tsx, globals.css, providers.tsx
│   ├── debug/                     # geocode/reverse/search/normalize/zipcode/explain
│   ├── admin/                     # tables/load/postal/cache/settings/logs
│   └── api/
│       ├── proxy/[...path]/route.ts
│       └── admin/[...path]/route.ts
├── components/
│   ├── ui/                        # shadcn auto-generated
│   ├── kakao/                     # KakaoMap, KakaoMapProvider, ClickToReverse, markers/Marker
│   ├── forms/                     # GeocodeForm, ReverseForm, SearchForm, ZipcodeForm, NormalizeForm
│   ├── tables/DataTable.tsx
│   ├── debug/                     # JsonViewer, NormalizeViewer, ExplainViewer, ZipSourceBadge
│   ├── admin/                     # TableStatsCard, LoadJobCard, CacheMetricsCard, UploadStage, ProcessingStage
│   └── nav/                       # Sidebar, Topbar
├── lib/
│   ├── api.ts                     # typed REST client (openapi-fetch)
│   ├── schemas.ts                 # zod schemas (mirror of pydantic v2)
│   ├── schemas.gen.ts             # auto-generated, do not edit
│   ├── kakao.ts, crs.ts, queryClient.ts, utils.ts, sido.ts
├── hooks/                         # useGeocode, useReverse, useDebounce, useTableStats, useUpload
├── types/                         # api.gen.ts (openapi-typescript), domain.ts
└── tests/                         # unit (vitest), e2e (playwright)
```

### 환경변수 (`.env.local.example`)

```
KRADDR_GEO_API_INTERNAL_URL=http://localhost:8000           # 서버 사이드 전용
NEXT_PUBLIC_API_BASE_URL=/api/proxy                      # 브라우저 노출
NEXT_PUBLIC_KAKAO_JS_KEY=your_kakao_app_js_key           # 도메인 제한이 보안 수단
```

`KRADDR_GEO_API_INTERNAL_URL`은 `NEXT_PUBLIC_` 접두사가 없어 서버 사이드에서만 접근 가능. 인증/시크릿은 두지 않는다(ADR-013).

`NEXT_PUBLIC_KAKAO_JS_KEY` 발급은 `docs/external-apis.md` Kakao Maps 항목 참조.

## A3. 공통 기반

### A3.1 백엔드 OpenAPI → TypeScript + Zod 자동 생성

`scripts/gen-types.ts`가 백엔드 `openapi.json`을 받아 `types/api.gen.ts`(openapi-typescript)와 `lib/schemas.gen.ts`(ts-to-zod)를 생성. 백엔드 DTO가 바뀌면 빌드 시 타입 에러로 즉시 드러난다.

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

### A3.3 `lib/api.ts` — Typed REST client

```ts
// 브라우저 → Next.js 프록시
export const api = createClient<paths>({
  baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/proxy",
});

// 서버 컴포넌트 / Route Handler용 (백엔드 직호출)
export function createServerApi() {
  return createClient<paths>({
    baseUrl: process.env.KRADDR_GEO_API_INTERNAL_URL ?? "http://localhost:8000",
  });
}
```

### A3.4 Next.js Route Handler 프록시

`app/api/proxy/[...path]/route.ts`와 `app/api/admin/[...path]/route.ts`가 동일 패턴으로 백엔드로 전달. 별도 인증 헤더 없음. body는 `req.text()`로 읽어 그대로 forward.

### A3.5 `lib/queryClient.ts`

```ts
new QueryClient({
  defaultOptions: { queries: {
    staleTime: 60_000, refetchOnWindowFocus: false,
    retry: (n, err) => (err?.status >= 400 && err?.status < 500) ? false : n < 2,
  }}
});
```

### A3.6 `lib/kakao.ts` (Kakao Maps SDK 로더)

`loadKakao()`가 한 번만 SDK script를 주입하고 `kakao.maps.load`로 ready를 보장. `NEXT_PUBLIC_KAKAO_JS_KEY` 미설정 시 즉시 reject.

### A3.7 Provider 체인 (`app/providers.tsx`)

`ThemeProvider` → `QueryClientProvider` → children → `Toaster` + `ReactQueryDevtools`.

## A4. 공통 컴포넌트

- **KakaoMap**: `center: LatLng`, `level=3`, `markers`, `onClick(pt)` — 역지오코딩 디버거에서 사용. `loadKakao()` 후 `kakao.maps.Map` 인스턴스 생성, 마커/InfoWindow/clean-up.
- **GeocodeForm** (RHF + Zod + shadcn): `address`, `type`, `crs`, `refine`, `simple`, `fallback`. `zodResolver(GeocodeInputSchema)`.
- **DataTable** (TanStack Table + shadcn): `data`, `columns: ColumnDef<T,any>[]`, `globalFilterPlaceholder`, `pageSize=25`. 정렬·필터·페이지네이션 내장.
- **JsonViewer** (`@uiw/react-json-view`): 다크모드 자동 적용. `collapsed=2` 기본.
- **ZipSourceBadge**: `ZipSource` enum별 색상/라벨 메타데이터로 시각화.

## A5. 디버깅 UI 페이지

| 경로 | 목적 | 주요 컴포넌트 |
|------|------|---------------|
| `/debug/geocode` | 주소 → 좌표 검증, Kakao 지도 마커 | GeocodeForm, KakaoMap, JsonViewer, ZipSourceBadge |
| `/debug/reverse` | 지도 클릭 → 역지오코딩 | KakaoMap(onClick), 결과 리스트 |
| `/debug/search` | 통합 검색 (address/place/district/road) | SearchForm, DataTable, KakaoMap |
| `/debug/normalize` | 주소 정규화 디버거 (parts 시각화) | NormalizeForm, NormalizeViewer |
| `/debug/zipcode` | 우편번호 lookup 우선순위 시각화 | ZipcodeForm, ZipSourceBadge |
| `/debug/explain` | 임의 SELECT의 EXPLAIN plan | ExplainViewer (SELECT/WITH만 허용) |

**EXPLAIN 일관성**: 백엔드 `/v1/admin/explain`은 `AsyncAddressClient.engine`을 그대로 사용해 `EXPLAIN(FORMAT JSON [, ANALYZE, BUFFERS])`를 실행. 디버거 결과가 운영 쿼리와 같은 환경(search_path, statement_timeout, pool)에서 평가됨.

## A6. DB 관리 UI 페이지

| 경로 | 기능 | 주요 API |
|------|------|----------|
| `/admin/tables` | 테이블 통계 (행/디스크/인덱스/마지막 VACUUM) | `GET /v1/admin/tables` |
| `/admin/load` | 적재 작업 제출과 진행상황 모니터링 | `POST /v1/admin/upload/sido-zip`, `POST /v1/admin/load/sido-batch`, `GET /v1/admin/jobs` |
| `/admin/postal` | 사서함·다량배달처 갱신 트리거 | `POST /v1/admin/load/pobox`, `.../bulk` |
| `/admin/cache` | 캐시 hit rate 시계열, 비우기 | `GET /v1/admin/cache/metrics` |
| `/admin/settings` | 외부 API 키 가림 표시, statement_timeout 슬라이더 | `GET/PUT /v1/admin/settings` |
| `/admin/logs` | structlog JSON 라인 stream | WS `/v1/admin/logs/stream` |

### `/admin/load` 상태 머신

```
idle → uploading → upload_done → processing → finished → (reset) idle
```

원칙: "파일 업로드와 입력 처리는 각각 다 끝나면 다음 단계로". 업로드 중 처리 시작 버튼 비활성, 처리 중 새 파일 추가 영역 닫힘.

- 업로드: `useUpload` 훅이 XMLHttpRequest로 진행률 보고 (fetch는 업로드 progress를 보고하지 않음). 병렬 3개까지.
- 시도명 추론: `lib/sido.ts`의 `guessSido(filename)` (`서울→seoul`, `부산→busan`, …).
- 처리: 큐가 직렬로 한 시도씩. UI는 2초 폴링 (`refetchInterval`). 모든 job이 종료 상태(`done`/`cancelled`/`failed`)면 `finished`.
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
