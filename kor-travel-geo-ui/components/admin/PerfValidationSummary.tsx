"use client";

import { ExternalLink } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DocumentNavLink } from "@/components/layout/DocumentNavLink";
import { HelpTip } from "@/components/admin/shared/HelpTip";
import { RefreshButton } from "@/components/admin/shared/RefreshButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { type VirtualColumn, VirtualTable } from "@/components/ui/VirtualTable";
import { getErrorMessage, type OpsArtifact, requestJson } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import {
  type BenchmarkMetrics,
  type BenchmarkSummaryRow,
  deltaTone,
  summarizeBenchmarkArtifacts
} from "@/lib/perf-summary";
import {
  matchSetStateLabels,
  type ConsistencyReportSummary,
  type SourceMatchSet,
  sourceFilesPaths
} from "@/lib/source-files";

/**
 * T-222: read-only 성능·검증 artifact 요약. benchmark run(T-265)의 latest-vs-baseline
 * p95/p99·error_rate 비교, C1~C17 consistency 최신 상태, source match set 상태를 한 화면에
 * 비교 노출한다. 모든 데이터는 읽기 전용이며 backup/restore artifact는 백업 탭이 담당한다.
 */
type SummaryState = {
  benchmarks: BenchmarkSummaryRow[];
  reports: ConsistencyReportSummary[];
  matchSets: SourceMatchSet[];
  error: string | null;
};

const EMPTY: SummaryState = { benchmarks: [], reports: [], matchSets: [], error: null };

const BENCHMARK_COLUMNS: VirtualColumn<BenchmarkSummaryRow>[] = [
  {
    key: "benchmark",
    header: "benchmark",
    cell: (row) => (
      <div className="perf-bench-name">
        <span>{row.kind}</span>
        {row.profile ? <small className="form-note">{row.profile}</small> : null}
        {row.baselineUnavailable ? (
          <small className="form-note warn">
            baseline 범위 밖
            <HelpTip label="baseline 범위 밖 도움말">
              명시된 baseline artifact가 조회 범위(최근 50건) 밖이라 delta 비교를 생략했습니다.
            </HelpTip>
          </small>
        ) : null}
      </div>
    )
  },
  { key: "p95", header: "p95 (ms)", cell: (row) => <MetricCell metric="p95_ms" row={row} /> },
  { key: "p99", header: "p99 (ms)", cell: (row) => <MetricCell metric="p99_ms" row={row} /> },
  {
    key: "error_rate",
    header: "error_rate",
    cell: (row) => <MetricCell digits={4} metric="error_rate" row={row} />
  },
  { key: "qps", header: "qps", cell: (row) => <MetricCell metric="qps" row={row} /> },
  {
    // storage_uri는 서버 로컬 경로라 클릭 가능한 link가 아니다 — id 축약을 보여 주고
    // 전체 id·경로는 Tooltip으로 노출한다(키보드/터치 접근 가능, Codex #282 후속).
    key: "artifact",
    header: "artifact",
    cell: (row) => (
      <Tooltip>
        <TooltipTrigger className="perf-artifact-id cursor-help border-0 bg-transparent p-0">
          {row.latestArtifactId.slice(0, 8)}…
        </TooltipTrigger>
        <TooltipContent>
          <p className="m-0">artifact: {row.latestArtifactId}</p>
          {row.storageUri ? <p className="m-0">{row.storageUri}</p> : null}
        </TooltipContent>
      </Tooltip>
    )
  }
];

export function PerfValidationSummary() {
  const [state, setState] = useState<SummaryState>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [artifacts, reports, matchSets] = await Promise.all([
        requestJson<OpsArtifact[]>("/admin/ops/artifacts?artifact_type=benchmark&limit=50"),
        requestJson<ConsistencyReportSummary[]>(sourceFilesPaths.consistency()),
        requestJson<SourceMatchSet[]>(sourceFilesPaths.matchSets())
      ]);
      setState({
        benchmarks: summarizeBenchmarkArtifacts(artifacts),
        reports,
        matchSets,
        error: null
      });
    } catch (err) {
      setState((cur) => ({ ...cur, error: getErrorMessage(err) }));
    } finally {
      setBusy(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const latestReport = state.reports[0] ?? null;
  const activeSet = state.matchSets.find((set) => set.state === "active") ?? null;

  return (
    <Panel
      title="성능·검증 요약"
      badges={<Badge tone="neutral">읽기 전용</Badge>}
      actions={<RefreshButton busy={busy} iconOnly onClick={() => void load()} />}
    >
      {state.error ? (
        <Alert role="alert" variant="destructive">
          <AlertDescription>{state.error}</AlertDescription>
        </Alert>
      ) : null}

      {loading ? (
        <div className="grid gap-2" aria-busy="true">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : (
        <>
          <section className="perf-summary-section">
            <strong>성능 benchmark (latest vs baseline)</strong>
            {state.benchmarks.length === 0 ? (
              <p className="form-note">
                등록된 benchmark artifact가 없습니다.
                <HelpTip label="benchmark 등록 방법 도움말">
                  benchmark run(T-138/T-141/T-146) 결과를{" "}
                  <code>POST /v1/admin/ops/benchmark-artifacts</code>로 등록하면 여기에 비교가
                  노출됩니다.
                </HelpTip>
              </p>
            ) : (
              <VirtualTable
                as="table"
                columns={BENCHMARK_COLUMNS}
                compact
                rowKey={(row) => row.group}
                rows={state.benchmarks}
              />
            )}
          </section>

          <section className="perf-summary-section">
            <strong>C1~C17 검증 (최신 정합성 리포트)</strong>
            {latestReport ? (
              <p className="perf-validation-line">
                <StatusBadge value={latestReport.severity_max} />{" "}
                <span>
                  {latestReport.scope} · {formatTimestamp(latestReport.finished_at)} ·{" "}
                  {latestReport.generated_by}
                </span>{" "}
                <DocumentNavLink className="perf-artifact-link" href="/admin/consistency">
                  <ExternalLink size={13} /> 상세
                </DocumentNavLink>
              </p>
            ) : (
              <p className="form-note">정합성 리포트가 없습니다.</p>
            )}
          </section>

          <section className="perf-summary-section">
            <strong>source match set 상태</strong>
            {state.matchSets.length === 0 ? (
              <p className="form-note">매칭 세트가 없습니다.</p>
            ) : (
              <p className="perf-validation-line">
                {activeSet ? (
                  <>
                    <span>활성: {activeSet.name}</span>{" "}
                    <StatusBadge value={matchSetStateLabels[activeSet.state]} />
                    {activeSet.integrity_alert ? (
                      <StatusBadge tone="error" value="무결성 경보" />
                    ) : null}
                  </>
                ) : (
                  <span>활성 매칭 세트가 없습니다.</span>
                )}{" "}
                <small className="form-note">총 {state.matchSets.length}개</small>
              </p>
            )}
          </section>
        </>
      )}
    </Panel>
  );
}

function MetricCell({
  metric,
  row,
  digits = 1
}: {
  metric: keyof BenchmarkMetrics;
  row: BenchmarkSummaryRow;
  digits?: number;
}) {
  const value = row.latest[metric];
  const delta = row.deltas[metric];
  if (value == null) {
    return <>—</>;
  }
  return (
    <div className="perf-metric-cell">
      <span>{value.toFixed(digits)}</span>
      {delta != null && delta !== 0 ? (
        <small className={`perf-delta ${deltaTone(metric, delta)}`}>
          {delta > 0 ? "▲" : "▼"}
          {Math.abs(delta).toFixed(digits)}
        </small>
      ) : null}
    </div>
  );
}
