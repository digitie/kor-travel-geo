"use client";

import maplibregl, {
  type ErrorEvent as MapLibreErrorEvent,
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

export type Coordinate = {
  x: number;
  y: number;
};

const DEFAULT_CENTER = { x: 126.978, y: 37.5665 };
const DEFAULT_ZOOM = 15;
const TILE_ERROR_OVERLAY_THRESHOLD = 6;

type MapResourceError = Error & {
  status?: number;
  statusText?: string;
  url?: string;
};

export function CoordinateMap({
  point,
  onClick,
  layerType = "Base"
}: {
  point: Coordinate | null;
  onClick?: (point: Coordinate) => void;
  layerType?: VWorldLayerType;
}) {
  const apiKey = process.env.NEXT_PUBLIC_VWORLD_API_KEY;

  if (!apiKey) {
    return <CoordinateFallback point={point} note="VWorld API 키 미설정" />;
  }

  return <LoadedCoordinateMap apiKey={apiKey} layerType={layerType} onClick={onClick} point={point} />;
}

function LoadedCoordinateMap({
  apiKey,
  layerType,
  point,
  onClick
}: {
  apiKey: string;
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
    const resizeObserver = new ResizeObserver(() => map.resize());

    map.on("load", handleLoad);
    map.on("error", handleError);
    map.on("click", handleClick);
    resizeObserver.observe(container);
    mapRef.current = map;

    return () => {
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

    if (!point) return;

    markerRef.current = new maplibregl.Marker({ color: "#0f766e" })
      .setLngLat([point.x, point.y])
      .addTo(map);
    map.flyTo({
      animate: false,
      center: [point.x, point.y],
      duration: 0,
      essential: false,
      zoom: Math.max(map.getZoom(), DEFAULT_ZOOM)
    });
  }, [loaded, point]);

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
