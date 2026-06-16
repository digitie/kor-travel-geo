"use client";

import { Play, RefreshCw, ShieldCheck } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { PerfValidationSummary } from "@/components/admin/PerfValidationSummary";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
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
    try {
      const [
        nextAudit,
        nextSnapshots,
        nextReleases,
        nextArtifacts,
        nextWindows,
        nextStats,
        nextPgStats
      ] = await Promise.all([
        requestJson<AuditEvent[]>("/admin/ops/audit-events?limit=20"),
        requestJson<DatasetSnapshot[]>("/admin/ops/snapshots?limit=10"),
        requestJson<ServingRelease[]>("/admin/ops/releases?limit=10"),
        requestJson<OpsArtifact[]>("/admin/ops/artifacts?limit=10"),
        requestJson<MaintenanceWindow[]>("/admin/ops/maintenance-windows?limit=10"),
        requestJson<TableStatsSnapshot[]>("/admin/ops/table-stats?limit=10"),
        requestJson<PgStatStatementSnapshot[]>("/admin/ops/pg-stat-statements?limit=10")
      ]);
      setOpsData((current) => ({
        ...current,
        artifacts: nextArtifacts,
        auditEvents: nextAudit,
        pgStats: nextPgStats,
        releases: nextReleases,
        snapshots: nextSnapshots,
        stats: nextStats,
        windows: nextWindows
      }));
    } catch (error) {
      setOpsData((current) => ({
        ...current,
        lastResult: { error: error instanceof Error ? error.message : String(error) }
      }));
    }
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
        <table className="table">
          <thead>
            <tr>
              <th>release</th>
              <th>state</th>
              <th>kind</th>
              <th>mv</th>
            </tr>
          </thead>
          <tbody>
            {releases.map((release) => (
              <tr key={release.serving_release_id}>
                <td>{release.serving_release_id}</td>
                <td>
                  <StatusBadge value={release.state} />
                </td>
                <td>{release.release_kind}</td>
                <td>{release.mv_name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel title="Dataset Snapshots">
        <table className="table">
          <thead>
            <tr>
              <th>snapshot</th>
              <th>state</th>
              <th>rows</th>
            </tr>
          </thead>
          <tbody>
            {snapshots.map((snapshot) => (
              <tr key={snapshot.dataset_snapshot_id}>
                <td>{snapshot.dataset_snapshot_id}</td>
                <td>
                  <StatusBadge value={snapshot.state} />
                </td>
                <td>{Object.keys(snapshot.row_counts).length}</td>
              </tr>
            ))}
          </tbody>
        </table>
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
        <table className="table">
          <thead>
            <tr>
              <th>kind</th>
              <th>state</th>
              <th>reason</th>
            </tr>
          </thead>
          <tbody>
            {windows.map((window) => (
              <tr key={window.maintenance_window_id}>
                <td>{window.kind}</td>
                <td>
                  <StatusBadge value={window.state} />
                </td>
                <td>{window.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <TableStatsSnapshotsPanel stats={stats} onCapture={captureStats} />

      <PgStatStatementsPanel pgStats={pgStats} onCapture={capturePgStats} />

      <Panel title="Artifacts">
        <table className="table">
          <thead>
            <tr>
              <th>type</th>
              <th>state</th>
              <th>size</th>
            </tr>
          </thead>
          <tbody>
            {artifacts.map((artifact) => (
              <tr key={artifact.artifact_id}>
                <td>{artifact.artifact_type}</td>
                <td>
                  <StatusBadge value={artifact.state} />
                </td>
                <td>{formatBytes(artifact.size_bytes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel title="Audit Events">
        <table className="table">
          <thead>
            <tr>
              <th>time</th>
              <th>action</th>
              <th>outcome</th>
            </tr>
          </thead>
          <tbody>
            {auditEvents.map((event) => (
              <tr key={event.audit_event_id}>
                <td>{event.occurred_at}</td>
                <td>{event.action}</td>
                <td>
                  <StatusBadge value={event.outcome} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
      <table className="table">
        <thead>
          <tr>
            <th>object</th>
            <th>kind</th>
            <th>rows</th>
            <th>size</th>
          </tr>
        </thead>
        <tbody>
          {stats.map((row) => (
            <tr key={row.table_stats_snapshot_id}>
              <td>
                {row.schema_name}.{row.object_name}
              </td>
              <td>{row.object_kind}</td>
              <td>{row.estimated_rows?.toLocaleString() ?? "-"}</td>
              <td>{formatBytes(row.total_bytes)}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
      <table className="table">
        <thead>
          <tr>
            <th>rank</th>
            <th>op</th>
            <th>calls</th>
            <th>total ms</th>
            <th>mean ms</th>
            <th>query</th>
          </tr>
        </thead>
        <tbody>
          {pgStats.map((row) => (
            <tr key={row.pg_stat_snapshot_id}>
              <td>{row.rank}</td>
              <td>{row.operation}</td>
              <td>{row.calls.toLocaleString()}</td>
              <td>{formatMs(row.total_exec_time_ms)}</td>
              <td>{formatMs(row.mean_exec_time_ms)}</td>
              <td>
                <code>{row.query_preview}</code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function formatMs(value: number) {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}
