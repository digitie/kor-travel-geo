"use client";

import { MousePointer2 } from "lucide-react";
import { FormEvent, useState } from "react";
import { LazyCoordinateMap as CoordinateMap } from "@/components/vworld/LazyCoordinateMap";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { postJson } from "@/lib/api";
import { reverseFormSchema } from "@/lib/schemas";
import type { components } from "@/types/api.gen";

type ReverseV2Input = components["schemas"]["ReverseV2Input"];
type ReverseV2Response = components["schemas"]["ReverseV2Response"];

export function ReverseDebugger() {
  const [x, setX] = useState("127.028601");
  const [y, setY] = useState("37.500344");
  const [radius, setRadius] = useState("200");
  const [result, setResult] = useState<unknown>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = reverseFormSchema.safeParse({ x, y, radius_m: radius });
    if (!parsed.success) {
      setResult({ error: parsed.error.issues[0]?.message ?? "좌표 입력을 확인하세요" });
      return;
    }
    try {
      const body: ReverseV2Input = {
        lon: parsed.data.x,
        lat: parsed.data.y,
        crs: "EPSG:4326",
        include_region: true,
        include_zipcode: true,
        radius_m: parsed.data.radius_m
      };
      setResult(await postJson<ReverseV2Response>("/v2/reverse", body));
    } catch (error) {
      setResult({ error: error instanceof Error ? error.message : String(error) });
    }
  }

  return (
    <div className="debug-map-layout">
      <div className="debug-control-stack">
        <Panel title="좌표 입력">
          <form className="form-grid" onSubmit={submit}>
            <div className="form-field-grid two">
              <div className="field">
                <label htmlFor="x">lon</label>
                <input id="x" value={x} onChange={(e) => setX(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="y">lat</label>
                <input id="y" value={y} onChange={(e) => setY(e.target.value)} />
              </div>
            </div>
            <div className="field">
              <label htmlFor="radius">radius_m</label>
              <input id="radius" value={radius} onChange={(e) => setRadius(e.target.value)} />
            </div>
            <button className="button" type="submit">
              <MousePointer2 size={16} />
              조회
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
            point={previewPoint(x, y)}
            onClick={(point) => {
              setX(point.x.toFixed(6));
              setY(point.y.toFixed(6));
            }}
          />
        </div>
      </Panel>
    </div>
  );
}

function previewPoint(x: string, y: string): { x: number; y: number } | null {
  const point = { x: Number(x), y: Number(y) };
  return Number.isFinite(point.x) &&
    Number.isFinite(point.y) &&
    point.x >= 123 &&
    point.x <= 132 &&
    point.y >= 32 &&
    point.y <= 39
    ? point
    : null;
}
