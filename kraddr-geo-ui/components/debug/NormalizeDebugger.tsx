"use client";

import { Braces } from "lucide-react";
import { FormEvent, useState } from "react";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { postJson } from "@/lib/api";

export function NormalizeDebugger() {
  const [address, setAddress] = useState("서울 강남구 테헤란로 152");
  const [result, setResult] = useState<unknown>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      setResult(await postJson("/admin/normalize", { address }));
    } catch (error) {
      setResult({ error: error instanceof Error ? error.message : String(error) });
    }
  }

  return (
    <div className="grid two">
      <Panel title="정규화 입력">
        <form className="form-grid" onSubmit={submit}>
          <div className="field">
            <label htmlFor="normalize-address">address</label>
            <input
              id="normalize-address"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
            />
          </div>
          <button className="button" type="submit">
            <Braces size={16} />
            토큰화
          </button>
        </form>
      </Panel>
      <Panel title="정규화 결과">
        <JsonBlock value={result ?? { status: "READY" }} />
      </Panel>
    </div>
  );
}
