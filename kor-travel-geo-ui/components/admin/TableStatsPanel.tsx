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
    // `≈` when the count came from the planner's estimate because this database's statistics
    // were reset (restore / hot-swap) and nothing has vacuumed/analyzed since (issue #515).
    // `≈` alone is announced only at high symbol verbosity and `title` never surfaces on
    // touch, so carry the meaning in text for AT instead of relying on either.
    cell: (r) =>
      r.row_count_estimated ? (
        <span title="이 테이블에 대한 vacuum/analyze 기록이 없어 근사치입니다. ANALYZE를 돌리면 값이 갱신되지만, 정확한 행 수는 count(*)로만 확인할 수 있습니다.">
          <span aria-hidden="true">≈ </span>
          <span className="sr-only">약 </span>
          {r.row_count.toLocaleString()}
          <span className="sr-only">, 추정치</span>
        </span>
      ) : (
        r.row_count.toLocaleString()
      )
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
        <>
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
          {/* A `title` tooltip never appears on touch and the sr-only text is invisible, so a
              sighted touch user would otherwise see a bare `≈` with no explanation. Shown only
              when at least one row is actually an estimate. */}
          {(data ?? []).some((r) => r.row_count_estimated) ? (
            <p className="table-stats-legend">
              <span aria-hidden="true">≈</span> 표시는 해당 테이블에 vacuum/analyze 기록이 없어
              행 수가 근사치라는 뜻입니다. 정확한 행 수는 <code>count(*)</code>로만 확인할 수 있습니다.
            </p>
          ) : null}
        </>
      )}
    </Panel>
  );
}
