"use client";

import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { requestJson } from "@/lib/api";

export function LogsPanel() {
  const [lines, setLines] = useState<string[]>([]);

  async function load() {
    setLines(await requestJson<string[]>("/admin/logs?limit=200"));
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <Panel
      title="Log Tail"
      actions={
        <button className="button secondary" onClick={load} type="button">
          <RefreshCw size={16} />
          새로고침
        </button>
      }
    >
      <pre className="json-box">{lines.join("\n") || "NO LOGS"}</pre>
    </Panel>
  );
}
