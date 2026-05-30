"use client";

import {
  Archive,
  Download,
  Play,
  RefreshCw,
  RotateCcw,
  Trash2,
  XCircle
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
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

export function BackupsPanel() {
  const [destinationDir, setDestinationDir] = useState("data/backups");
  const [allowedDirs, setAllowedDirs] = useState<string[]>([]);
  const [profile, setProfile] = useState<BackupProfile>("serving-ready");
  const [jobs, setJobs] = useState(4);
  const [compressionLevel, setCompressionLevel] = useState(3);
  const [callbackUrl, setCallbackUrl] = useState("");
  const [restoreArtifactId, setRestoreArtifactId] = useState("");
  const [restoreArchivePath, setRestoreArchivePath] = useState("");
  const [targetDatabase, setTargetDatabase] = useState("kraddr_geo_restore");
  const [restoreJobs, setRestoreJobs] = useState(4);
  const [runAnalyze, setRunAnalyze] = useState(true);
  const [runSmokeTest, setRunSmokeTest] = useState(true);
  const [artifacts, setArtifacts] = useState<BackupArtifact[]>([]);
  const [jobRows, setJobRows] = useState<LoadJobStatus[]>([]);
  const [lastResult, setLastResult] = useState<unknown>({ status: "READY" });

  const running = useMemo(
    () => jobRows.some((job) => !terminalJobState(job.state)),
    [jobRows]
  );

  async function loadAll() {
    try {
      const [nextArtifacts, nextJobs] = await Promise.all([
        requestJson<BackupArtifact[]>("/admin/backups?limit=50"),
        requestJson<LoadJobStatus[]>("/admin/jobs?limit=50")
      ]);
      setArtifacts(nextArtifacts);
      setJobRows(nextJobs.filter((job) => job.kind === "db_backup" || job.kind === "db_restore"));
    } catch (error) {
      setLastResult({ error: error instanceof Error ? error.message : String(error) });
    }
  }

  async function submitBackup(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await postJson<LoadJobStatus>("/admin/backups", {
        destination_dir: destinationDir || undefined,
        profile,
        jobs,
        compression_level: compressionLevel,
        callback_url: callbackUrl || undefined
      });
      setLastResult(result);
      await loadAll();
    } catch (error) {
      setLastResult({ error: error instanceof Error ? error.message : String(error) });
    }
  }

  async function submitRestore(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await postJson<LoadJobStatus>("/admin/restores", {
        artifact_id: restoreArtifactId || undefined,
        archive_path: restoreArchivePath || undefined,
        target_database: targetDatabase,
        jobs: restoreJobs,
        run_analyze: runAnalyze,
        run_smoke_test: runSmokeTest
      });
      setLastResult(result);
      await loadAll();
    } catch (error) {
      setLastResult({ error: error instanceof Error ? error.message : String(error) });
    }
  }

  async function cancelJob(jobId: string) {
    try {
      const result = await postJson<LoadJobStatus>(`/admin/jobs/${jobId}/cancel`, {});
      setLastResult(result);
      await loadAll();
    } catch (error) {
      setLastResult({ error: error instanceof Error ? error.message : String(error) });
    }
  }

  async function deleteArtifact(artifactId: string) {
    try {
      const result = await postJson<BackupArtifact>(`/admin/backups/${artifactId}/delete`, {});
      setLastResult(result);
      await loadAll();
    } catch (error) {
      setLastResult({ error: error instanceof Error ? error.message : String(error) });
    }
  }

  useEffect(() => {
    void loadAll();
  }, []);

  useEffect(() => {
    async function loadAllowedDirs() {
      try {
        const config = await requestJson<BackupAllowedDirs>("/admin/backups/allowed-dirs");
        setAllowedDirs(config.dirs);
        if (config.default_dir) {
          setDestinationDir(config.default_dir);
        }
      } catch {
        // 허용 디렉터리 조회 실패 시 직접 입력 폴백을 유지한다.
        setAllowedDirs([]);
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
  }, [running]);

  return (
    <div className="grid two">
      <Panel
        title="DB Backup"
        actions={
          <button className="button secondary" onClick={loadAll} type="button">
            <RefreshCw size={16} />
            새로고침
          </button>
        }
      >
        <form className="form-grid" onSubmit={submitBackup}>
          <div className="field">
            <label htmlFor="backup-destination">백업본 저장 폴더 (destination_dir)</label>
            {allowedDirs.length > 0 ? (
              <select
                id="backup-destination"
                value={destinationDir}
                onChange={(event) => setDestinationDir(event.target.value)}
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
                value={destinationDir}
                onChange={(event) => setDestinationDir(event.target.value)}
              />
            )}
          </div>
          <div className="field">
            <label htmlFor="backup-profile">백업 프로파일 (profile)</label>
            <select
              id="backup-profile"
              value={profile}
              onChange={(event) => setProfile(event.target.value as BackupProfile)}
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
            value={jobs}
            onChange={setJobs}
          />
          <NumberField
            id="backup-compression"
            label="압축 레벨 (compression_level)"
            max={19}
            min={1}
            value={compressionLevel}
            onChange={setCompressionLevel}
          />
          <div className="field">
            <label htmlFor="backup-callback">완료 알림 URL (callback_url)</label>
            <input
              id="backup-callback"
              value={callbackUrl}
              onChange={(event) => setCallbackUrl(event.target.value)}
            />
          </div>
          <button className="button" type="submit">
            <Archive size={16} />
            백업 시작
          </button>
        </form>
      </Panel>

      <Panel title="DB Restore">
        <form className="form-grid" onSubmit={submitRestore}>
          <div className="field">
            <label htmlFor="restore-artifact">복원할 백업본 (artifact_id)</label>
            <select
              id="restore-artifact"
              value={restoreArtifactId}
              onChange={(event) => setRestoreArtifactId(event.target.value)}
            >
              <option value="">직접 경로 사용</option>
              {artifacts
                .filter((artifact) => artifact.state === "available")
                .map((artifact) => (
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
              value={restoreArchivePath}
              onChange={(event) => setRestoreArchivePath(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="restore-target">복원 대상 DB 이름 (target_database)</label>
            <input
              id="restore-target"
              value={targetDatabase}
              onChange={(event) => setTargetDatabase(event.target.value)}
            />
          </div>
          <NumberField
            id="restore-jobs"
            label="병렬 작업 수 (jobs)"
            max={64}
            min={1}
            value={restoreJobs}
            onChange={setRestoreJobs}
          />
          <label className="checkbox-row">
            <input
              checked={runAnalyze}
              onChange={(event) => setRunAnalyze(event.target.checked)}
              type="checkbox"
            />
            ANALYZE
          </label>
          <label className="checkbox-row">
            <input
              checked={runSmokeTest}
              onChange={(event) => setRunSmokeTest(event.target.checked)}
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
                      onClick={() => void cancelJob(job.job_id)}
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
                        onClick={() => void deleteArtifact(artifact.artifact_id)}
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

      <Panel title="Last Response">
        <JsonBlock value={lastResult} />
      </Panel>
    </div>
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
