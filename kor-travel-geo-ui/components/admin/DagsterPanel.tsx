"use client";

import { Check, Download, ExternalLink } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { RefreshButton } from "@/components/admin/shared/RefreshButton";
import { MetricTile } from "@/components/admin/shared/MetricTile";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { VirtualTable, type VirtualColumn } from "@/components/ui/VirtualTable";
import { getErrorMessage } from "@/lib/api";
import { backupDownloadHref } from "@/lib/backup-workflow";
import {
  dagsterRunUrl,
  dagsterStatusTone,
  formatDagsterEpoch,
  type DagsterInstigationTick,
  type DagsterRepository,
  type DagsterRunDetailData,
  type DagsterRunEvent,
  type DagsterRunFailureAlert,
  type DagsterRunSummary,
  type DagsterSummaryData,
  useAckRunFailureMutation,
  useDagsterRunDetailQuery,
  useDagsterRunFailuresQuery,
  useDagsterSummaryQuery
} from "@/lib/dagster";
import { formatBytes, formatTimestamp } from "@/lib/format";

type OverdueSchedule = { repository: string; name: string; nextTickAt: number | null };

type EventGroup = { stepId: string | null; events: DagsterRunEvent[] };

function isBackupStep(stepId: string | null): boolean {
  return (stepId ?? "").toLowerCase().includes("backup");
}

function groupEventsByStep(events: DagsterRunEvent[]): EventGroup[] {
  const groups: EventGroup[] = [];
  const indexByKey = new Map<string, number>();
  for (const event of events) {
    const stepId = event.step_id ?? null;
    const key = stepId ?? " run-level";
    let index = indexByKey.get(key);
    if (index === undefined) {
      index = groups.length;
      indexByKey.set(key, index);
      groups.push({ stepId, events: [] });
    }
    groups[index].events.push(event);
  }
  return groups;
}

function overdueSchedules(summary: DagsterSummaryData | undefined): OverdueSchedule[] {
  if (!summary) return [];
  const overdue: OverdueSchedule[] = [];
  for (const repository of summary.repositories) {
    for (const schedule of repository.schedules) {
      if (schedule.overdue) {
        overdue.push({
          repository: repository.name,
          name: schedule.name,
          nextTickAt: schedule.next_tick_at ?? null
        });
      }
    }
  }
  return overdue;
}

type InstigationRow = {
  id: string;
  type: "schedule" | "sensor";
  repository: string;
  name: string;
  status?: string | null;
  cron?: string | null;
  timezone?: string | null;
  lastTick?: DagsterInstigationTick | null;
};

const runColumns = (onSelect: (runId: string) => void): VirtualColumn<DagsterRunSummary>[] => [
  {
    key: "run",
    header: "run",
    sortValue: (row) => row.run_id,
    cellClassName: "path-cell",
    cell: (row) => (
      <button
        aria-label={`${row.run_id} run 상세`}
        className="max-w-full truncate rounded-control text-left font-mono text-brand underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        onClick={() => onSelect(row.run_id)}
        type="button"
      >
        {row.run_id}
      </button>
    )
  },
  {
    key: "job",
    header: "job",
    sortValue: (row) => row.job_name ?? "",
    cell: (row) => row.job_name ?? "-"
  },
  {
    key: "status",
    header: "status",
    sortValue: (row) => row.status,
    cell: (row) => <StatusBadge value={row.status} tone={dagsterStatusTone(row.status)} />
  },
  {
    key: "start",
    header: "started",
    sortValue: (row) => row.start_time ?? 0,
    cell: (row) => formatDagsterEpoch(row.start_time)
  },
  {
    key: "updated",
    header: "updated",
    sortValue: (row) => row.update_time ?? 0,
    cell: (row) => formatDagsterEpoch(row.update_time)
  }
];

const repositoryColumns: VirtualColumn<DagsterRepository>[] = [
  {
    key: "location",
    header: "location",
    sortValue: (row) => row.location_name,
    cell: (row) => row.location_name
  },
  {
    key: "repository",
    header: "repository",
    sortValue: (row) => row.name,
    cell: (row) => row.name
  },
  {
    key: "jobs",
    header: "jobs",
    align: "right",
    sortValue: (row) => row.jobs.length,
    cell: (row) => row.jobs.length.toLocaleString()
  },
  {
    key: "schedules",
    header: "schedules",
    align: "right",
    sortValue: (row) => row.schedules.length,
    cell: (row) => row.schedules.length.toLocaleString()
  },
  {
    key: "sensors",
    header: "sensors",
    align: "right",
    sortValue: (row) => row.sensors.length,
    cell: (row) => row.sensors.length.toLocaleString()
  },
  {
    key: "assets",
    header: "assets",
    align: "right",
    sortValue: (row) => row.asset_count,
    cell: (row) => row.asset_count.toLocaleString()
  }
];

const instigationColumns: VirtualColumn<InstigationRow>[] = [
  {
    key: "type",
    header: "type",
    sortValue: (row) => row.type,
    cell: (row) => <Badge tone="neutral">{row.type}</Badge>
  },
  {
    key: "repository",
    header: "repository",
    sortValue: (row) => row.repository,
    cell: (row) => row.repository
  },
  {
    key: "name",
    header: "name",
    sortValue: (row) => row.name,
    cell: (row) => row.name
  },
  {
    key: "status",
    header: "status",
    sortValue: (row) => row.status ?? "",
    cell: (row) =>
      row.status ? <StatusBadge value={row.status} tone={dagsterStatusTone(row.status)} /> : "-"
  },
  {
    key: "cron",
    header: "cron",
    cell: (row) => [row.cron, row.timezone].filter(Boolean).join(" / ") || "-"
  },
  {
    key: "last",
    header: "last tick",
    sortValue: (row) => row.lastTick?.timestamp ?? 0,
    cell: (row) =>
      row.lastTick ? (
        <span className="inline-flex flex-wrap items-center gap-2">
          <StatusBadge
            value={row.lastTick.status}
            tone={dagsterStatusTone(row.lastTick.status)}
          />
          <span>{formatDagsterEpoch(row.lastTick.timestamp)}</span>
        </span>
      ) : (
        "-"
      )
  }
];

export function DagsterPanel() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const summaryQuery = useDagsterSummaryQuery();
  const summary = summaryQuery.data?.data;
  const recentRuns = useMemo(() => summary?.recent_runs ?? [], [summary?.recent_runs]);
  const runDetailQuery = useDagsterRunDetailQuery(selectedRunId);
  const runDetail = runDetailQuery.data?.data;
  const recentRunColumns = useMemo(() => runColumns(setSelectedRunId), []);
  const ackMutation = useAckRunFailureMutation();

  useEffect(() => {
    if (selectedRunId || recentRuns.length === 0) return;
    setSelectedRunId(recentRuns[0]?.run_id ?? null);
  }, [recentRuns, selectedRunId]);

  const instigations = useMemo(
    () => flattenInstigations(summary?.repositories ?? []),
    [summary?.repositories]
  );

  return (
    <div className="grid gap-4">
      {summaryQuery.isError ? (
        <Alert role="alert" variant="destructive">
          <AlertTitle>Dagster 요약 조회 실패</AlertTitle>
          <AlertDescription>{getErrorMessage(summaryQuery.error)}</AlertDescription>
        </Alert>
      ) : null}

      {summary ? <DagsterOutageAlert summary={summary} /> : null}
      {summary ? <ScheduleOverdueAlert schedules={overdueSchedules(summary)} /> : null}

      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile
          label="repositories"
          value={summary?.repository_count.toLocaleString() ?? "-"}
          loading={summaryQuery.isPending}
        />
        <MetricTile
          label="assets"
          value={summary?.asset_count.toLocaleString() ?? "-"}
          loading={summaryQuery.isPending}
        />
        <MetricTile
          label="jobs"
          value={summary?.job_count.toLocaleString() ?? "-"}
          loading={summaryQuery.isPending}
        />
        <MetricTile
          label="failed (recent)"
          value={failedRunCount(summary).toLocaleString()}
          loading={summaryQuery.isPending}
          hint={summary ? `checked ${formatTimestamp(summary.checked_at)}` : undefined}
        />
      </div>

      <RecentFailuresPanel onSelectRun={setSelectedRunId} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)]">
        <Panel
          title="Recent runs"
          description="Dagster run store 최근 실행"
          actions={<RefreshButton busy={summaryQuery.isFetching} onClick={() => void summaryQuery.refetch()} />}
        >
          <VirtualTable
            as="table"
            compact
            caption="최근 Dagster run"
            columns={recentRunColumns}
            emptyHint={summaryQuery.isPending ? "로딩 중입니다." : "최근 run이 없습니다."}
            getRowClassName={(row) => (row.run_id === selectedRunId ? "bg-muted" : undefined)}
            getSearchText={(row) => `${row.run_id} ${row.job_name ?? ""} ${row.status}`}
            initialSortKey="updated"
            initialSortDir="desc"
            rowKey={(row) => row.run_id}
            rows={recentRuns}
            searchPlaceholder="run 검색"
          />
        </Panel>

        <RunDetailPanel
          ackPending={ackMutation.isPending}
          dagsterUrl={summary?.dagster_url ?? ""}
          detail={runDetail}
          error={runDetailQuery.error}
          isError={runDetailQuery.isError}
          isFetching={runDetailQuery.isFetching}
          isPending={runDetailQuery.isPending && Boolean(selectedRunId)}
          onAckFailure={(runId) => ackMutation.mutate(runId)}
          onRefresh={() => {
            if (selectedRunId) void runDetailQuery.refetch();
          }}
          selectedRunId={selectedRunId}
        />
      </div>

      <Panel title="Code locations" description="repository와 정의 요약">
        <VirtualTable
          as="table"
          compact
          caption="Dagster repository"
          columns={repositoryColumns}
          emptyHint={summaryQuery.isPending ? "로딩 중입니다." : "repository가 없습니다."}
          getSearchText={(row) => `${row.location_name} ${row.name}`}
          rowKey={(row) => `${row.location_name}:${row.name}`}
          rows={summary?.repositories ?? []}
          searchPlaceholder="repository 검색"
        />
      </Panel>

      <Panel title="Schedules and sensors" description="최근 tick 상태">
        <VirtualTable
          as="table"
          compact
          caption="Dagster schedule 및 sensor"
          columns={instigationColumns}
          emptyHint={summaryQuery.isPending ? "로딩 중입니다." : "schedule/sensor가 없습니다."}
          getSearchText={(row) => `${row.type} ${row.name} ${row.status ?? ""}`}
          rowKey={(row) => row.id}
          rows={instigations}
          searchPlaceholder="schedule/sensor 검색"
        />
      </Panel>
    </div>
  );
}

function RunDetailPanel({
  ackPending,
  dagsterUrl,
  detail,
  error,
  isError,
  isFetching,
  isPending,
  onAckFailure,
  onRefresh,
  selectedRunId
}: {
  ackPending: boolean;
  dagsterUrl: string;
  detail: DagsterRunDetailData | undefined;
  error: unknown;
  isError: boolean;
  isFetching: boolean;
  isPending: boolean;
  onAckFailure: (runId: string) => void;
  onRefresh: () => void;
  selectedRunId: string | null;
}) {
  const run = detail?.run;
  const failureAlert = detail?.failure_alert ?? null;
  const backupArtifact = detail?.backup_artifact ?? null;
  const backupArtifactHref = backupDownloadHref(backupArtifact?.download_url);
  const loadJobId = run?.tags?.["kor_travel_geo.job_id"];
  return (
    <Panel
      title="Run detail"
      description={selectedRunId ? selectedRunId : "선택된 run 없음"}
      actions={
        <>
          {selectedRunId && dagsterUrl ? (
            <Button asChild size="sm" variant="outline">
              <a href={dagsterRunUrl(dagsterUrl, selectedRunId)} rel="noreferrer" target="_blank">
                <ExternalLink aria-hidden="true" />
                Dagster
              </a>
            </Button>
          ) : null}
          {selectedRunId ? <RefreshButton busy={isFetching} onClick={onRefresh} /> : null}
        </>
      }
    >
      {isError ? (
        <Alert role="alert" variant="destructive">
          <AlertTitle>Run 상세 조회 실패</AlertTitle>
          <AlertDescription>{getErrorMessage(error)}</AlertDescription>
        </Alert>
      ) : null}

      {!selectedRunId ? (
        <p className="wizard-hint">최근 run이 없습니다.</p>
      ) : isPending ? (
        <Skeleton className="h-48 w-full" />
      ) : detail ? (
        <div className="grid gap-3">
          {detail.errors?.length ? (
            <Alert role="alert" variant={detail.status === "ok" ? "default" : "destructive"}>
              <AlertTitle>Dagster 응답 메시지</AlertTitle>
              <AlertDescription>{detail.errors.join(" / ")}</AlertDescription>
            </Alert>
          ) : null}
          {run && dagsterStatusTone(run.status) === "error" ? (
            <RunFailureBanner
              ackPending={ackPending}
              alert={failureAlert}
              onAck={onAckFailure}
              run={run}
            />
          ) : null}
          <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
            <dt className="text-muted-foreground">status</dt>
            <dd>
              <StatusBadge value={detail.status} tone={dagsterStatusTone(detail.status)} />
            </dd>
            <dt className="text-muted-foreground">job</dt>
            <dd className="min-w-0 break-all">{run?.job_name ?? "-"}</dd>
            {loadJobId ? (
              <>
                <dt className="text-muted-foreground">load job</dt>
                <dd className="min-w-0 break-all font-mono">{loadJobId}</dd>
              </>
            ) : null}
            {backupArtifact ? (
              <>
                <dt className="text-muted-foreground">backup artifact</dt>
                <dd className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className="min-w-0 break-all font-mono">
                    {backupArtifact.display_name ?? backupArtifact.artifact_id}
                  </span>
                  <StatusBadge
                    value={backupArtifact.state}
                    tone={dagsterStatusTone(backupArtifact.state)}
                  />
                  {backupArtifact.size_bytes != null ? (
                    <span className="text-muted-foreground">
                      {formatBytes(backupArtifact.size_bytes)}
                    </span>
                  ) : null}
                  {backupArtifactHref ? (
                    <Button asChild size="sm" variant="outline">
                      <a aria-label="backup artifact 다운로드" href={backupArtifactHref}>
                        <Download aria-hidden="true" />
                        다운로드
                      </a>
                    </Button>
                  ) : null}
                </dd>
              </>
            ) : null}
            <dt className="text-muted-foreground">started</dt>
            <dd>{formatDagsterEpoch(run?.start_time)}</dd>
            <dt className="text-muted-foreground">updated</dt>
            <dd>{formatDagsterEpoch(run?.update_time)}</dd>
          </dl>
          <OpLogGroups events={detail.events ?? []} />
        </div>
      ) : (
        <p className="wizard-hint">Run 상세를 불러오지 않았습니다.</p>
      )}
    </Panel>
  );
}

function DagsterOutageAlert({ summary }: { summary: DagsterSummaryData }) {
  if (summary.status === "ok" && !summary.errors?.length) return null;
  return (
    <Alert role="alert" variant={summary.status === "ok" ? "default" : "destructive"}>
      <AlertTitle>Dagster 상태: {summary.status}</AlertTitle>
      <AlertDescription>
        {summary.errors?.length ? summary.errors.join(" / ") : "Dagster GraphQL 응답을 확인하세요."}
      </AlertDescription>
    </Alert>
  );
}

function failedRunCount(summary: DagsterSummaryData | undefined): number {
  if (!summary) return 0;
  return Object.entries(summary.run_counts).reduce((total, [status, count]) => {
    return dagsterStatusTone(status) === "error" ? total + count : total;
  }, 0);
}

function flattenInstigations(repositories: DagsterRepository[]): InstigationRow[] {
  return repositories.flatMap((repository) => {
    const schedules = repository.schedules.map((schedule) => ({
      id: `${repository.location_name}:${repository.name}:schedule:${schedule.name}`,
      type: "schedule" as const,
      repository: repository.name,
      name: schedule.name,
      status: schedule.status,
      cron: schedule.cron_schedule,
      timezone: schedule.execution_timezone,
      lastTick: schedule.recent_ticks?.[0] ?? null
    }));
    const sensors = repository.sensors.map((sensor) => ({
      id: `${repository.location_name}:${repository.name}:sensor:${sensor.name}`,
      type: "sensor" as const,
      repository: repository.name,
      name: sensor.name,
      status: sensor.status,
      cron: null,
      timezone: null,
      lastTick: sensor.recent_ticks?.[0] ?? null
    }));
    return [...schedules, ...sensors];
  });
}

function RunFailureBanner({
  ackPending,
  alert,
  onAck,
  run
}: {
  ackPending: boolean;
  alert: DagsterRunFailureAlert | null;
  onAck: (runId: string) => void;
  run: DagsterRunSummary;
}) {
  const acknowledged = Boolean(alert?.acknowledged_at);
  return (
    <Alert role="alert" variant="destructive">
      <AlertTitle>run 실패: {run.status}</AlertTitle>
      <AlertDescription>
        <div className="flex flex-wrap items-center gap-2">
          <span>
            {alert?.error_code ? `오류 유형: ${alert.error_code}` : "이 run은 실패로 종료됐습니다."}
          </span>
          {alert ? (
            <span className="text-muted-foreground">
              · 기록됨 {formatTimestamp(alert.recorded_at)}
            </span>
          ) : null}
          {acknowledged ? <Badge tone="ok">확인됨</Badge> : null}
          {alert && !acknowledged ? (
            <Button
              disabled={ackPending}
              onClick={() => onAck(run.run_id)}
              size="sm"
              variant="outline"
            >
              <Check aria-hidden="true" />
              확인
            </Button>
          ) : null}
        </div>
      </AlertDescription>
    </Alert>
  );
}

function ScheduleOverdueAlert({ schedules }: { schedules: OverdueSchedule[] }) {
  if (schedules.length === 0) return null;
  return (
    <Alert role="alert" variant="warning">
      <AlertTitle>스케줄 지연(overdue) {schedules.length}건</AlertTitle>
      <AlertDescription>
        예정된 실행 시각을 지나도록 실행되지 않았습니다(스케줄러 데몬 지연 가능):{" "}
        {schedules
          .map((schedule) =>
            schedule.nextTickAt != null
              ? `${schedule.name} (다음 예정 ${formatDagsterEpoch(schedule.nextTickAt)})`
              : schedule.name
          )
          .join(", ")}
      </AlertDescription>
    </Alert>
  );
}

function RecentFailuresPanel({ onSelectRun }: { onSelectRun: (runId: string) => void }) {
  const failuresQuery = useDagsterRunFailuresQuery();
  const ackMutation = useAckRunFailureMutation();
  const alerts = failuresQuery.data?.data.alerts ?? [];
  return (
    <Panel
      title="최근 실패 알림"
      description="확인하지 않은 Dagster run 실패"
      actions={
        <RefreshButton
          busy={failuresQuery.isFetching}
          onClick={() => void failuresQuery.refetch()}
        />
      }
    >
      {failuresQuery.isError ? (
        <Alert role="alert" variant="destructive">
          <AlertTitle>실패 알림 조회 실패</AlertTitle>
          <AlertDescription>{getErrorMessage(failuresQuery.error)}</AlertDescription>
        </Alert>
      ) : alerts.length === 0 ? (
        <p className="wizard-hint">
          {failuresQuery.isPending ? "로딩 중입니다." : "확인하지 않은 실패 알림이 없습니다."}
        </p>
      ) : (
        <ul className="grid gap-2">
          {alerts.map((alert) => (
            <li
              key={alert.run_id}
              className="flex flex-wrap items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm"
            >
              <button
                aria-label={`${alert.run_id} run 상세`}
        className="max-w-full truncate rounded-control text-left font-mono text-brand underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                onClick={() => onSelectRun(alert.run_id)}
                type="button"
              >
                {alert.run_id}
              </button>
              <span className="min-w-0 break-all text-muted-foreground">
                {alert.job_name ?? alert.job_kind ?? "-"}
              </span>
              <StatusBadge value={alert.status} tone={dagsterStatusTone(alert.status)} />
              {alert.error_code ? <Badge tone="neutral">{alert.error_code}</Badge> : null}
              <span className="text-muted-foreground">{formatTimestamp(alert.run_failed_at)}</span>
              <Button
                className="ml-auto"
                disabled={ackMutation.isPending}
                onClick={() => ackMutation.mutate(alert.run_id)}
                size="sm"
                variant="outline"
              >
                <Check aria-hidden="true" />
                확인
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function OpLogGroups({ events }: { events: DagsterRunEvent[] }) {
  const groups = useMemo(() => groupEventsByStep(events), [events]);
  if (groups.length === 0) {
    return <p className="wizard-hint">event log가 없습니다.</p>;
  }
  return (
    <div className="grid gap-2">
      <h3 className="text-sm font-medium text-muted-foreground">op 로그 · {groups.length} step</h3>
      {groups.map((group) => {
        const backup = isBackupStep(group.stepId);
        return (
          <details
            key={group.stepId ?? " run-level"}
            className={`rounded-lg border ${
              backup ? "border-primary/40 bg-primary/5" : "border-border"
            }`}
            open={backup || group.stepId === null}
          >
            <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-2 text-sm">
              <span className="min-w-0 break-all font-mono">
                {group.stepId ?? "run-level 이벤트"}
              </span>
              {backup ? <Badge tone="info">backup op</Badge> : null}
              <Badge tone="neutral">{group.events.length} event</Badge>
            </summary>
            <div className="overflow-x-auto border-t border-border">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="text-muted-foreground">
                    <th className="px-3 py-1 font-medium">time</th>
                    <th className="px-3 py-1 font-medium">event</th>
                    <th className="px-3 py-1 font-medium">level</th>
                    <th className="px-3 py-1 font-medium">message</th>
                  </tr>
                </thead>
                <tbody>
                  {group.events.map((event) => (
                    <tr
                      key={`${event.timestamp ?? ""}:${event.event_type}:${event.level ?? ""}:${event.message ?? event.error?.message ?? ""}`}
                      className="border-t border-border/50 align-top"
                    >
                      <td className="whitespace-nowrap px-3 py-1 font-mono">
                        {formatDagsterEpoch(event.timestamp)}
                      </td>
                      <td className="px-3 py-1">{event.event_type}</td>
                      <td className="px-3 py-1">{event.level ?? "-"}</td>
                      <td className="px-3 py-1 break-all">
                        {event.message ?? event.error?.message ?? "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        );
      })}
    </div>
  );
}
