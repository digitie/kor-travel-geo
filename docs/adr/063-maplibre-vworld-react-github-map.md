# ADR-063: 디버그 UI 지도는 GitHub `maplibre-vworld-react` 패키지를 소비한다

- 상태: accepted
- 날짜: 2026-06-18
- 결정자: 사용자 요청, codex

## 컨텍스트

ADR-020/028/032는 디버그 UI 지도를 VWorld WMTS + MapLibre GL JS로 고정하고, 범용 지도 기능은 `digitie/maplibre-vworld-js`에서 소비하며 이 저장소 특화 UX는 `kor-travel-geo-ui` domain wrapper에 남기도록 했다. 이번 작업의 사용자 요구는 JS 저장소가 아니라 GitHub `digitie/maplibre-vworld-react`를 활용하는 것이다.

`digitie/maplibre-vworld-react`는 2026-06-18 확인 시 npm registry에 공개된 package가 아니며, GitHub monorepo root package `maplibre-vworld-react` 아래에 `packages/vworld-map-core`, `packages/vworld-map-web`, `packages/vworld-map-rn` 소스가 포함되어 있다. `vworld-map-web`은 `VWorldMapView`, `Marker`, map store hook, VWorld helper를 TypeScript source로 제공하고, 내부에서 bare package name `vworld-map-core`를 import한다.

## 결정

`kor-travel-geo-ui`는 `maplibre-vworld-js` 의존성을 제거하고, GitHub `digitie/maplibre-vworld-react` tarball을 검증된 commit SHA로 직접 소비한다.

- 현재 고정 SHA는 `a7cb0f8f41ec00b44b1d106664506730b87033bd`다.
- 의존성 spec은 SSH key 없이 설치되도록 `https://github.com/digitie/maplibre-vworld-react/archive/a7cb0f8f41ec00b44b1d106664506730b87033bd.tar.gz`를 사용한다.
- `maplibre-gl`은 UI가 직접 의존성을 유지하고, 전역 CSS는 `maplibre-gl/dist/maplibre-gl.css`를 import한다.
- `kor-travel-geo-ui/lib/vworld.ts`는 이 저장소의 단일 지도 경계로 유지하고, `maplibre-vworld-react/packages/vworld-map-web/src/*`에서 `VWorldMapView`, `Marker`, hook, VWorld helper를 재수출한다.
- root tarball은 컴파일된 public export가 아니라 monorepo source를 포함하므로 TypeScript, Vitest, Next.js webpack, Next.js 16 Turbopack에 `vworld-map-core`와 `vworld-map-web` alias를 명시한다.
- `CoordinateMap.tsx`는 upstream React map lifecycle을 사용하되, 지도 click의 `{ x, y }` 변환, VWorld key 미설정 preview, tile error warning/overlay 임계치, API 응답 geometry overlay는 계속 이 저장소 domain wrapper에서 담당한다.

## 근거

- 사용자 요구가 `maplibre-vworld-react` 활용으로 명확하므로, 더 이상 `maplibre-vworld-js`를 소비자 dependency로 유지하지 않는다.
- GitHub tarball URL은 npm registry 미공개 상태에서도 `npm ci`가 SSH key 없이 재현 가능하게 만든다.
- `lib/vworld.ts` 경계를 유지하면 `CoordinateMap`과 디버그 화면은 upstream package 구조 변경의 영향을 한 파일에서 흡수할 수 있다.
- Next.js 16은 Turbopack을 기본 build path로 사용하므로 webpack alias만으로는 source package import를 안정적으로 해석할 수 없다.

## 결과

- `kor-travel-geo-ui/package.json`과 lockfile에서 `maplibre-vworld` / `maplibre-vworld-js` 의존성이 제거된다.
- `maplibre-vworld-react` source package가 쓰는 `vworld-map-core` bare import를 해석하기 위한 alias 설정이 `tsconfig.json`, `vitest.config.ts`, `next.config.mjs`에 생긴다.
- `getVWorldStyle()`의 source id 계약은 새 core 기준으로 바뀐다. `Base`/`gray`/`midnight`는 `vworld-base` source를 쓰고, `Hybrid`는 `vworld-satellite`와 `vworld-base` source를 함께 쓴다.
- 후속으로 `maplibre-vworld-react`가 npm release와 compiled export를 제공하면 tarball/source subpath import와 alias를 줄일 수 있다. 이 전환도 `npm ci`, lint, type-check, unit test, build, Windows Playwright e2e를 통과한 뒤 별도 PR로 처리한다.
