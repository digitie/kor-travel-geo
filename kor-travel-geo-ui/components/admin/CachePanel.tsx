"use client";

import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { CacheMetrics, requestJson } from "@/lib/api";

export function CachePanel() {
  const [metrics, setMetrics] = useState<CacheMetrics | null>(null);

  async function load() {
    setMetrics(await requestJson<CacheMetrics>("/admin/cache/metrics"));
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <Panel
      title="Cache Metrics"
      actions={
        <button className="button secondary" onClick={load} type="button">
          <RefreshCw size={16} />
          새로고침
        </button>
      }
    >
      <div className="grid three">
        <Metric label="entries" value={metrics?.entries ?? 0} />
        <Metric label="hits" value={metrics?.hits ?? 0} />
        <Metric label="expired" value={metrics?.expired ?? 0} />
      </div>
    </Panel>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <strong>{value.toLocaleString()}</strong>
      <span>{label}</span>
    </div>
  );
}
