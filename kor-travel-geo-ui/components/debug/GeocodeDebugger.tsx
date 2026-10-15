"use client";

import { LocateFixed } from "lucide-react";
import { FormEvent, useEffect, useReducer, useRef } from "react";
import { LazyCoordinateMap as CoordinateMap } from "@/components/vworld/LazyCoordinateMap";
import type {
  Coordinate,
  CoordinateBBox,
  MapGeometryOverlay
} from "@/components/vworld/CoordinateMap";
import { CandidateAddressSummary } from "@/components/debug/CandidateAddressSummary";
import { extractCandidates } from "@/lib/candidate-addresses";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { apiErrorResult, postPublicJson, resultErrorMessage } from "@/lib/api";
import { geocodeFormSchema } from "@/lib/schemas";
import { useVWorldApiKey } from "@/lib/vworld-key";
import type { components } from "@/types/api.gen";

type GeocodeV2Input = components["schemas"]["GeocodeV2Input-Input"];
type GeocodeV2Response = components["schemas"]["GeocodeV2Response"];

type GeocodeDebuggerState = {
  address: string;
  type: string;
  fallback: string;
  includeGeometry: boolean;
  result: unknown;
  loading: boolean;
  notice: string;
};

type GeocodeDebuggerAction = {
  patch: Partial<GeocodeDebuggerState>;
  type: "merge";
};

const initialGeocodeDebuggerState: GeocodeDebuggerState = {
  address: "서울특별시 강남구 테헤란로 152",
  type: "road",
  fallback: "none",
  includeGeometry: true,
  result: null,
  loading: false,
  notice: ""
};

export function GeocodeDebugger() {
  const [state, dispatch] = useReducer(geocodeDebuggerReducer, initialGeocodeDebuggerState);
  const { apiKey } = useVWorldApiKey();
  const { address, type, fallback, includeGeometry, result, loading, notice } = state;
  const requestVersion = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);
  const errorMessage = resultErrorMessage(result);

  useEffect(() => {
    const version = requestVersion;
    const request = activeRequest;
    return () => {
      ++version.current;
      request.current?.abort();
      request.current = null;
    };
  }, []);

  function mergeState(patch: Partial<GeocodeDebuggerState>) {
    dispatch({ type: "merge", patch });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = geocodeFormSchema.safeParse({ address, type, fallback });
    if (!parsed.success) {
      mergeState({ result: { error: parsed.error.issues[0]?.message ?? "주소 입력을 확인하세요" } });
      return;
    }
    const version = ++requestVersion.current;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    mergeState({ loading: true, result: null, notice: "" });
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
      const response = await postPublicJson<GeocodeV2Response>("/v2/geocode", body, apiKey, controller.signal);
      if (version === requestVersion.current && !controller.signal.aborted) {
        mergeState({ result: response });
      }
    } catch (error) {
      if (version === requestVersion.current && !controller.signal.aborted) {
        mergeState({ result: apiErrorResult(error) });
      }
    } finally {
      if (version === requestVersion.current && !controller.signal.aborted) {
        activeRequest.current = null;
        mergeState({ loading: false });
      }
    }
  }

  function cancel() {
    ++requestVersion.current;
    activeRequest.current?.abort();
    activeRequest.current = null;
    mergeState({ loading: false, notice: "요청을 취소했습니다. 다시 실행할 수 있습니다." });
  }

  return (
    <div className="debug-map-layout">
      <div className="debug-control-stack">
        <Panel title="주소 입력">
          <form aria-busy={loading} className="form-grid" onSubmit={submit}>
            <div className="field">
              <label htmlFor="address">address</label>
              <input
                id="address"
                disabled={loading}
                value={address}
                onChange={(e) => mergeState({ address: e.target.value })}
              />
            </div>
            <div className="form-field-grid two">
              <div className="field">
                <label htmlFor="type">type</label>
                <select
                  id="type"
                  disabled={loading}
                  value={type}
                  onChange={(e) => mergeState({ type: e.target.value })}
                >
                  <option value="road">road</option>
                  <option value="parcel">parcel</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="fallback">fallback</label>
                <select
                  id="fallback"
                  disabled={loading}
                  value={fallback}
                  onChange={(e) => mergeState({ fallback: e.target.value })}
                >
                  <option value="none">none</option>
                  <option value="api">api</option>
                </select>
              </div>
            </div>
            <label className="checkbox-row" htmlFor="include-geometry">
              <input
                checked={includeGeometry}
                disabled={loading}
                id="include-geometry"
                onChange={(e) => mergeState({ includeGeometry: e.target.checked })}
                type="checkbox"
              />
              <span>include_geometry</span>
            </label>
            <button className="button" disabled={loading} type="submit">
              <LocateFixed size={16} />
              실행
            </button>
            {loading ? <button className="button" onClick={cancel} type="button">취소</button> : null}
          </form>
        </Panel>
        <Panel title="응답">
          {notice ? <p role="status">{notice}</p> : null}
          {errorMessage ? (
            <Alert role="alert" variant="destructive">
              <AlertDescription>{errorMessage}</AlertDescription>
            </Alert>
          ) : null}
          <CandidateAddressSummary candidates={extractCandidates(result)} />
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

function geocodeDebuggerReducer(
  state: GeocodeDebuggerState,
  action: GeocodeDebuggerAction
): GeocodeDebuggerState {
  return { ...state, ...action.patch };
}

function firstCandidate(result: unknown): unknown {
  return extractCandidates(result)[0] ?? null;
}

function extractPoint(result: unknown): Coordinate | null {
  const candidate = firstCandidate(result);
  if (!candidate || typeof candidate !== "object") return null;
  // v2 candidate point is { lon, lat } (ADR-060 §6); the map uses internal { x, y } (x=lon).
  const point = (candidate as { point?: { lon?: unknown; lat?: unknown } | null }).point;
  return typeof point?.lon === "number" && typeof point.lat === "number"
    ? { x: point.lon, y: point.lat }
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
