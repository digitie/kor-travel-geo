"use client";

import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, RotateCcw, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useReducer } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldLabel,
  FieldLegend,
  FieldSet,
  FieldTitle
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { NativeSelect } from "@/components/ui/native-select";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { HelpTip } from "@/components/admin/shared/HelpTip";
import { IssueList } from "@/components/admin/shared/IssueList";
import { TypedConfirmField } from "@/components/admin/shared/TypedConfirmField";
import { WizardSteps } from "@/components/admin/shared/WizardSteps";
import { KeyValueGrid } from "@/components/admin/shared/KeyValueGrid";
import { nestedRecord, textValue, triState } from "@/components/admin/backups/manifest-utils";
import {
  BackupArtifact,
  LoadJobStatus,
  RestoreDryRunResult,
  getErrorMessage,
  postJson,
  requestJson
} from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { pgIdentifierSchema } from "@/lib/schemas";
import { toast } from "@/lib/toast";

type RestoreMode = "new_database" | "replace_current";
type WizardStep = 1 | 2 | 3 | 4;

const STEP_LABELS: Record<WizardStep, string> = {
  1: "1. 백업·모드 선택",
  2: "2. manifest 미리보기",
  3: "3. dry-run 검사",
  4: "4. 확인·실행"
};

type RestoreWizardState = {
  artifacts: BackupArtifact[];
  step: WizardStep;
  artifactId: string;
  archivePath: string;
  mode: RestoreMode;
  targetDatabase: string;
  confirmation: string;
  dryRun: RestoreDryRunResult | null;
  busy: boolean;
  error: string | null;
  submitted: LoadJobStatus | null;
};

const INITIAL_RESTORE_WIZARD_STATE: RestoreWizardState = {
  artifacts: [],
  step: 1,
  artifactId: "",
  archivePath: "",
  mode: "new_database",
  targetDatabase: "kor_travel_geo_restore",
  confirmation: "",
  dryRun: null,
  busy: false,
  error: null,
  submitted: null
};

function restoreWizardReducer(
  state: RestoreWizardState,
  patch: Partial<RestoreWizardState>
): RestoreWizardState {
  return { ...state, ...patch };
}

function artifactOptionLabel(artifact: BackupArtifact): string {
  const name = artifact.display_name ?? artifact.artifact_id;
  const created = artifact.created_at ? ` · ${artifact.created_at.slice(0, 10)}` : "";
  return `${name} · ${formatBytes(artifact.size_bytes)}${created}`;
}

export function RestoreWizard({
  onSubmitted
}: {
  onSubmitted?: (result: LoadJobStatus) => void;
}) {
  const [state, dispatchState] = useReducer(
    restoreWizardReducer,
    INITIAL_RESTORE_WIZARD_STATE
  );
  const {
    artifacts,
    step,
    artifactId,
    archivePath,
    mode,
    targetDatabase,
    confirmation,
    dryRun,
    busy,
    error,
    submitted
  } = state;

  const loadArtifacts = useCallback(async () => {
    try {
      const rows = await requestJson<BackupArtifact[]>("/admin/backups?limit=50&state=available");
      dispatchState({ artifacts: rows });
    } catch (err) {
      dispatchState({ error: getErrorMessage(err) });
    }
  }, []);

  useEffect(() => {
    void loadArtifacts();
  }, [loadArtifacts]);

  const selected = useMemo(
    () => artifacts.find((a) => a.artifact_id === artifactId) ?? null,
    [artifacts, artifactId]
  );

  // For replace_current the backend resolves the target to the current DB and the
  // confirmation must be exactly `RESTORE <current>`. The dry-run echoes the resolved target.
  const expectedConfirmation =
    mode === "replace_current" && dryRun?.target_database
      ? `RESTORE ${dryRun.target_database}`
      : null;

  const restoreBody = useMemo(
    () => ({
      artifact_id: artifactId || undefined,
      archive_path: artifactId ? undefined : archivePath || undefined,
      mode,
      target_database: mode === "replace_current" ? targetDatabase || undefined : targetDatabase,
      confirmation: mode === "replace_current" ? confirmation || undefined : undefined
    }),
    [artifactId, archivePath, mode, targetDatabase, confirmation]
  );

  const runDryRun = useCallback(async () => {
    dispatchState({ busy: true, error: null });
    try {
      const result = await postJson<RestoreDryRunResult>("/admin/restores/dry-run", {
        artifact_id: artifactId || undefined,
        archive_path: artifactId ? undefined : archivePath || undefined,
        mode,
        target_database: targetDatabase || undefined
      });
      dispatchState({ dryRun: result, step: 3 });
    } catch (err) {
      const message = getErrorMessage(err);
      dispatchState({ error: message });
      toast.error("dry-run 실패", message);
    } finally {
      dispatchState({ busy: false });
    }
  }, [artifactId, archivePath, mode, targetDatabase]);

  const submitRestore = useCallback(async () => {
    dispatchState({ busy: true, error: null });
    try {
      const result = await postJson<LoadJobStatus>("/admin/restores", restoreBody);
      dispatchState({ submitted: result });
      toast.success("복원 job이 제출됐습니다");
      onSubmitted?.(result);
    } catch (err) {
      const message = getErrorMessage(err);
      dispatchState({ error: message });
      toast.error("복원 시작 실패", message);
    } finally {
      dispatchState({ busy: false });
    }
  }, [restoreBody, onSubmitted]);

  const targetDbCheck = pgIdentifierSchema.safeParse(targetDatabase);
  const targetDbError =
    targetDatabase.length > 0 && !targetDbCheck.success
      ? targetDbCheck.error.issues[0]?.message ?? "형식이 올바르지 않습니다"
      : null;
  const step1Valid =
    Boolean(artifactId || archivePath) && Boolean(targetDatabase) && !targetDbError;
  const confirmationValid =
    mode === "new_database" ||
    (expectedConfirmation !== null && confirmation === expectedConfirmation);
  // The dry-run is the safety gate: a can_restore=false result must block submit (not just
  // warn), otherwise the wizard would bypass its own blockers. Codex H1 review of #235.
  const canSubmit = confirmationValid && !busy && dryRun?.can_restore === true;

  return (
    <Panel title="복원 위저드">
      <WizardSteps
        current={step - 1}
        steps={[STEP_LABELS[1], STEP_LABELS[2], STEP_LABELS[3], STEP_LABELS[4]]}
      />

      {error ? (
        <Alert role="alert" variant="destructive">
          <XCircle aria-hidden="true" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {submitted ? (
        <div className="wizard-done">
          <p>
            <CheckCircle2 size={16} /> 복원 job이 제출됐습니다 — [작업] 탭에서 진행률을 확인하세요.
          </p>
          <JsonBlock value={submitted} />
        </div>
      ) : step === 1 ? (
        <div className="form-grid">
          <Field>
            <span className="flex items-center gap-1">
              <FieldLabel htmlFor="rw-artifact">복원할 백업본</FieldLabel>
              <HelpTip label="복원할 백업본 도움말">
                API 필드 <code>artifact_id</code> — 등록된 백업본(state=available)을 선택합니다.
                선택하지 않으면 아래 직접 경로(<code>archive_path</code>)로 복원합니다.
              </HelpTip>
            </span>
            <NativeSelect
              id="rw-artifact"
              onChange={(e) => dispatchState({ artifactId: e.target.value })}
              value={artifactId}
            >
              <option value="">직접 경로 사용</option>
              {artifacts.map((a) => (
                <option key={a.artifact_id} value={a.artifact_id}>
                  {artifactOptionLabel(a)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          {artifactId ? null : (
            <Field>
              <span className="flex items-center gap-1">
                <FieldLabel htmlFor="rw-archive">백업본 직접 경로</FieldLabel>
                <HelpTip label="백업본 직접 경로 도움말">
                  API 필드 <code>archive_path</code> — 서버 파일시스템의 백업 파일(
                  <code>.tar.zst</code>) 경로.
                </HelpTip>
              </span>
              <Input
                id="rw-archive"
                onChange={(e) => dispatchState({ archivePath: e.target.value })}
                placeholder="/data/backups/backup.tar.zst"
                value={archivePath}
              />
            </Field>
          )}
          <FieldSet>
            <FieldLegend className="flex items-center gap-1" variant="label">
              복원 모드
              <HelpTip label="복원 모드 도움말">
                API 필드 <code>mode</code> — <code>new_database</code> 또는{" "}
                <code>replace_current</code>로 전송됩니다.
              </HelpTip>
            </FieldLegend>
            <div className="grid gap-2">
              <ModeCard
                badge={<Badge tone="ok">안전</Badge>}
                checked={mode === "new_database"}
                description="별도 이름의 새 DB를 만들어 복원합니다 — 운영 DB는 그대로 둡니다."
                id="rw-mode-new"
                onSelect={() => dispatchState({ mode: "new_database" })}
                title="새 DB로 복원"
                value="new_database"
              />
              <ModeCard
                badge={<Badge tone="error">위험</Badge>}
                checked={mode === "replace_current"}
                description="현재 운영 DB를 이 백업으로 교체합니다 — typed confirmation이 필요합니다."
                destructive
                id="rw-mode-replace"
                onSelect={() => dispatchState({ mode: "replace_current" })}
                title="운영 DB 교체"
                value="replace_current"
              />
            </div>
          </FieldSet>
          <Field data-invalid={targetDbError ? true : undefined}>
            <span className="flex items-center gap-1">
              <FieldLabel htmlFor="rw-target">복원 대상 DB 이름</FieldLabel>
              <HelpTip label="복원 대상 DB 이름 도움말">
                API 필드 <code>target_database</code> — PostgreSQL 식별자: 소문자/숫자/밑줄, 문자로
                시작, 63자 이하.
              </HelpTip>
            </span>
            <Input
              aria-invalid={targetDbError ? true : undefined}
              id="rw-target"
              onChange={(e) => dispatchState({ targetDatabase: e.target.value })}
              value={targetDatabase}
            />
            {targetDbError ? <FieldError>{targetDbError}</FieldError> : null}
            {mode === "replace_current" ? (
              <FieldDescription>
                replace_current는 현재 운영 DB와 같은 이름이어야 하며 typed confirmation이
                필요합니다.
              </FieldDescription>
            ) : null}
          </Field>
          <div className="button-row">
            <Button disabled={!step1Valid} onClick={() => dispatchState({ step: 2 })} type="button">
              다음 <ArrowRight aria-hidden="true" size={15} />
            </Button>
          </div>
        </div>
      ) : step === 2 ? (
        <div className="wizard-preview">
          <ManifestPreview archivePath={archivePath} artifact={selected} />
          <div className="button-row">
            <Button onClick={() => dispatchState({ step: 1 })} type="button" variant="outline">
              <ArrowLeft aria-hidden="true" size={15} /> 이전
            </Button>
            <Button disabled={busy} onClick={runDryRun} type="button">
              dry-run 실행 <ArrowRight aria-hidden="true" size={15} />
            </Button>
          </div>
        </div>
      ) : step === 3 ? (
        <div className="wizard-dryrun">
          <DryRunReport result={dryRun} />
          <div className="button-row">
            <Button onClick={() => dispatchState({ step: 2 })} type="button" variant="outline">
              <ArrowLeft aria-hidden="true" size={15} /> 이전
            </Button>
            <Button onClick={() => dispatchState({ step: 4 })} type="button">
              확인 단계로 <ArrowRight aria-hidden="true" size={15} />
            </Button>
          </div>
        </div>
      ) : (
        <div className="wizard-confirm">
          <DryRunReport compact result={dryRun} />
          {dryRun && !dryRun.can_restore ? (
            <p className="wizard-blocker" role="alert">
              <AlertTriangle size={15} /> dry-run이 복원 불가로 판정했습니다. 아래 blocker를 해소한
              뒤 다시 dry-run 하세요.
            </p>
          ) : null}
          {mode === "replace_current" && expectedConfirmation ? (
            <TypedConfirmField
              heading="운영 DB 교체 확인"
              label="typed confirmation"
              onChange={(value) => dispatchState({ confirmation: value })}
              phrase={expectedConfirmation}
              value={confirmation}
            />
          ) : null}
          <div className="button-row">
            <Button onClick={() => dispatchState({ step: 3 })} type="button" variant="outline">
              <ArrowLeft aria-hidden="true" size={15} /> 이전
            </Button>
            <Button disabled={!canSubmit} onClick={submitRestore} type="button">
              <RotateCcw aria-hidden="true" size={15} /> 복원 시작
            </Button>
          </div>
        </div>
      )}
    </Panel>
  );
}

/** 복원 모드 라디오 카드 — 안전(new_database) 기본, 위험(replace_current)은 destructive 강조. */
function ModeCard({
  id,
  value,
  title,
  description,
  badge,
  checked,
  destructive = false,
  onSelect
}: {
  id: string;
  value: RestoreMode;
  title: string;
  description: string;
  badge: React.ReactNode;
  checked: boolean;
  destructive?: boolean;
  onSelect: () => void;
}) {
  return (
    <FieldLabel
      className={
        destructive
          ? "has-data-checked:border-[color-mix(in_srgb,var(--danger)_45%,transparent)] has-data-checked:bg-[color-mix(in_srgb,var(--danger)_6%,white)]"
          : undefined
      }
      htmlFor={id}
    >
      <Field orientation="horizontal">
        <FieldContent>
          <FieldTitle>
            {title} {badge}
          </FieldTitle>
          <FieldDescription>{description}</FieldDescription>
        </FieldContent>
        <input
          aria-label={title}
          checked={checked}
          className="size-4 shrink-0 accent-[var(--brand)]"
          data-checked={checked ? "" : undefined}
          id={id}
          name="rw-mode"
          onChange={onSelect}
          type="radio"
          value={value}
        />
      </Field>
    </FieldLabel>
  );
}

function ManifestPreview({
  artifact,
  archivePath
}: {
  artifact: BackupArtifact | null;
  archivePath: string;
}) {
  if (!artifact) {
    return (
      <p className="wizard-hint">
        직접 경로(<code>{archivePath || "미입력"}</code>)로 복원합니다. manifest 미리보기는 등록된
        artifact를 선택할 때 제공됩니다.
      </p>
    );
  }
  const manifest = artifact.manifest ?? {};
  const database = nestedRecord(manifest, "database");
  const backup = nestedRecord(manifest, "backup");
  const rowCounts = nestedRecord(manifest, "row_counts");
  return (
    <div className="wizard-manifest">
      <KeyValueGrid
        items={[
          { label: "profile", value: textValue(backup?.profile) ?? "-" },
          { label: "PostgreSQL", value: textValue(database?.postgres_version) ?? "-" },
          { label: "PostGIS", value: textValue(database?.postgis_version) ?? "-" },
          { label: "size", value: formatBytes(artifact.size_bytes) }
        ]}
      />
      {rowCounts ? (
        <div className="wizard-rowcounts">
          <strong>row_counts</strong>
          <JsonBlock value={rowCounts} />
        </div>
      ) : (
        <p className="wizard-hint">이 백업 manifest에는 row_counts가 없습니다(legacy).</p>
      )}
    </div>
  );
}

function DryRunReport({
  result,
  compact = false
}: {
  result: RestoreDryRunResult | null;
  compact?: boolean;
}) {
  if (!result) {
    return <p className="wizard-hint">아직 dry-run을 실행하지 않았습니다.</p>;
  }
  const checks: { label: string; ok: boolean | null | undefined }[] = [
    { label: "archive sha256", ok: result.archive_sha256_ok },
    { label: "internal checksums", ok: result.internal_checksums_ok },
    { label: "manifest", ok: result.manifest_ok }
  ];
  return (
    <div className="wizard-dryrun-report">
      <p className="wizard-verdict">
        {result.can_restore ? (
          <StatusBadge tone="ok" value="복원 가능" />
        ) : (
          <StatusBadge tone="error" value="복원 불가" />
        )}{" "}
        <span>대상 DB: {result.target_database ?? "-"}</span>
      </p>
      {!compact ? (
        <ul className="wizard-checks">
          {checks.map((c) => {
            const state = triState(c.ok);
            return (
              <li className="flex items-center gap-2" key={c.label}>
                <StatusBadge tone={state.tone} value={state.label} /> {c.label}
              </li>
            );
          })}
        </ul>
      ) : null}
      {!compact ? (
        <p className="wizard-hint">
          버전 — 백업 {result.backup_postgres_version ?? "?"}/{result.backup_postgis_version ?? "?"}{" "}
          → 대상 {result.target_postgres_version ?? "?"}/{result.target_postgis_version ?? "?"}
        </p>
      ) : null}
      {result.blockers && result.blockers.length > 0 ? (
        <IssueList items={result.blockers} title="blockers" tone="error" />
      ) : null}
      {result.warnings && result.warnings.length > 0 ? (
        <IssueList items={result.warnings} title="warnings" tone="warn" />
      ) : null}
    </div>
  );
}
