"use client";

import {
  Archive,
  ArrowRight,
  BarChart3,
  Database,
  FileText,
  Files,
  FolderUp,
  ListChecks,
  Settings,
  ShieldCheck,
  Workflow
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { DocumentNavLink } from "@/components/layout/DocumentNavLink";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  ADMIN_NAV_GROUPS,
  ADMIN_PAGES,
  type AdminPageKey
} from "@/lib/admin-pages";
import {
  requestJson,
  type BackupArtifact,
  type ConsistencyReportSummary,
  type ServingRelease
} from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import { shortHash } from "@/lib/source-files";

const pageIcons: Record<AdminPageKey, typeof Archive> = {
  home: ShieldCheck,
  sourceFiles: FolderUp,
  files: Files,
  consistency: ListChecks,
  backups: Archive,
  dagster: Workflow,
  ops: ShieldCheck,
  logs: FileText,
  tables: Database,
  cache: BarChart3,
  settings: Settings,
  load: FolderUp
};

/**
 * 관리 홈 — 운영 상태 3종 요약과 기능 그룹 안내.
 * 상태 조회는 read-only GET 3건뿐이며 실패 시 카드에 "확인 불가"만 표시한다.
 */
export function AdminHome() {
  return (
    <div className="admin-home">
      <StatusStrip />
      {ADMIN_NAV_GROUPS.map((group) => (
        <Panel className="admin-nav-panel" key={group.title} title={group.title}>
          <ul className="m-0 grid list-none gap-1 p-0 md:grid-cols-2">
            {group.keys.map((key) => {
              const page = ADMIN_PAGES[key];
              const Icon = pageIcons[key];
              return (
                <li key={key}>
                  <DocumentNavLink
                    href={page.path}
                    className="group relative flex min-h-11 items-center gap-2.5 rounded-control px-3 text-sm font-medium whitespace-nowrap text-text-secondary transition-[color,background-color,border-color] duration-fast ease-out hover:bg-surface-subtle hover:text-text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:bg-surface-muted"
                  >
                    <Icon aria-hidden="true" className="size-4 shrink-0 text-brand" />
                    <span className="grid min-w-0 gap-0.5">
                      <span className="text-sm font-medium text-text-primary">
                        {page.title}
                      </span>
                      {page.description ? (
                        <span className="text-xs text-text-secondary">
                          {page.description}
                        </span>
                      ) : null}
                    </span>
                    <ArrowRight
                      aria-hidden="true"
                      className="ml-auto size-4 shrink-0 text-text-tertiary opacity-0 transition-opacity duration-fast group-hover:opacity-100 group-focus-visible:opacity-100"
                    />
                  </DocumentNavLink>
                </li>
              );
            })}
          </ul>
        </Panel>
      ))}
    </div>
  );
}

function StatusStrip() {
  return (
    <dl aria-label="운영 상태 요약" className="admin-status-strip">
      <StatusCard title="서빙 릴리스" queryKey="admin-home-release" load={loadActiveRelease} />
      <StatusCard title="최근 백업" queryKey="admin-home-backup" load={loadLatestBackup} />
      <StatusCard
        title="최근 정합성 검증"
        queryKey="admin-home-consistency"
        load={loadLatestConsistency}
      />
    </dl>
  );
}

interface StatusValue {
  headline: string;
  detail?: string;
  badge?: { value: string; tone?: "ok" | "warn" | "error" };
}

function StatusCard({
  title,
  queryKey,
  load
}: {
  title: string;
  queryKey: string;
  load: () => Promise<StatusValue | null>;
}) {
  const { data, isPending, isError } = useQuery({
    queryKey: [queryKey],
    queryFn: load,
    retry: false
  });

  return (
    <div className="admin-status-item">
      <dt className="admin-status-label">{title}</dt>
      {isPending ? (
        <dd className="admin-status-value">
          <Skeleton className="h-8 w-3/4" />
        </dd>
      ) : isError ? (
        <dd className="admin-status-value">
          <span className="text-sm text-muted-foreground">확인 불가</span>
        </dd>
      ) : data == null ? (
        <dd className="admin-status-value">
          <span className="text-sm text-muted-foreground">기록 없음</span>
        </dd>
      ) : (
        <dd className="admin-status-value">
          <div className="flex min-w-0 flex-wrap items-baseline gap-2">
            <strong className="break-all text-sm">{data.headline}</strong>
            {data.badge ? <StatusBadge value={data.badge.value} tone={data.badge.tone} /> : null}
          </div>
          {data.detail ? <span className="admin-status-detail">{data.detail}</span> : null}
        </dd>
      )}
    </div>
  );
}

async function loadActiveRelease(): Promise<StatusValue | null> {
  const releases = await requestJson<ServingRelease[]>("/admin/ops/releases?limit=5");
  const active = releases.find((release) => release.state === "active") ?? releases[0];
  if (!active) return null;
  const activatedAt = `활성화 ${formatTimestamp(active.activated_at ?? active.created_at)}`;
  const token = active.version_token ? shortHash(active.version_token, 16) : null;
  return {
    headline: active.mv_name,
    detail: token ? `${activatedAt} · ${token}` : activatedAt,
    badge: {
      value: active.state,
      tone: active.state === "active" ? "ok" : active.state === "failed" ? "error" : "warn"
    }
  };
}

async function loadLatestBackup(): Promise<StatusValue | null> {
  const artifacts = await requestJson<BackupArtifact[]>("/admin/backups?limit=5");
  const latest = artifacts[0];
  if (!latest) return null;
  return {
    headline: latest.display_name ?? latest.artifact_id,
    detail: `생성 ${formatTimestamp(latest.created_at)}`,
    badge: {
      value: latest.state,
      tone:
        latest.state === "available" ? "ok" : latest.state === "failed" ? "error" : "warn"
    }
  };
}

async function loadLatestConsistency(): Promise<StatusValue | null> {
  const reports = await requestJson<ConsistencyReportSummary[]>("/admin/consistency");
  const latest = reports[0];
  if (!latest) return null;
  const tone =
    latest.severity_max === "ERROR" ? "error" : latest.severity_max === "WARN" ? "warn" : "ok";
  return {
    headline: latest.report_id,
    detail: `실행 ${formatTimestamp(latest.started_at)}`,
    badge: { value: latest.severity_max, tone }
  };
}
