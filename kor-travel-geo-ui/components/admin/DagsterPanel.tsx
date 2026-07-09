"use client";

import { Download, ExternalLink } from "lucide-react";
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
  type DagsterRunSummary,
  type DagsterSummaryData,
  useDagsterRunDetailQuery,
  useDagsterSummaryQuery
} from "@/lib/dagster";
import { formatBytes, formatTimestamp } from "@/lib/format";

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
        className="max-w-full truncate text-left font-mono text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
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

const eventColumns: VirtualColumn<DagsterRunEvent>[] = [
  {
    key: "time",
    header: "time",
    sortValue: (row) => row.timestamp ?? "",
    cell: (row) => formatDagsterEpoch(row.timestamp)
  },
  {
    key: "event",
    header: "event",
    sortValue: (row) => row.event_type,
    cell: (row) => row.event_type
  },
  {
    key: "level",
    header: "level",
    sortValue: (row) => row.level ?? "",
    cell: (row) => row.level ?? "-"
  },
  {
    key: "step",
    header: "step",
    sortValue: (row) => row.step_id ?? "",
    cell: (row) => row.step_id ?? "-"
  },
  {
    key: "message",
    header: "message",
    cellClassName: "table-description",
    cell: (row) => row.message ?? row.error?.message ?? "-"
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

      <Panel
        title="Dagster UI"
        description="Dagster webserver 화면"
        actions={
          <>
            {summary?.dagster_url ? (
              <Button asChild size="sm" variant="outline">
                <a href={summary.dagster_url} rel="noreferrer" target="_blank">
                  <ExternalLink aria-hidden="true" />
                  새 창
                </a>
              </Button>
            ) : null}
            <RefreshButton busy={summaryQuery.isFetching} onClick={() => void summaryQuery.refetch()} />
          </>
        }
      >
        {summaryQuery.isPending ? (
          <Skeleton className="h-[520px] w-full" />
        ) : summary?.dagster_url ? (
          <iframe
            className="min-h-[520px] w-full rounded-lg border border-border bg-background"
            referrerPolicy="no-referrer"
            sandbox="allow-scripts allow-forms allow-popups allow-downloads allow-same-origin"
            src={summary.dagster_url}
            title="Dagster UI"
          />
        ) : (
          <p className="wizard-hint">Dagster URL이 설정되지 않았습니다.</p>
        )}
      </Panel>

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
          dagsterUrl={summary?.dagster_url ?? ""}
          detail={runDetail}
          error={runDetailQuery.error}
          isError={runDetailQuery.isError}
          isFetching={runDetailQuery.isFetching}
          isPending={runDetailQuery.isPending && Boolean(selectedRunId)}
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
  dagsterUrl,
  detail,
  error,
  isError,
  isFetching,
  isPending,
  onRefresh,
  selectedRunId
}: {
  dagsterUrl: string;
  detail: DagsterRunDetailData | undefined;
  error: unknown;
  isError: boolean;
  isFetching: boolean;
  isPending: boolean;
  onRefresh: () => void;
  selectedRunId: string | null;
}) {
  const run = detail?.run;
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
          <VirtualTable
            as="table"
            compact
            caption="Dagster run events"
            columns={eventColumns}
            emptyHint="event log가 없습니다."
            getSearchText={(row) =>
              `${row.event_type} ${row.level ?? ""} ${row.step_id ?? ""} ${row.message ?? ""}`
            }
            rowKey={(row) => `${row.timestamp ?? ""}:${row.event_type}:${row.step_id ?? ""}`}
            rows={detail.events ?? []}
            searchPlaceholder="event 검색"
            wrapCells
          />
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
