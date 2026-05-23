"use client";

import { Map, MapMarker, useKakaoLoader } from "react-kakao-maps-sdk";

export type Coordinate = {
  x: number;
  y: number;
};

const DEFAULT_CENTER = { x: 126.978, y: 37.5665 };

export function CoordinateMap({
  point,
  onClick
}: {
  point: Coordinate | null;
  onClick?: (point: Coordinate) => void;
}) {
  const appkey = process.env.NEXT_PUBLIC_KAKAO_JS_KEY;
  if (!appkey) {
    return <CoordinateFallback point={point} note="Kakao JS 키 미설정" />;
  }
  return <LoadedCoordinateMap appkey={appkey} point={point} onClick={onClick} />;
}

function LoadedCoordinateMap({
  appkey,
  point,
  onClick
}: {
  appkey: string;
  point: Coordinate | null;
  onClick?: (point: Coordinate) => void;
}) {
  const [loading, error] = useKakaoLoader({ appkey, libraries: ["services"] });
  if (loading) {
    return <CoordinateFallback point={point} note="지도 로딩 중" />;
  }
  if (error) {
    return <CoordinateFallback point={point} note="지도 로딩 실패" />;
  }

  const center = point ?? DEFAULT_CENTER;
  return (
    <Map
      center={{ lat: center.y, lng: center.x }}
      className="kakao-map"
      level={3}
      onClick={
        onClick
          ? (_map, mouseEvent) => {
              const latLng = mouseEvent.latLng;
              onClick({ x: latLng.getLng(), y: latLng.getLat() });
            }
          : undefined
      }
    >
      {point ? <MapMarker position={{ lat: point.y, lng: point.x }} /> : null}
    </Map>
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
