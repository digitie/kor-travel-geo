# ADR-020: 디버그 UI 지도는 VWorld WMTS + MapLibre를 사용하고 wrapper도 적극 보강한다

- 상태: accepted, amended by ADR-028 and ADR-032
- 날짜: 2026-05-25
- 결정자: 사용자 요청, codex 구현

## 컨텍스트

PR #12까지의 `kor-travel-geo-ui`는 Kakao Maps SDK를 기준으로 좌표 지도 컴포넌트를 만들었다. 그러나 이 프로젝트의 백엔드 응답은 vworld 호환 구조를 1차 공개 표면으로 삼고 있고, 외부 폴백도 vworld 주소 좌표 API를 먼저 호출한다. 디버그 UI가 다른 지도 공급자 위에서만 동작하면 운영자가 실제 vworld 기반 응답과 지도 타일을 같은 조건으로 비교하기 어렵다.

별도 저장소 `digitie/maplibre-vworld-js`는 MapLibre GL JS 위에서 VWorld 지도 layer, marker, cluster를 재사용 가능한 형태로 제공하려는 목적에 맞다. PR #15 최초 리뷰 시점에는 GitHub 의존성으로 설치했을 때 package `exports`가 가리키는 `dist/` 산출물이 포함되지 않아 소비자 프로젝트에서 직접 import하면 build 실패 위험이 있었다. 이후 upstream PR #6/#7이 merge되어 `dist/`, `exports`, `types`, `style.css`, zod v4 peer dependency가 정리되었고, PR #9 이후 click/error/flyTo helper와 tile error helper까지 소비한다.

## 결정

`kor-travel-geo-ui`의 디버그 지도는 Kakao Maps SDK가 아니라 VWorld WMTS + MapLibre GL JS를 사용한다.

- 브라우저 환경변수는 `NEXT_PUBLIC_VWORLD_API_KEY`다. 실제 키는 `.env.local`에만 두고 저장소에는 커밋하지 않는다.
- 지도 타일 URL, style 생성 규칙, CSS import는 `digitie/maplibre-vworld-js`의 package API를 사용한다. `kor-travel-geo-ui/lib/vworld.ts`는 로컬 구현을 갖지 않고 `maplibre-vworld`의 `getVWorldTileUrl()`, `getVWorldStyle()`, `getVWorldMaxZoom()`, `isVWorldTileError()`, `redactVWorldUrl()`, `VWorldMap`, `Marker`, map hook, `VWorldLayerType`를 재수출한다.
- `maplibre-vworld` package는 CI에서 SSH key 없이 설치할 수 있도록 검증된 최신 `main` SHA 또는 최신 stable release로 고정한다. 현재 확인된 최신 SHA는 `2f8ef8c59f2ff6d6360a16db038841473ea1dc41`이다. 2026-05-31 현재 npm registry에는 아직 `maplibre-vworld` package가 없으므로 GitHub SHA를 유지한다. upstream이 npm registry release 또는 stable tag를 제공하면 lockfile drift와 검증 결과를 확인한 뒤 dependency spec을 바꾼다.
- `maplibre-vworld/style.css`를 전역 CSS에서 import해 MapLibre GL 기본 CSS와 upstream package CSS를 한 경로에서 가져온다.
- `CoordinateMap`은 upstream `VWorldMap`/`Marker`/hook을 감싸는 domain wrapper다. 디버그 화면 전용 동작, 즉 지도 클릭 시 `(lon, lat)` callback, key 미설정 fallback, transient overlay 임계치, API 응답 geometry overlay, SSR 차단 wrapper는 이 저장소에서 보장한다. VWorld tile 오류 분류와 URL redaction은 `maplibre-vworld`의 `isVWorldTileError()`/`redactVWorldUrl()` helper를 사용한다.
- `digitie/maplibre-vworld-js`에서 패키징, 타입, CSS import, Next.js 호환성, VWorld layer/marker/cluster 공통 문제가 발견되면 이 저장소 전용 workaround에 그치지 않고 upstream도 적극 수정한다. 단, geocode/reverse 디버그 입력, API 응답 overlay, 정합성/성능/적재 상태 표시처럼 `kor-travel-geo-ui`에만 의미가 있는 특화 기능은 이 저장소의 domain wrapper에서 구현한다.

## 근거

- 디버그 UI가 백엔드의 vworld 호환 응답과 같은 공급자의 지도 타일 위에서 좌표를 확인할 수 있다.
- MapLibre는 표준 WebGL 지도 엔진이므로 VWorld WMTS 외에도 후속 SHP/GeoJSON overlay, consistency sample 표시, load 검증 layer를 붙이기 쉽다.
- `digitie/maplibre-vworld-js`를 개선하면 이 저장소뿐 아니라 다른 VWorld/MapLibre 소비자도 같은 보강을 재사용할 수 있다.

## 구현 규칙

- 좌표 callback과 marker 입력은 기존과 동일하게 `(lon, lat)` 순서를 유지한다.
- `NEXT_PUBLIC_VWORLD_API_KEY`가 없거나 tile loading이 실패하면 같은 크기의 fallback preview를 보여 주어 CI/내부망/키 미등록 환경에서도 화면이 깨지지 않게 한다.
- 실제 VWorld key는 문서, 코드, 테스트, PR 본문에 평문으로 남기지 않는다.
- `maplibre-vworld` package root import는 `npm ci`, type-check, Next.js build에서 계속 검증한다. 패키지 SHA를 바꿀 때는 `dist/`/`types`/`exports`/`style.css` 포함 여부를 먼저 확인한다.
- Next.js App Router에서 `maplibre-gl`은 브라우저 전역 객체와 WebGL에 의존하므로, 상위 디버그 화면은 `next/dynamic(..., { ssr: false })`로 지도 컴포넌트를 지연 로딩한다.
- VWorld tile fetch 실패는 일시적 네트워크/zoom 범위 문제일 수 있으므로 즉시 치명 overlay로 고정하지 않는다. transient tile error는 redacted URL로 경고만 남기고, 누적 임계치를 넘거나 style/WebGL 계열 오류일 때만 사용자에게 실패 상태를 표시한다.
- VWorld `Satellite`/`Hybrid` 계열은 z18까지만 요청하도록 레이어별 `maxZoom`을 둔다. `Base`/`gray`/`midnight`는 z19까지 허용한다.
- `maplibre-vworld`의 현재 style source id는 `vworld-${layerType}`이고, `Hybrid`는 `vworld-satellite`와 `vworld-Hybrid`를 함께 사용한다. tile error source 판별은 특정 id 하나가 아니라 `vworld` prefix를 기준으로 한다.
- 향후 CSP를 도입하면 VWorld tile 호출을 위해 `connect-src`/`img-src`에 `https://api.vworld.kr`를 포함해야 한다.

## 결과

- `kor-travel-geo-ui/components/vworld/CoordinateMap.tsx`는 upstream `VWorldMap`/`Marker`/hook을 감싸며 click/marker/geometry/fallback/error UX를 담당한다.
- `kor-travel-geo-ui/components/vworld/LazyCoordinateMap.tsx`가 Next.js dynamic import, SSR 차단, skeleton UI를 담당한다.
- `kor-travel-geo-ui/lib/vworld.ts`는 upstream package의 VWorld helper 재수출 지점이다.
- `maplibre-vworld` GitHub 의존성은 `2f8ef8c59f2ff6d6360a16db038841473ea1dc41`로 갱신했다. React 18 소비자와 upstream zod v4 peer dependency를 맞추기 위해 `kor-travel-geo-ui`도 `zod ^4.4.3`을 직접 의존성으로 둔다.
- 프론트엔드 문서와 외부 API 문서는 Kakao Maps가 아니라 VWorld WMTS 기준으로 갱신한다.
- 후속 PR에서는 API 응답 geometry overlay를 upstream `PolygonArea`/`RouteLine` primitive로 더 줄일 수 있는지 검토한다. 다만 geocode/reverse 입력 연결과 운영 콘솔 문구·임계치는 계속 이 저장소 domain wrapper에 둔다.
