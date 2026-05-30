"use client";

import { LocateFixed } from "lucide-react";
import { FormEvent, useState } from "react";
import { LazyCoordinateMap as CoordinateMap } from "@/components/vworld/LazyCoordinateMap";
import type {
  Coordinate,
  CoordinateBBox,
  MapGeometryOverlay
} from "@/components/vworld/CoordinateMap";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { postJson } from "@/lib/api";
import { geocodeFormSchema } from "@/lib/schemas";
import type { components } from "@/types/api.gen";

type GeocodeV2Input = components["schemas"]["GeocodeV2Input"];
type GeocodeV2Response = components["schemas"]["GeocodeV2Response"];

export function GeocodeDebugger() {
  const [address, setAddress] = useState("서울특별시 강남구 테헤란로 152");
  const [type, setType] = useState("road");
  const [fallback, setFallback] = useState("none");
  const [includeGeometry, setIncludeGeometry] = useState(true);
  const [result, setResult] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = geocodeFormSchema.safeParse({ address, type, fallback });
    if (!parsed.success) {
      setResult({ error: parsed.error.issues[0]?.message ?? "주소 입력을 확인하세요" });
      return;
    }
    setLoading(true);
    try {
      const body: GeocodeV2Input =
        parsed.data.type === "parcel"
          ? {
              jibun_address: parsed.data.address,
              fallback: parsed.data.fallback,
              include_geometry: includeGeometry,
              limit: 10
            }
          : {
              road_address: parsed.data.address,
              fallback: parsed.data.fallback,
              include_geometry: includeGeometry,
              limit: 10
            };
      setResult(await postJson<GeocodeV2Response>("/v2/geocode", body));
    } catch (error) {
      setResult({ error: error instanceof Error ? error.message : String(error) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="debug-map-layout">
      <div className="debug-control-stack">
        <Panel title="주소 입력">
          <form className="form-grid" onSubmit={submit}>
            <div className="field">
              <label htmlFor="address">address</label>
              <input id="address" value={address} onChange={(e) => setAddress(e.target.value)} />
            </div>
            <div className="form-field-grid two">
              <div className="field">
                <label htmlFor="type">type</label>
                <select id="type" value={type} onChange={(e) => setType(e.target.value)}>
                  <option value="road">road</option>
                  <option value="parcel">parcel</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="fallback">fallback</label>
                <select
                  id="fallback"
                  value={fallback}
                  onChange={(e) => setFallback(e.target.value)}
                >
                  <option value="none">none</option>
                  <option value="api">api</option>
                </select>
              </div>
            </div>
            <label className="checkbox-row" htmlFor="include-geometry">
              <input
                checked={includeGeometry}
                id="include-geometry"
                onChange={(e) => setIncludeGeometry(e.target.checked)}
                type="checkbox"
              />
              <span>include_geometry</span>
            </label>
            <button className="button" disabled={loading} type="submit">
              <LocateFixed size={16} />
              실행
            </button>
          </form>
        </Panel>
        <Panel title="응답">
          <JsonBlock value={result ?? { status: "READY" }} />
        </Panel>
      </div>
      <Panel title="지도">
        <div className="debug-map">
          <CoordinateMap
            bbox={extractBBox(result)}
            geometry={extractGeometry(result)}
            point={extractPoint(result)}
          />
        </div>
      </Panel>
    </div>
  );
}

function firstCandidate(result: unknown): unknown {
  if (!result || typeof result !== "object") return null;
  const candidates = (result as { candidates?: unknown }).candidates;
  return Array.isArray(candidates) ? candidates[0] : null;
}

function extractPoint(result: unknown): Coordinate | null {
  const candidate = firstCandidate(result);
  if (!candidate || typeof candidate !== "object") return null;
  const point = (candidate as { point?: { x?: unknown; y?: unknown } | null }).point;
  return typeof point?.x === "number" && typeof point.y === "number"
    ? { x: point.x, y: point.y }
    : null;
}

function extractBBox(result: unknown): CoordinateBBox | null {
  const candidate = firstCandidate(result);
  if (!candidate || typeof candidate !== "object") return null;
  const bbox = (candidate as { bbox?: Partial<CoordinateBBox> | null }).bbox;
  return typeof bbox?.min_lon === "number" &&
    typeof bbox.min_lat === "number" &&
    typeof bbox.max_lon === "number" &&
    typeof bbox.max_lat === "number"
    ? {
        min_lon: bbox.min_lon,
        min_lat: bbox.min_lat,
        max_lon: bbox.max_lon,
        max_lat: bbox.max_lat
      }
    : null;
}

function extractGeometry(result: unknown): MapGeometryOverlay | null {
  const candidate = firstCandidate(result);
  if (!candidate || typeof candidate !== "object") return null;
  const geometry = (
    candidate as {
      geometry?: { kind?: unknown; geojson?: unknown } | null;
    }
  ).geometry;
  if (!geometry || typeof geometry !== "object") return null;
  const geojson = geometry.geojson;
  if (!isGeoJsonGeometry(geojson)) return null;
  return {
    kind: typeof geometry.kind === "string" ? geometry.kind : null,
    geojson
  };
}

function isGeoJsonGeometry(value: unknown): value is GeoJSON.Geometry {
  if (!value || typeof value !== "object") return false;
  const type = (value as { type?: unknown }).type;
  return (
    type === "Point" ||
    type === "MultiPoint" ||
    type === "LineString" ||
    type === "MultiLineString" ||
    type === "Polygon" ||
    type === "MultiPolygon" ||
    type === "GeometryCollection"
  );
}
