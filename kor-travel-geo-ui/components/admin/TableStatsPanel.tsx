"use client";

import { useQuery } from "@tanstack/react-query";
import { RefreshButton } from "@/components/admin/shared/RefreshButton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/skeleton";
import { type VirtualColumn, VirtualTable } from "@/components/ui/VirtualTable";
import { getErrorMessage, requestJson, type TableStat } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { tableDescription } from "@/lib/table-descriptions";

const columns: VirtualColumn<TableStat>[] = [
  {
    key: "table_name",
    header: "테이블",
    sortValue: (r) => r.table_name,
    cell: (r) => r.table_name
  },
  {
    key: "description",
    header: "설명",
    cellClassName: "table-description",
    cell: (r) => tableDescription(r.table_name)
  },
  {
    key: "row_count",
    header: "행 수",
    align: "right",
    sortValue: (r) => r.row_count,
    cell: (r) => r.row_count.toLocaleString()
  },
  {
    key: "size_bytes",
    header: "크기",
    align: "right",
    sortValue: (r) => r.size_bytes ?? null,
    cell: (r) => formatBytes(r.size_bytes)
  },
  {
    key: "updated_at",
    header: "최근 갱신",
    sortValue: (r) => r.updated_at ?? null,
    cell: (r) => r.updated_at ?? "-"
  }
];

export function TableStatsPanel() {
  const { data, error, isError, isFetching, isPending, refetch } = useQuery({
    queryKey: ["admin-tables"],
    queryFn: () => requestJson<TableStat[]>("/admin/tables")
  });

  return (
    <Panel
      title="PostgreSQL 테이블"
      actions={<RefreshButton busy={isFetching} onClick={() => void refetch()} />}
    >
      {isPending ? (
        <div aria-hidden="true" className="grid gap-2">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      ) : isError ? (
        <Alert role="alert" variant="destructive">
          <AlertTitle>테이블 통계를 불러오지 못했습니다</AlertTitle>
          <AlertDescription>
            <p>{getErrorMessage(error)}</p>
            <Button onClick={() => void refetch()} size="sm" type="button" variant="outline">
              다시 시도
            </Button>
          </AlertDescription>
        </Alert>
      ) : (
        <VirtualTable
          as="table"
          caption="PostgreSQL 테이블 통계"
          columns={columns}
          emptyHint="테이블 통계가 없습니다."
          getSearchText={(r) => `${r.table_name} ${tableDescription(r.table_name)}`}
          rowKey={(r) => r.table_name}
          rows={data ?? []}
          searchPlaceholder="테이블 검색"
        />
      )}
    </Panel>
  );
}
