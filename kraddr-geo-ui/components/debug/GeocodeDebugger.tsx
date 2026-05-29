"use client";

import { LocateFixed } from "lucide-react";
import { FormEvent, useState } from "react";
import { LazyCoordinateMap as CoordinateMap } from "@/components/vworld/LazyCoordinateMap";
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
              limit: 10
            }
          : {
              road_address: parsed.data.address,
              fallback: parsed.data.fallback,
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
                <option value="none">none</option>
                <option value="api">api</option>
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
  const point = (result as { candidates?: { point?: { x?: unknown; y?: unknown } | null }[] })
    .candidates?.[0]?.point;
  return typeof point?.x === "number" && typeof point.y === "number"
    ? { x: point.x, y: point.y }
    : null;
}
