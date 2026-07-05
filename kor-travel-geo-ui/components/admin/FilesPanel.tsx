"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { HelpTip } from "@/components/admin/shared/HelpTip";
import { EmptyState } from "@/components/admin/shared/EmptyState";
import { KeyValueGrid } from "@/components/admin/shared/KeyValueGrid";
import { MetricTile } from "@/components/admin/shared/MetricTile";
import { RefreshButton } from "@/components/admin/shared/RefreshButton";
import { DocumentNavLink } from "@/components/layout/DocumentNavLink";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { NativeSelect } from "@/components/ui/native-select";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { VirtualTable, type VirtualColumn } from "@/components/ui/VirtualTable";
import { ADMIN_PAGES } from "@/lib/admin-pages";
import { getErrorMessage, requestJson } from "@/lib/api";
import {
  fileInventoryPaths,
  fileKindLabels,
  lifecycleOf,
  type FileInventoryItem,
  type FileInventoryPage,
  type FileInventorySourceDetail
} from "@/lib/file-inventory";
import { formatBytes, formatTimestamp } from "@/lib/format";

const KIND_OPTIONS = [
  { value: "all", label: "전체" },
  { value: "source_group", label: "원천 파일" },
  { value: "artifact", label: "백업/산출물" },
  { value: "orphan_object", label: "저장소 객체" }
];

export function FilesPanel() {
  const [kind, setKind] = useState("all");
  const [lifecycle, setLifecycle] = useState("");
  const [temporaryOnly, setTemporaryOnly] = useState(false);
  const [selected, setSelected] = useState<FileInventoryItem | null>(null);

  const listPath = fileInventoryPaths.list({ kind, lifecycle, temporaryOnly });
  const {
    data: inventoryData,
    isPending,
    isError,
    error,
    isFetching,
    refetch
  } = useQuery({
    queryKey: ["file-inventory", listPath],
    queryFn: () => requestJson<FileInventoryPage>(listPath)
  });

  const items = useMemo(() => inventoryData?.items ?? [], [inventoryData]);
  const summary = inventoryData?.summary;
  const lifecycleOptions = useMemo(() => {
    const present = new Set(items.map((item) => item.lifecycle));
    if (lifecycle) present.add(lifecycle);
    return [...present].sort();
  }, [items, lifecycle]);

  const columns = useMemo<VirtualColumn<FileInventoryItem>[]>(
    () => [
      {
        key: "name",
        header: "이름",
        sortValue: (row) => row.name,
        cell: (row) => (
          <span className="inline-flex max-w-full items-center gap-2">
            <Badge tone="neutral">{fileKindLabels[row.file_kind] ?? row.file_kind}</Badge>
            <span className="truncate font-semibold" title={row.name}>
              {row.name}
            </span>
          </span>
        )
      },
      {
        key: "category",
        header: "분류",
        sortValue: (row) => row.category,
        cell: (row) => row.category
      },
      {
        key: "lifecycle",
        header: "상태",
        sortValue: (row) => row.lifecycle,
        cell: (row) => {
          const meta = lifecycleOf(row.lifecycle);
          return <StatusBadge value={meta.label} tone={badgeToneOf(meta.tone)} />;
        }
      },
      {
        key: "in_use",
        header: "사용",
        sortValue: (row) => (row.in_use ? 1 : 0),
        cell: (row) =>
          row.in_use ? (
            <Badge tone="ok">사용 중</Badge>
          ) : row.temporary ? (
            <Badge tone="warn">임시</Badge>
          ) : (
            <span className="text-muted-foreground">—</span>
          )
      },
      {
        key: "size",
        header: "크기",
        align: "right",
        sortValue: (row) => row.size_bytes ?? -1,
        cell: (row) => formatBytes(row.size_bytes)
      },
      {
        key: "acquired",
        header: "받은 시각",
        sortValue: (row) => row.acquired_at ?? "",
        cell: (row) => formatTimestamp(row.acquired_at)
      },
      {
        key: "loaded",
        header: "마지막 적재",
        sortValue: (row) => row.last_loaded_at ?? "",
        cell: (row) => formatTimestamp(row.last_loaded_at)
      },
      {
        key: "issues",
        header: "이슈",
        align: "right",
        sortValue: (row) => row.open_issue_count ?? 0,
        cell: (row) =>
          row.open_issue_count ? (
            <Badge tone="error">{row.open_issue_count}건</Badge>
          ) : (
            <span className="text-muted-foreground">—</span>
          )
      }
    ],
    []
  );

  return (
    <div className="grid gap-4">
      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile label="전체 파일" value={summary?.total_count ?? 0} loading={isPending} />
        <MetricTile label="사용 중" value={summary?.in_use_count ?? 0} loading={isPending} />
        <MetricTile label="임시/정리 대상" value={summary?.temporary_count ?? 0} loading={isPending} />
        <MetricTile
          label="총 용량"
          value={formatBytes(summary?.total_bytes)}
          loading={isPending}
          hint={summary?.open_issue_count ? `미해결 이슈 ${summary.open_issue_count}건` : undefined}
        />
      </div>

      <Panel
        title="파일 인벤토리"
        description="원천 파일·백업·저장소 객체가 어디에 연결되어 어떻게 쓰이는지 추적합니다."
        badges={
          <HelpTip label="파일 인벤토리 도움말">
            원천 파일 그룹, 백업/산출물(artifact), DB에 등록되지 않은 저장소 객체를 한
            목록으로 보여 줍니다. 행을 클릭하면 연결 상세(업로드 세션·매칭 세트·적재
            이력)를 확인할 수 있습니다.
          </HelpTip>
        }
        actions={<RefreshButton busy={isFetching} onClick={() => void refetch()} />}
      >
        <div className="mb-3 flex flex-wrap items-end gap-3">
          <Field className="w-40">
            <FieldLabel htmlFor="files-kind">종류</FieldLabel>
            <NativeSelect
              id="files-kind"
              value={kind}
              onChange={(event) => setKind(event.target.value)}
            >
              {KIND_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field className="w-44">
            <FieldLabel htmlFor="files-lifecycle">상태 필터</FieldLabel>
            <NativeSelect
              id="files-lifecycle"
              value={lifecycle}
              onChange={(event) => setLifecycle(event.target.value)}
            >
              <option value="">전체</option>
              {lifecycleOptions.map((value) => (
                <option key={value} value={value}>
                  {lifecycleOf(value).label}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <label className="flex min-h-11 items-center gap-2 text-sm" htmlFor="files-temp-only">
            <Checkbox
              id="files-temp-only"
              checked={temporaryOnly}
              onCheckedChange={(checked) => setTemporaryOnly(checked === true)}
            />
            임시/정리 대상만
          </label>
        </div>

        {isPending ? (
          <div aria-busy="true" className="grid gap-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : isError ? (
          <Alert role="alert" variant="destructive">
            <AlertTitle>파일 목록을 불러오지 못했습니다</AlertTitle>
            <AlertDescription>
              <p>{getErrorMessage(error)}</p>
              <Button size="sm" variant="outline" onClick={() => void refetch()}>
                다시 시도
              </Button>
            </AlertDescription>
          </Alert>
        ) : (
          <VirtualTable
            as="table"
            caption="파일 인벤토리 목록"
            columns={columns}
            emptyHint="저장된 파일이 없습니다."
            getSearchText={(row) => `${row.name} ${row.category} ${row.storage_ref ?? ""}`}
            initialSortKey="acquired"
            initialSortDir="desc"
            onRowClick={(row) => setSelected(row)}
            rowKey={(row) => `${row.file_kind}:${row.id}`}
            rows={[...items]}
            searchPlaceholder="파일 검색"
          />
        )}
      </Panel>

      <FileDetailDialog item={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function badgeToneOf(tone: string): "ok" | "warn" | "error" | undefined {
  return tone === "ok" || tone === "warn" || tone === "error" ? tone : undefined;
}

function FileDetailDialog({
  item,
  onClose
}: {
  item: FileInventoryItem | null;
  onClose: () => void;
}) {
  const isSourceGroup = item?.file_kind === "source_group";
  const {
    data: detailData,
    isPending: detailPending,
    isError: detailError,
    error: detailErrorValue
  } = useQuery({
    queryKey: ["file-inventory-detail", item?.id],
    enabled: Boolean(item && isSourceGroup),
    queryFn: () =>
      requestJson<FileInventorySourceDetail>(
        fileInventoryPaths.sourceGroupDetail(item?.id ?? "")
      )
  });

  if (!item) return null;
  const meta = lifecycleOf(item.lifecycle);

  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>파일 상세</DialogTitle>
          <DialogDescription className="break-all">{item.name}</DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">{fileKindLabels[item.file_kind] ?? item.file_kind}</Badge>
            <StatusBadge value={meta.label} tone={badgeToneOf(meta.tone)} />
            {item.in_use ? <Badge tone="ok">사용 중</Badge> : null}
            {item.temporary ? <Badge tone="warn">임시</Badge> : null}
            <HelpTip label="상태 도움말">{meta.hint}</HelpTip>
          </div>

          <KeyValueGrid
            items={[
              { label: "분류", value: item.category },
              { label: "원본 상태", value: item.state, help: "백엔드가 기록한 원본 state 값입니다." },
              { label: "크기", value: formatBytes(item.size_bytes) },
              { label: "파일 수", value: item.file_count ?? "—" },
              { label: "기준년월", value: item.user_yyyymm ?? "—" },
              { label: "받은 시각", value: formatTimestamp(item.acquired_at) },
              { label: "등록 시각", value: formatTimestamp(item.registered_at) },
              { label: "마지막 검증", value: formatTimestamp(item.last_verified_at) },
              {
                label: "마지막 적재",
                value: formatTimestamp(item.last_loaded_at),
                help: "이 파일이 포함된 매칭 세트가 마지막으로 적재 완료된 시각입니다."
              },
              { label: "만료 시각", value: formatTimestamp(item.expires_at) },
              {
                label: "저장 위치",
                value: (
                  <code className="break-all text-xs">{item.storage_ref ?? "—"}</code>
                ),
                help: item.storage_kind ? `storage_kind: ${item.storage_kind}` : undefined
              },
              { label: "SHA-256", value: <code className="break-all text-xs">{item.sha256 ?? "—"}</code> }
            ]}
          />

          {isSourceGroup ? (
            detailPending ? (
              <Skeleton className="h-24 w-full" />
            ) : detailError ? (
              <Alert role="alert" variant="destructive">
                <AlertTitle>연결 상세를 불러오지 못했습니다</AlertTitle>
                <AlertDescription>{getErrorMessage(detailErrorValue)}</AlertDescription>
              </Alert>
            ) : detailData ? (
              <SourceGroupLinkage detail={detailData} />
            ) : null
          ) : (
            <ArtifactLinkage item={item} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function SourceGroupLinkage({ detail }: { detail: FileInventorySourceDetail }) {
  return (
    <div className="grid gap-4">
      <section className="grid gap-2">
        <h3 className="m-0 text-sm font-bold">매칭 세트 사용처 ({detail.usages.length})</h3>
        {detail.usages.length === 0 ? (
          <EmptyState>이 파일을 참조하는 매칭 세트가 없습니다.</EmptyState>
        ) : (
          <ul className="m-0 grid list-none gap-2 p-0">
            {detail.usages.map((usage) => (
              <li
                key={usage.source_match_set_id}
                className="flex flex-wrap items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm"
              >
                <StatusBadge
                  value={usage.state === "active" ? "활성" : usage.state}
                  tone={usage.state === "active" ? "ok" : undefined}
                />
                <span className="font-semibold">{usage.name}</span>
                {usage.role ? <Badge tone="neutral">{usage.role}</Badge> : null}
                <span className="ml-auto text-xs text-muted-foreground">
                  마지막 적재 {formatTimestamp(usage.last_loaded_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="grid gap-2">
        <h3 className="m-0 text-sm font-bold">구성 파일 ({detail.files.length})</h3>
        {detail.files.length === 0 ? (
          <EmptyState>등록된 파일이 없습니다.</EmptyState>
        ) : (
          <ul className="m-0 grid list-none gap-1 p-0 text-sm">
            {detail.files.map((file) => (
              <li key={file.source_file_id} className="flex flex-wrap items-center gap-2">
                <span className="truncate" title={file.original_filename}>
                  {file.original_filename}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatBytes(file.size_bytes)} · 검증 {formatTimestamp(file.last_verified_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="grid gap-2">
        <h3 className="m-0 text-sm font-bold">업로드 이력 ({detail.sessions.length})</h3>
        {detail.sessions.length === 0 ? (
          <EmptyState>업로드 세션 기록이 없습니다.</EmptyState>
        ) : (
          <ul className="m-0 grid list-none gap-1 p-0 text-sm">
            {detail.sessions.map((session) => (
              <li key={session.source_upload_session_id} className="flex flex-wrap items-center gap-2">
                <Badge tone="neutral">{session.state}</Badge>
                <span className="text-xs text-muted-foreground">
                  시작 {formatTimestamp(session.created_at)} · 등록{" "}
                  {formatTimestamp(session.registered_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {detail.open_issues.length > 0 ? (
        <Alert role="alert" variant="warning">
          <AlertTitle>미해결 저장소 이슈 {detail.open_issues.length}건</AlertTitle>
          <AlertDescription>
            <ul className="m-0 list-disc pl-4">
              {detail.open_issues.map((issue) => (
                <li key={issue.source_storage_reconcile_item_id}>
                  {issue.issue_type} ({issue.severity})
                </li>
              ))}
            </ul>
            <Button asChild size="sm" variant="outline">
              <DocumentNavLink href={ADMIN_PAGES.sourceFiles.path}>
                원천 파일 화면에서 처리
              </DocumentNavLink>
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button asChild size="sm" variant="outline">
          <DocumentNavLink href={ADMIN_PAGES.sourceFiles.path}>
            원천 파일 화면으로 이동
          </DocumentNavLink>
        </Button>
      </div>
    </div>
  );
}

function ArtifactLinkage({ item }: { item: FileInventoryItem }) {
  const isOrphan = item.file_kind === "orphan_object";
  return (
    <div className="grid gap-3">
      {isOrphan ? (
        <Alert role="alert" variant="warning">
          <AlertTitle>DB에 등록되지 않은 저장소 객체입니다</AlertTitle>
          <AlertDescription>
            <p>원천 파일 화면의 RustFS 정합성 탭에서 등록하거나 정리할 수 있습니다.</p>
            <Button asChild size="sm" variant="outline">
              <DocumentNavLink href={ADMIN_PAGES.sourceFiles.path}>
                RustFS 정합성으로 이동
              </DocumentNavLink>
            </Button>
          </AlertDescription>
        </Alert>
      ) : (
        <>
          <KeyValueGrid
            items={[
              { label: "작업 ID", value: item.job_id ?? "—", help: "이 파일을 만든 백업/복원 작업입니다." },
              { label: "데이터셋 스냅샷", value: item.dataset_snapshot_id ?? "—" },
              { label: "서빙 릴리스", value: item.serving_release_id ?? "—" }
            ]}
          />
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm" variant="outline">
              <DocumentNavLink href={ADMIN_PAGES.backups.path}>
                백업/복원 화면으로 이동
              </DocumentNavLink>
            </Button>
            <Button asChild size="sm" variant="outline">
              <DocumentNavLink href={ADMIN_PAGES.ops.path}>운영 이력으로 이동</DocumentNavLink>
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
