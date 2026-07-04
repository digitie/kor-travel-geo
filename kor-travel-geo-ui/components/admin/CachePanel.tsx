"use client";

import { useCallback, useEffect, useState } from "react";
import { MetricTile } from "@/components/admin/shared/MetricTile";
import { RefreshButton } from "@/components/admin/shared/RefreshButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/Panel";
import { CacheMetrics, getErrorMessage, requestJson } from "@/lib/api";

export function CachePanel() {
  const [metrics, setMetrics] = useState<CacheMetrics | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      setMetrics(await requestJson<CacheMetrics>("/admin/cache/metrics"));
      setError(null);
    } catch (loadError) {
      setError(getErrorMessage(loadError));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const loading = metrics === null && error === null;

  return (
    <Panel
      title="캐시 지표"
      badges={
        metrics ? (
          <Badge tone={metrics.enabled ? "ok" : "neutral"}>
            {metrics.enabled ? "캐시 사용 중" : "캐시 비활성"}
          </Badge>
        ) : null
      }
      actions={<RefreshButton busy={busy} onClick={() => void load()} />}
    >
      {error ? (
        <Alert role="alert" variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="grid three">
        <MetricTile
          hint="캐시에 저장된 항목 수"
          label="entries"
          loading={loading}
          value={(metrics?.entries ?? 0).toLocaleString()}
        />
        <MetricTile
          hint="캐시 적중 누적 횟수"
          label="hits"
          loading={loading}
          value={(metrics?.hits ?? 0).toLocaleString()}
        />
        <MetricTile
          hint="만료로 제거된 항목 누적"
          label="expired"
          loading={loading}
          value={(metrics?.expired ?? 0).toLocaleString()}
        />
      </div>
    </Panel>
  );
}
