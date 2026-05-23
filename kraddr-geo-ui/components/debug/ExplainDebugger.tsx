"use client";

import { Play } from "lucide-react";
import { FormEvent, useState } from "react";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { postJson } from "@/lib/api";

export function ExplainDebugger() {
  const [sql, setSql] = useState("SELECT * FROM mv_geocode_target LIMIT 5");
  const [analyze, setAnalyze] = useState(false);
  const [buffers, setBuffers] = useState(false);
  const [result, setResult] = useState<unknown>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      setResult(await postJson("/admin/explain", { sql, analyze, buffers }));
    } catch (error) {
      setResult({ error: error instanceof Error ? error.message : String(error) });
    }
  }

  return (
    <div className="grid two">
      <Panel title="SQL">
        <form className="form-grid" onSubmit={submit}>
          <div className="field">
            <label htmlFor="sql">SELECT / WITH</label>
            <textarea id="sql" value={sql} onChange={(e) => setSql(e.target.value)} />
          </div>
          <label>
            <input
              checked={analyze}
              onChange={(e) => setAnalyze(e.target.checked)}
              type="checkbox"
            />{" "}
            ANALYZE
          </label>
          <label>
            <input
              checked={buffers}
              onChange={(e) => setBuffers(e.target.checked)}
              type="checkbox"
            />{" "}
            BUFFERS
          </label>
          <button className="button" type="submit">
            <Play size={16} />
            EXPLAIN
          </button>
        </form>
      </Panel>
      <Panel title="Plan JSON">
        <JsonBlock value={result ?? { status: "READY" }} />
      </Panel>
    </div>
  );
}
