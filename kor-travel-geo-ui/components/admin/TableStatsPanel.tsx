"use client";

import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { type VirtualColumn, VirtualTable } from "@/components/ui/VirtualTable";
import { TableStat, requestJson } from "@/lib/api";
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
  const [rows, setRows] = useState<TableStat[]>([]);

  async function load() {
    setRows(await requestJson<TableStat[]>("/admin/tables"));
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <Panel
      title="PostgreSQL Tables"
      actions={
        <button className="button secondary" onClick={load} type="button">
          <RefreshCw size={16} />
          새로고침
        </button>
      }
    >
      <VirtualTable
        as="table"
        caption="PostgreSQL 테이블 통계"
        columns={columns}
        emptyHint="테이블 통계가 없습니다."
        getSearchText={(r) => `${r.table_name} ${tableDescription(r.table_name)}`}
        rowKey={(r) => r.table_name}
        rows={rows}
        searchPlaceholder="테이블 검색"
      />
    </Panel>
  );
}
