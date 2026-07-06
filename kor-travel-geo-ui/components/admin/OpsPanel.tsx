"use client";

import { Play, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { PerfValidationSummary } from "@/components/admin/PerfValidationSummary";
import { ActionResultPanel } from "@/components/admin/shared/ActionResultPanel";
import { ConfirmActionDialog } from "@/components/admin/shared/ConfirmActionDialog";
import { HelpTip } from "@/components/admin/shared/HelpTip";
import { RefreshButton } from "@/components/admin/shared/RefreshButton";
import { TypedConfirmField } from "@/components/admin/shared/TypedConfirmField";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/skeleton";
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
  getErrorMessage,
  postJson,
  requestJson
} from "@/lib/api";
import { formatBytes, formatMs } from "@/lib/format";
import { toast } from "@/lib/toast";

const maintenanceKinds = [
  "full_load",
  "restore",
  "schema_migration",
  "mv_refresh",
  "read_only",
  "exclusive"
] as const;

type MaintenanceWindowKind = (typeof maintenanceKinds)[number];

/** kind 원값(서버 계약)에 대한 한국어 라벨·한 줄 설명. 위험 kind는 경고 배지로 구분한다. */
const maintenanceKindMeta: Record<
  MaintenanceWindowKind,
  { label: string; description: string; dangerous?: boolean }
> = {
  full_load: { label: "전체 적재", description: "분기 전체 재적재 작업을 선언합니다." },
  restore: { label: "복원", description: "백업에서 DB 복원 작업을 선언합니다." },
  schema_migration: { label: "스키마 변경", description: "DB 스키마 변경 작업을 선언합니다." },
  mv_refresh: { label: "MV 갱신", description: "materialized view 갱신 작업을 선언합니다." },
  read_only: {
    label: "읽기 전용 잠금",
    description: "쓰기 요청을 차단합니다 (조회만 허용).",
    dangerous: true
  },
  exclusive: {
    label: "모든 접근 차단",
    description: "유지보수 동안 모든 요청이 거부됩니다.",
    dangerous: true
  }
};

const REASON_MIN_LENGTH = 4;

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
  kind: "full_load",
  reason: ""
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
  const [confirmText, setConfirmText] = useState("");
  const [loadFailures, setLoadFailures] = useState<string[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [capturing, setCapturing] = useState<"stats" | "pgStats" | null>(null);
  const { artifacts, auditEvents, lastResult, pgStats, releases, snapshots, stats, windows } =
    opsData;
  const { kind, reason } = windowForm;
  const kindMeta = maintenanceKindMeta[kind];
  const reasonValid = reason.trim().length >= REASON_MIN_LENGTH;
  const reasonInvalid = reason.length > 0 && !reasonValid;

  function setLastResult(value: unknown) {
    setOpsData((current) => ({ ...current, lastResult: value }));
  }

  const loadAll = useCallback(async () => {
    // Load each ops surface independently (Promise.allSettled, not Promise.all): one
    // unavailable endpoint (e.g. pg-stat-statements → 503 when pg_stat_statements is not
    // installed) must not blank every other table. Each panel keeps its last-good data on
    // failure, and the failed endpoints are surfaced in an alert + "최근 결과".
    setRefreshing(true);
    try {
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
      setLoadFailures(failed);
    } finally {
      setRefreshing(false);
      setInitialLoading(false);
    }
  }, []);

  async function createWindow() {
    try {
      const result = await postJson<MaintenanceWindow>("/admin/ops/maintenance-windows", {
        confirmation: confirmText,
        kind,
        reason
      });
      setLastResult(result);
      toast.success("유지보수 윈도우를 등록했습니다.");
      setWindowForm(initialWindowFormState);
      await loadAll();
    } catch (error) {
      const message = getErrorMessage(error);
      setLastResult({ error: message });
      toast.error("유지보수 윈도우 등록 실패", message);
    }
  }

  async function captureStats() {
    setCapturing("stats");
    try {
      const result = await postJson<TableStatsSnapshot[]>("/admin/ops/table-stats/capture", {});
      setLastResult(result.slice(0, 5));
      toast.success("테이블 통계 스냅샷을 캡처했습니다.");
      await loadAll();
    } catch (error) {
      const message = getErrorMessage(error);
      setLastResult({ error: message });
      toast.error("테이블 통계 캡처 실패", message);
    } finally {
      setCapturing(null);
    }
  }

  async function capturePgStats() {
    setCapturing("pgStats");
    try {
      const result = await postJson<PgStatStatementSnapshot[]>(
        "/admin/ops/pg-stat-statements/capture?limit=20",
        {}
      );
      setLastResult(result.slice(0, 5));
      toast.success("pg_stat_statements 스냅샷을 캡처했습니다.");
      await loadAll();
    } catch (error) {
      const message = getErrorMessage(error);
      setLastResult({ error: message });
      toast.error("쿼리 통계 캡처 실패", message);
    } finally {
      setCapturing(null);
    }
  }

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  return (
    <div className="ops-stack">
      <PerfValidationSummary />
      {loadFailures.length ? (
        <Alert role="alert" variant="destructive">
          <AlertTitle>일부 ops 데이터 로드 실패</AlertTitle>
          <AlertDescription>{loadFailures.join(", ")}</AlertDescription>
        </Alert>
      ) : null}
      <div className="grid two">
        <OpsTablePanel
          title="서빙 릴리스"
          caption="서빙 릴리스 목록"
          columns={servingReleaseColumns}
          emptyHint="서빙 릴리스가 없습니다."
          loading={initialLoading}
          rowKey={(r) => r.serving_release_id}
          rows={releases}
          actions={<RefreshButton busy={refreshing} onClick={() => void loadAll()} />}
        />

        <OpsTablePanel
          title="데이터셋 스냅샷"
          caption="데이터셋 스냅샷 목록"
          columns={datasetSnapshotColumns}
          emptyHint="데이터셋 스냅샷이 없습니다."
          loading={initialLoading}
          rowKey={(r) => r.dataset_snapshot_id}
          rows={snapshots}
        />

        <Panel
          title="유지보수 윈도우"
          description="적재·복원 등 운영 작업 전에 선언하는 잠금 윈도우"
        >
          <div className="form-grid">
            <Field>
              <div className="flex items-center gap-1">
                <FieldLabel htmlFor="ops-kind">작업 종류</FieldLabel>
                <HelpTip label="작업 종류 도움말">
                  서버 필드 <code>kind</code> — 유지보수 윈도우가 선언하는 작업 종류입니다.
                </HelpTip>
              </div>
              <NativeSelect
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
                    {maintenanceKindMeta[item].label}
                  </option>
                ))}
              </NativeSelect>
              <FieldDescription className="flex flex-wrap items-center gap-2">
                {kindMeta.dangerous ? <Badge tone="warn">위험</Badge> : null}
                <span>
                  <code>{kind}</code> — {kindMeta.description}
                </span>
              </FieldDescription>
            </Field>
            <Field data-invalid={reasonInvalid || undefined}>
              <div className="flex items-center gap-1">
                <FieldLabel htmlFor="ops-reason">사유</FieldLabel>
                <HelpTip label="사유 도움말">
                  서버 필드 <code>reason</code> — 감사 이력에 기록되는 필수 항목입니다.
                </HelpTip>
              </div>
              <Input
                id="ops-reason"
                value={reason}
                placeholder="예: 202606 전국 재적재 사전 점검"
                aria-invalid={reasonInvalid || undefined}
                onChange={(event) =>
                  setWindowForm((current) => ({ ...current, reason: event.target.value }))
                }
              />
              {reasonInvalid ? (
                <FieldError>사유를 {REASON_MIN_LENGTH}자 이상 입력하세요.</FieldError>
              ) : (
                <FieldDescription>필수 입력 ({REASON_MIN_LENGTH}자 이상)</FieldDescription>
              )}
            </Field>
            <ConfirmActionDialog
              trigger={
                <Button className="justify-self-start" disabled={!reasonValid} type="button">
                  <ShieldCheck aria-hidden="true" size={16} />
                  윈도우 등록
                </Button>
              }
              title="유지보수 윈도우 등록"
              description={
                <>
                  <code>{kind}</code> ({kindMeta.label}) 윈도우를 엽니다 — {kindMeta.description}
                </>
              }
              confirmLabel="윈도우 등록"
              confirmDisabled={confirmText !== "CONFIRM"}
              onOpenChange={(open) => {
                if (!open) setConfirmText("");
              }}
              onConfirm={createWindow}
            >
              <TypedConfirmField
                phrase="CONFIRM"
                value={confirmText}
                onChange={setConfirmText}
                label="유지보수 윈도우 확인 문구"
              />
            </ConfirmActionDialog>
          </div>
          <TableSection
            caption="유지보수 윈도우 목록"
            columns={maintenanceWindowColumns}
            emptyHint="유지보수 윈도우가 없습니다."
            loading={initialLoading}
            rowKey={(r) => r.maintenance_window_id}
            rows={windows}
          />
        </Panel>

        <OpsTablePanel
          title="테이블 통계 스냅샷"
          caption="테이블 통계 스냅샷 목록"
          columns={tableStatsColumns}
          emptyHint="테이블 통계 스냅샷이 없습니다."
          loading={initialLoading}
          rowKey={(r) => r.table_stats_snapshot_id}
          rows={stats}
          actions={
            <CaptureButton busy={capturing === "stats"} onClick={() => void captureStats()} />
          }
        />

        <OpsTablePanel
          title="쿼리 통계"
          description="pg_stat_statements 상위 쿼리 스냅샷"
          caption="pg_stat_statements 상위 쿼리 목록"
          columns={pgStatColumns}
          emptyHint="pg_stat_statements 스냅샷이 없습니다."
          loading={initialLoading}
          rowKey={(r) => r.pg_stat_snapshot_id}
          rows={pgStats}
          actions={
            <CaptureButton busy={capturing === "pgStats"} onClick={() => void capturePgStats()} />
          }
        />

        <OpsTablePanel
          title="아티팩트"
          caption="아티팩트 목록"
          columns={artifactColumns}
          emptyHint="아티팩트가 없습니다."
          loading={initialLoading}
          rowKey={(r) => r.artifact_id}
          rows={artifacts}
        />

        <OpsTablePanel
          title="감사 이벤트"
          caption="감사 이벤트 목록"
          columns={auditEventColumns}
          emptyHint="감사 이벤트가 없습니다."
          loading={initialLoading}
          rowKey={(r) => r.audit_event_id}
          rows={auditEvents}
        />

        <ActionResultPanel result={lastResult} />
      </div>
    </div>
  );
}

/** Panel + semantic VirtualTable 반복(7회)의 공용 셸. 로딩 중엔 Skeleton을 보여준다. */
function OpsTablePanel<T>({
  title,
  description,
  actions,
  ...tableProps
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
} & TableSectionProps<T>) {
  return (
    <Panel actions={actions} description={description} title={title}>
      <TableSection {...tableProps} />
    </Panel>
  );
}

type TableSectionProps<T> = {
  caption: string;
  columns: VirtualColumn<T>[];
  emptyHint: string;
  loading: boolean;
  rowKey: (row: T) => string;
  rows: T[];
};

function TableSection<T>({ caption, columns, emptyHint, loading, rowKey, rows }: TableSectionProps<T>) {
  if (loading) {
    return (
      <div className="grid gap-2" aria-busy="true">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </div>
    );
  }
  return (
    <VirtualTable
      as="table"
      caption={caption}
      columns={columns}
      emptyHint={emptyHint}
      rowKey={rowKey}
      rows={rows}
    />
  );
}

function CaptureButton({ busy, onClick }: { busy: boolean; onClick: () => void }) {
  return (
    <Button
      aria-busy={busy || undefined}
      disabled={busy}
      onClick={onClick}
      size="sm"
      type="button"
      variant="outline"
    >
      <Play aria-hidden="true" size={16} />
      캡처
    </Button>
  );
}
