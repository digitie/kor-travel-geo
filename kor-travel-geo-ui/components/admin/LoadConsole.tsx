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
  useEffect,
  useMemo,
  useReducer,
  useRef
} from "react";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  API_BASE,
  LoadJobStatus,
  RustfsStorageConfig,
  RustfsSyncLocalResult,
  SourceCandidate,
  SourceKind,
  SourceSetDiscovery,
  SourceSetPlan,
  UploadFileStatus,
  UploadStorageKind,
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

type LoadConsoleUiState = {
  activeJobId: string | null;
  confirmation: string;
  discovery: SourceSetDiscovery | null;
  dropActive: boolean;
  files: LocalUploadFile[];
  jobs: LoadJobStatus[];
  localSyncPath: string;
  localSyncPrefix: string;
  lastResult: unknown;
  plan: SourceSetPlan | null;
  rustfsBusy: boolean;
  rustfsConfig: RustfsStorageConfig | null;
  rustfsMessage: string | null;
  rustfsPrefix: string;
  storageKind: UploadStorageKind;
  uploadSet: UploadSetStatus | null;
};

type LoadConsoleUiAction =
  | { type: "merge"; patch: Partial<LoadConsoleUiState> }
  | { type: "patch_file"; key: string; patch: Partial<LocalUploadFile> }
  | { type: "mark_non_uploaded"; nextState: LocalUploadFile["state"] }
  | { type: "reset" }
  | { type: "select_files"; files: LocalUploadFile[] };

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

const initialLoadConsoleUiState: LoadConsoleUiState = {
  activeJobId: null,
  confirmation: "",
  discovery: null,
  dropActive: false,
  files: [],
  jobs: [],
  localSyncPath: "/data",
  localSyncPrefix: "",
  lastResult: null,
  plan: null,
  rustfsBusy: false,
  rustfsConfig: null,
  rustfsMessage: null,
  rustfsPrefix: "kor-travel-geo/uploads",
  storageKind: "local",
  uploadSet: null
};

export function LoadConsole() {
  const controller = useLoadConsoleController();
  const {
    activeJob,
    canCreatePlan,
    expectedConfirmation,
    loadPercent,
    selectedBytes,
    state,
    uiState,
    uploadPercent,
    cancelActiveJob,
    cancelUpload,
    createPlan,
    onDragOver,
    onDrop,
    onFileInput,
    refreshJobs,
    refreshMv,
    resetAll,
    importRustfsPrefix,
    setLocalSyncPath,
    setLocalSyncPrefix,
    setConfirmation,
    setDiscovery,
    setDropActive,
    setRustfsPrefix,
    setStorageKind,
    syncLocalToRustfs,
    submitPlan,
    uploadSelectedFiles
  } = controller;

  return (
    <div className="grid two">
      <SourceSetUploadPanel
        dropActive={uiState.dropActive}
        files={uiState.files}
        onDragLeave={() => setDropActive(false)}
        onDragOver={onDragOver}
        onDrop={onDrop}
        onFileInput={onFileInput}
        onReset={resetAll}
        onSubmit={uploadSelectedFiles}
        onUploadCancel={cancelUpload}
        selectedBytes={selectedBytes}
        state={state}
        storageKind={uiState.storageKind}
        rustfsConfig={uiState.rustfsConfig}
        onStorageKindChange={setStorageKind}
        uploadPercent={uploadPercent}
        uploadSet={uiState.uploadSet}
      />
      <RustfsSourcePanel
        config={uiState.rustfsConfig}
        busy={uiState.rustfsBusy}
        localSyncPath={uiState.localSyncPath}
        localSyncPrefix={uiState.localSyncPrefix}
        message={uiState.rustfsMessage}
        onImportPrefix={importRustfsPrefix}
        onLocalSyncPathChange={setLocalSyncPath}
        onLocalSyncPrefixChange={setLocalSyncPrefix}
        onPrefixChange={setRustfsPrefix}
        onSyncLocal={syncLocalToRustfs}
        prefix={uiState.rustfsPrefix}
      />
      <SourceSetReviewPanel
        canCreatePlan={canCreatePlan}
        confirmation={uiState.confirmation}
        discovery={uiState.discovery}
        onConfirmationChange={setConfirmation}
        onCreatePlan={createPlan}
        onRefreshJobs={refreshJobs}
        onSubmitPlan={submitPlan}
        plan={uiState.plan}
        state={state}
      />
      <UploadFilesPanel files={uiState.files} />
      <LoadJobsPanel
        activeJob={activeJob}
        jobs={uiState.jobs}
        loadPercent={loadPercent}
        onCancelActiveJob={cancelActiveJob}
        onRefreshMv={refreshMv}
      />
      <Panel title="Source Set JSON">
        <JsonBlock value={uiState.plan ?? uiState.discovery ?? uiState.uploadSet ?? { status: "READY" }} />
      </Panel>
      <Panel title="Last Response">
        <JsonBlock value={uiState.lastResult ?? { status: "READY" }} />
      </Panel>
      <MixedYyyymmDialog
        canCreatePlan={canCreatePlan}
        confirmation={uiState.confirmation}
        discovery={uiState.discovery}
        expectedConfirmation={expectedConfirmation}
        onClose={() => setDiscovery(null)}
        onConfirmationChange={setConfirmation}
        onConfirm={createPlan}
        plan={uiState.plan}
      />
    </div>
  );
}

function useLoadConsoleController() {
  const [state, dispatch] = useReducer(loadWorkflowReducer, "idle");
  const [uiState, dispatchUi] = useReducer(loadConsoleUiReducer, initialLoadConsoleUiState);
  const uploadCancelRequested = useRef(false);
  const activeUploads = useRef<Map<string, XMLHttpRequest> | null>(null);
  if (activeUploads.current === null) {
    activeUploads.current = new Map();
  }
  const uploadRequests = activeUploads.current;

  const selectedBytes = useMemo(
    () => uiState.files.reduce((total, item) => total + item.file.size, 0),
    [uiState.files]
  );
  const uploadedBytes = useMemo(
    () => uiState.files.reduce((total, item) => total + item.uploadedBytes, 0),
    [uiState.files]
  );
  const uploadPercent = percent(uploadedBytes, selectedBytes);
  const activeJob = useMemo(
    () =>
      uiState.jobs.find((job) => job.job_id === uiState.activeJobId) ??
      uiState.jobs.find((job) => ["queued", "running"].includes(job.state)),
    [uiState.activeJobId, uiState.jobs]
  );
  const loadPercent = activeJob ? Math.round(activeJob.progress * 100) : 0;
  const expectedConfirmation = confirmationTokenFor(uiState.discovery?.yyyymm_by_kind ?? {}) ?? "";
  const canCreatePlan =
    uiState.discovery !== null &&
    uiState.discovery.missing_required.length === 0 &&
    (!uiState.discovery.mixed_yyyymm || uiState.confirmation === expectedConfirmation);

  function mergeUi(patch: Partial<LoadConsoleUiState>) {
    dispatchUi({ type: "merge", patch });
  }

  function patchFileState(key: string, patch: Partial<LocalUploadFile>) {
    dispatchUi({ type: "patch_file", key, patch });
  }

  useEffect(() => {
    async function loadRustfsConfig() {
      try {
        const config = await requestJson<RustfsStorageConfig>("/admin/storage/rustfs/config");
        mergeUi({
          rustfsConfig: config,
          rustfsPrefix: `${config.prefix}/uploads`,
          storageKind: config.enabled ? "rustfs" : "local"
        });
      } catch (error) {
        mergeUi({
          rustfsMessage: error instanceof Error ? error.message : String(error),
          storageKind: "local"
        });
      }
    }
    void loadRustfsConfig();
  }, []);

  function selectFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList).map((file, index) => ({
      file,
      key: `${file.webkitRelativePath || file.name}:${file.size}:${file.lastModified}:${index}`,
      relativePath: file.webkitRelativePath || file.name,
      state: "pending" as const,
      uploadedBytes: 0
    }));
    dispatchUi({ type: "select_files", files });
    dispatch({ type: "reset" });
  }

  function onFileInput(event: ChangeEvent<HTMLInputElement>) {
    if (event.target.files) {
      selectFiles(event.target.files);
      event.target.value = "";
    }
  }

  function setDropActive(dropActive: boolean) {
    mergeUi({ dropActive });
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

  function setConfirmation(confirmation: string) {
    mergeUi({ confirmation });
  }

  function setDiscovery(discovery: SourceSetDiscovery | null) {
    mergeUi({ discovery });
  }

  function setStorageKind(storageKind: UploadStorageKind) {
    mergeUi({ storageKind });
  }

  function setRustfsPrefix(rustfsPrefix: string) {
    mergeUi({ rustfsPrefix });
  }

  function setLocalSyncPath(localSyncPath: string) {
    mergeUi({ localSyncPath });
  }

  function setLocalSyncPrefix(localSyncPrefix: string) {
    mergeUi({ localSyncPrefix });
  }

  async function uploadSelectedFiles(event: FormEvent) {
    event.preventDefault();
    if (uiState.files.length === 0) {
      mergeUi({ lastResult: { error: "선택된 파일이 없습니다." } });
      return;
    }
    dispatch({ type: "upload_start" });
    uploadCancelRequested.current = false;
    try {
      const created = await postJson<UploadSetStatus>("/admin/uploads", {
        purpose: "full_load_source_set",
        storage_kind: uiState.storageKind
      });
      mergeUi({ uploadSet: created });
      const uploadResults = await Promise.allSettled(
        uiState.files.map((item) => uploadOneFile(created.upload_set_id, item))
      );
      const failures = uploadResults.filter(
        (result): result is PromiseRejectedResult => result.status === "rejected"
      );
      if (failures.length > 0) {
        throw new Error(
          failures
            .map((result) =>
              result.reason instanceof Error ? result.reason.message : String(result.reason)
            )
            .join("\n")
        );
      }
      const status = await requestJson<UploadSetStatus>(`/admin/uploads/${created.upload_set_id}`);
      const discovered = await postJson<SourceSetDiscovery>("/admin/load-sources/discover", {
        upload_set_id: created.upload_set_id,
        include_optional: true
      });
      mergeUi({ discovery: discovered, lastResult: discovered, uploadSet: status });
      dispatch({ type: "upload_done" });
    } catch (error) {
      mergeUi({ lastResult: { error: error instanceof Error ? error.message : String(error) } });
      dispatch({ type: uploadCancelRequested.current ? "cancel" : "fail" });
    } finally {
      uploadRequests.clear();
    }
  }

  async function discoverUploadSet(uploadSet: UploadSetStatus) {
    const discovered = await postJson<SourceSetDiscovery>("/admin/load-sources/discover", {
      upload_set_id: uploadSet.upload_set_id,
      include_optional: true
    });
    mergeUi({ discovery: discovered, lastResult: discovered, uploadSet });
    dispatch({ type: "upload_done" });
  }

  async function importRustfsPrefix(event: FormEvent) {
    event.preventDefault();
    if (!uiState.rustfsPrefix.trim()) {
      mergeUi({ rustfsMessage: "RustFS prefix를 입력하세요." });
      return;
    }
    dispatch({ type: "upload_start" });
    mergeUi({ rustfsBusy: true, rustfsMessage: null });
    try {
      const uploadSet = await postJson<UploadSetStatus>("/admin/storage/rustfs/import-prefix", {
        prefix: uiState.rustfsPrefix.trim(),
        purpose: "full_load_source_set"
      });
      await discoverUploadSet(uploadSet);
      mergeUi({ rustfsMessage: "RustFS prefix를 source set으로 가져왔습니다." });
    } catch (error) {
      mergeUi({
        lastResult: { error: error instanceof Error ? error.message : String(error) },
        rustfsMessage: error instanceof Error ? error.message : String(error)
      });
      dispatch({ type: "fail" });
    } finally {
      mergeUi({ rustfsBusy: false });
    }
  }

  async function syncLocalToRustfs(event: FormEvent) {
    event.preventDefault();
    if (!uiState.localSyncPath.trim()) {
      mergeUi({ rustfsMessage: "로컬 경로를 입력하세요." });
      return;
    }
    dispatch({ type: "upload_start" });
    mergeUi({ rustfsBusy: true, rustfsMessage: null });
    try {
      const result = await postJson<RustfsSyncLocalResult>("/admin/storage/rustfs/sync-local", {
        root_path: uiState.localSyncPath.trim(),
        prefix: uiState.localSyncPrefix.trim() || null,
        purpose: "full_load_source_set"
      });
      await discoverUploadSet(result.upload_set);
      mergeUi({
        lastResult: result,
        rustfsMessage: `${result.uploaded_files}개 파일을 RustFS로 업로드했습니다.`
      });
    } catch (error) {
      mergeUi({
        lastResult: { error: error instanceof Error ? error.message : String(error) },
        rustfsMessage: error instanceof Error ? error.message : String(error)
      });
      dispatch({ type: "fail" });
    } finally {
      mergeUi({ rustfsBusy: false });
    }
  }

  function uploadOneFile(uploadSetId: string, item: LocalUploadFile): Promise<UploadFileStatus> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const params = new URLSearchParams({
        filename: item.file.name,
        relative_path: item.relativePath
      });
      uploadRequests.set(item.key, xhr);
      patchFileState(item.key, { error: undefined, state: "uploading", uploadedBytes: 0 });

      const finish = () => {
        uploadRequests.delete(item.key);
      };

      xhr.open(
        "PUT",
        `${API_BASE}${backendPath(`/admin/uploads/${uploadSetId}/files?${params}`)}`
      );
      xhr.upload.onprogress = (progressEvent) => {
        const uploaded = progressEvent.lengthComputable ? progressEvent.loaded : item.file.size;
        patchFileState(item.key, { state: "uploading", uploadedBytes: uploaded });
      };
      xhr.onload = () => {
        finish();
        if (xhr.status < 200 || xhr.status >= 300) {
          const message = xhr.responseText || `${xhr.status} ${xhr.statusText}`;
          patchFileState(item.key, { error: message, state: "failed" });
          reject(new Error(message));
          return;
        }
        const result = JSON.parse(xhr.responseText) as UploadFileStatus;
        patchFileState(item.key, {
          result,
          state: "uploaded",
          uploadedBytes: result.uploaded_bytes
        });
        resolve(result);
      };
      xhr.onerror = () => {
        finish();
        const message = "업로드 요청이 실패했습니다.";
        patchFileState(item.key, { error: message, state: "failed" });
        reject(new Error(message));
      };
      xhr.onabort = () => {
        finish();
        patchFileState(item.key, { error: "업로드가 취소되었습니다.", state: "cancelled" });
        reject(new Error("업로드가 취소되었습니다."));
      };
      xhr.send(item.file);
    });
  }

  async function cancelUpload() {
    uploadCancelRequested.current = true;
    for (const xhr of uploadRequests.values()) {
      xhr.abort();
    }
    if (uiState.uploadSet) {
      const cancelled = await postJson<UploadSetStatus>(
        `/admin/uploads/${uiState.uploadSet.upload_set_id}/cancel`,
        {}
      );
      mergeUi({ uploadSet: cancelled });
    }
    dispatchUi({ type: "mark_non_uploaded", nextState: "cancelled" });
    dispatch({ type: "cancel" });
  }

  async function createPlan() {
    if (!uiState.discovery || !uiState.uploadSet || !canCreatePlan) return;
    const versions = Object.fromEntries(
      Object.entries(uiState.discovery.yyyymm_by_kind).filter(([, value]) => Boolean(value))
    );
    try {
      const result = await postJson<SourceSetPlan>("/admin/load-sources/plan", {
        acknowledged_by: "ui",
        allow_mixed_yyyymm: uiState.discovery.mixed_yyyymm,
        confirmation_token: uiState.discovery.mixed_yyyymm ? uiState.confirmation : null,
        include_optional: true,
        upload_set_id: uiState.uploadSet.upload_set_id,
        versions
      });
      mergeUi({ lastResult: result, plan: result });
      dispatch({ type: "plan_ready" });
    } catch (error) {
      mergeUi({ lastResult: { error: error instanceof Error ? error.message : String(error) } });
      dispatch({ type: "fail" });
    }
  }

  async function submitPlan() {
    if (!uiState.plan) return;
    dispatch({ type: "process_start" });
    try {
      const result = await postJson<LoadJobStatus>("/admin/loads", {
        kind: "full_load_batch",
        payload: uiState.plan.batch_payload
      });
      mergeUi({ activeJobId: result.job_id, lastResult: result });
      await refreshJobs();
    } catch (error) {
      mergeUi({ lastResult: { error: error instanceof Error ? error.message : String(error) } });
      dispatch({ type: "fail" });
    }
  }

  async function refreshJobs() {
    const jobs = await requestJson<LoadJobStatus[]>("/admin/loads?limit=20");
    mergeUi({ jobs });
    if (
      uiState.activeJobId &&
      jobs.some(
        (job) =>
          job.job_id === uiState.activeJobId &&
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
    mergeUi({ lastResult: result });
    await refreshJobs();
    dispatch({ type: "cancel" });
  }

  async function refreshMv() {
    const result = await postJson("/admin/maintenance/refresh-mv?strategy=concurrent", {});
    mergeUi({ lastResult: result });
    await refreshJobs();
  }

  function resetAll() {
    for (const xhr of uploadRequests.values()) {
      xhr.abort();
    }
    uploadCancelRequested.current = false;
    dispatchUi({ type: "reset" });
    dispatch({ type: "reset" });
  }

  return {
    activeJob,
    canCreatePlan,
    expectedConfirmation,
    loadPercent,
    selectedBytes,
    state,
    uiState,
    uploadPercent,
    cancelActiveJob,
    cancelUpload,
    createPlan,
    onDragOver,
    onDrop,
    onFileInput,
    importRustfsPrefix,
    refreshJobs,
    refreshMv,
    resetAll,
    setLocalSyncPath,
    setLocalSyncPrefix,
    setConfirmation,
    setDiscovery,
    setDropActive,
    setRustfsPrefix,
    setStorageKind,
    syncLocalToRustfs,
    submitPlan,
    uploadSelectedFiles
  };
}

function SourceSetUploadPanel({
  dropActive,
  files,
  onDragLeave,
  onDragOver,
  onDrop,
  onFileInput,
  onReset,
  onSubmit,
  onUploadCancel,
  onStorageKindChange,
  rustfsConfig,
  selectedBytes,
  state,
  storageKind,
  uploadPercent,
  uploadSet
}: {
  dropActive: boolean;
  files: LocalUploadFile[];
  onDragLeave: () => void;
  onDragOver: (event: DragEvent<HTMLDivElement>) => void;
  onDrop: (event: DragEvent<HTMLDivElement>) => void;
  onFileInput: (event: ChangeEvent<HTMLInputElement>) => void;
  onReset: () => void;
  onSubmit: (event: FormEvent) => void;
  onUploadCancel: () => Promise<void>;
  onStorageKindChange: (storageKind: UploadStorageKind) => void;
  rustfsConfig: RustfsStorageConfig | null;
  selectedBytes: number;
  state: string;
  storageKind: UploadStorageKind;
  uploadPercent: number;
  uploadSet: UploadSetStatus | null;
}) {
  const rustfsEnabled = rustfsConfig?.enabled === true;
  return (
    <Panel title="Source Set Upload" actions={<span className="status ok">{state}</span>}>
      <form className="form-grid" onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="upload-storage-kind">저장소</label>
          <select
            id="upload-storage-kind"
            onChange={(event) => onStorageKindChange(event.target.value as UploadStorageKind)}
            value={storageKind}
          >
            <option value="local">로컬 디렉터리</option>
            <option disabled={!rustfsEnabled} value="rustfs">
              RustFS
            </option>
          </select>
          <p className="form-note">
            {rustfsEnabled
              ? `${rustfsConfig.bucket}/${rustfsConfig.prefix}`
              : "RustFS는 /admin/settings에서 먼저 켭니다."}
          </p>
        </div>
        <div
          className={`drop-zone${dropActive ? " active" : ""}`}
          onDragLeave={onDragLeave}
          onDragOver={onDragOver}
          onDrop={onDrop}
        >
          <UploadCloud size={26} />
          <strong>파일 선택 또는 드롭</strong>
          <span>
            {files.length} files · {formatBytes(selectedBytes)}
          </span>
          <label className="button secondary">
            <FileUp size={16} />
            파일 선택
            <input hidden multiple onChange={onFileInput} type="file" />
          </label>
        </div>
        <ProgressLine label="업로드" percentValue={uploadPercent} />
        <div className="button-row">
          <button className="button" disabled={files.length === 0 || state === "uploading"} type="submit">
            <UploadCloud size={16} />
            업로드
          </button>
          <button
            className="button secondary"
            disabled={state !== "uploading" && !uploadSet}
            onClick={() => void onUploadCancel()}
            type="button"
          >
            <Ban size={16} />
            업로드 취소
          </button>
          <button className="button secondary" onClick={onReset} type="button">
            <RotateCcw size={16} />
            초기화
          </button>
        </div>
      </form>
    </Panel>
  );
}

function RustfsSourcePanel({
  busy,
  config,
  localSyncPath,
  localSyncPrefix,
  message,
  onImportPrefix,
  onLocalSyncPathChange,
  onLocalSyncPrefixChange,
  onPrefixChange,
  onSyncLocal,
  prefix
}: {
  busy: boolean;
  config: RustfsStorageConfig | null;
  localSyncPath: string;
  localSyncPrefix: string;
  message: string | null;
  onImportPrefix: (event: FormEvent) => Promise<void>;
  onLocalSyncPathChange: (value: string) => void;
  onLocalSyncPrefixChange: (value: string) => void;
  onPrefixChange: (value: string) => void;
  onSyncLocal: (event: FormEvent) => Promise<void>;
  prefix: string;
}) {
  const disabled = busy || config?.enabled !== true;
  return (
    <Panel
      title="RustFS Source"
      actions={<span className={`status ${config?.enabled ? "ok" : "warn"}`}>{config?.enabled ? "enabled" : "off"}</span>}
    >
      <div className="form-grid">
        <form className="form-grid" onSubmit={onImportPrefix}>
          <div className="field">
            <label htmlFor="rustfs-prefix">RustFS prefix 가져오기</label>
            <input
              id="rustfs-prefix"
              onChange={(event) => onPrefixChange(event.target.value)}
              placeholder="kor-travel-geo/uploads/upload_..."
              value={prefix}
            />
          </div>
          <div className="button-row">
            <button className="button secondary" disabled={disabled} type="submit">
              <RefreshCw size={16} />
              Prefix 가져오기
            </button>
          </div>
        </form>
        <form className="form-grid" onSubmit={onSyncLocal}>
          <div className="form-field-grid two">
            <div className="field">
              <label htmlFor="rustfs-local-root">로컬 경로</label>
              <input
                id="rustfs-local-root"
                onChange={(event) => onLocalSyncPathChange(event.target.value)}
                placeholder="/data"
                value={localSyncPath}
              />
            </div>
            <div className="field">
              <label htmlFor="rustfs-local-prefix">저장 prefix</label>
              <input
                id="rustfs-local-prefix"
                onChange={(event) => onLocalSyncPrefixChange(event.target.value)}
                placeholder={config ? `${config.prefix}/imports/...` : "kor-travel-geo/imports/..."}
                value={localSyncPrefix}
              />
            </div>
          </div>
          <div className="button-row">
            <button className="button secondary" disabled={disabled} type="submit">
              <FileUp size={16} />
              로컬 파일 올리기
            </button>
          </div>
        </form>
        {message ? <p className="form-note">{message}</p> : null}
      </div>
    </Panel>
  );
}

function SourceSetReviewPanel({
  canCreatePlan,
  confirmation,
  discovery,
  onConfirmationChange,
  onCreatePlan,
  onRefreshJobs,
  onSubmitPlan,
  plan,
  state
}: {
  canCreatePlan: boolean;
  confirmation: string;
  discovery: SourceSetDiscovery | null;
  onConfirmationChange: (confirmation: string) => void;
  onCreatePlan: () => Promise<void>;
  onRefreshJobs: () => Promise<void>;
  onSubmitPlan: () => Promise<void>;
  plan: SourceSetPlan | null;
  state: string;
}) {
  return (
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
              onChange={(event) => onConfirmationChange(event.target.value)}
              value={confirmation}
            />
          </div>
        ) : null}
        <div className="button-row">
          <button
            className="button"
            disabled={!canCreatePlan || plan !== null}
            onClick={() => void onCreatePlan()}
            type="button"
          >
            <CheckCircle2 size={16} />
            계획 확정
          </button>
          <button
            className="button"
            disabled={plan === null || state === "processing"}
            onClick={() => void onSubmitPlan()}
            type="button"
          >
            <Send size={16} />
            적재 시작
          </button>
          <button className="button secondary" onClick={() => void onRefreshJobs()} type="button">
            <RefreshCw size={16} />
            새로고침
          </button>
        </div>
      </div>
    </Panel>
  );
}

function UploadFilesPanel({ files }: { files: LocalUploadFile[] }) {
  return (
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
  );
}

function LoadJobsPanel({
  activeJob,
  jobs,
  loadPercent,
  onCancelActiveJob,
  onRefreshMv
}: {
  activeJob: LoadJobStatus | undefined;
  jobs: LoadJobStatus[];
  loadPercent: number;
  onCancelActiveJob: () => Promise<void>;
  onRefreshMv: () => Promise<void>;
}) {
  return (
    <Panel title="Jobs">
      <div className="form-grid">
        <ProgressLine label="적재" percentValue={loadPercent} />
        <div className="button-row">
          <button
            className="button secondary"
            disabled={!activeJob}
            onClick={() => void onCancelActiveJob()}
            type="button"
          >
            <Ban size={16} />
            적재 취소
          </button>
          <button className="button secondary" onClick={() => void onRefreshMv()} type="button">
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
  );
}

function MixedYyyymmDialog({
  canCreatePlan,
  confirmation,
  discovery,
  expectedConfirmation,
  onClose,
  onConfirmationChange,
  onConfirm,
  plan
}: {
  canCreatePlan: boolean;
  confirmation: string;
  discovery: SourceSetDiscovery | null;
  expectedConfirmation: string;
  onClose: () => void;
  onConfirmationChange: (confirmation: string) => void;
  onConfirm: () => Promise<void>;
  plan: SourceSetPlan | null;
}) {
  if (!discovery?.mixed_yyyymm || plan) {
    return null;
  }

  return (
    <div className="modal-backdrop">
      <dialog aria-labelledby="source-set-confirm-title" className="modal" open>
        <h2 id="source-set-confirm-title">기준월 확인</h2>
        <SourceSummary discovery={discovery} />
        <div className="confirm-box">
          <label htmlFor="source-set-confirm-modal">{expectedConfirmation}</label>
          <input
            id="source-set-confirm-modal"
            onChange={(event) => onConfirmationChange(event.target.value)}
            value={confirmation}
          />
        </div>
        <div className="button-row">
          <button className="button" disabled={!canCreatePlan} onClick={() => void onConfirm()} type="button">
            <CheckCircle2 size={16} />
            확인
          </button>
          <button className="button secondary" onClick={onClose} type="button">
            <Ban size={16} />
            닫기
          </button>
        </div>
      </dialog>
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

function loadConsoleUiReducer(
  state: LoadConsoleUiState,
  action: LoadConsoleUiAction
): LoadConsoleUiState {
  switch (action.type) {
    case "merge":
      return { ...state, ...action.patch };
    case "patch_file":
      return {
        ...state,
        files: state.files.map((file) =>
          file.key === action.key ? { ...file, ...action.patch } : file
        )
      };
    case "mark_non_uploaded":
      return {
        ...state,
        files: state.files.map((file) =>
          file.state === "uploaded" ? file : { ...file, state: action.nextState }
        )
      };
    case "reset":
      return initialLoadConsoleUiState;
    case "select_files":
      return {
        ...initialLoadConsoleUiState,
        files: action.files,
        lastResult: { selected_files: action.files.length }
      };
  }
}
