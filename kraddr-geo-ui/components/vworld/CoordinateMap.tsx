"use client";

import type {
  ErrorEvent as MapLibreErrorEvent,
  Map as MapLibreMap,
  MapMouseEvent
} from "maplibre-gl";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  getVWorldMaxZoom,
  isVWorldTileError,
  Marker,
  redactVWorldUrl,
  useMap,
  useMapLoaded,
  VWorldMap,
  type VWorldMapFallbackInfo,
  type VWorldLayerType
} from "@/lib/vworld";
import { useVWorldApiKey } from "@/lib/vworld-key";

export type Coordinate = {
  x: number;
  y: number;
};

export type CoordinateBBox = {
  min_lon: number;
  min_lat: number;
  max_lon: number;
  max_lat: number;
};

export type MapGeometryOverlay = {
  kind?: string | null;
  geojson?: GeoJSON.Geometry | null;
};

const DEFAULT_CENTER = { x: 126.978, y: 37.5665 };
const DEFAULT_ZOOM = 15;
const TILE_ERROR_OVERLAY_THRESHOLD = 6;
const OVERLAY_SOURCE_ID = "kraddr-geo-overlay";
const OVERLAY_FILL_LAYER_ID = "kraddr-geo-overlay-fill";
const OVERLAY_LINE_LAYER_ID = "kraddr-geo-overlay-line";
const OVERLAY_POINT_LAYER_ID = "kraddr-geo-overlay-point";
type MapBBox = [number, number, number, number];

type MapResourceError = Error & {
  status?: number;
  statusText?: string;
  url?: string;
};

// Map load/error state in a single reducer so the init effect dispatches one
// action per event instead of juggling several independent setState setters.
type MapStatus = { error: string | null };
type MapStatusAction = { type: "loaded" } | { type: "error"; message: string };
const INITIAL_MAP_STATUS: MapStatus = { error: null };

function mapStatusReducer(state: MapStatus, action: MapStatusAction): MapStatus {
  switch (action.type) {
    case "loaded":
      return state.error === null ? state : { error: null };
    case "error":
      return state.error === action.message ? state : { error: action.message };
    default:
      return state;
  }
}

export function CoordinateMap({
  point,
  bbox,
  geometry,
  onClick,
  layerType = "Base"
}: {
  point: Coordinate | null;
  bbox?: CoordinateBBox | null;
  geometry?: MapGeometryOverlay | null;
  onClick?: (point: Coordinate) => void;
  layerType?: VWorldLayerType;
}) {
  const { apiKey, loading } = useVWorldApiKey();

  if (!apiKey) {
    return <CoordinateFallback point={point} note={loading ? "VWorld API 키 확인 중" : "VWorld API 키 미설정"} />;
  }

  return (
    // Remount on apiKey/layerType change so map-init state (loaded/error) resets
    // naturally via a fresh mount instead of being adjusted inside an effect.
    <LoadedCoordinateMap
      apiKey={apiKey}
      bbox={bbox}
      geometry={geometry}
      key={`${apiKey}::${layerType}`}
      layerType={layerType}
      onClick={onClick}
      point={point}
    />
  );
}

function LoadedCoordinateMap({
  apiKey,
  bbox,
  geometry,
  layerType,
  point,
  onClick
}: {
  apiKey: string;
  bbox?: CoordinateBBox | null;
  geometry?: MapGeometryOverlay | null;
  layerType: VWorldLayerType;
  point: Coordinate | null;
  onClick?: (point: Coordinate) => void;
}) {
  const [initialCenter] = useState(() => point ?? DEFAULT_CENTER);
  const transientTileErrorsRef = useRef(0);
  const [status, dispatchStatus] = useReducer(mapStatusReducer, INITIAL_MAP_STATUS);
  const { error } = status;
  const unsupportedTileFallback = useMemo(() => ({ label: "지원하지 않는 타일" }), []);
  const mapBounds = useMemo(
    () => boundsFromBBox(bbox, point) ?? boundsFromGeoJson(geometry?.geojson, point),
    [bbox, geometry?.geojson, point]
  );
  const cameraTarget = useMemo(() => {
    if (!point || mapBounds) return undefined;
    return { center: [point.x, point.y] as [number, number], zoom: DEFAULT_ZOOM };
  }, [mapBounds, point]);
  const handleLoad = useCallback(() => {
    transientTileErrorsRef.current = 0;
    dispatchStatus({ type: "loaded" });
  }, []);
  const handleError = useCallback((event: MapLibreErrorEvent) => {
    if (isVWorldTileError(event)) {
      transientTileErrorsRef.current += 1;
      warnMapTileError(event);
      if (transientTileErrorsRef.current >= TILE_ERROR_OVERLAY_THRESHOLD) {
        dispatchStatus({ type: "error", message: "지도 타일 로딩이 불안정합니다" });
      }
      return;
    }

    dispatchStatus({ type: "error", message: "지도 로딩 실패" });
  }, []);
  const handleClick = useCallback((event: MapMouseEvent) => {
    onClick?.({ x: event.lngLat.lng, y: event.lngLat.lat });
  }, [onClick]);

  return (
    <div className="vworld-map-shell">
      <VWorldMap
        apiKey={apiKey}
        bbox={mapBounds}
        cameraTarget={cameraTarget}
        cameraTransition="instant"
        center={[initialCenter.x, initialCenter.y]}
        className="vworld-map"
        fallback={(info) => <VWorldMapFallback info={info} />}
        geolocate={false}
        layerType={layerType}
        loadingSkeleton={<MapOverlay text="지도 로딩 중" />}
        maxZoom={getVWorldMaxZoom(layerType)}
        onClick={handleClick}
        onError={handleError}
        onLoad={handleLoad}
        scale={false}
        style={{ width: "100%", height: "100%" }}
        unsupportedTileFallback={unsupportedTileFallback}
        zoom={DEFAULT_ZOOM}
      >
        <GeometryOverlay geometry={geometry} />
        {point ? <Marker color="#0f766e" lngLat={[point.x, point.y]} /> : null}
      </VWorldMap>
      {error ? <MapOverlay text={error} /> : null}
    </div>
  );
}

function GeometryOverlay({ geometry }: { geometry?: MapGeometryOverlay | null }) {
  const map = useMap();
  const loaded = useMapLoaded();

  useEffect(() => {
    if (!map || !loaded) return;

    removeGeometryOverlay(map);
    if (geometry?.geojson) {
      addGeometryOverlay(map, geometry);
    }

    return () => {
      removeGeometryOverlay(map);
    };
  }, [geometry, loaded, map]);

  return null;
}

function addGeometryOverlay(map: MapLibreMap, geometry: MapGeometryOverlay): void {
  if (!geometry.geojson) return;
  const feature: GeoJSON.Feature = {
    type: "Feature",
    properties: { kind: geometry.kind ?? "geometry" },
    geometry: geometry.geojson
  };
  map.addSource(OVERLAY_SOURCE_ID, {
    type: "geojson",
    data: feature
  });

  const geometryType = geometry.geojson.type;
  if (geometryType === "Polygon" || geometryType === "MultiPolygon") {
    map.addLayer({
      id: OVERLAY_FILL_LAYER_ID,
      source: OVERLAY_SOURCE_ID,
      type: "fill",
      paint: {
        "fill-color": "#14b8a6",
        "fill-opacity": 0.22
      }
    });
    map.addLayer({
      id: OVERLAY_LINE_LAYER_ID,
      source: OVERLAY_SOURCE_ID,
      type: "line",
      paint: {
        "line-color": "#0f766e",
        "line-width": 3
      }
    });
    return;
  }

  if (geometryType === "LineString" || geometryType === "MultiLineString") {
    map.addLayer({
      id: OVERLAY_LINE_LAYER_ID,
      source: OVERLAY_SOURCE_ID,
      type: "line",
      paint: {
        "line-color": "#2563eb",
        "line-width": 5,
        "line-opacity": 0.86
      }
    });
    return;
  }

  if (geometryType === "Point" || geometryType === "MultiPoint") {
    map.addLayer({
      id: OVERLAY_POINT_LAYER_ID,
      source: OVERLAY_SOURCE_ID,
      type: "circle",
      paint: {
        "circle-color": "#2563eb",
        "circle-radius": 7,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 2
      }
    });
  }
}

function removeGeometryOverlay(map: MapLibreMap): void {
  for (const layerId of [
    OVERLAY_POINT_LAYER_ID,
    OVERLAY_LINE_LAYER_ID,
    OVERLAY_FILL_LAYER_ID
  ]) {
    if (map.getLayer(layerId)) {
      map.removeLayer(layerId);
    }
  }
  if (map.getSource(OVERLAY_SOURCE_ID)) {
    map.removeSource(OVERLAY_SOURCE_ID);
  }
}

function boundsFromBBox(
  bbox: CoordinateBBox | null | undefined,
  point?: Coordinate | null
): MapBBox | undefined {
  if (!bbox) return undefined;
  const expanded = expandBBoxWithPoint(bbox, point);
  if (expanded.min_lon >= expanded.max_lon || expanded.min_lat >= expanded.max_lat) return undefined;
  return [
    expanded.min_lon,
    expanded.min_lat,
    expanded.max_lon,
    expanded.max_lat
  ];
}

function boundsFromGeoJson(
  geometry: GeoJSON.Geometry | null | undefined,
  point?: Coordinate | null
): MapBBox | undefined {
  const bbox = geometry && "bbox" in geometry ? geometry.bbox : undefined;
  if (!bbox || bbox.length < 4) return undefined;
  return boundsFromBBox({
    min_lon: bbox[0],
    min_lat: bbox[1],
    max_lon: bbox[2],
    max_lat: bbox[3]
  }, point);
}

function expandBBoxWithPoint(bbox: CoordinateBBox, point?: Coordinate | null): CoordinateBBox {
  if (!point) return bbox;
  return {
    min_lon: Math.min(bbox.min_lon, point.x),
    min_lat: Math.min(bbox.min_lat, point.y),
    max_lon: Math.max(bbox.max_lon, point.x),
    max_lat: Math.max(bbox.max_lat, point.y)
  };
}

function warnMapTileError(event: MapLibreErrorEvent): void {
  const error = event.error as MapResourceError;

  console.warn("VWorld tile load warning", {
    message: error.message,
    sourceId: "sourceId" in event ? event.sourceId : undefined,
    status: error.status,
    statusText: error.statusText,
    url: redactVWorldUrl(error.url)
  });
}

function VWorldMapFallback({ info }: { info: VWorldMapFallbackInfo }) {
  const message = info.reason === "missing-api-key" ? "VWorld API 키 미설정" : "지도 로딩 실패";
  return <MapOverlay text={message} />;
}

function MapOverlay({ text }: { text: string }) {
  return (
    <div className="vworld-map-overlay">
      <span>{text}</span>
    </div>
  );
}

function CoordinateFallback({ point, note }: { point: Coordinate | null; note: string }) {
  return (
    <div className="map-box">
      <div className="map-marker">
        <strong>{point ? `${point.x.toFixed(6)}, ${point.y.toFixed(6)}` : "좌표 대기"}</strong>
        <span>{point ? "EPSG:4326" : note}</span>
      </div>
    </div>
  );
}
