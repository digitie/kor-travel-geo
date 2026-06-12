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
    return <CoordinateMapSkeleton />;
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
