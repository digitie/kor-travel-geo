"use client";

import { LocateFixed } from "lucide-react";
import { FormEvent, useState } from "react";
import { CoordinateMap } from "@/components/kakao/CoordinateMap";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { requestJson } from "@/lib/api";

export function GeocodeDebugger() {
  const [address, setAddress] = useState("서울특별시 강남구 테헤란로 152");
  const [type, setType] = useState("road");
  const [fallback, setFallback] = useState("local_only");
  const [result, setResult] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    try {
      const params = new URLSearchParams({ address, type, fallback });
      setResult(await requestJson(`/address/geocode?${params}`));
    } catch (error) {
      setResult({ error: error instanceof Error ? error.message : String(error) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid two">
      <Panel title="주소 입력">
        <form className="form-grid" onSubmit={submit}>
          <div className="field">
            <label htmlFor="address">address</label>
            <input id="address" value={address} onChange={(e) => setAddress(e.target.value)} />
          </div>
          <div className="grid two">
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
                <option value="local_only">local_only</option>
                <option value="api">api</option>
                <option value="off">off</option>
              </select>
            </div>
          </div>
          <button className="button" disabled={loading} type="submit">
            <LocateFixed size={16} />
            실행
          </button>
        </form>
      </Panel>
      <Panel title="응답과 지도">
        <div className="grid">
          <CoordinateMap point={extractPoint(result)} />
          <JsonBlock value={result ?? { status: "READY" }} />
        </div>
      </Panel>
    </div>
  );
}

function extractPoint(result: unknown): { x: number; y: number } | null {
  if (!result || typeof result !== "object") return null;
  const point = (result as { result?: { point?: { x?: unknown; y?: unknown } } }).result?.point;
  return typeof point?.x === "number" && typeof point.y === "number"
    ? { x: point.x, y: point.y }
    : null;
}
