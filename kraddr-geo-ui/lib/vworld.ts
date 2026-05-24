import type { StyleSpecification } from "maplibre-gl";

export type VWorldLayerType = "Base" | "gray" | "midnight" | "Hybrid" | "Satellite";

const RASTER_LAYER_TYPES = new Set<VWorldLayerType>(["Base", "gray", "midnight", "Hybrid"]);
const LIMITED_ZOOM_LAYER_TYPES = new Set<VWorldLayerType>(["Hybrid", "Satellite"]);
const VWORLD_ATTRIBUTION = "공간정보 오픈플랫폼 브이월드";

export function getVWorldTileUrl(apiKey: string, layerType: VWorldLayerType): string {
  const trimmedKey = apiKey.trim();
  const extension = RASTER_LAYER_TYPES.has(layerType) ? "png" : "jpeg";

  return `https://api.vworld.kr/req/wmts/1.0.0/${encodeURIComponent(
    trimmedKey
  )}/${layerType}/{z}/{y}/{x}.${extension}`;
}

export function getVWorldMaxZoom(layerType: VWorldLayerType): number {
  return LIMITED_ZOOM_LAYER_TYPES.has(layerType) ? 18 : 19;
}

export function getVWorldRasterStyle(
  apiKey: string,
  layerType: VWorldLayerType = "Base"
): StyleSpecification {
  const maxzoom = getVWorldMaxZoom(layerType);

  return {
    version: 8,
    sources: {
      vworld: {
        type: "raster",
        tiles: [getVWorldTileUrl(apiKey, layerType)],
        maxzoom,
        tileSize: 256,
        attribution: VWORLD_ATTRIBUTION
      }
    },
    layers: [
      {
        id: "vworld",
        type: "raster",
        source: "vworld"
      }
    ]
  };
}
