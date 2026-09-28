"use client";

import { useCallback, useEffect, useState } from "react";
import { MetricTile } from "@/components/admin/shared/MetricTile";
import { RefreshButton } from "@/components/admin/shared/RefreshButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/Panel";
import { CacheMetrics, getErrorMessage, requestJson } from "@/lib/api";

// T-310: 기본 조회는 geo_cache를 scan하지 않는 통계 기반 추정치다. 전수 집계는 공용 DB에
// 부담이 커서 "정확히 세기"를 눌렀을 때만 요청한다(API statement_timeout이 상한).
const ESTIMATE_PATH = "/admin/cache/metrics";
const EXACT_PATH = "/admin/cache/metrics?exact=true";

export function CachePanel() {
  const [metrics, setMetrics] = useState<CacheMetrics | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (path: string) => {
    setBusy(true);
    try {
      setMetrics(await requestJson<CacheMetrics>(path));
      setError(null);
    } catch (loadError) {
      setError(getErrorMessage(loadError));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load(ESTIMATE_PATH);
  }, [load]);

  const loading = metrics === null && error === null;
  const exact = metrics?.exact === true;

  return (
    <Panel
      title="캐시 지표"
      badges={
        metrics ? (
          <>
            <Badge tone={metrics.enabled ? "ok" : "neutral"}>
              {metrics.enabled ? "캐시 사용 중" : "캐시 비활성"}
            </Badge>
            <Badge tone={exact ? "info" : "neutral"}>{exact ? "정확 집계" : "추정치"}</Badge>
          </>
        ) : null
      }
      actions={
        <>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => void load(EXACT_PATH)}
          >
            정확히 세기
          </Button>
          <RefreshButton busy={busy} onClick={() => void load(ESTIMATE_PATH)} />
        </>
      }
    >
      {error ? (
        <Alert role="alert" variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="grid three">
        <MetricTile
          hint={exact ? "캐시에 저장된 항목 수" : "캐시 항목 수 (DB 통계 추정)"}
          label="entries"
          loading={loading}
          value={(metrics?.entries ?? 0).toLocaleString()}
        />
        <MetricTile
          hint={exact ? "현재 항목의 적중 합계" : "통계 초기화 이후 적중 누적 (추정)"}
          label="hits"
          loading={loading}
          value={(metrics?.hits ?? 0).toLocaleString()}
        />
        <MetricTile
          hint="만료됐지만 아직 남아 있는 항목 수"
          label="expired"
          loading={loading}
          value={(metrics?.expired ?? 0).toLocaleString()}
        />
      </div>
    </Panel>
  );
}
