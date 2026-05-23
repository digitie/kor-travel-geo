"use client";

import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { TableStat, requestJson } from "@/lib/api";
import { formatBytes } from "@/lib/format";

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
            <th>table</th>
            <th>rows</th>
            <th>size</th>
            <th>updated_at</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.table_name}>
              <td>{row.table_name}</td>
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
