"use client";

import {
  Ban,
  CheckCircle2,
  FileUp,
  Play,
  RefreshCw,
  RotateCcw,
  Send,
  UploadCloud
} from "lucide-react";
import {
  ChangeEvent,
  DragEvent,
  FormEvent,
  useMemo,
  useReducer,
  useRef,
  useState
} from "react";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  API_BASE,
  LoadJobStatus,
  SourceCandidate,
  SourceKind,
  SourceSetDiscovery,
  SourceSetPlan,
  UploadFileStatus,
  UploadSetStatus,
  backendPath,
  postJson,
  requestJson
} from "@/lib/api";
import { formatBytes } from "@/lib/format";
import {
  confirmationTokenFor,
  loadWorkflowReducer,
  percent
} from "@/lib/load-workflow";

type LocalUploadFile = {
  key: string;
  file: File;
  relativePath: string;
  uploadedBytes: number;
  state: "pending" | "uploading" | "uploaded" | "failed" | "cancelled";
  result?: UploadFileStatus;
  error?: string;
};

const sourceOrder: SourceKind[] = [
  "juso",
  "parcel_link",
  "locsum",
  "navi",
  "shp",
  "roadaddr_entrance",
  "sppn_makarea",
  "pobox",
  "bulk"
];

const sourceLabels: Record<SourceKind, string> = {
  juso: "도로명주소",
  parcel_link: "지번 연결",
  locsum: "위치요약",
  navi: "내비게이션",
  shp: "전자지도 SHP",
  roadaddr_entrance: "출입구",
  sppn_makarea: "국가지점번호 구역",
  pobox: "사서함",
  bulk: "다량배달처"
};

export function LoadConsole() {
  const [state, dispatch] = useReducer(loadWorkflowReducer, "idle");
  const [files, setFiles] = useState<LocalUploadFile[]>([]);
  const [uploadSet, setUploadSet] = useState<UploadSetStatus | null>(null);
  const [discovery, setDiscovery] = useState<SourceSetDiscovery | null>(null);
  const [plan, setPlan] = useState<SourceSetPlan | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [dropActive, setDropActive] = useState(false);
  const [jobs, setJobs] = useState<LoadJobStatus[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<unknown>(null);
  const activeUpload = useRef<XMLHttpRequest | null>(null);
  const uploadCancelRequested = useRef(false);

  const selectedBytes = useMemo(
    () => files.reduce((total, item) => total + item.file.size, 0),
    [files]
  );
  const uploadedBytes = useMemo(
    () => files.reduce((total, item) => total + item.uploadedBytes, 0),
    [files]
  );
  const uploadPercent = percent(uploadedBytes, selectedBytes);
  const activeJob =
    jobs.find((job) => job.job_id === activeJobId) ??
    jobs.find((job) => ["queued", "running"].includes(job.state));
  const loadPercent = activeJob ? Math.round(activeJob.progress * 100) : 0;
  const expectedConfirmation = confirmationTokenFor(discovery?.yyyymm_by_kind ?? {});
  const canCreatePlan =
    discovery !== null &&
    discovery.missing_required.length === 0 &&
    (!discovery.mixed_yyyymm || confirmation === expectedConfirmation);

  function selectFiles(fileList: FileList | File[]) {
    const nextFiles = Array.from(fileList).map((file, index) => {
      const relativePath = file.webkitRelativePath || file.name;
      return {
        key: `${relativePath}:${file.size}:${file.lastModified}:${index}`,
        file,
        relativePath,
        uploadedBytes: 0,
        state: "pending" as const
      };
    });
    setFiles(nextFiles);
    setUploadSet(null);
    setDiscovery(null);
    setPlan(null);
    setConfirmation("");
    setLastResult({ selected_files: nextFiles.length });
    dispatch({ type: "reset" });
  }

  function onFileInput(event: ChangeEvent<HTMLInputElement>) {
    if (event.target.files) {
      selectFiles(event.target.files);
      event.target.value = "";
    }
  }

  function onDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDropActive(true);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDropActive(false);
    selectFiles(event.dataTransfer.files);
  }

  async function uploadSelectedFiles(event: FormEvent) {
    event.preventDefault();
    if (files.length === 0) {
      setLastResult({ error: "선택된 파일이 없습니다." });
      return;
    }
    dispatch({ type: "upload_start" });
    uploadCancelRequested.current = false;
    try {
      const created = await postJson<UploadSetStatus>("/admin/uploads", {
        purpose: "full_load_source_set"
      });
      setUploadSet(created);
      for (const item of files) {
        const uploaded = await uploadOneFile(created.upload_set_id, item);
        setFiles((current) =>
          current.map((file) =>
            file.key === item.key
              ? {
                  ...file,
                  uploadedBytes: uploaded.uploaded_bytes,
                  state: "uploaded",
                  result: uploaded
                }
              : file
          )
        );
      }
      const status = await requestJson<UploadSetStatus>(
        `/admin/uploads/${created.upload_set_id}`
      );
      setUploadSet(status);
      const discovered = await postJson<SourceSetDiscovery>("/admin/load-sources/discover", {
        upload_set_id: created.upload_set_id,
        include_optional: true
      });
      setDiscovery(discovered);
      setLastResult(discovered);
      dispatch({ type: "upload_done" });
    } catch (error) {
      setLastResult({ error: error instanceof Error ? error.message : String(error) });
      dispatch({ type: uploadCancelRequested.current ? "cancel" : "fail" });
    } finally {
      activeUpload.current = null;
    }
  }

  function uploadOneFile(
    uploadSetId: string,
    item: LocalUploadFile
  ): Promise<UploadFileStatus> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      activeUpload.current = xhr;
      const params = new URLSearchParams({
        filename: item.file.name,
        relative_path: item.relativePath
      });
      xhr.open(
        "PUT",
        `${API_BASE}${backendPath(`/admin/uploads/${uploadSetId}/files?${params}`)}`
      );
      xhr.upload.onprogress = (event) => {
        const uploaded = event.lengthComputable ? event.loaded : item.file.size;
        setFiles((current) =>
          current.map((file) =>
            file.key === item.key
              ? { ...file, state: "uploading", uploadedBytes: uploaded }
              : file
          )
        );
      };
      xhr.onload = () => {
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(new Error(xhr.responseText || `${xhr.status} ${xhr.statusText}`));
          return;
        }
        resolve(JSON.parse(xhr.responseText) as UploadFileStatus);
      };
      xhr.onerror = () => reject(new Error("업로드 요청이 실패했습니다."));
      xhr.onabort = () => reject(new Error("업로드가 취소되었습니다."));
      xhr.send(item.file);
    });
  }

  async function cancelUpload() {
    uploadCancelRequested.current = true;
    activeUpload.current?.abort();
    if (uploadSet) {
      const cancelled = await postJson<UploadSetStatus>(
        `/admin/uploads/${uploadSet.upload_set_id}/cancel`,
        {}
      );
      setUploadSet(cancelled);
    }
    setFiles((current) =>
      current.map((file) =>
        file.state === "uploaded" ? file : { ...file, state: "cancelled" }
      )
    );
    dispatch({ type: "cancel" });
  }

  async function createPlan() {
    if (!discovery || !uploadSet || !canCreatePlan) return;
    const versions = Object.fromEntries(
      Object.entries(discovery.yyyymm_by_kind).filter(([, value]) => Boolean(value))
    );
    try {
      const result = await postJson<SourceSetPlan>("/admin/load-sources/plan", {
        upload_set_id: uploadSet.upload_set_id,
        versions,
        include_optional: true,
        allow_mixed_yyyymm: discovery.mixed_yyyymm,
        confirmation_token: discovery.mixed_yyyymm ? confirmation : null,
        acknowledged_by: "ui"
      });
      setPlan(result);
      setLastResult(result);
      dispatch({ type: "plan_ready" });
    } catch (error) {
      setLastResult({ error: error instanceof Error ? error.message : String(error) });
      dispatch({ type: "fail" });
    }
  }

  async function submitPlan() {
    if (!plan) return;
    dispatch({ type: "process_start" });
    try {
      const result = await postJson<LoadJobStatus>("/admin/loads", {
        kind: "full_load_batch",
        payload: plan.batch_payload
      });
      setActiveJobId(result.job_id);
      setLastResult(result);
      await refreshJobs();
    } catch (error) {
      setLastResult({ error: error instanceof Error ? error.message : String(error) });
      dispatch({ type: "fail" });
    }
  }

  async function refreshJobs() {
    const result = await requestJson<LoadJobStatus[]>("/admin/loads?limit=20");
    setJobs(result);
    if (
      activeJobId &&
      result.some(
        (job) =>
          job.job_id === activeJobId &&
          ["done", "failed", "cancelled"].includes(job.state)
      )
    ) {
      dispatch({ type: "finish" });
    }
  }

  async function cancelActiveJob() {
    const jobId = activeJob?.job_id;
    if (!jobId) return;
    const result = await postJson<LoadJobStatus>(`/admin/loads/${jobId}/cancel`, {});
    setLastResult(result);
    await refreshJobs();
    dispatch({ type: "cancel" });
  }

  async function refreshMv() {
    setLastResult(await postJson("/admin/maintenance/refresh-mv?strategy=concurrent", {}));
    await refreshJobs();
  }

  function resetAll() {
    activeUpload.current?.abort();
    uploadCancelRequested.current = false;
    setFiles([]);
    setUploadSet(null);
    setDiscovery(null);
    setPlan(null);
    setConfirmation("");
    setActiveJobId(null);
    setLastResult(null);
    dispatch({ type: "reset" });
  }

  return (
    <div className="grid two">
      <Panel
        title="Source Set Upload"
        actions={<span className="status ok">{state}</span>}
      >
        <form className="form-grid" onSubmit={uploadSelectedFiles}>
          <div
            className={`drop-zone${dropActive ? " active" : ""}`}
            onDragLeave={() => setDropActive(false)}
            onDragOver={onDragOver}
            onDrop={onDrop}
          >
            <UploadCloud size={26} />
            <strong>파일 선택 또는 드롭</strong>
            <span>{files.length} files · {formatBytes(selectedBytes)}</span>
            <label className="button secondary">
              <FileUp size={16} />
              파일 선택
              <input hidden multiple onChange={onFileInput} type="file" />
            </label>
          </div>
          <ProgressLine label="업로드" percentValue={uploadPercent} />
          <div className="button-row">
            <button
              className="button"
              disabled={files.length === 0 || state === "uploading"}
              type="submit"
            >
              <UploadCloud size={16} />
              업로드
            </button>
            <button
              className="button secondary"
              disabled={state !== "uploading" && !uploadSet}
              onClick={cancelUpload}
              type="button"
            >
              <Ban size={16} />
              업로드 취소
            </button>
            <button className="button secondary" onClick={resetAll} type="button">
              <RotateCcw size={16} />
              초기화
            </button>
          </div>
        </form>
      </Panel>

      <Panel
        title="Source Set Review"
        actions={
          discovery?.mixed_yyyymm ? (
            <span className="status warn">mixed</span>
          ) : (
            <span className="status ok">{discovery ? "ready" : "idle"}</span>
          )
        }
      >
        <div className="form-grid">
          <SourceSummary discovery={discovery} />
          {discovery?.mixed_yyyymm ? (
            <div className="confirm-box">
              <label htmlFor="source-set-confirm">확인 문구</label>
              <input
                id="source-set-confirm"
                onChange={(event) => setConfirmation(event.target.value)}
                value={confirmation}
              />
            </div>
          ) : null}
          <div className="button-row">
            <button
              className="button"
              disabled={!canCreatePlan || plan !== null}
              onClick={createPlan}
              type="button"
            >
              <CheckCircle2 size={16} />
              계획 확정
            </button>
            <button
              className="button"
              disabled={plan === null || state === "processing"}
              onClick={submitPlan}
              type="button"
            >
              <Send size={16} />
              적재 시작
            </button>
            <button className="button secondary" onClick={refreshJobs} type="button">
              <RefreshCw size={16} />
              새로고침
            </button>
          </div>
        </div>
      </Panel>

      <Panel title="Upload Files">
        <table className="table compact">
          <thead>
            <tr>
              <th>file</th>
              <th>state</th>
              <th>progress</th>
              <th>source</th>
            </tr>
          </thead>
          <tbody>
            {files.map((file) => (
              <tr key={file.key}>
                <td className="path-cell">{file.relativePath}</td>
                <td>
                  <StatusBadge value={file.state} />
                </td>
                <td>{percent(file.uploadedBytes, file.file.size)}%</td>
                <td>{file.result?.source_kind ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel title="Jobs">
        <div className="form-grid">
          <ProgressLine label="적재" percentValue={loadPercent} />
          <div className="button-row">
            <button
              className="button secondary"
              disabled={!activeJob}
              onClick={cancelActiveJob}
              type="button"
            >
              <Ban size={16} />
              적재 취소
            </button>
            <button className="button secondary" onClick={refreshMv} type="button">
              <Play size={16} />
              MV refresh
            </button>
          </div>
          <table className="table compact">
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
        </div>
      </Panel>

      <Panel title="Source Set JSON">
        <JsonBlock value={plan ?? discovery ?? uploadSet ?? { status: "READY" }} />
      </Panel>
      <Panel title="Last Response">
        <JsonBlock value={lastResult ?? { status: "READY" }} />
      </Panel>

      {discovery?.mixed_yyyymm && !plan ? (
        <div className="modal-backdrop" role="presentation">
          <div aria-modal="true" className="modal" role="dialog">
            <h2>기준월 확인</h2>
            <SourceSummary discovery={discovery} />
            <div className="confirm-box">
              <label htmlFor="source-set-confirm-modal">{expectedConfirmation}</label>
              <input
                id="source-set-confirm-modal"
                onChange={(event) => setConfirmation(event.target.value)}
                value={confirmation}
              />
            </div>
            <div className="button-row">
              <button
                className="button"
                disabled={!canCreatePlan}
                onClick={createPlan}
                type="button"
              >
                <CheckCircle2 size={16} />
                확인
              </button>
              <button
                className="button secondary"
                onClick={() => setDiscovery(null)}
                type="button"
              >
                <Ban size={16} />
                닫기
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ProgressLine({
  label,
  percentValue
}: {
  label: string;
  percentValue: number;
}) {
  return (
    <div className="progress-line">
      <div className="progress-label">
        <span>{label}</span>
        <strong>{percentValue}%</strong>
      </div>
      <div className="progress-shell">
        <div className="progress-bar" style={{ width: `${percentValue}%` }} />
      </div>
    </div>
  );
}

function SourceSummary({ discovery }: { discovery: SourceSetDiscovery | null }) {
  if (!discovery) {
    return <JsonBlock value={{ status: "NO_SOURCE_SET" }} />;
  }
  return (
    <table className="table compact">
      <thead>
        <tr>
          <th>source</th>
          <th>yyyymm</th>
          <th>files</th>
          <th>path</th>
        </tr>
      </thead>
      <tbody>
        {sourceOrder.map((kind) => {
          const candidate = discovery.recommended[kind] as SourceCandidate | undefined;
          if (!candidate) return null;
          return (
            <tr key={kind}>
              <td>{sourceLabels[kind]}</td>
              <td>{candidate.inferred_yyyymm ?? "-"}</td>
              <td>{candidate.file_count ?? "-"}</td>
              <td className="path-cell">{candidate.path}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
