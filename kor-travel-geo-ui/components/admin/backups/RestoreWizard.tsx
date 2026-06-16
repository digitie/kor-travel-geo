"use client";

import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, RotateCcw, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  BackupArtifact,
  LoadJobStatus,
  RestoreDryRunResult,
  postJson,
  requestJson
} from "@/lib/api";
import { formatBytes } from "@/lib/format";

type RestoreMode = "new_database" | "replace_current";
type WizardStep = 1 | 2 | 3 | 4;

const STEP_LABELS: Record<WizardStep, string> = {
  1: "1. 백업·모드 선택",
  2: "2. manifest 미리보기",
  3: "3. dry-run 검사",
  4: "4. 확인·실행"
};

export function RestoreWizard({
  onSubmitted
}: {
  onSubmitted?: (result: LoadJobStatus) => void;
}) {
  const [artifacts, setArtifacts] = useState<BackupArtifact[]>([]);
  const [step, setStep] = useState<WizardStep>(1);
  const [artifactId, setArtifactId] = useState("");
  const [archivePath, setArchivePath] = useState("");
  const [mode, setMode] = useState<RestoreMode>("new_database");
  const [targetDatabase, setTargetDatabase] = useState("kor_travel_geo_restore");
  const [confirmation, setConfirmation] = useState("");
  const [dryRun, setDryRun] = useState<RestoreDryRunResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<LoadJobStatus | null>(null);

  const loadArtifacts = useCallback(async () => {
    try {
      const rows = await requestJson<BackupArtifact[]>("/admin/backups?limit=50&state=available");
      setArtifacts(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
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
    setBusy(true);
    setError(null);
    try {
      const result = await postJson<RestoreDryRunResult>("/admin/restores/dry-run", {
        artifact_id: artifactId || undefined,
        archive_path: artifactId ? undefined : archivePath || undefined,
        mode,
        target_database: targetDatabase || undefined
      });
      setDryRun(result);
      setStep(3);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [artifactId, archivePath, mode, targetDatabase]);

  const submitRestore = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await postJson<LoadJobStatus>("/admin/restores", restoreBody);
      setSubmitted(result);
      onSubmitted?.(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [restoreBody, onSubmitted]);

  const step1Valid = Boolean(artifactId || archivePath) && Boolean(targetDatabase);
  const confirmationValid =
    mode === "new_database" ||
    (expectedConfirmation !== null && confirmation === expectedConfirmation);
  // The dry-run is the safety gate: a can_restore=false result must block submit (not just
  // warn), otherwise the wizard would bypass its own blockers. Codex H1 review of #235.
  const canSubmit = confirmationValid && !busy && dryRun?.can_restore === true;

  return (
    <Panel title="복원 위저드">
      <ol className="wizard-steps" role="list">
        {([1, 2, 3, 4] as WizardStep[]).map((n) => (
          <li className={n === step ? "wizard-step active" : "wizard-step"} key={n}>
            {STEP_LABELS[n]}
          </li>
        ))}
      </ol>

      {error ? (
        <p className="wizard-error" role="alert">
          <XCircle size={15} /> {error}
        </p>
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
          <div className="field">
            <label htmlFor="rw-artifact">복원할 백업본 (artifact)</label>
            <select
              id="rw-artifact"
              onChange={(e) => setArtifactId(e.target.value)}
              value={artifactId}
            >
              <option value="">직접 경로 사용 (archive_path)</option>
              {artifacts.map((a) => (
                <option key={a.artifact_id} value={a.artifact_id}>
                  {(a.display_name ?? a.artifact_id) + ` · ${formatBytes(a.size_bytes)}`}
                </option>
              ))}
            </select>
          </div>
          {artifactId ? null : (
            <div className="field">
              <label htmlFor="rw-archive">백업본 직접 경로 (archive_path)</label>
              <input
                id="rw-archive"
                onChange={(e) => setArchivePath(e.target.value)}
                value={archivePath}
              />
            </div>
          )}
          <div className="field">
            <label htmlFor="rw-mode">복원 모드 (mode)</label>
            <select
              id="rw-mode"
              onChange={(e) => setMode(e.target.value as RestoreMode)}
              value={mode}
            >
              <option value="new_database">new_database — 새 DB로 복원 (안전)</option>
              <option value="replace_current">replace_current — 운영 DB 교체 (위험)</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="rw-target">복원 대상 DB 이름 (target_database)</label>
            <input
              id="rw-target"
              onChange={(e) => setTargetDatabase(e.target.value)}
              value={targetDatabase}
            />
            {mode === "replace_current" ? (
              <small className="wizard-hint">
                replace_current는 현재 운영 DB와 같은 이름이어야 하며 typed confirmation이
                필요합니다.
              </small>
            ) : null}
          </div>
          <div className="button-row">
            <button
              className="button"
              disabled={!step1Valid}
              onClick={() => setStep(2)}
              type="button"
            >
              다음 <ArrowRight size={15} />
            </button>
          </div>
        </div>
      ) : step === 2 ? (
        <div className="wizard-preview">
          <ManifestPreview artifact={selected} archivePath={archivePath} />
          <div className="button-row">
            <button className="button secondary" onClick={() => setStep(1)} type="button">
              <ArrowLeft size={15} /> 이전
            </button>
            <button className="button" disabled={busy} onClick={runDryRun} type="button">
              dry-run 실행 <ArrowRight size={15} />
            </button>
          </div>
        </div>
      ) : step === 3 ? (
        <div className="wizard-dryrun">
          <DryRunReport result={dryRun} />
          <div className="button-row">
            <button className="button secondary" onClick={() => setStep(2)} type="button">
              <ArrowLeft size={15} /> 이전
            </button>
            <button className="button" onClick={() => setStep(4)} type="button">
              확인 단계로 <ArrowRight size={15} />
            </button>
          </div>
        </div>
      ) : (
        <div className="wizard-confirm">
          <DryRunReport result={dryRun} compact />
          {dryRun && !dryRun.can_restore ? (
            <p className="wizard-blocker" role="alert">
              <AlertTriangle size={15} /> dry-run이 복원 불가로 판정했습니다. 아래 blocker를 해소한
              뒤 다시 dry-run 하세요.
            </p>
          ) : null}
          {mode === "replace_current" && expectedConfirmation ? (
            <div className="confirm-box">
              <span className="confirm-title">
                운영 DB 교체 확인 — 정확히 <code>{expectedConfirmation}</code> 를 입력하세요
              </span>
              <input
                aria-label="typed confirmation"
                onChange={(e) => setConfirmation(e.target.value)}
                value={confirmation}
              />
            </div>
          ) : null}
          <div className="button-row">
            <button className="button secondary" onClick={() => setStep(3)} type="button">
              <ArrowLeft size={15} /> 이전
            </button>
            <button className="button" disabled={!canSubmit} onClick={submitRestore} type="button">
              <RotateCcw size={15} /> 복원 시작
            </button>
          </div>
        </div>
      )}
    </Panel>
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
  const database = nested(manifest, "database");
  const backup = nested(manifest, "backup");
  const rowCounts = nested(manifest, "row_counts");
  return (
    <div className="wizard-manifest">
      <dl className="wizard-meta">
        <div>
          <dt>profile</dt>
          <dd>{text(backup?.profile) ?? "-"}</dd>
        </div>
        <div>
          <dt>PostgreSQL</dt>
          <dd>{text(database?.postgres_version) ?? "-"}</dd>
        </div>
        <div>
          <dt>PostGIS</dt>
          <dd>{text(database?.postgis_version) ?? "-"}</dd>
        </div>
        <div>
          <dt>size</dt>
          <dd>{formatBytes(artifact.size_bytes)}</dd>
        </div>
      </dl>
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
          {checks.map((c) => (
            <li key={c.label}>
              {c.ok === true ? "✅" : c.ok === false ? "❌" : "—"} {c.label}
            </li>
          ))}
        </ul>
      ) : null}
      {!compact ? (
        <p className="wizard-hint">
          버전 — 백업 {result.backup_postgres_version ?? "?"}/{result.backup_postgis_version ?? "?"}{" "}
          → 대상 {result.target_postgres_version ?? "?"}/{result.target_postgis_version ?? "?"}
        </p>
      ) : null}
      {result.blockers && result.blockers.length > 0 ? (
        <div className="wizard-list blocker">
          <strong>blockers</strong>
          <ul>
            {result.blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {result.warnings && result.warnings.length > 0 ? (
        <div className="wizard-list warn">
          <strong>warnings</strong>
          <ul>
            {result.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function nested(value: Record<string, unknown>, key: string): Record<string, unknown> | undefined {
  const v = value[key];
  return v && typeof v === "object" ? (v as Record<string, unknown>) : undefined;
}

function text(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}
