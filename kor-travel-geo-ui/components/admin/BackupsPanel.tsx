"use client";

import { Archive, AlertTriangle, ChevronDown, Download, FileText, Trash2, XCircle } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { HotSwapTab } from "@/components/admin/backups/HotSwapTab";
import { JobProgress } from "@/components/admin/backups/JobProgress";
import { inventoryTone, nestedRecord } from "@/components/admin/backups/manifest-utils";
import { ManifestViewer } from "@/components/admin/backups/ManifestViewer";
import { RestoreReconcilePanel } from "@/components/admin/backups/RestoreReconcilePanel";
import { RestoreWizard } from "@/components/admin/backups/RestoreWizard";
import { ActionResultPanel } from "@/components/admin/shared/ActionResultPanel";
import { AdminTabs, AdminTabsContent } from "@/components/admin/shared/AdminTabs";
import { ConfirmActionDialog } from "@/components/admin/shared/ConfirmActionDialog";
import { HelpTip } from "@/components/admin/shared/HelpTip";
import { NumberField } from "@/components/admin/shared/NumberField";
import { RefreshButton } from "@/components/admin/shared/RefreshButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger
} from "@/components/ui/collapsible";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { type VirtualColumn, VirtualTable } from "@/components/ui/VirtualTable";
import {
  BackupAllowedDirs,
  BackupArtifact,
  LoadJobStatus,
  getErrorMessage,
  postJson,
  requestJson
} from "@/lib/api";
import {
  backupDownloadHref,
  backupProfileDescriptions,
  backupProfileLabel,
  stagePhase,
  terminalJobState
} from "@/lib/backup-workflow";
import { formatBytes } from "@/lib/format";
import { httpUrlSchema } from "@/lib/schemas";
import { toast } from "@/lib/toast";

const profiles = ["serving-ready", "lean-serving", "forensic"] as const;

type BackupProfile = (typeof profiles)[number];
type BackupFormState = {
  callbackUrl: string;
  compressionLevel: number | null;
  destinationDir: string;
  jobs: number | null;
  profile: BackupProfile;
};
type BackupsPanelState = {
  allowedDirs: string[];
  allowedDirsError: boolean;
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
  allowedDirsError: false,
  artifacts: [],
  jobRows: [],
  lastResult: null
};

export type BackupsTabId = "overview" | "backup" | "restore" | "hotswap" | "jobs";
type BackupWorkflowStep = {
  title: string;
  hint?: string;
  cli?: string;
  cliHint?: string;
  tab?: BackupsTabId;
};

const BACKUPS_TABS: { id: BackupsTabId; label: string }[] = [
  { id: "overview", label: "개요" },
  { id: "backup", label: "백업" },
  { id: "restore", label: "복원" },
  { id: "hotswap", label: "Hot-swap" },
  { id: "jobs", label: "작업" }
];
const BACKUP_WORKFLOW_STEPS: BackupWorkflowStep[] = [
  {
    title: "1. 백업 생성",
    hint: "[백업] 탭에서 profile·저장 폴더·압축 레벨을 골라 시작합니다.",
    tab: "backup"
  },
  {
    title: "2. 무결성 검증",
    cli: "ktgctl backup verify <id> --deep",
    cliHint: "archive 손상(bit rot)을 복원 전에 확인합니다."
  },
  {
    title: "3. 복원 드릴",
    cli: "ktgctl backup restore-drill --artifact-id <id>",
    cliHint: "throwaway DB에 복원해 PASS/FAIL을 점검합니다."
  },
  {
    title: "4. 복원 / Hot-swap",
    hint: "[복원] 탭에서 새 DB로 복원하고, 운영 교체는 [Hot-swap] 탭에서 진행합니다.",
    tab: "restore"
  }
];

export function BackupsPanel({ initialTab = "overview" }: { initialTab?: BackupsTabId }) {
  const [activeTab, setActiveTab] = useState<BackupsTabId>(initialTab);
  const controller = useBackupsPanelController();
  const {
    allowedDirs,
    allowedDirsError,
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
    <AdminTabs
      className="backups-shell"
      items={BACKUPS_TABS.map((tab) => ({ value: tab.id, label: tab.label }))}
      label="백업/복원 관리 탭"
      onValueChange={setActiveTab}
      value={activeTab}
    >
      <AdminTabsContent value="overview">
        <div className="grid two">
          <BackupsWorkflowGuide
            availableCount={availableArtifacts.length}
            onGoTo={setActiveTab}
            onRefresh={loadAll}
            runningCount={runningCount}
            totalArtifacts={artifacts.length}
          />
          <ActionResultPanel result={lastResult} />
        </div>
      </AdminTabsContent>
      <AdminTabsContent value="backup">
        <div className="grid two">
          <BackupFormPanel
            allowedDirs={allowedDirs}
            allowedDirsError={allowedDirsError}
            form={backupForm}
            onChange={updateBackupForm}
            onRefresh={loadAll}
            onSubmit={submitBackup}
          />
          <BackupArtifactsPanel artifacts={artifacts} onDeleteArtifact={deleteArtifact} />
        </div>
      </AdminTabsContent>
      <AdminTabsContent value="restore">
        <RestoreWizard
          onSubmitted={(result) => {
            recordResult(result);
            void loadAll();
          }}
        />
        <RestoreReconcilePanel />
      </AdminTabsContent>
      <AdminTabsContent value="hotswap">
        <HotSwapTab />
      </AdminTabsContent>
      <AdminTabsContent value="jobs">
        <BackupJobsPanel jobRows={jobRows} onCancelJob={cancelJob} />
      </AdminTabsContent>
    </AdminTabs>
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

  return (
    <Panel actions={<RefreshButton onClick={onRefresh} />} title="백업/복원 다음 액션">
      <p className="backups-next-action">{nextAction}</p>
      <ol className="backups-guide">
        {BACKUP_WORKFLOW_STEPS.map((step) => (
          <li key={step.title}>
            <div className="backups-guide-step">
              <strong>{step.title}</strong>
              {step.cli ? <Badge tone="neutral">CLI 전용</Badge> : null}
              {step.tab ? (
                <Button
                  onClick={() => onGoTo(step.tab as BackupsTabId)}
                  size="sm"
                  type="button"
                  variant="outline"
                >
                  열기
                </Button>
              ) : null}
            </div>
            {step.hint ? <p>{step.hint}</p> : null}
            {step.cli ? (
              <Collapsible>
                <CollapsibleTrigger className="inline-flex min-h-9 items-center gap-1 rounded-md px-1.5 text-xs font-semibold text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 [&>svg]:-rotate-90 [&>svg]:transition-transform data-[state=open]:[&>svg]:rotate-0">
                  <ChevronDown aria-hidden="true" className="size-3.5" />
                  CLI 명령 보기
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <p className="m-0 text-xs text-muted-foreground">
                    <code>{step.cli}</code> — {step.cliHint}
                  </p>
                </CollapsibleContent>
              </Collapsible>
            ) : null}
          </li>
        ))}
      </ol>
    </Panel>
  );
}

function useBackupsPanelController() {
  const [backupForm, setBackupForm] = useState<BackupFormState>(initialBackupFormState);
  const [panelState, setPanelState] = useState<BackupsPanelState>(initialBackupsPanelState);
  const { allowedDirs, allowedDirsError, artifacts, jobRows, lastResult } = panelState;

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
        lastResult: { error: getErrorMessage(error) }
      }));
    }
  }, []);

  const updateBackupForm = useCallback((patch: Partial<BackupFormState>) => {
    setBackupForm((current) => ({ ...current, ...patch }));
  }, []);
  // M1 (Codex #235): surface child-panel results (e.g. the restore wizard) in the shared
  // Overview "최근 결과" so they survive tab switches.
  const recordResult = useCallback((value: unknown) => {
    setPanelState((current) => ({ ...current, lastResult: value }));
  }, []);

  async function submitBackup(event: FormEvent) {
    event.preventDefault();
    if (backupForm.jobs == null || backupForm.compressionLevel == null) return;
    if (backupForm.callbackUrl && !httpUrlSchema.safeParse(backupForm.callbackUrl).success) {
      return;
    }
    try {
      const result = await postJson<LoadJobStatus>("/admin/backups", {
        callback_url: backupForm.callbackUrl || undefined,
        compression_level: backupForm.compressionLevel,
        destination_dir: backupForm.destinationDir || undefined,
        jobs: backupForm.jobs,
        profile: backupForm.profile
      });
      setPanelState((current) => ({ ...current, lastResult: result }));
      toast.success("백업 job이 제출됐습니다");
      await loadAll();
    } catch (error) {
      const message = getErrorMessage(error);
      setPanelState((current) => ({ ...current, lastResult: { error: message } }));
      toast.error("백업 시작 실패", message);
    }
  }

  async function cancelJob(jobId: string) {
    try {
      const result = await postJson<LoadJobStatus>(`/admin/jobs/${jobId}/cancel`, {});
      setPanelState((current) => ({ ...current, lastResult: result }));
      toast.success("작업 취소를 요청했습니다");
      await loadAll();
    } catch (error) {
      const message = getErrorMessage(error);
      setPanelState((current) => ({ ...current, lastResult: { error: message } }));
      toast.error("작업 취소 실패", message);
    }
  }

  async function deleteArtifact(artifactId: string) {
    try {
      const result = await postJson<BackupArtifact>(`/admin/backups/${artifactId}/delete`, {});
      setPanelState((current) => ({ ...current, lastResult: result }));
      toast.success("백업본을 삭제했습니다");
      await loadAll();
    } catch (error) {
      const message = getErrorMessage(error);
      setPanelState((current) => ({ ...current, lastResult: { error: message } }));
      toast.error("백업본 삭제 실패", message);
    }
  }

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    async function loadAllowedDirs() {
      try {
        const config = await requestJson<BackupAllowedDirs>("/admin/backups/allowed-dirs");
        setPanelState((current) => ({
          ...current,
          allowedDirs: config.dirs,
          allowedDirsError: false
        }));
        const defaultDir = config.default_dir;
        if (typeof defaultDir === "string" && defaultDir.length > 0) {
          setBackupForm((current) => ({ ...current, destinationDir: defaultDir }));
        }
      } catch {
        setPanelState((current) => ({ ...current, allowedDirs: [], allowedDirsError: true }));
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
    allowedDirsError,
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
  allowedDirsError,
  form,
  onChange,
  onRefresh,
  onSubmit
}: {
  allowedDirs: string[];
  allowedDirsError: boolean;
  form: BackupFormState;
  onChange: (patch: Partial<BackupFormState>) => void;
  onRefresh: () => void;
  onSubmit: (event: FormEvent) => void;
}) {
  const callbackInvalid =
    form.callbackUrl.length > 0 && !httpUrlSchema.safeParse(form.callbackUrl).success;
  const formValid = form.jobs != null && form.compressionLevel != null && !callbackInvalid;

  return (
    <Panel actions={<RefreshButton onClick={onRefresh} />} title="DB Backup">
      <form className="form-grid" noValidate onSubmit={onSubmit}>
        <Field>
          <span className="flex items-center gap-1">
            <FieldLabel htmlFor="backup-destination">백업본 저장 폴더</FieldLabel>
            <HelpTip label="백업본 저장 폴더 도움말">
              API 필드 <code>destination_dir</code> — 서버가 허용한 디렉터리에만 저장할 수
              있습니다.
            </HelpTip>
          </span>
          {allowedDirs.length > 0 ? (
            <NativeSelect
              id="backup-destination"
              onChange={(event) => onChange({ destinationDir: event.target.value })}
              value={form.destinationDir}
            >
              {allowedDirs.map((dir) => (
                <option key={dir} value={dir}>
                  {dir}
                </option>
              ))}
            </NativeSelect>
          ) : (
            <Input
              id="backup-destination"
              onChange={(event) => onChange({ destinationDir: event.target.value })}
              placeholder="data/backups"
              value={form.destinationDir}
            />
          )}
        </Field>
        {allowedDirsError ? (
          <Alert role="status" variant="warning">
            <AlertTriangle aria-hidden="true" />
            <AlertDescription>
              허용 폴더 목록을 불러오지 못했습니다 — 직접 입력한 경로는 서버가 허용 목록으로 최종
              검증합니다.
            </AlertDescription>
          </Alert>
        ) : null}
        <Field>
          <span className="flex items-center gap-1">
            <FieldLabel htmlFor="backup-profile">백업 프로파일</FieldLabel>
            <HelpTip label="백업 프로파일 도움말">
              API 필드 <code>profile</code> — 백업 범위 사전 구성. 선택지별 설명은 아래에
              표시됩니다.
            </HelpTip>
          </span>
          <NativeSelect
            id="backup-profile"
            onChange={(event) => onChange({ profile: event.target.value as BackupProfile })}
            value={form.profile}
          >
            {profiles.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </NativeSelect>
          <FieldDescription>{backupProfileDescriptions[form.profile]}</FieldDescription>
        </Field>
        <NumberField
          help={
            <>
              API 필드 <code>jobs</code> — pg_dump 병렬 작업 수 (1~64). 서버 CPU 코어 수 이하
              권장, 기본 4.
            </>
          }
          id="backup-jobs"
          label="병렬 작업 수"
          max={64}
          min={1}
          onChange={(value) => onChange({ jobs: value })}
          value={form.jobs}
        />
        <NumberField
          help={
            <>
              API 필드 <code>compression_level</code> — zstd 압축 레벨 (1~19). 높을수록 작고
              느립니다, 기본 3.
            </>
          }
          id="backup-compression"
          label="압축 레벨"
          max={19}
          min={1}
          onChange={(value) => onChange({ compressionLevel: value })}
          value={form.compressionLevel}
        />
        <Field data-invalid={callbackInvalid || undefined}>
          <span className="flex items-center gap-1">
            <FieldLabel htmlFor="backup-callback">완료 알림 URL</FieldLabel>
            <HelpTip label="완료 알림 URL 도움말">
              API 필드 <code>callback_url</code> (선택) — 백업 완료 시 job 상태를 이 URL로
              POST합니다.
            </HelpTip>
          </span>
          <Input
            aria-invalid={callbackInvalid || undefined}
            id="backup-callback"
            onChange={(event) => onChange({ callbackUrl: event.target.value })}
            placeholder="https://example.com/hooks/backup"
            type="url"
            value={form.callbackUrl}
          />
          {callbackInvalid ? (
            <FieldError>http:// 또는 https:// URL 형식이어야 합니다</FieldError>
          ) : null}
        </Field>
        <Button disabled={!formValid} type="submit">
          <Archive aria-hidden="true" size={16} />
          백업 시작
        </Button>
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
  const columns: VirtualColumn<LoadJobStatus>[] = [
    {
      key: "job",
      header: "job",
      sortValue: (job) => job.job_id,
      cell: (job) => job.job_id
    },
    {
      key: "kind",
      header: "kind",
      sortValue: (job) => job.kind,
      cell: (job) => job.kind
    },
    {
      key: "state",
      header: "state",
      sortValue: (job) => job.state,
      cell: (job) => <StatusBadge value={job.state} />
    },
    {
      key: "progress",
      header: "progress",
      align: "right",
      sortValue: (job) => job.progress,
      cell: (job) => `${Math.round(job.progress * 100)}%`
    },
    {
      key: "stage",
      header: "stage",
      cell: (job) => stagePhase(job.current_stage)
    },
    {
      key: "action",
      header: "action",
      cell: (job) =>
        !terminalJobState(job.state) ? (
          <ConfirmActionDialog
            confirmLabel="작업 취소"
            description={
              <>
                진행 중인 <code>{job.kind}</code> 작업을 취소합니다.
              </>
            }
            onConfirm={() => onCancelJob(job.job_id)}
            title="작업 취소"
            trigger={
              <Button
                aria-label="취소"
                size="icon-sm"
                title="취소"
                type="button"
                variant="outline"
              >
                <XCircle aria-hidden="true" size={16} />
              </Button>
            }
          />
        ) : null
    }
  ];
  return (
    <Panel title="Backup / Restore Jobs">
      {activeJobs.length > 0 ? (
        <div className="job-progress-list">
          {activeJobs.map((job) => (
            <JobProgress job={job} key={job.job_id} />
          ))}
        </div>
      ) : null}
      <VirtualTable
        as="table"
        caption="백업/복원 작업 목록"
        columns={columns}
        emptyHint="진행 중이거나 완료된 백업/복원 작업이 없습니다."
        rowKey={(job) => job.job_id}
        rows={jobRows}
      />
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
      cell: (a) => backupProfileLabel(nestedRecord(a.manifest, "backup")?.["profile"])
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
            <Button
              aria-label="manifest 보기"
              onClick={() => setViewing(a)}
              size="icon-sm"
              title="manifest 보기"
              type="button"
              variant="outline"
            >
              <FileText aria-hidden="true" size={16} />
            </Button>
            {href && (
              <Button asChild size="icon-sm" variant="outline">
                <a aria-label="다운로드" href={href} title="다운로드">
                  <Download aria-hidden="true" size={16} />
                </a>
              </Button>
            )}
            <ConfirmActionDialog
              confirmLabel="삭제"
              description={
                <>
                  백업본 <strong>{a.display_name ?? a.artifact_id}</strong>을(를) 영구
                  삭제합니다. 되돌릴 수 없습니다.
                </>
              }
              onConfirm={() => onDeleteArtifact(a.artifact_id)}
              title="백업본 삭제"
              trigger={
                <Button
                  aria-label="삭제"
                  size="icon-sm"
                  title="삭제"
                  type="button"
                  variant="outline"
                >
                  <Trash2 aria-hidden="true" size={16} />
                </Button>
              }
            />
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
