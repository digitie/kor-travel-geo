"use client";

import {
  CheckCircle2,
  FileArchive,
  FolderOpen,
  LoaderCircle,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

type DatasetKind =
  | "auto"
  | "location_summary"
  | "navigation_building"
  | "navigation_road_section_entrance"
  | "boundary_shapes";

type LoadJobStatus = "pending" | "running" | "succeeded" | "failed";

type LoadJob = {
  id: string;
  dataset: DatasetKind;
  replace: boolean;
  status: LoadJobStatus;
  total_files: number;
  processed_files: number;
  current_file: string;
  loaded: number;
  skipped: number;
  message: string;
  errors: string[];
  progress_percent: number;
};

type UploadItem = {
  id: string;
  file: File;
  path: string;
};

type ManualLoadPanelProps = {
  apiBaseUrl: string;
  onJobComplete: () => void;
};

const datasetOptions: { value: DatasetKind; label: string }[] = [
  { value: "auto", label: "자동 판별" },
  { value: "location_summary", label: "위치정보요약DB" },
  { value: "navigation_building", label: "내비게이션 건물" },
  { value: "navigation_road_section_entrance", label: "도로구간 출입구" },
  { value: "boundary_shapes", label: "구역 도형" },
];

export function ManualLoadPanel({ apiBaseUrl, onJobComplete }: ManualLoadPanelProps) {
  const [files, setFiles] = useState<UploadItem[]>([]);
  const [dataset, setDataset] = useState<DatasetKind>("auto");
  const [replace, setReplace] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [job, setJob] = useState<LoadJob | null>(null);
  const [error, setError] = useState("");
  const notifiedJobRef = useRef("");

  const totalSize = useMemo(
    () => files.reduce((total, item) => total + item.file.size, 0),
    [files],
  );
  const active = job?.status === "pending" || job?.status === "running";

  useEffect(() => {
    if (!job || !active) {
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/load-jobs/${job.id}`);
        if (!response.ok) {
          throw new Error(`작업 상태 조회 실패: ${response.status}`);
        }
        setJob((await response.json()) as LoadJob);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "작업 상태를 조회하지 못했습니다.");
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [active, apiBaseUrl, job]);

  useEffect(() => {
    if (!job || job.status !== "succeeded" || notifiedJobRef.current === job.id) {
      return;
    }
    notifiedJobRef.current = job.id;
    onJobComplete();
  }, [job, onJobComplete]);

  const addFiles = (items: UploadItem[]) => {
    setFiles((current) => mergeUploadItems(current, items));
    setError("");
  };

  const submit = async () => {
    if (files.length === 0) {
      setError("업로드할 파일을 먼저 선택하세요.");
      return;
    }
    setUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("dataset", dataset);
      form.append("replace", String(replace));
      files.forEach((item) => form.append("files", item.file, item.path));
      const response = await fetch(`${apiBaseUrl}/load-jobs`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) {
        throw new Error(`적재 작업 생성 실패: ${response.status}`);
      }
      setJob((await response.json()) as LoadJob);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "파일 업로드에 실패했습니다.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="rounded-lg border border-[#d9dfeb] bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold text-[#39485c]">
          <UploadCloud aria-hidden="true" size={18} />
          수동 데이터 적재
        </div>
        <select
          aria-label="자료 유형"
          value={dataset}
          onChange={(event) => setDataset(event.target.value as DatasetKind)}
          className="h-9 rounded-lg border border-[#d6dee8] bg-[#f8fafc] px-3 text-xs font-bold text-[#39485c] outline-none focus:border-[#2b7a78] focus:ring-2 focus:ring-[#2b7a78]/15"
        >
          {datasetOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <label
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={async (event) => {
          event.preventDefault();
          setDragging(false);
          addFiles(await uploadItemsFromDrop(event.dataTransfer));
        }}
        className={`mt-4 flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed px-4 py-6 text-center transition ${
          dragging
            ? "border-[#2b7a78] bg-[#edf8f6]"
            : "border-[#b9c7d7] bg-[#f8fafc] hover:border-[#2b7a78]"
        }`}
      >
        <FolderOpen aria-hidden="true" className="text-[#0f766e]" size={24} />
        <span className="mt-2 text-sm font-semibold text-[#182033]">
          TXT, ZIP, 7Z, SHP 묶음을 여러 개 드롭
        </span>
        <span className="mt-1 text-xs font-medium text-[#607086]">
          SHP는 같은 이름의 DBF/SHX/PRJ/CPG를 함께 올리면 자동으로 한 묶음으로 적재합니다.
        </span>
        <input
          type="file"
          multiple
          className="sr-only"
          accept=".txt,.dat,.zip,.7z,.shp,.dbf,.shx,.prj,.cpg,.qix,.sbn,.sbx"
          onChange={(event) => {
            addFiles(uploadItemsFromFileList(event.currentTarget.files));
            event.currentTarget.value = "";
          }}
        />
      </label>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <label className="flex items-center gap-2 text-xs font-bold text-[#4c5d72]">
          <input
            type="checkbox"
            checked={replace}
            onChange={(event) => setReplace(event.target.checked)}
            className="h-4 w-4 accent-[#0f766e]"
          />
          같은 자료를 먼저 비우고 적재
        </label>
        <button
          type="button"
          disabled={uploading || active}
          onClick={submit}
          className="inline-flex h-9 items-center gap-2 rounded-lg bg-[#163b53] px-3 text-xs font-bold text-white transition hover:bg-[#0f2e42] disabled:cursor-not-allowed disabled:opacity-45"
        >
          {uploading || active ? (
            <LoaderCircle aria-hidden="true" className="animate-spin" size={15} />
          ) : (
            <FileArchive aria-hidden="true" size={15} />
          )}
          적재 시작
        </button>
      </div>

      {files.length > 0 ? (
        <div className="mt-4 rounded-lg border border-[#e2e7ef] bg-[#fbfcfe]">
          <div className="flex items-center justify-between border-b border-[#e2e7ef] px-3 py-2 text-xs font-bold text-[#607086]">
            <span>
              {files.length.toLocaleString("ko-KR")}개 파일 · {formatBytes(totalSize)}
            </span>
            <button
              type="button"
              onClick={() => setFiles([])}
              className="text-[#a33a25] hover:text-[#7f1d1d]"
            >
              비우기
            </button>
          </div>
          <div className="max-h-40 overflow-auto p-2">
            {files.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between gap-3 rounded-md px-2 py-1.5 text-xs"
              >
                <span className="min-w-0 truncate font-medium text-[#39485c]">{item.path}</span>
                <button
                  type="button"
                  aria-label={`${item.path} 제거`}
                  onClick={() => setFiles((current) => current.filter((file) => file.id !== item.id))}
                  className="shrink-0 rounded p-1 text-[#8a98aa] hover:bg-[#eef3f7] hover:text-[#182033]"
                >
                  <X aria-hidden="true" size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {job ? <LoadJobProgress job={job} /> : null}

      {error ? (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-[#f3c8bf] bg-[#fff7f5] px-3 py-2 text-xs font-semibold text-[#a33a25]">
          <XCircle aria-hidden="true" className="mt-0.5 shrink-0" size={15} />
          <span>{error}</span>
        </div>
      ) : null}
    </div>
  );
}

function LoadJobProgress({ job }: { job: LoadJob }) {
  const done = job.status === "succeeded";
  const failed = job.status === "failed";
  return (
    <div className="mt-4 rounded-lg border border-[#d9dfeb] bg-[#f8fafc] p-3">
      <div className="flex items-center justify-between gap-3 text-xs font-bold text-[#39485c]">
        <span className="flex min-w-0 items-center gap-2">
          {done ? (
            <CheckCircle2 aria-hidden="true" className="text-[#0f766e]" size={16} />
          ) : failed ? (
            <XCircle aria-hidden="true" className="text-[#a33a25]" size={16} />
          ) : (
            <LoaderCircle aria-hidden="true" className="animate-spin text-[#0f766e]" size={16} />
          )}
          <span className="truncate">{job.message}</span>
        </span>
        <span className="font-mono">{job.progress_percent.toFixed(1)}%</span>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-[#dce5ee]">
        <div
          className={`h-full rounded-full ${failed ? "bg-[#c2410c]" : "bg-[#0f766e]"}`}
          style={{ width: `${Math.max(2, job.progress_percent)}%` }}
        />
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
        <Metric label="파일" value={`${job.processed_files}/${job.total_files || "-"}`} />
        <Metric label="로드" value={job.loaded.toLocaleString("ko-KR")} />
        <Metric label="스킵" value={job.skipped.toLocaleString("ko-KR")} />
      </div>
      {job.current_file ? (
        <p className="mt-3 truncate font-mono text-[11px] font-semibold text-[#607086]">
          {job.current_file}
        </p>
      ) : null}
      {job.errors.length > 0 ? (
        <ul className="mt-2 space-y-1 text-xs font-semibold text-[#a33a25]">
          {job.errors.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[#dbe3ed] bg-white px-2 py-2">
      <div className="text-[11px] font-bold text-[#7a8797]">{label}</div>
      <div className="mt-1 font-mono text-xs font-bold text-[#182033]">{value}</div>
    </div>
  );
}

export function uploadItemsFromFileList(fileList: FileList | null): UploadItem[] {
  return Array.from(fileList ?? []).map((file) => fileToUploadItem(file));
}

async function uploadItemsFromDrop(dataTransfer: DataTransfer): Promise<UploadItem[]> {
  const entries = Array.from(dataTransfer.items)
    .map((item) => {
      const entryGetter = item as DataTransferItem & {
        webkitGetAsEntry?: () => FileSystemEntry | null;
      };
      return entryGetter.webkitGetAsEntry?.() ?? null;
    })
    .filter((entry): entry is FileSystemEntry => entry !== null);
  if (entries.length === 0) {
    return uploadItemsFromFileList(dataTransfer.files);
  }
  const nested = await Promise.all(entries.map((entry) => uploadItemsFromEntry(entry)));
  return nested.flat();
}

async function uploadItemsFromEntry(entry: FileSystemEntry): Promise<UploadItem[]> {
  if (entry.isFile) {
    const file = await fileFromEntry(entry as FileSystemFileEntry);
    return [fileToUploadItem(file, entry.fullPath.replace(/^\/+/, ""))];
  }
  if (!entry.isDirectory) {
    return [];
  }
  const directory = entry as FileSystemDirectoryEntry;
  const entries = await entriesFromDirectory(directory);
  const nested = await Promise.all(entries.map((item) => uploadItemsFromEntry(item)));
  return nested.flat();
}

function fileFromEntry(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

function entriesFromDirectory(directory: FileSystemDirectoryEntry): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => {
    const reader = directory.createReader();
    const entries: FileSystemEntry[] = [];
    const readBatch = () => {
      reader.readEntries(
        (batch) => {
          if (batch.length === 0) {
            resolve(entries);
            return;
          }
          entries.push(...batch);
          readBatch();
        },
        (error) => reject(error),
      );
    };
    readBatch();
  });
}

function fileToUploadItem(file: File, path?: string): UploadItem {
  const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
  const resolvedPath = path || relativePath || file.name;
  return {
    id: `${resolvedPath}:${file.size}:${file.lastModified}`,
    file,
    path: resolvedPath,
  };
}

function mergeUploadItems(current: UploadItem[], incoming: UploadItem[]) {
  const byId = new Map(current.map((item) => [item.id, item]));
  incoming.forEach((item) => byId.set(item.id, item));
  return Array.from(byId.values()).sort((a, b) => a.path.localeCompare(b.path));
}

export function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  if (value < 1024 * 1024 * 1024) {
    return `${(value / 1024 / 1024).toFixed(1)} MB`;
  }
  return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`;
}
