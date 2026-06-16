"use client";

import { ExternalLink, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { type OpsArtifact, requestJson } from "@/lib/api";
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

export function PerfValidationSummary() {
  const [state, setState] = useState<SummaryState>(EMPTY);

  const load = useCallback(async () => {
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
      setState((cur) => ({ ...cur, error: err instanceof Error ? err.message : String(err) }));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const latestReport = state.reports[0] ?? null;
  const activeSet = state.matchSets.find((set) => set.state === "active") ?? null;

  return (
    <Panel
      title="성능·검증 요약 (read-only)"
      actions={
        <button className="icon-button" onClick={() => void load()} title="새로고침" type="button">
          <RefreshCw size={16} />
        </button>
      }
    >
      {state.error ? (
        <p className="wizard-error" role="alert">
          {state.error}
        </p>
      ) : null}

      <section className="perf-summary-section">
        <strong>성능 benchmark (latest vs baseline)</strong>
        {state.benchmarks.length === 0 ? (
          <p className="form-note">
            등록된 benchmark artifact가 없습니다. T-138/T-141/T-146 run을 `POST
            /v1/admin/ops/benchmark-artifacts`로 등록하면 여기에 비교가 노출됩니다.
          </p>
        ) : (
          <table className="table compact">
            <thead>
              <tr>
                <th>benchmark</th>
                <th>p95 (ms)</th>
                <th>p99 (ms)</th>
                <th>error_rate</th>
                <th>qps</th>
                <th>artifact</th>
              </tr>
            </thead>
            <tbody>
              {state.benchmarks.map((row) => (
                <tr key={row.group}>
                  <td>
                    <div className="perf-bench-name">
                      <span>{row.kind}</span>
                      {row.profile ? <small className="form-note">{row.profile}</small> : null}
                    </div>
                  </td>
                  <MetricCell metric="p95_ms" row={row} />
                  <MetricCell metric="p99_ms" row={row} />
                  <MetricCell digits={4} metric="error_rate" row={row} />
                  <MetricCell metric="qps" row={row} />
                  <td>
                    {row.storageUri ? (
                      <span className="perf-artifact-link" title={row.storageUri}>
                        <ExternalLink size={13} /> {row.latestArtifactId.slice(0, 8)}…
                      </span>
                    ) : (
                      `${row.latestArtifactId.slice(0, 8)}…`
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
            <Link className="perf-artifact-link" href="/admin/consistency">
              <ExternalLink size={13} /> 상세
            </Link>
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
  return (
    <td>
      {value == null ? (
        "—"
      ) : (
        <div className="perf-metric-cell">
          <span>{value.toFixed(digits)}</span>
          {delta != null && delta !== 0 ? (
            <small className={`perf-delta ${deltaTone(metric, delta)}`}>
              {delta > 0 ? "▲" : "▼"}
              {Math.abs(delta).toFixed(digits)}
            </small>
          ) : null}
        </div>
      )}
    </td>
  );
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "-";
  return value.slice(0, 19).replace("T", " ");
}
