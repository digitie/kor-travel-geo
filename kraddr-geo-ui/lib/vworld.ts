import type { StyleSpecification } from "maplibre-gl";

export type VWorldLayerType = "Base" | "gray" | "midnight" | "Hybrid" | "Satellite";

const RASTER_LAYER_TYPES = new Set<VWorldLayerType>(["Base", "gray", "midnight", "Hybrid"]);

export function getVWorldTileUrl(apiKey: string, layerType: VWorldLayerType): string {
  const trimmedKey = apiKey.trim();
  const extension = RASTER_LAYER_TYPES.has(layerType) ? "png" : "jpeg";

  return `https://api.vworld.kr/req/wmts/1.0.0/${encodeURIComponent(
    trimmedKey
  )}/${layerType}/{z}/{y}/{x}.${extension}`;
}

export function getVWorldRasterStyle(
  apiKey: string,
  layerType: VWorldLayerType = "Base"
): StyleSpecification {
  return {
    version: 8,
    sources: {
      vworld: {
        type: "raster",
        tiles: [getVWorldTileUrl(apiKey, layerType)],
        tileSize: 256,
        attribution: "VWorld"
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
