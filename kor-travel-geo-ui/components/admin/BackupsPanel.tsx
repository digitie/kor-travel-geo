"use client";

import {
  Archive,
  Download,
  RefreshCw,
  RotateCcw,
  Trash2,
  XCircle
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { BackupAllowedDirs, BackupArtifact, LoadJobStatus, postJson, requestJson } from "@/lib/api";
import {
  backupDownloadHref,
  backupProfileLabel,
  shaPrefix,
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
type RestoreFormState = {
  restoreArchivePath: string;
  restoreArtifactId: string;
  restoreJobs: number;
  runAnalyze: boolean;
  runSmokeTest: boolean;
  targetDatabase: string;
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
const initialRestoreFormState: RestoreFormState = {
  restoreArchivePath: "",
  restoreArtifactId: "",
  restoreJobs: 4,
  runAnalyze: true,
  runSmokeTest: true,
  targetDatabase: "kor_travel_geo_restore"
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
    restoreForm,
    submitBackup,
    submitRestore,
    cancelJob,
    updateBackupForm,
    updateRestoreForm
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
          <RestoreFormPanel
            artifacts={availableArtifacts}
            form={restoreForm}
            onChange={updateRestoreForm}
            onSubmit={submitRestore}
          />
        ) : null}
        {activeTab === "hotswap" ? <HotSwapGuideTab /> : null}
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

function HotSwapGuideTab() {
  return (
    <Panel title="Hot-swap (운영 DB 교체)">
      <p className="backups-next-action">
        Hot-swap은 복원된 DB를 <code>ALTER DATABASE RENAME</code> 2-step으로 운영 serving DB와
        교체합니다. 활성 maintenance window(kind=restore)와 정확한 typed confirmation이 필요하며,
        smoke 실패 시 자동 rollback됩니다.
      </p>
      <ol className="backups-guide">
        <li>
          <p>
            먼저 [복원] 탭에서 새 DB로 복원하고 <code>restore-drill</code>로 복원 가능성을
            확인합니다.
          </p>
        </li>
        <li>
          <p>
            <code>POST /v1/admin/restores/hot-swap-plan</code>으로 plan·blockers·typed
            confirmation을 확인합니다.
          </p>
        </li>
        <li>
          <p>
            maintenance window를 열고 <code>POST /v1/admin/restores/hot-swap</code>으로 실행,
            필요 시 <code>POST /v1/admin/restores/hot-swap-rollback</code>으로 되돌립니다.
          </p>
        </li>
      </ol>
      <p className="backups-guide-note">
        전용 위저드 UI(plan·maintenance window·실행·rollback)는 T-250에서 제공됩니다.
      </p>
    </Panel>
  );
}

function useBackupsPanelController() {
  const [backupForm, setBackupForm] = useState<BackupFormState>(initialBackupFormState);
  const [restoreForm, setRestoreForm] = useState<RestoreFormState>(initialRestoreFormState);
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
  const updateRestoreForm = useCallback((patch: Partial<RestoreFormState>) => {
    setRestoreForm((current) => ({ ...current, ...patch }));
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

  async function submitRestore(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await postJson<LoadJobStatus>("/admin/restores", {
        archive_path: restoreForm.restoreArchivePath || undefined,
        artifact_id: restoreForm.restoreArtifactId || undefined,
        jobs: restoreForm.restoreJobs,
        run_analyze: restoreForm.runAnalyze,
        run_smoke_test: restoreForm.runSmokeTest,
        target_database: restoreForm.targetDatabase
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
    restoreForm,
    submitBackup,
    submitRestore,
    updateBackupForm,
    updateRestoreForm
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

function RestoreFormPanel({
  artifacts,
  form,
  onChange,
  onSubmit
}: {
  artifacts: BackupArtifact[];
  form: RestoreFormState;
  onChange: (patch: Partial<RestoreFormState>) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <Panel title="DB Restore">
      <form className="form-grid" onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="restore-artifact">복원할 백업본 (artifact_id)</label>
          <select
            id="restore-artifact"
            value={form.restoreArtifactId}
            onChange={(event) => onChange({ restoreArtifactId: event.target.value })}
          >
            <option value="">직접 경로 사용</option>
            {artifacts.map((artifact) => (
              <option key={artifact.artifact_id} value={artifact.artifact_id}>
                {artifact.display_name ?? artifact.artifact_id}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="restore-archive">백업본 직접 경로 (archive_path)</label>
          <input
            id="restore-archive"
            value={form.restoreArchivePath}
            onChange={(event) => onChange({ restoreArchivePath: event.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="restore-target">복원 대상 DB 이름 (target_database)</label>
          <input
            id="restore-target"
            value={form.targetDatabase}
            onChange={(event) => onChange({ targetDatabase: event.target.value })}
          />
        </div>
        <NumberField
          id="restore-jobs"
          label="병렬 작업 수 (jobs)"
          max={64}
          min={1}
          value={form.restoreJobs}
          onChange={(value) => onChange({ restoreJobs: value })}
        />
        <label className="checkbox-row">
          <input
            checked={form.runAnalyze}
            onChange={(event) => onChange({ runAnalyze: event.target.checked })}
            type="checkbox"
          />
          ANALYZE
        </label>
        <label className="checkbox-row">
          <input
            checked={form.runSmokeTest}
            onChange={(event) => onChange({ runSmokeTest: event.target.checked })}
            type="checkbox"
          />
          smoke test
        </label>
        <button className="button" type="submit">
          <RotateCcw size={16} />
          Restore 시작
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
  return (
    <Panel title="Backup / Restore Jobs">
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
  return (
    <Panel title="Backup Artifacts">
      <table className="table">
        <thead>
          <tr>
            <th>file</th>
            <th>state</th>
            <th>profile</th>
            <th>size</th>
            <th>sha256</th>
            <th>callback</th>
            <th>action</th>
          </tr>
        </thead>
        <tbody>
          {artifacts.map((artifact) => {
            const href = backupDownloadHref(artifact.download_url);
            return (
              <tr key={artifact.artifact_id}>
                <td>{artifact.display_name ?? artifact.artifact_id}</td>
                <td>
                  <StatusBadge value={artifact.state} />
                </td>
                <td>{backupProfileLabel(readNested(artifact.manifest, "backup", "profile"))}</td>
                <td>{formatBytes(artifact.size_bytes)}</td>
                <td>{shaPrefix(artifact.sha256)}</td>
                <td>{artifact.callback_state ?? "-"}</td>
                <td>
                  <div className="toolbar-inline">
                    {href && (
                      <a className="icon-button" href={href} title="다운로드">
                        <Download size={16} />
                      </a>
                    )}
                    <button
                      className="icon-button"
                      onClick={() => void onDeleteArtifact(artifact.artifact_id)}
                      title="삭제"
                      type="button"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
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
