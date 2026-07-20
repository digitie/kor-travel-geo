"use client";

import dynamic from "next/dynamic";
import type {
  Coordinate,
  CoordinateBBox,
  MapGeometryOverlay
} from "@/components/vworld/CoordinateMap";
import type { VWorldLayerType } from "@/lib/vworld";

export type CoordinateMapProps = {
  point: Coordinate | null;
  bbox?: CoordinateBBox | null;
  geometry?: MapGeometryOverlay | null;
  onClick?: (point: Coordinate) => void;
  layerType?: VWorldLayerType;
};

const DynamicCoordinateMap = dynamic<CoordinateMapProps>(
  () => import("@/components/vworld/CoordinateMap").then((mod) => mod.CoordinateMap),
  {
    ssr: false,
    loading: () => <CoordinateMapSkeleton />
  }
);

export function LazyCoordinateMap(props: CoordinateMapProps) {
  if (!props.point && !props.bbox && !props.geometry) {
    return <CoordinateMapIdle />;
  }
  return <DynamicCoordinateMap {...props} />;
}

export function CoordinateMapSkeleton() {
  return (
    <div aria-label="VWorld 지도 로딩" className="vworld-map-shell vworld-map-skeleton">
      <span>지도 로딩 중</span>
    </div>
  );
}

// Distinct from CoordinateMapSkeleton: this is the idle "no coordinate to show yet" state
// (nothing is loading), not the transient bundle/tile-load state. Sharing the "지도 로딩 중"
// copy for both made an idle map look permanently stuck.
export function CoordinateMapIdle() {
  return (
    <div aria-label="VWorld 지도 대기" className="vworld-map-shell vworld-map-skeleton">
      <span>좌표가 없습니다 — 조회 후 지도가 표시됩니다</span>
    </div>
  );
}
