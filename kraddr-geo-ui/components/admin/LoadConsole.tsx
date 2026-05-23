"use client";

import { RefreshCw, Send, Upload } from "lucide-react";
import { ChangeEvent, FormEvent, useReducer, useState } from "react";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { LoadJobStatus, postJson, requestJson } from "@/lib/api";
import { loadWorkflowReducer } from "@/lib/load-workflow";
import { guessSido } from "@/lib/sido";

const defaultPayloads = {
  juso_text_load: "data/juso/202603_도로명주소 한글_전체분",
  locsum_load: "data/juso/202604_위치정보요약DB_전체분.zip",
  navi_load: "data/juso/202604_내비게이션용DB_전체분",
  shp_polygons_load: "data/juso/도로명주소 전자지도",
  pobox_load: "data/epost/zipcode_full.zip"
};

export function LoadConsole() {
  const [state, dispatch] = useReducer(loadWorkflowReducer, "idle");
  const [payloads, setPayloads] = useState(defaultPayloads);
  const [jobs, setJobs] = useState<LoadJobStatus[]>([]);
  const [uploadResult, setUploadResult] = useState<unknown>(null);
  const [lastResult, setLastResult] = useState<unknown>(null);

  async function submitBatch(event: FormEvent) {
    event.preventDefault();
    dispatch({ type: "process_start" });
    const payload = {
      payloads: Object.fromEntries(
        Object.entries(payloads).map(([kind, path]) => [kind, { path }])
      )
    };
    try {
      const result = await postJson<LoadJobStatus>("/admin/loads", {
        kind: "full_load_batch",
        payload
      });
      setLastResult(result);
      await refreshJobs();
    } catch (error) {
      setLastResult({ error: error instanceof Error ? error.message : String(error) });
    }
  }

  async function uploadFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    dispatch({ type: "upload_start" });
    const sido = guessSido(file.name);
    const params = new URLSearchParams({ filename: file.name });
    if (sido) params.set("sido", sido);
    const response = await fetch(`/api/proxy/v1/admin/upload/sido-zip?${params}`, {
      method: "POST",
      body: file
    });
    const result = (await response.json()) as unknown;
    setUploadResult(result);
    dispatch({ type: "upload_done" });
  }

  async function refreshJobs() {
    const result = await requestJson<LoadJobStatus[]>("/admin/loads?limit=20");
    setJobs(result);
    if (result.every((job) => ["done", "failed", "cancelled"].includes(job.state))) {
      dispatch({ type: "finish" });
    }
  }

  async function refreshMv() {
    setLastResult(await postJson("/admin/maintenance/refresh-mv?strategy=concurrent", {}));
    await refreshJobs();
  }

  return (
    <div className="grid two">
      <Panel
        title="Full Load Batch"
        actions={<span className="status ok">{state}</span>}
      >
        <form className="form-grid" onSubmit={submitBatch}>
          {Object.entries(payloads).map(([kind, path]) => (
            <div className="field" key={kind}>
              <label htmlFor={kind}>{kind}</label>
              <input
                id={kind}
                value={path}
                onChange={(event) =>
                  setPayloads((current) => ({ ...current, [kind]: event.target.value }))
                }
              />
            </div>
          ))}
          <div className="button-row">
            <button className="button" type="submit">
              <Send size={16} />
              Batch 등록
            </button>
            <button className="button secondary" onClick={refreshJobs} type="button">
              <RefreshCw size={16} />
              새로고침
            </button>
            <button className="button secondary" onClick={refreshMv} type="button">
              <RefreshCw size={16} />
              MV refresh
            </button>
          </div>
        </form>
      </Panel>
      <Panel title="Upload">
        <div className="form-grid">
          <label className="button secondary">
            <Upload size={16} />
            ZIP 선택
            <input hidden onChange={uploadFile} type="file" />
          </label>
          <JsonBlock value={uploadResult ?? { status: "READY" }} />
        </div>
      </Panel>
      <Panel title="Jobs">
        <table className="table">
          <thead>
            <tr>
              <th>kind</th>
              <th>state</th>
              <th>progress</th>
              <th>stage</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.job_id}>
                <td>{job.kind}</td>
                <td>
                  <StatusBadge value={job.state} />
                </td>
                <td>{Math.round(job.progress * 100)}%</td>
                <td>{job.current_stage ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel title="Last Response">
        <JsonBlock value={lastResult ?? { status: "READY" }} />
      </Panel>
    </div>
  );
}
