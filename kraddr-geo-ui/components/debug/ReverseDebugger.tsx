"use client";

import { MousePointer2 } from "lucide-react";
import { FormEvent, useState } from "react";
import { CoordinateMap } from "@/components/kakao/CoordinateMap";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { requestJson } from "@/lib/api";

export function ReverseDebugger() {
  const [x, setX] = useState("127.028601");
  const [y, setY] = useState("37.500344");
  const [radius, setRadius] = useState("200");
  const [result, setResult] = useState<unknown>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const params = new URLSearchParams({ x, y, radius_m: radius, type: "both" });
      setResult(await requestJson(`/address/reverse?${params}`));
    } catch (error) {
      setResult({ error: error instanceof Error ? error.message : String(error) });
    }
  }

  return (
    <div className="grid two">
      <Panel title="좌표 입력">
        <form className="form-grid" onSubmit={submit}>
          <div className="grid two">
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
      <Panel title="역지오코딩 결과">
        <div className="grid">
          <CoordinateMap
            point={{ x: Number(x), y: Number(y) }}
            onClick={(point) => {
              setX(point.x.toFixed(6));
              setY(point.y.toFixed(6));
            }}
          />
          <JsonBlock value={result ?? { status: "READY" }} />
        </div>
      </Panel>
    </div>
  );
}
