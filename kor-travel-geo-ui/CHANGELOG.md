# CHANGELOG

## [Unreleased]

### Added
- GitHub `digitie/maplibre-vworld-react` 기반 VWorld 지도 dependency와 Next.js 16 Turbopack/Vitest/TypeScript alias를 추가했다.
- StyleSeed 기반 운영 콘솔 디자인 규칙 문서(`docs/DESIGN-RULES.md`)를 추가했다.
- `/admin/source-files` 업로드 탭의 epost 카드에서 `epost 받기` 버튼을 활성화했다. 버튼은 `/v1/admin/source-files/epost-fetch`를 호출해 사서함/다량배달처 server-fetch 등록과 `pobox_load`/`bulk_load` enqueue 결과를 표시한다.
- Playwright e2e에 좌측 메뉴 반복 이동 회귀 테스트를 추가했다. 메뉴 15개를 4회 순회하며 Next 기본 전역 오류 화면, page error, 비정상 request failure, `_rsc` client routing 요청 부재를 확인한다.
- `/debug/geocode`에 반경 행정구역 디버거를 추가했다. POI 좌표, 반경 km, 행정구역 레벨을 React Hook Form/Zod로 검증하고, TanStack Query mutation으로 `/v2/regions/within-radius`를 호출하며, Zustand로 마지막 초안과 결과를 보존한다.
- shadcn/ui source components(`Button`, `Card`, `Checkbox`, `Field`, `Input`)와 `components.json`을 추가해 신규 디버그 폼을 구성한다.
- Playwright e2e에 실제 Python API `.env` VWorld 키를 사용해 MapLibre canvas와 VWorld WMTS 타일 응답을 확인하는 지도 로딩 테스트를 추가했다.
- `/debug/geocode` 지도에 v2 `geometry` overlay를 추가했다. `include_geometry` 옵션이 켜진 geocode 응답에서 point marker와 행정구역 polygon, 도로 line, 건물 polygon을 함께 표시한다.
- T-021~T-023/T-026: Next.js 기반 디버그·관리 UI 초안 추가.
- T-020 연계: `openapi.json` 기반 타입 생성 스크립트 추가.
- Playwright e2e 테스트를 추가해 `/debug/geocode`, `/debug/reverse`의 v2 REST 요청 body와 입력 검증을 브라우저에서 확인한다.
- Docker image 실행을 위한 `Dockerfile`과 `.dockerignore`를 추가한다.
- `/api/runtime-config`와 `/admin/settings`를 추가해 `.env`의 VWorld 인증키를 런타임에 읽고, 브라우저에서 저장·수정할 수 있게 한다.
- MapLibre GL JS + VWorld WMTS 기반 좌표 지도 컴포넌트와 key 미설정 fallback 프리뷰 추가.
- VWorld 지도 컴포넌트 dynamic import wrapper와 skeleton 테스트 추가.
- `digitie/maplibre-vworld-js` 연동 원칙 문서화: 패키징·타입·Next.js 호환 문제가 나오면 UI workaround만 두지 않고 upstream도 적극 수정한다.
- `/api/proxy/[...path]` Route Handler로 raw ZIP 업로드와 JSON API 호출을 같은 경로에서 프록시.
- Vitest 단위 테스트: 시도 추론, load workflow reducer, consistency severity, schema name generation, API path helper.

### Changed
- `maplibre-vworld-js`/`maplibre-vworld` 의존성을 제거하고, 디버그 지도 wrapper를 GitHub `maplibre-vworld-react` tarball SHA `a7cb0f8f41ec00b44b1d106664506730b87033bd` 기반 `VWorldMapView`/`Marker` 소비로 전환했다.
- 공통 UI token과 primitive에 단일 accent, 5단계 텍스트 토큰, 약한 shadow, 44px touch target, 상태 dot+text 규칙을 반영했다.
- 좌측 메뉴와 Consistency report 목록은 `DocumentNavLink`를 사용한다. `next/link`는 유지하되 `prefetch={false}`와 document navigation으로 이동해 내부 운영 UI에서 Next App Router client transition/RSC fetch 실패 화면을 피한다.
- `/api/runtime-config`는 Python API `.env` 또는 프로세스 환경의 `KTG_VWORLD_API_KEY`를 우선 읽고, 없을 때만 `NEXT_PUBLIC_VWORLD_API_KEY`를 사용한다.
- 프론트엔드 실행과 정적 검증은 WSL ext4 미러의 Linux Node/npm에서 수행하고, Playwright 실행과 브라우저만 Windows에서 수행하도록 문서화했다.
- `/admin/` 기본 진입 시 404 대신 `/debug/geocode`로 이동하도록 했다.
- 모든 프론트엔드 작업 뒤 React Doctor를 실행하고 경고를 수정한 뒤 재실행하는 검증 절차를 문서화했다.
- `maplibre-vworld`를 upstream `main` commit `2f8ef8c59f2ff6d6360a16db038841473ea1dc41`로 동기화하고, `CoordinateMap`이 직접 MapLibre lifecycle을 소유하지 않도록 upstream `VWorldMap`/`Marker`/hook 기반 domain wrapper로 전환한다.
- `/debug/geocode`와 `/debug/reverse`는 응답 JSON을 입력 패널 아래에 표시하고, 지도 패널을 더 크게 배치한다.
- `/debug/geocode`와 `/debug/reverse`는 `/v2/geocode`, `/v2/reverse` POST API를 사용한다. proxy는 `/v1/*`와 `/v2/*`를 모두 허용하고 non-versioned path는 기존처럼 `/v1`로 보낸다.
- `maplibre-vworld`를 upstream main commit `c91c9f304669ce3f5fc4915f21186b23731d5816`로 동기화한다. 최신 upstream redaction helper는 `redactVWorldUrl()`이며, UI 내부에서는 기존 import 계약을 유지하기 위해 `redactVWorldTileUrl` alias로 재수출한다.
- `maplibre-vworld`를 `git+https://github.com/digitie/maplibre-vworld-js.git#a5b3c65`로 고정하고, VWorld WMTS helper와 CSS를 upstream package에서 소비한다.
- `maplibre-vworld`를 upstream PR #9 commit `11321fe`로 동기화하고, VWorld tile error 분류와 URL redaction을 upstream helper로 공유한다.
- upstream zod v4 peer dependency에 맞춰 `zod ^4.4.3`을 직접 의존성으로 둔다.
- VWorld tile transient error는 즉시 fatal overlay로 고정하지 않고 redacted warning과 누적 임계치로 처리한다.
- VWorld `Hybrid`/`Satellite`는 z18, `Base`/`gray`/`midnight`는 z19 maxZoom을 적용한다.

### Fixed
- Chrome/Firefox에서 좌측 메뉴 이동 중 Next 기본 전역 오류 화면(`This page couldn’t load`, `Reload to try again, or go back.`)으로 떨어질 수 있던 문제를 수정했다.
- VWorld 타일 요청이 페이지 이동 중 정상 취소될 때(`ERR_ABORTED`, `NS_BINDING_ABORTED`) 지도 타일 불안정 overlay와 warning 카운트에 반영하지 않도록 했다.
