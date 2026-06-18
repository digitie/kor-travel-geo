// 이 경계는 upstream `maplibre-vworld-react` web package의 *심층 source 경로*
// (`packages/vworld-map-web/src/...`)에서 재수출한다. package barrel(bare
// `vworld-map-web` index)을 일부러 쓰지 않는다: barrel은 `ClusterLayer`/
// `ServerClusterLayer`도 함께 re-export하고 이들이 `use-supercluster`/`supercluster`를
// 정적 import하는데, 그 의존성은 이 UI lockfile에서 제거됐다(ADR-063). barrel로
// "단순화"하면 Next/Vitest 빌드가 모듈 미해석으로 깨진다. 새 심볼이 필요하면 같은
// 패턴으로 심층 경로에서 추가하고, 그 경로가 새로 닿는 런타임 의존성은 UI
// `package.json`에 직접 선언한다(tarball은 inner workspace deps를 설치하지 않는다).
export {
  getVWorldMaxZoom,
  getVWorldStyle,
  getVWorldTileUrl,
  isVWorldTileError,
  redactVWorldUrl,
  registerVWorldProtocol,
  type VWorldLayerType,
  type VWorldResourceError
} from "maplibre-vworld-react/packages/vworld-map-web/src/vworld";

export {
  VWorldMapView as VWorldMap,
  type MapInteractionContext,
  type VWorldMapFallbackInfo,
  type VWorldMapFallbackReason,
  type VWorldMapViewProps
} from "maplibre-vworld-react/packages/vworld-map-web/src/VWorldMapView.web";

export { Marker, type MarkerProps } from "maplibre-vworld-react/packages/vworld-map-web/src/components/Marker";
export {
  MapStore,
  MapStoreContext,
  useMap,
  useMapLoaded,
  useMapSelector,
  useMapZoom,
  type MapStoreSnapshot
} from "maplibre-vworld-react/packages/vworld-map-web/src/store";
