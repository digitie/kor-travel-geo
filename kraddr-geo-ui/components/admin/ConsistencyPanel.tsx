"use client";

import { Play, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  ConsistencyReport,
  ConsistencyReportSummary,
  postJson,
  requestJson
} from "@/lib/api";

export function ConsistencyPanel() {
  const [reports, setReports] = useState<ConsistencyReportSummary[]>([]);
  const [selected, setSelected] = useState<ConsistencyReport | null>(null);
  const [lastRun, setLastRun] = useState<unknown>(null);

  const openReport = useCallback(async (reportId: string) => {
    setSelected(await requestJson<ConsistencyReport>(`/admin/consistency/${reportId}`));
  }, []);

  const loadReports = useCallback(async () => {
    const next = await requestJson<ConsistencyReportSummary[]>("/admin/consistency");
    setReports(next);
    if (next[0]) {
      await openReport(next[0].report_id);
    }
  }, [openReport]);

  async function runConsistency() {
    setLastRun(await postJson("/admin/consistency/run", { scope: "full" }));
    await loadReports();
  }

  useEffect(() => {
    void loadReports();
  }, [loadReports]);

  return (
    <div className="grid two">
      <Panel
        title="Reports"
        actions={
          <div className="button-row">
            <button className="button secondary" onClick={loadReports} type="button">
              <RefreshCw size={16} />
              새로고침
            </button>
            <button className="button" onClick={runConsistency} type="button">
              <Play size={16} />
              재검증
            </button>
          </div>
        }
      >
        <table className="table">
          <thead>
            <tr>
              <th>report</th>
              <th>severity</th>
              <th>scope</th>
            </tr>
          </thead>
          <tbody>
            {reports.map((report) => (
              <tr key={report.report_id}>
                <td>
                  <button
                    className="button secondary"
                    onClick={() => void openReport(report.report_id)}
                    type="button"
                  >
                    {report.report_id}
                  </button>
                </td>
                <td>
                  <StatusBadge value={report.severity_max} />
                </td>
                <td>{report.scope}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel title="Case Detail">
        {selected ? (
          <div className="grid">
            <div className="grid three">
              {selected.cases.map((item) => (
                <div className="case-tile" key={item.code}>
                  <strong>{item.code}</strong>
                  <p>{item.name}</p>
                  <StatusBadge value={item.severity} />
                  <p>{item.count.toLocaleString()} rows</p>
                </div>
              ))}
            </div>
            <JsonBlock value={selected} />
          </div>
        ) : (
          <JsonBlock value={lastRun ?? { status: "READY" }} />
        )}
      </Panel>
    </div>
  );
}
