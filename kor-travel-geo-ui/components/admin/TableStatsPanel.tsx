"use client";

import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { TableStat, requestJson } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { tableDescription } from "@/lib/table-descriptions";

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
      <table className="table">
        <thead>
          <tr>
            <th>테이블</th>
            <th>설명</th>
            <th>행 수</th>
            <th>크기</th>
            <th>최근 갱신</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.table_name}>
              <td>{row.table_name}</td>
              <td className="table-description">{tableDescription(row.table_name)}</td>
              <td>{row.row_count.toLocaleString()}</td>
              <td>{formatBytes(row.size_bytes)}</td>
              <td>{row.updated_at ?? "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}
