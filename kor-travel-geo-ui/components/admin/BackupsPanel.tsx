"use client";

import { Archive, Download, FileText, RefreshCw, Trash2, XCircle } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { HotSwapTab } from "@/components/admin/backups/HotSwapTab";
import { JobProgress } from "@/components/admin/backups/JobProgress";
import { inventoryTone, ManifestViewer } from "@/components/admin/backups/ManifestViewer";
import { RestoreReconcilePanel } from "@/components/admin/backups/RestoreReconcilePanel";
import { RestoreWizard } from "@/components/admin/backups/RestoreWizard";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { type VirtualColumn, VirtualTable } from "@/components/ui/VirtualTable";
import { BackupAllowedDirs, BackupArtifact, LoadJobStatus, postJson, requestJson } from "@/lib/api";
import {
  backupDownloadHref,
  backupProfileLabel,
  stagePhase,
  terminalJobState
} from "@/lib/backup-workflow";
import { formatBytes } from "@/lib/format";

const profiles = ["serving-ready", "lean-serving", "forensic"] as const;

type BackupProfile = (typeof profiles)[number];
type BackupFormState = {
  callbackUrl: string;
  compressionLevel: number;
  destinationDir: string;
  jobs: number;
  profile: BackupProfile;
};
type BackupsPanelState = {
  allowedDirs: string[];
  artifacts: BackupArtifact[];
  jobRows: LoadJobStatus[];
  lastResult: unknown;
};

const initialBackupFormState: BackupFormState = {
  callbackUrl: "",
  compressionLevel: 3,
  destinationDir: "data/backups",
  jobs: 4,
  profile: "serving-ready"
};
const initialBackupsPanelState: BackupsPanelState = {
  allowedDirs: [],
  artifacts: [],
  jobRows: [],
  lastResult: { status: "READY" }
};

export type BackupsTabId = "overview" | "backup" | "restore" | "hotswap" | "jobs";

const BACKUPS_TABS: { id: BackupsTabId; label: string }[] = [
  { id: "overview", label: "개요" },
  { id: "backup", label: "백업" },
  { id: "restore", label: "복원" },
  { id: "hotswap", label: "Hot-swap" },
  { id: "jobs", label: "작업" }
];

export function BackupsPanel({ initialTab = "overview" }: { initialTab?: BackupsTabId }) {
  const [activeTab, setActiveTab] = useState<BackupsTabId>(initialTab);
  const controller = useBackupsPanelController();
  const {
    allowedDirs,
    artifacts,
    availableArtifacts,
    backupForm,
    deleteArtifact,
    jobRows,
    lastResult,
    loadAll,
    recordResult,
    submitBackup,
    cancelJob,
    updateBackupForm
  } = controller;

  const runningCount = useMemo(
    () => jobRows.filter((job) => !terminalJobState(job.state)).length,
    [jobRows]
  );

  return (
    <div className="backups-shell">
      <nav aria-label="백업/복원 탭" className="case-tabs">
        <div
          aria-label="백업/복원 관리 탭"
          aria-orientation="horizontal"
          className="case-tab-list"
          role="tablist"
        >
          {BACKUPS_TABS.map((tab) => {
            const isSelected = tab.id === activeTab;
            return (
              <button
                aria-controls="backups-panel"
                aria-selected={isSelected}
                className={isSelected ? "case-tab active" : "case-tab"}
                id={`backups-tab-${tab.id}`}
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                role="tab"
                type="button"
              >
                <strong>{tab.label}</strong>
              </button>
            );
          })}
        </div>
      </nav>

      <section
        aria-labelledby={`backups-tab-${activeTab}`}
        className="backups-pane"
        id="backups-panel"
        role="tabpanel"
      >
        {activeTab === "overview" ? (
          <div className="grid two">
            <BackupsWorkflowGuide
              availableCount={availableArtifacts.length}
              onGoTo={setActiveTab}
              onRefresh={loadAll}
              runningCount={runningCount}
              totalArtifacts={artifacts.length}
            />
            <Panel title="Last Response">
              <JsonBlock value={lastResult} />
            </Panel>
          </div>
        ) : null}
        {activeTab === "backup" ? (
          <div className="grid two">
            <BackupFormPanel
              allowedDirs={allowedDirs}
              form={backupForm}
              onChange={updateBackupForm}
              onRefresh={loadAll}
              onSubmit={submitBackup}
            />
            <BackupArtifactsPanel artifacts={artifacts} onDeleteArtifact={deleteArtifact} />
          </div>
        ) : null}
        {activeTab === "restore" ? (
          <div className="backups-pane">
            <RestoreWizard
              onSubmitted={(result) => {
                recordResult(result);
                void loadAll();
              }}
            />
            <RestoreReconcilePanel />
          </div>
        ) : null}
        {activeTab === "hotswap" ? <HotSwapTab /> : null}
        {activeTab === "jobs" ? (
          <BackupJobsPanel jobRows={jobRows} onCancelJob={cancelJob} />
        ) : null}
      </section>
    </div>
  );
}

function BackupsWorkflowGuide({
  availableCount,
  onGoTo,
  onRefresh,
  runningCount,
  totalArtifacts
}: {
  availableCount: number;
  onGoTo: (tab: BackupsTabId) => void;
  onRefresh: () => void;
  runningCount: number;
  totalArtifacts: number;
}) {
  const nextAction =
    totalArtifacts === 0
      ? "백업본이 없습니다 — [백업] 탭에서 첫 백업을 생성하세요."
      : runningCount > 0
        ? `진행 중인 백업/복원 작업 ${runningCount}개 — [작업] 탭에서 진행률을 확인하세요.`
        : `사용 가능한 백업 ${availableCount}개 — 검증·복원 드릴로 복원 가능성을 정기 점검하세요.`;

  const steps: { title: string; hint: string; tab?: BackupsTabId }[] = [
    {
      title: "1. 백업 생성",
      hint: "[백업] 탭에서 profile·destination·압축 레벨을 골라 백업을 시작합니다.",
      tab: "backup"
    },
    {
      title: "2. 무결성 검증",
      hint: "`ktgctl backup verify <id> --deep` 로 archive 손상(bit rot)을 복원 전에 확인합니다."
    },
    {
      title: "3. 복원 드릴",
      hint: "`ktgctl backup restore-drill --artifact-id <id>` 로 throwaway DB에 복원해 PASS/FAIL을 점검합니다."
    },
    {
      title: "4. 복원 / Hot-swap",
      hint: "[복원]에서 new_database로 복원하고, 운영 교체는 [Hot-swap]에서 maintenance window + typed confirmation으로 진행합니다.",
      tab: "restore"
    }
  ];

  return (
    <Panel
      title="백업/복원 다음 액션"
      actions={
        <button className="button secondary" onClick={onRefresh} type="button">
          <RefreshCw size={16} />
          새로고침
        </button>
      }
    >
      <p className="backups-next-action">{nextAction}</p>
      <ol className="backups-guide">
        {steps.map((step) => (
          <li key={step.title}>
            <div className="backups-guide-step">
              <strong>{step.title}</strong>
              {step.tab ? (
                <button
                  className="button secondary"
                  onClick={() => onGoTo(step.tab as BackupsTabId)}
                  type="button"
                >
                  열기
                </button>
              ) : null}
            </div>
            <p>{step.hint}</p>
          </li>
        ))}
      </ol>
    </Panel>
  );
}

function useBackupsPanelController() {
  const [backupForm, setBackupForm] = useState<BackupFormState>(initialBackupFormState);
  const [panelState, setPanelState] = useState<BackupsPanelState>(initialBackupsPanelState);
  const { allowedDirs, artifacts, jobRows, lastResult } = panelState;

  const availableArtifacts = useMemo(() => {
    const next: BackupArtifact[] = [];
    for (const artifact of artifacts) {
      if (artifact.state === "available") {
        next.push(artifact);
      }
    }
    return next;
  }, [artifacts]);
  const running = useMemo(
    () => jobRows.some((job) => !terminalJobState(job.state)),
    [jobRows]
  );

  const loadAll = useCallback(async () => {
    try {
      const [nextArtifacts, nextJobs] = await Promise.all([
        requestJson<BackupArtifact[]>("/admin/backups?limit=50"),
        requestJson<LoadJobStatus[]>("/admin/jobs?limit=50")
      ]);
      setPanelState((current) => ({
        ...current,
        artifacts: nextArtifacts,
        jobRows: nextJobs.filter((job) => job.kind === "db_backup" || job.kind === "db_restore")
      }));
    } catch (error) {
      setPanelState((current) => ({
        ...current,
        lastResult: { error: error instanceof Error ? error.message : String(error) }
      }));
    }
  }, []);

  const updateBackupForm = useCallback((patch: Partial<BackupFormState>) => {
    setBackupForm((current) => ({ ...current, ...patch }));
  }, []);
  // M1 (Codex #235): surface child-panel results (e.g. the restore wizard) in the shared
  // Overview "Last Response" so they survive tab switches.
  const recordResult = useCallback((value: unknown) => {
    setPanelState((current) => ({ ...current, lastResult: value }));
  }, []);

  async function submitBackup(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await postJson<LoadJobStatus>("/admin/backups", {
        callback_url: backupForm.callbackUrl || undefined,
        compression_level: backupForm.compressionLevel,
        destination_dir: backupForm.destinationDir || undefined,
        jobs: backupForm.jobs,
        profile: backupForm.profile
      });
      setPanelState((current) => ({ ...current, lastResult: result }));
      await loadAll();
    } catch (error) {
      setPanelState((current) => ({
        ...current,
        lastResult: { error: error instanceof Error ? error.message : String(error) }
      }));
    }
  }

  async function cancelJob(jobId: string) {
    try {
      const result = await postJson<LoadJobStatus>(`/admin/jobs/${jobId}/cancel`, {});
      setPanelState((current) => ({ ...current, lastResult: result }));
      await loadAll();
    } catch (error) {
      setPanelState((current) => ({
        ...current,
        lastResult: { error: error instanceof Error ? error.message : String(error) }
      }));
    }
  }

  async function deleteArtifact(artifactId: string) {
    try {
      const result = await postJson<BackupArtifact>(`/admin/backups/${artifactId}/delete`, {});
      setPanelState((current) => ({ ...current, lastResult: result }));
      await loadAll();
    } catch (error) {
      setPanelState((current) => ({
        ...current,
        lastResult: { error: error instanceof Error ? error.message : String(error) }
      }));
    }
  }

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    async function loadAllowedDirs() {
      try {
        const config = await requestJson<BackupAllowedDirs>("/admin/backups/allowed-dirs");
        setPanelState((current) => ({ ...current, allowedDirs: config.dirs }));
        const defaultDir = config.default_dir;
        if (typeof defaultDir === "string" && defaultDir.length > 0) {
          setBackupForm((current) => ({ ...current, destinationDir: defaultDir }));
        }
      } catch {
        setPanelState((current) => ({ ...current, allowedDirs: [] }));
      }
    }
    void loadAllowedDirs();
  }, []);

  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => {
      void loadAll();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [loadAll, running]);

  return {
    allowedDirs,
    artifacts,
    availableArtifacts,
    backupForm,
    cancelJob,
    deleteArtifact,
    jobRows,
    lastResult,
    loadAll,
    recordResult,
    submitBackup,
    updateBackupForm
  };
}

function BackupFormPanel({
  allowedDirs,
  form,
  onChange,
  onRefresh,
  onSubmit
}: {
  allowedDirs: string[];
  form: BackupFormState;
  onChange: (patch: Partial<BackupFormState>) => void;
  onRefresh: () => void;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <Panel
      title="DB Backup"
      actions={
        <button className="button secondary" onClick={onRefresh} type="button">
          <RefreshCw size={16} />
          새로고침
        </button>
      }
    >
      <form className="form-grid" onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="backup-destination">백업본 저장 폴더 (destination_dir)</label>
          {allowedDirs.length > 0 ? (
            <select
              id="backup-destination"
              value={form.destinationDir}
              onChange={(event) => onChange({ destinationDir: event.target.value })}
            >
              {allowedDirs.map((dir) => (
                <option key={dir} value={dir}>
                  {dir}
                </option>
              ))}
            </select>
          ) : (
            <input
              id="backup-destination"
              value={form.destinationDir}
              onChange={(event) => onChange({ destinationDir: event.target.value })}
            />
          )}
        </div>
        <div className="field">
          <label htmlFor="backup-profile">백업 프로파일 (profile)</label>
          <select
            id="backup-profile"
            value={form.profile}
            onChange={(event) => onChange({ profile: event.target.value as BackupProfile })}
          >
            {profiles.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>
        <NumberField
          id="backup-jobs"
          label="병렬 작업 수 (jobs)"
          max={64}
          min={1}
          value={form.jobs}
          onChange={(value) => onChange({ jobs: value })}
        />
        <NumberField
          id="backup-compression"
          label="압축 레벨 (compression_level)"
          max={19}
          min={1}
          value={form.compressionLevel}
          onChange={(value) => onChange({ compressionLevel: value })}
        />
        <div className="field">
          <label htmlFor="backup-callback">완료 알림 URL (callback_url)</label>
          <input
            id="backup-callback"
            value={form.callbackUrl}
            onChange={(event) => onChange({ callbackUrl: event.target.value })}
          />
        </div>
        <button className="button" type="submit">
          <Archive size={16} />
          백업 시작
        </button>
      </form>
    </Panel>
  );
}

function BackupJobsPanel({
  jobRows,
  onCancelJob
}: {
  jobRows: LoadJobStatus[];
  onCancelJob: (jobId: string) => Promise<void>;
}) {
  const activeJobs = jobRows.filter((job) => !terminalJobState(job.state));
  return (
    <Panel title="Backup / Restore Jobs">
      {activeJobs.length > 0 ? (
        <div className="job-progress-list">
          {activeJobs.map((job) => (
            <JobProgress job={job} key={job.job_id} />
          ))}
        </div>
      ) : null}
      <table className="table">
        <thead>
          <tr>
            <th>job</th>
            <th>kind</th>
            <th>state</th>
            <th>progress</th>
            <th>stage</th>
            <th>action</th>
          </tr>
        </thead>
        <tbody>
          {jobRows.map((job) => (
            <tr key={job.job_id}>
              <td>{job.job_id}</td>
              <td>{job.kind}</td>
              <td>
                <StatusBadge value={job.state} />
              </td>
              <td>{Math.round(job.progress * 100)}%</td>
              <td>{stagePhase(job.current_stage)}</td>
              <td>
                {!terminalJobState(job.state) && (
                  <button
                    className="icon-button"
                    onClick={() => void onCancelJob(job.job_id)}
                    title="취소"
                    type="button"
                  >
                    <XCircle size={16} />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {jobRows.length === 0 ? (
        <p className="form-note">진행 중이거나 완료된 백업/복원 작업이 없습니다.</p>
      ) : null}
    </Panel>
  );
}

function BackupArtifactsPanel({
  artifacts,
  onDeleteArtifact
}: {
  artifacts: BackupArtifact[];
  onDeleteArtifact: (artifactId: string) => Promise<void>;
}) {
  const [viewing, setViewing] = useState<BackupArtifact | null>(null);
  const columns: VirtualColumn<BackupArtifact>[] = [
    {
      key: "file",
      header: "file",
      width: "1.7fr",
      sortValue: (a) => a.display_name ?? a.artifact_id,
      cell: (a) => a.display_name ?? a.artifact_id
    },
    {
      key: "state",
      header: "state",
      width: "0.8fr",
      sortValue: (a) => a.state,
      cell: (a) => <StatusBadge value={a.state} />
    },
    {
      key: "profile",
      header: "profile",
      width: "0.9fr",
      cell: (a) => backupProfileLabel(readNested(a.manifest, "backup", "profile"))
    },
    {
      key: "size",
      header: "size",
      width: "0.7fr",
      sortValue: (a) => a.size_bytes ?? 0,
      cell: (a) => formatBytes(a.size_bytes)
    },
    {
      key: "retention",
      header: "retention",
      width: "0.9fr",
      sortValue: (a) => a.retention_class ?? "default",
      cell: (a) => a.retention_class ?? "default"
    },
    {
      key: "expires",
      header: "expires",
      width: "0.9fr",
      sortValue: (a) => a.expires_at ?? "",
      cell: (a) => (a.expires_at ? a.expires_at.slice(0, 10) : "-")
    },
    {
      key: "inv",
      header: "인벤토리",
      width: "0.8fr",
      cell: (a) => {
        const inv = inventoryTone(a.source_inventory_ok);
        return <StatusBadge tone={inv.tone} value={inv.label} />;
      }
    },
    {
      key: "action",
      header: "action",
      width: "1fr",
      cell: (a) => {
        const href = backupDownloadHref(a.download_url);
        return (
          <div className="toolbar-inline">
            <button
              className="icon-button"
              onClick={() => setViewing(a)}
              title="manifest 보기"
              type="button"
            >
              <FileText size={16} />
            </button>
            {href && (
              <a className="icon-button" href={href} title="다운로드">
                <Download size={16} />
              </a>
            )}
            <button
              className="icon-button"
              onClick={() => void onDeleteArtifact(a.artifact_id)}
              title="삭제"
              type="button"
            >
              <Trash2 size={16} />
            </button>
          </div>
        );
      }
    }
  ];
  return (
    <Panel title="Backup Artifacts">
      <VirtualTable
        columns={columns}
        emptyHint="백업본이 없습니다."
        getSearchText={(a) => a.display_name ?? a.artifact_id}
        rowKey={(a) => a.artifact_id}
        rows={artifacts}
        searchPlaceholder="파일명 검색"
      />
      {viewing ? <ManifestViewer artifact={viewing} onClose={() => setViewing(null)} /> : null}
    </Panel>
  );
}

function NumberField({
  id,
  label,
  value,
  min,
  max,
  onChange
}: {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        max={max}
        min={min}
        type="number"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </div>
  );
}

function readNested(
  value: Record<string, unknown> | undefined,
  first: string,
  second: string
): unknown {
  const firstValue = value?.[first];
  if (!firstValue || typeof firstValue !== "object") return undefined;
  return (firstValue as Record<string, unknown>)[second];
}
