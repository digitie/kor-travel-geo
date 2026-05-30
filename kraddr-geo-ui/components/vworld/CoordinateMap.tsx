"use client";

import maplibregl, {
  type ErrorEvent as MapLibreErrorEvent,
  type LngLatBoundsLike,
  type Map as MapLibreMap,
  type MapMouseEvent,
  type Marker as MapLibreMarker
} from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import {
  getVWorldMaxZoom,
  getVWorldRasterStyle,
  isVWorldTileError,
  redactVWorldTileUrl,
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

type MapResourceError = Error & {
  status?: number;
  statusText?: string;
  url?: string;
};

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
    <LoadedCoordinateMap
      apiKey={apiKey}
      bbox={bbox}
      geometry={geometry}
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
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<MapLibreMarker | null>(null);
  const onClickRef = useRef<typeof onClick>(onClick);
  const initialCenterRef = useRef(point ?? DEFAULT_CENTER);
  const transientTileErrorsRef = useRef(0);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    onClickRef.current = onClick;
  }, [onClick]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    setLoaded(false);
    setError(null);

    const map = new maplibregl.Map({
      center: [initialCenterRef.current.x, initialCenterRef.current.y],
      container,
      maxZoom: getVWorldMaxZoom(layerType),
      minZoom: 6,
      style: getVWorldRasterStyle(apiKey, layerType),
      zoom: DEFAULT_ZOOM
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const handleLoad = () => {
      transientTileErrorsRef.current = 0;
      setLoaded(true);
    };
    const handleError = (event: MapLibreErrorEvent) => {
      if (isVWorldTileError(event)) {
        transientTileErrorsRef.current += 1;
        warnMapTileError(event);
        if (transientTileErrorsRef.current >= TILE_ERROR_OVERLAY_THRESHOLD) {
          setError("지도 타일 로딩이 불안정합니다");
        }
        return;
      }

      setError("지도 로딩 실패");
    };
    const handleClick = (event: MapMouseEvent) => {
      onClickRef.current?.({ x: event.lngLat.lng, y: event.lngLat.lat });
    };
    // Coalesce resize callbacks into a single animation frame. Calling map.resize()
    // synchronously inside the ResizeObserver callback can retrigger layout and produce
    // a "ResizeObserver loop" that pins the main thread and freezes the tab.
    let resizeFrame = 0;
    const resizeObserver = new ResizeObserver(() => {
      if (resizeFrame) return;
      resizeFrame = window.requestAnimationFrame(() => {
        resizeFrame = 0;
        mapRef.current?.resize();
      });
    });

    map.on("load", handleLoad);
    map.on("error", handleError);
    map.on("click", handleClick);
    resizeObserver.observe(container);
    mapRef.current = map;

    return () => {
      if (resizeFrame) window.cancelAnimationFrame(resizeFrame);
      markerRef.current?.remove();
      markerRef.current = null;
      resizeObserver.disconnect();
      map.off("click", handleClick);
      map.off("error", handleError);
      map.off("load", handleLoad);
      map.remove();
      mapRef.current = null;
    };
  }, [apiKey, layerType]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;

    markerRef.current?.remove();
    markerRef.current = null;
    removeGeometryOverlay(map);

    if (geometry?.geojson) {
      addGeometryOverlay(map, geometry);
    }

    if (point) {
      markerRef.current = new maplibregl.Marker({ color: "#0f766e" })
        .setLngLat([point.x, point.y])
        .addTo(map);
    }

    const bounds = boundsFromBBox(bbox, point) ?? boundsFromGeoJson(geometry?.geojson, point);
    if (bounds) {
      map.fitBounds(bounds, {
        animate: false,
        duration: 0,
        essential: false,
        maxZoom: 17,
        padding: 36
      });
      return;
    }

    if (point) {
      map.flyTo({
        animate: false,
        center: [point.x, point.y],
        duration: 0,
        essential: false,
        zoom: Math.max(map.getZoom(), DEFAULT_ZOOM)
      });
    }
  }, [bbox, geometry, loaded, point]);

  return (
    <div className="vworld-map-shell">
      <div aria-label="VWorld MapLibre 지도" className="vworld-map" ref={containerRef} />
      {!loaded || error ? (
        <div className="vworld-map-overlay">
          <span>{error ?? "지도 로딩 중"}</span>
        </div>
      ) : null}
    </div>
  );
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
): LngLatBoundsLike | null {
  if (!bbox) return null;
  const expanded = expandBBoxWithPoint(bbox, point);
  if (expanded.min_lon >= expanded.max_lon || expanded.min_lat >= expanded.max_lat) return null;
  return [
    [expanded.min_lon, expanded.min_lat],
    [expanded.max_lon, expanded.max_lat]
  ];
}

function boundsFromGeoJson(
  geometry: GeoJSON.Geometry | null | undefined,
  point?: Coordinate | null
): LngLatBoundsLike | null {
  const bbox = geometry && "bbox" in geometry ? geometry.bbox : undefined;
  if (!bbox || bbox.length < 4) return null;
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
    url: redactVWorldTileUrl(error.url)
  });
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
