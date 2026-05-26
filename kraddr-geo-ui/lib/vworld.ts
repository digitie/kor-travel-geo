export {
  getVWorldMaxZoom,
  getVWorldStyle as getVWorldRasterStyle,
  getVWorldTileUrl,
  isVWorldTileError,
  // 내부 컴포넌트 계약 보존용 alias다. T-044에서 domain wrapper를 정리할 때
  // 호출자를 upstream 이름인 redactVWorldUrl로 옮기고 제거한다.
  redactVWorldUrl as redactVWorldTileUrl,
  type VWorldLayerType
} from "maplibre-vworld";
