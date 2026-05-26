"use client";

import { Play, RefreshCw, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  AuditEvent,
  DatasetSnapshot,
  MaintenanceWindow,
  OpsArtifact,
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

export function OpsPanel() {
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [snapshots, setSnapshots] = useState<DatasetSnapshot[]>([]);
  const [releases, setReleases] = useState<ServingRelease[]>([]);
  const [artifacts, setArtifacts] = useState<OpsArtifact[]>([]);
  const [windows, setWindows] = useState<MaintenanceWindow[]>([]);
  const [stats, setStats] = useState<TableStatsSnapshot[]>([]);
  const [kind, setKind] = useState<(typeof maintenanceKinds)[number]>("full_load");
  const [reason, setReason] = useState("운영 점검");
  const [confirmation, setConfirmation] = useState("CONFIRM");
  const [lastResult, setLastResult] = useState<unknown>({ status: "READY" });

  async function loadAll() {
    try {
      const [nextAudit, nextSnapshots, nextReleases, nextArtifacts, nextWindows, nextStats] =
        await Promise.all([
          requestJson<AuditEvent[]>("/admin/ops/audit-events?limit=20"),
          requestJson<DatasetSnapshot[]>("/admin/ops/snapshots?limit=10"),
          requestJson<ServingRelease[]>("/admin/ops/releases?limit=10"),
          requestJson<OpsArtifact[]>("/admin/ops/artifacts?limit=10"),
          requestJson<MaintenanceWindow[]>("/admin/ops/maintenance-windows?limit=10"),
          requestJson<TableStatsSnapshot[]>("/admin/ops/table-stats?limit=10")
        ]);
      setAuditEvents(nextAudit);
      setSnapshots(nextSnapshots);
      setReleases(nextReleases);
      setArtifacts(nextArtifacts);
      setWindows(nextWindows);
      setStats(nextStats);
    } catch (error) {
      setLastResult({ error: error instanceof Error ? error.message : String(error) });
    }
  }

  async function createWindow(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await postJson<MaintenanceWindow>("/admin/ops/maintenance-windows", {
        kind,
        reason,
        confirmation
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

  useEffect(() => {
    void loadAll();
  }, []);

  return (
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
              <tr key={release.release_id}>
                <td>{release.release_id}</td>
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
              <tr key={snapshot.snapshot_id}>
                <td>{snapshot.snapshot_id}</td>
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
              onChange={(event) => setKind(event.target.value as typeof kind)}
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
            <input id="ops-reason" value={reason} onChange={(event) => setReason(event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="ops-confirmation">confirmation</label>
            <input
              id="ops-confirmation"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
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
              <tr key={window.window_id}>
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

      <Panel
        title="Table Stats Snapshots"
        actions={
          <button className="button secondary" onClick={captureStats} type="button">
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
              <tr key={row.stats_id}>
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
              <tr key={event.event_id}>
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
  );
}
