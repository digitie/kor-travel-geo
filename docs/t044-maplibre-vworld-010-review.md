# T-044: `maplibre-vworld-js` 0.1.0 기준 문서-only 재확인

## 목적

사용자 지시: 현재 작업 완료 후 `maplibre-vworld-js`를 0.1.0 기준으로 코드 재확인하고, `maplibre-vworld-js` 코드를 직접 수정하지 말고 이 저장소 문서에만 보완할 점을 T-044로 업데이트한다.

따라서 이번 T-044 범위는 **문서-only**다. `digitie/maplibre-vworld-js` 저장소와 `kor-travel-geo-ui` 코드는 수정하지 않는다. 실제 UI wrapper 전환이나 dependency 갱신이 필요하면 별도 후속 PR에서 진행한다.

## 확인 기준

확인 일시: 2026-05-28

| 항목 | 결과 |
|------|------|
| GitHub tag | `v0.1.0` |
| tag commit | `8559bf4f8d5a32011a51669552bb7e1aedd42cfb` |
| commit message | `chore: release v0.1.0` |
| commit date | `2026-05-28T00:33:56Z` |
| GitHub release | 없음 (`gh release view v0.1.0` → release not found) |
| npm package | `maplibre-vworld@0.1.0`, `maplibre-vworld-js@0.1.0` 모두 registry `E404` |
| package name/version | `maplibre-vworld` / `0.1.0` |
| 현재 UI dependency | `git+https://github.com/digitie/maplibre-vworld-js.git#7947b2e170ddb36ab28a7a9034dd4dbf8f18370b` |

추가 비교:

- 현재 UI 고정 SHA `7947b2e...` 대비 `v0.1.0`은 26 commits ahead다.
- `v0.1.0` 대비 upstream `main`은 2 commits ahead이며, 확인 시점의 변경 파일은 upstream 문서/agent 설정 계열이었다.
- `v0.1.0` repository에는 `dist/index.d.ts`, `dist/maplibre-vworld-js.css`, `dist/maplibre-vworld-js.mjs`, `dist/maplibre-vworld-js.umd.js`가 포함되어 있다.

## 0.1.0 public API 요약

`src/index.ts` 기준 export:

- VWorld helper: `getVWorldTileUrl()`, `getVWorldStyle()`, `getVWorldMaxZoom()`, `redactVWorldUrl()`, `isVWorldTileError()`, `VWorldLayerType`, `VWorldResourceError`
- map store/hook: `MapStore`, `MapStoreContext`, `useMap()`, `useMapZoom()`, `useMapLoaded()`, `useMapSelector()`, `useEvent()`
- map container: `VWorldMap`, `VWorldMapProps`, `VWorldMapFallbackInfo`, `VWorldMapFallbackReason`
- marker primitive: `Marker`, `PinMarker`, `MakiMarker`, `PulsingMarker`, `UserLocationMarker`, `SimpleMarker`, `PlaceMarker`, `PriceMarker`, `WeatherMarker`, `RoutePointMarker`, `ClusterMarker`
- layer primitive: `ClusterLayer`, `ServerClusterLayer`, `RouteLine`, `PolygonArea`
- popup/context menu: `Popup`, `MapContextMenu`
- schema/helper: `LngLatSchema`, `BoundsSchema`, `PointSchema`, `RouteCoordinatesSchema`, `makeBoundedLngLatSchema()`, `formatLngLat()` 등

`VWorldMap` 0.1.0은 다음 T-044 요구와 맞는 기능을 이미 갖고 있다.

- `apiKey`가 비어 있으면 MapLibre 인스턴스를 만들지 않고 `fallback`을 렌더링한다.
- `onClick(event, context)`로 raw MapLibre click event와 interaction context를 전달한다. 소비자는 `event.lngLat.lng/lat`를 `{ x, y }`로 변환할 수 있다.
- `onError`와 `isVWorldTileError()`/`redactVWorldUrl()` 조합으로 tile 오류와 URL redaction을 처리할 수 있다.
- `flyToOptions`, `animateCameraChanges`, `cameraTarget`, `cameraTransition`, `bbox`로 camera update 정책을 제어할 수 있다.
- `unsupportedTileFallback`은 `vworld://` custom protocol을 등록해 실패 tile을 mock tile로 대체한다.
- `Marker`는 `lngLat`, `color`, `selected`, `highlighted`, `ariaLabel`, `onClick`, `onDragEnd` 등 기본 marker lifecycle을 component로 감싼다.
- `PolygonArea`는 GeoJSON Polygon/MultiPolygon을 style swap 뒤에도 재등록하므로 `TL_SPPN_MAKAREA`나 정합성 sample polygon overlay 후속에 쓸 수 있다.

## 현재 `kor-travel-geo-ui`와 차이

현재 `kor-travel-geo-ui`는 이미 다음을 upstream package에서 소비한다.

- `maplibre-vworld/style.css`
- `getVWorldStyle()`를 `getVWorldRasterStyle` alias로 재수출
- `getVWorldMaxZoom()`
- `isVWorldTileError()`
- `redactVWorldUrl()`를 `redactVWorldTileUrl` alias로 재수출

아직 `CoordinateMap.tsx`가 직접 소유하는 부분:

- `new maplibregl.Map(...)` 생성과 `ResizeObserver`
- `maplibregl.Marker` 생성/삭제와 marker 위치 갱신
- 지도 click event를 `{ x, y }`로 바꾸는 domain callback
- `NEXT_PUBLIC_VWORLD_API_KEY` 미설정 시 좌표 preview fallback 문구와 layout
- tile error 누적 count와 overlay threshold(`TILE_ERROR_OVERLAY_THRESHOLD = 6`)
- marker 이동 시 `flyTo({ animate: false, duration: 0 })`로 되튐을 줄이는 정책

0.1.0 기준으로는 `VWorldMap` + `Marker` + `onError` + `fallback` 조합으로 위 대부분을 wrapper 바깥 primitive에서 처리할 수 있다. 다만 fallback 문구, `{ x, y }` 변환, tile error overlay threshold, geocode/reverse/debug form 연결은 이 저장소 domain wrapper에 남긴다.

## T-044 문서-only 결론

1. T-044는 0.1.0 code/API 기준 재확인과 문서 보강으로 완료한다.
2. 이번 PR에서는 `maplibre-vworld-js` 코드를 직접 수정하지 않는다.
3. 이번 PR에서는 `kor-travel-geo-ui` dependency를 0.1.0 tag로 올리지 않는다. npm registry에 stable package가 아직 없으므로, 실제 갱신이 필요하면 `git+https://github.com/digitie/maplibre-vworld-js.git#v0.1.0` 또는 tag commit SHA `8559bf4...`를 별도 PR에서 검증한다.
4. 실제 `CoordinateMap` 전환은 별도 구현 PR에서 진행한다. 그 PR의 검증 조건은 `kor-travel-geo-ui`의 `npm ci`, `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`다.
5. 후속 구현에서 upstream 범용 기능이 부족하다고 판단되면, 이번 T-044 안에서 수정하지 않고 별도 upstream task/PR로 분리한다.

## 후속 구현 메모

후속 PR에서 `CoordinateMap`을 바꾼다면 형태는 다음이 자연스럽다.

- `CoordinateMap`은 계속 `{ x, y }` domain type과 `NEXT_PUBLIC_VWORLD_API_KEY` fallback 문구를 소유한다.
- 내부 지도는 `VWorldMap`으로 대체하고 `center={[point.x, point.y]}`, `zoom`, `animateCameraChanges={false}` 또는 `cameraTransition="instant"`를 검토한다.
- point marker는 `Marker lngLat={[point.x, point.y]} color="#0f766e"`로 대체한다.
- map click은 `onClick={(event) => onClick?.({ x: event.lngLat.lng, y: event.lngLat.lat })}` 형태로 변환한다.
- tile error는 `onError`에서 `isVWorldTileError()`와 `redactVWorldUrl()`를 사용하고, 이 저장소의 overlay threshold 정책은 wrapper state로 유지한다.
- `TL_SPPN_MAKAREA` 또는 C1~C10 정합성 sample overlay는 `PolygonArea`를 우선 후보로 검토한다.

## 검증

- `/home/digitie/dev/kor-travel-geo/.venv/bin/ruff check .` → 통과.
- `PYTHONPATH=/home/digitie/dev/geo-codex/src:/home/digitie/dev/geo-codex /home/digitie/dev/kor-travel-geo/.venv/bin/mypy src/kortravelgeo` → 통과.
- `PYTHONPATH=/home/digitie/dev/geo-codex/src:/home/digitie/dev/geo-codex /home/digitie/dev/kor-travel-geo/.venv/bin/lint-imports` → Layered architecture kept.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp PYTHONPATH=/home/digitie/dev/geo-codex/src:/home/digitie/dev/geo-codex /home/digitie/dev/kor-travel-geo/.venv/bin/python -m pytest -q` → 216 passed, 6 skipped, 3 warnings.
- `git diff --check` → 통과.
- `codegraph sync` → 통과.
