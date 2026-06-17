"use client";

import { Play, RefreshCw, ShieldCheck } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { PerfValidationSummary } from "@/components/admin/PerfValidationSummary";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { type VirtualColumn, VirtualTable } from "@/components/ui/VirtualTable";
import {
  AuditEvent,
  DatasetSnapshot,
  MaintenanceWindow,
  OpsArtifact,
  PgStatStatementSnapshot,
  ServingRelease,
  TableStatsSnapshot,
  postJson,
  requestJson
} from "@/lib/api";
import { formatBytes } from "@/lib/format";

const maintenanceKinds = [
  "full_load",
  "restore",
  "schema_migration",
  "mv_refresh",
  "read_only",
  "exclusive"
] as const;

type MaintenanceWindowKind = (typeof maintenanceKinds)[number];
type OpsDataState = {
  artifacts: OpsArtifact[];
  auditEvents: AuditEvent[];
  lastResult: unknown;
  pgStats: PgStatStatementSnapshot[];
  releases: ServingRelease[];
  snapshots: DatasetSnapshot[];
  stats: TableStatsSnapshot[];
  windows: MaintenanceWindow[];
};
type MaintenanceWindowFormState = {
  confirmation: string;
  kind: MaintenanceWindowKind;
  reason: string;
};

const initialOpsDataState: OpsDataState = {
  artifacts: [],
  auditEvents: [],
  lastResult: { status: "READY" },
  pgStats: [],
  releases: [],
  snapshots: [],
  stats: [],
  windows: []
};
const initialWindowFormState: MaintenanceWindowFormState = {
  confirmation: "CONFIRM",
  kind: "full_load",
  reason: "운영 점검"
};

const servingReleaseColumns: VirtualColumn<ServingRelease>[] = [
  { key: "release", header: "release", cell: (r) => r.serving_release_id },
  { key: "state", header: "state", cell: (r) => <StatusBadge value={r.state} /> },
  { key: "kind", header: "kind", cell: (r) => r.release_kind },
  { key: "mv", header: "mv", cell: (r) => r.mv_name }
];

const datasetSnapshotColumns: VirtualColumn<DatasetSnapshot>[] = [
  { key: "snapshot", header: "snapshot", cell: (r) => r.dataset_snapshot_id },
  { key: "state", header: "state", cell: (r) => <StatusBadge value={r.state} /> },
  { key: "rows", header: "rows", cell: (r) => Object.keys(r.row_counts).length }
];

const maintenanceWindowColumns: VirtualColumn<MaintenanceWindow>[] = [
  { key: "kind", header: "kind", cell: (r) => r.kind },
  { key: "state", header: "state", cell: (r) => <StatusBadge value={r.state} /> },
  { key: "reason", header: "reason", cellClassName: "table-description", cell: (r) => r.reason }
];

const tableStatsColumns: VirtualColumn<TableStatsSnapshot>[] = [
  { key: "object", header: "object", cell: (r) => `${r.schema_name}.${r.object_name}` },
  { key: "kind", header: "kind", cell: (r) => r.object_kind },
  { key: "rows", header: "rows", align: "right", cell: (r) => r.estimated_rows?.toLocaleString() ?? "-" },
  { key: "size", header: "size", align: "right", cell: (r) => formatBytes(r.total_bytes) }
];

const pgStatColumns: VirtualColumn<PgStatStatementSnapshot>[] = [
  { key: "rank", header: "rank", align: "right", cell: (r) => r.rank },
  { key: "op", header: "op", cell: (r) => r.operation },
  { key: "calls", header: "calls", align: "right", cell: (r) => r.calls.toLocaleString() },
  { key: "total", header: "total ms", align: "right", cell: (r) => formatMs(r.total_exec_time_ms) },
  { key: "mean", header: "mean ms", align: "right", cell: (r) => formatMs(r.mean_exec_time_ms) },
  { key: "query", header: "query", cellClassName: "path-cell", cell: (r) => <code>{r.query_preview}</code> }
];

const artifactColumns: VirtualColumn<OpsArtifact>[] = [
  { key: "type", header: "type", cell: (r) => r.artifact_type },
  { key: "state", header: "state", cell: (r) => <StatusBadge value={r.state} /> },
  { key: "size", header: "size", align: "right", cell: (r) => formatBytes(r.size_bytes) }
];

const auditEventColumns: VirtualColumn<AuditEvent>[] = [
  { key: "time", header: "time", cell: (r) => r.occurred_at },
  { key: "action", header: "action", cell: (r) => r.action },
  { key: "outcome", header: "outcome", cell: (r) => <StatusBadge value={r.outcome} /> }
];

export function OpsPanel() {
  const [opsData, setOpsData] = useState<OpsDataState>(initialOpsDataState);
  const [windowForm, setWindowForm] = useState<MaintenanceWindowFormState>(initialWindowFormState);
  const { artifacts, auditEvents, lastResult, pgStats, releases, snapshots, stats, windows } =
    opsData;
  const { confirmation, kind, reason } = windowForm;

  function setLastResult(value: unknown) {
    setOpsData((current) => ({ ...current, lastResult: value }));
  }

  const loadAll = useCallback(async () => {
    // Load each ops surface independently (Promise.allSettled, not Promise.all): one
    // unavailable endpoint (e.g. pg-stat-statements → 503 when pg_stat_statements is not
    // installed) must not blank every other table. Each panel keeps its last-good data on
    // failure, and the failed endpoints are surfaced in "Last Response".
    const [audit, snapshots, releases, artifacts, windows, stats, pgStats] =
      await Promise.allSettled([
        requestJson<AuditEvent[]>("/admin/ops/audit-events?limit=20"),
        requestJson<DatasetSnapshot[]>("/admin/ops/snapshots?limit=10"),
        requestJson<ServingRelease[]>("/admin/ops/releases?limit=10"),
        requestJson<OpsArtifact[]>("/admin/ops/artifacts?limit=10"),
        requestJson<MaintenanceWindow[]>("/admin/ops/maintenance-windows?limit=10"),
        requestJson<TableStatsSnapshot[]>("/admin/ops/table-stats?limit=10"),
        requestJson<PgStatStatementSnapshot[]>("/admin/ops/pg-stat-statements?limit=10")
      ]);

    const failed: string[] = [];
    const note = (label: string, result: PromiseSettledResult<unknown>) => {
      if (result.status === "rejected") failed.push(label);
    };
    note("audit-events", audit);
    note("snapshots", snapshots);
    note("releases", releases);
    note("artifacts", artifacts);
    note("maintenance-windows", windows);
    note("table-stats", stats);
    note("pg-stat-statements", pgStats);

    setOpsData((current) => ({
      ...current,
      auditEvents: audit.status === "fulfilled" ? audit.value : current.auditEvents,
      snapshots: snapshots.status === "fulfilled" ? snapshots.value : current.snapshots,
      releases: releases.status === "fulfilled" ? releases.value : current.releases,
      artifacts: artifacts.status === "fulfilled" ? artifacts.value : current.artifacts,
      windows: windows.status === "fulfilled" ? windows.value : current.windows,
      stats: stats.status === "fulfilled" ? stats.value : current.stats,
      pgStats: pgStats.status === "fulfilled" ? pgStats.value : current.pgStats,
      lastResult: failed.length
        ? { error: `일부 ops 데이터 로드 실패 (${failed.join(", ")})`, partial_failure: failed }
        : current.lastResult
    }));
  }, []);

  async function createWindow(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await postJson<MaintenanceWindow>("/admin/ops/maintenance-windows", {
        confirmation,
        kind,
        reason
      });
      setLastResult(result);
      await loadAll();
    } catch (error) {
      setLastResult({ error: error instanceof Error ? error.message : String(error) });
    }
  }

  async function captureStats() {
    try {
      const result = await postJson<TableStatsSnapshot[]>("/admin/ops/table-stats/capture", {});
      setLastResult(result.slice(0, 5));
      await loadAll();
    } catch (error) {
      setLastResult({ error: error instanceof Error ? error.message : String(error) });
    }
  }

  async function capturePgStats() {
    try {
      const result = await postJson<PgStatStatementSnapshot[]>(
        "/admin/ops/pg-stat-statements/capture?limit=20",
        {}
      );
      setLastResult(result.slice(0, 5));
      await loadAll();
    } catch (error) {
      setLastResult({ error: error instanceof Error ? error.message : String(error) });
    }
  }

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  return (
    <div className="ops-stack">
      <PerfValidationSummary />
      <div className="grid two">
      <Panel
        title="Serving Releases"
        actions={
          <button className="button secondary" onClick={loadAll} type="button">
            <RefreshCw size={16} />
            새로고침
          </button>
        }
      >
        <VirtualTable
          as="table"
          caption="서빙 릴리스 목록"
          columns={servingReleaseColumns}
          emptyHint="서빙 릴리스가 없습니다."
          rowKey={(r) => r.serving_release_id}
          rows={releases}
        />
      </Panel>

      <Panel title="Dataset Snapshots">
        <VirtualTable
          as="table"
          caption="데이터셋 스냅샷 목록"
          columns={datasetSnapshotColumns}
          emptyHint="데이터셋 스냅샷이 없습니다."
          rowKey={(r) => r.dataset_snapshot_id}
          rows={snapshots}
        />
      </Panel>

      <Panel title="Maintenance Window">
        <form className="form-grid" onSubmit={createWindow}>
          <div className="field">
            <label htmlFor="ops-kind">kind</label>
            <select
              id="ops-kind"
              value={kind}
              onChange={(event) =>
                setWindowForm((current) => ({
                  ...current,
                  kind: event.target.value as MaintenanceWindowKind
                }))
              }
            >
              {maintenanceKinds.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="ops-reason">reason</label>
            <input
              id="ops-reason"
              value={reason}
              onChange={(event) =>
                setWindowForm((current) => ({ ...current, reason: event.target.value }))
              }
            />
          </div>
          <div className="field">
            <label htmlFor="ops-confirmation">confirmation</label>
            <input
              id="ops-confirmation"
              value={confirmation}
              onChange={(event) =>
                setWindowForm((current) => ({
                  ...current,
                  confirmation: event.target.value
                }))
              }
            />
          </div>
          <button className="button" type="submit">
            <ShieldCheck size={16} />
            Window 등록
          </button>
        </form>
        <VirtualTable
          as="table"
          caption="유지보수 윈도우 목록"
          columns={maintenanceWindowColumns}
          emptyHint="유지보수 윈도우가 없습니다."
          rowKey={(r) => r.maintenance_window_id}
          rows={windows}
        />
      </Panel>

      <TableStatsSnapshotsPanel stats={stats} onCapture={captureStats} />

      <PgStatStatementsPanel pgStats={pgStats} onCapture={capturePgStats} />

      <Panel title="Artifacts">
        <VirtualTable
          as="table"
          caption="아티팩트 목록"
          columns={artifactColumns}
          emptyHint="아티팩트가 없습니다."
          rowKey={(r) => r.artifact_id}
          rows={artifacts}
        />
      </Panel>

      <Panel title="Audit Events">
        <VirtualTable
          as="table"
          caption="감사 이벤트 목록"
          columns={auditEventColumns}
          emptyHint="감사 이벤트가 없습니다."
          rowKey={(r) => r.audit_event_id}
          rows={auditEvents}
        />
      </Panel>

      <Panel title="Last Response">
        <JsonBlock value={lastResult} />
      </Panel>
      </div>
    </div>
  );
}

function TableStatsSnapshotsPanel({
  stats,
  onCapture
}: {
  stats: TableStatsSnapshot[];
  onCapture: () => void;
}) {
  return (
    <Panel
      title="Table Stats Snapshots"
      actions={
        <button className="button secondary" onClick={onCapture} type="button">
          <Play size={16} />
          Capture
        </button>
      }
    >
      <VirtualTable
        as="table"
        caption="테이블 통계 스냅샷 목록"
        columns={tableStatsColumns}
        emptyHint="테이블 통계 스냅샷이 없습니다."
        rowKey={(r) => r.table_stats_snapshot_id}
        rows={stats}
      />
    </Panel>
  );
}

function PgStatStatementsPanel({
  pgStats,
  onCapture
}: {
  pgStats: PgStatStatementSnapshot[];
  onCapture: () => void;
}) {
  return (
    <Panel
      title="pg_stat Statements"
      actions={
        <button className="button secondary" onClick={onCapture} type="button">
          <Play size={16} />
          Capture
        </button>
      }
    >
      <VirtualTable
        as="table"
        caption="pg_stat_statements 상위 쿼리 목록"
        columns={pgStatColumns}
        emptyHint="pg_stat_statements 스냅샷이 없습니다."
        rowKey={(r) => r.pg_stat_snapshot_id}
        rows={pgStats}
      />
    </Panel>
  );
}

function formatMs(value: number) {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}
