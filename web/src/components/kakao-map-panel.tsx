"use client";

import { useEffect, useRef } from "react";
import { Circle, CustomOverlayMap, Map, MapMarker, Polyline, useKakaoLoader } from "react-kakao-maps-sdk";

import type { AddressPlace, Coordinate } from "@/data/address-data";

type KakaoMapPanelProps = {
  places: AddressPlace[];
  selected: AddressPlace;
  showBoundary: boolean;
  showRadius: boolean;
  onSelect: (id: string) => void;
};

const kakaoKey = process.env.NEXT_PUBLIC_KAKAO_JAVASCRIPT_KEY ?? "";

export function KakaoMapPanel({
  places,
  selected,
  showBoundary,
  showRadius,
  onSelect,
}: KakaoMapPanelProps) {
  const safePlaces = places.filter(hasRenderableCoordinate);
  const safeSelected = hasRenderableCoordinate(selected) ? selected : safePlaces[0];

  if (!safeSelected) {
    return (
      <div className="relative flex min-h-[520px] flex-1 items-center justify-center bg-[#eef3f7] text-sm font-semibold text-[#536579]">
        표시 가능한 국내 좌표가 없습니다
      </div>
    );
  }

  if (!kakaoKey) {
    return (
      <StaticMapPreview
        places={safePlaces}
        selected={safeSelected}
        showBoundary={showBoundary}
        showRadius={showRadius}
        onSelect={onSelect}
      />
    );
  }

  return (
    <KakaoMapCanvas
      places={safePlaces}
      selected={safeSelected}
      showBoundary={showBoundary}
      showRadius={showRadius}
      onSelect={onSelect}
    />
  );
}

function KakaoMapCanvas({
  places,
  selected,
  showBoundary,
  showRadius,
  onSelect,
}: KakaoMapPanelProps) {
  const mapRef = useRef<kakao.maps.Map | null>(null);
  const [, error] = useKakaoLoader({
    appkey: kakaoKey,
    libraries: ["services", "clusterer"],
  });

  useEffect(() => {
    if (!mapRef.current) {
      return;
    }
    mapRef.current.setCenter(new kakao.maps.LatLng(selected.coordinate.lat, selected.coordinate.lng));
  }, [selected.coordinate.lat, selected.coordinate.lng, selected.id]);

  if (error) {
    return (
      <StaticMapPreview
        places={places}
        selected={selected}
        showBoundary={showBoundary}
        showRadius={showRadius}
        onSelect={onSelect}
      />
    );
  }

  return (
    <div className="relative min-h-[520px] flex-1">
      <Map
        key={selected.id}
        center={selected.coordinate}
        className="h-full min-h-[520px] w-full"
        level={7}
        isPanto
        onCreate={(map) => {
          mapRef.current = map;
          map.setCenter(new kakao.maps.LatLng(selected.coordinate.lat, selected.coordinate.lng));
        }}
      >
        {showBoundary && selected.boundary.length > 1 ? (
          <Polyline
            path={selected.boundary}
            strokeWeight={4}
            strokeColor="#0f766e"
            strokeOpacity={0.9}
            strokeStyle="solid"
          />
        ) : null}
        {showRadius ? (
          <Circle
            center={selected.coordinate}
            radius={selected.radiusMeters}
            strokeWeight={2}
            strokeColor="#d97706"
            strokeOpacity={0.85}
            fillColor="#f59e0b"
            fillOpacity={0.12}
          />
        ) : null}
        {places.map((place) => (
          <MapMarker
            key={place.id}
            position={place.coordinate}
            clickable
            onClick={() => onSelect(place.id)}
          />
        ))}
        <CustomOverlayMap position={selected.coordinate} yAnchor={1.35}>
          <button
            type="button"
            onClick={() => onSelect(selected.id)}
            className="rounded-lg border border-[#0f766e] bg-white px-3 py-2 text-left shadow-lg"
          >
            <span className="block text-sm font-bold text-[#142033]">{selected.title}</span>
            <span className="mt-0.5 block font-mono text-[11px] font-semibold text-[#607086]">
              {selected.legalDongCode}
            </span>
          </button>
        </CustomOverlayMap>
      </Map>
    </div>
  );
}

function StaticMapPreview({
  places,
  selected,
  showBoundary,
  showRadius,
  onSelect,
}: KakaoMapPanelProps) {
  const bounds = mapBounds(places, selected.coordinate, showBoundary ? selected.boundary : []);
  const selectedPoint = toPercent(selected.coordinate, bounds);
  const boundaryPoints = selected.boundary.map((point) => toPercent(point, bounds));

  return (
    <div className="relative min-h-[520px] flex-1 overflow-hidden bg-[#dfe8ee]">
      <div className="absolute inset-0 opacity-70 [background-image:linear-gradient(#c8d5df_1px,transparent_1px),linear-gradient(90deg,#c8d5df_1px,transparent_1px)] [background-size:42px_42px]" />
      <div className="absolute inset-x-4 top-4 z-20 flex items-center justify-between gap-3 rounded-lg border border-[#cfd7e5] bg-white/95 px-3 py-2 shadow-sm backdrop-blur">
        <span className="text-sm font-semibold text-[#39485c]">Kakao 지도 대기</span>
        <span className="font-mono text-xs font-semibold text-[#0f766e]">
          {selected.coordinate.lat.toFixed(5)}, {selected.coordinate.lng.toFixed(5)}
        </span>
      </div>

      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none">
        {showBoundary && boundaryPoints.length > 1 ? (
          <polyline
            points={boundaryPoints.map((point) => `${point.x},${point.y}`).join(" ")}
            fill="rgba(15, 118, 110, 0.10)"
            stroke="#0f766e"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="0.8"
          />
        ) : null}
        {showRadius ? (
          <circle
            cx={selectedPoint.x}
            cy={selectedPoint.y}
            r="7.5"
            fill="rgba(245, 158, 11, 0.16)"
            stroke="#d97706"
            strokeWidth="0.5"
          />
        ) : null}
      </svg>

      {places.map((place) => {
        const point = toPercent(place.coordinate, bounds);
        const isSelected = place.id === selected.id;
        return (
          <button
            key={place.id}
            type="button"
            onClick={() => onSelect(place.id)}
            className={`absolute z-10 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 shadow-md transition ${
              isSelected
                ? "border-white bg-[#0f766e] text-white ring-4 ring-[#0f766e]/25"
                : "border-white bg-[#163b53] text-white hover:bg-[#24516b]"
            }`}
            style={{ left: `${point.x}%`, top: `${point.y}%` }}
            aria-label={place.title}
          >
            <span className="h-2.5 w-2.5 rounded-full bg-current" />
          </button>
        );
      })}

      <div
        className="absolute z-20 max-w-[240px] -translate-x-1/2 rounded-lg border border-[#0f766e] bg-white px-3 py-2 shadow-lg"
        style={{ left: `${selectedPoint.x}%`, top: `calc(${selectedPoint.y}% + 26px)` }}
      >
        <p className="truncate text-sm font-bold text-[#142033]">{selected.title}</p>
        <p className="mt-0.5 truncate font-mono text-[11px] font-semibold text-[#607086]">
          {selected.legalDongCode}
        </p>
      </div>
    </div>
  );
}

export function mapBounds(
  places: AddressPlace[],
  center: Coordinate,
  extraPoints: Coordinate[] = [],
) {
  const coordinates = [...places.map((place) => place.coordinate), ...extraPoints];
  const latitudes = coordinates.map((point) => point.lat);
  const longitudes = coordinates.map((point) => point.lng);
  const maxLatDelta = Math.max(...latitudes.map((lat) => Math.abs(lat - center.lat)), 0.01);
  const maxLngDelta = Math.max(...longitudes.map((lng) => Math.abs(lng - center.lng)), 0.01);
  const latRadius = Math.max(maxLatDelta + 0.01, 0.02);
  const lngRadius = Math.max(maxLngDelta + 0.01, 0.02);
  return {
    minLat: center.lat - latRadius,
    maxLat: center.lat + latRadius,
    minLng: center.lng - lngRadius,
    maxLng: center.lng + lngRadius,
  };
}

export function toPercent(point: Coordinate, bounds: ReturnType<typeof mapBounds>) {
  const x = ((point.lng - bounds.minLng) / (bounds.maxLng - bounds.minLng)) * 100;
  const y = 100 - ((point.lat - bounds.minLat) / (bounds.maxLat - bounds.minLat)) * 100;
  return {
    x: clamp(x, 5, 95),
    y: clamp(y, 9, 91),
  };
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function hasRenderableCoordinate(place: AddressPlace) {
  const { lat, lng } = place.coordinate;
  return Number.isFinite(lat) && Number.isFinite(lng) && lat >= 32 && lat <= 39.5 && lng >= 123 && lng <= 132;
}
