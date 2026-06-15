"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Download, RefreshCw, Upload } from "lucide-react";
import { useMemo, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError, postJson, requestJson } from "@/lib/api";
import { uploadSlotFile, type SlotUploadProgress } from "@/lib/multipart-upload";
import {
  isEpostCategory,
  isResumableSession,
  isValidYyyymm,
  sourceFilesPaths,
  sourceRoleLabels,
  suggestYyyymm,
  type EpostServerFetchResponse,
  type SourceFileCategoryCatalog,
  type SourceFileCategoryInfo,
  type UploadSessionStatus
} from "@/lib/source-files";

const EMPTY_CATEGORIES: SourceFileCategoryInfo[] = [];
const EMPTY_SESSIONS: UploadSessionStatus[] = [];

type DuplicateConflict = {
  category: SourceFileCategoryInfo["category"];
  userYyyymm: string;
  existing: UploadSessionStatus | null;
  message: string;
};

export function UploadTab() {
  const queryClient = useQueryClient();
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [progress, setProgress] = useState<Record<string, SlotUploadProgress>>({});
  const [conflict, setConflict] = useState<DuplicateConflict | null>(null);
  const [lastResult, setLastResult] = useState<unknown>(null);

  const { data: catalog } = useQuery({
    queryKey: ["source-file-categories"],
    queryFn: () => requestJson<SourceFileCategoryCatalog>(sourceFilesPaths.categories())
  });
  const categories = catalog?.categories ?? EMPTY_CATEGORIES;

  const { data: resumable = EMPTY_SESSIONS, refetch: refetchSessions } = useQuery({
    queryKey: ["upload-sessions", "resumable"],
    queryFn: async () => {
      const all = await requestJson<UploadSessionStatus[]>(
        sourceFilesPaths.uploadSessionsList()
      );
      return all.filter(isResumableSession);
    }
  });

  function onSlotProgress(next: SlotUploadProgress) {
    setProgress((current) => ({ ...current, [next.slot]: next }));
  }

  const createSession = useMutation({
    mutationFn: (request: { category: string; userYyyymm: string; displayName: string }) =>
      postJson<UploadSessionStatus>(sourceFilesPaths.uploadSessions(), {
        category: request.category,
        user_yyyymm: request.userYyyymm,
        display_name: request.displayName,
        storage_kind: "rustfs",
        upload_strategy: "multipart"
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["upload-sessions"] });
    },
    onError: (error, variables) => {
      if (error instanceof ApiError && error.status === 409) {
        setConflict({
          category: variables.category as SourceFileCategoryInfo["category"],
          userYyyymm: variables.userYyyymm,
          existing: parseConflictSession(error.message),
          message: error.message
        });
      } else {
        setLastResult({ error: error instanceof Error ? error.message : String(error) });
      }
    }
  });

  const epostFetch = useMutation({
    mutationFn: (request: { category: SourceFileCategoryInfo["category"]; userYyyymm: string }) =>
      postJson<EpostServerFetchResponse>(sourceFilesPaths.epostFetch(), {
        category: request.category,
        user_yyyymm: request.userYyyymm,
        enqueue_load: true
      }),
    onSuccess: (result) => {
      setLastResult({
        category: result.category,
        upload_session_id: result.upload_session.upload_session_id,
        source_file_group_id: result.registration?.source_file_group_id,
        load_job_id: result.load_job_id,
        load_job_kind: result.load_job_kind,
        warnings: result.warnings,
        validation: result.validation
      });
      void queryClient.invalidateQueries({ queryKey: ["upload-sessions"] });
    },
    onError: (error) => {
      setLastResult({ error: error instanceof Error ? error.message : String(error) });
      void queryClient.invalidateQueries({ queryKey: ["upload-sessions"] });
    }
  });

  async function startUpload(
    category: SourceFileCategoryInfo,
    userYyyymm: string,
    file: File
  ) {
    setConflict(null);
    setLastResult(null);
    setProgress({});
    let session: UploadSessionStatus;
    try {
      session = await createSession.mutateAsync({
        category: category.category,
        userYyyymm,
        displayName: file.name
      });
    } catch {
      return; // 409 / error handled in onError
    }
    await runUpload(session, file);
  }

  async function runUpload(session: UploadSessionStatus, file: File) {
    const slot = session.file_slots[0];
    if (!slot) {
      setLastResult({ error: "세션에 업로드 슬롯이 없습니다" });
      return;
    }
    try {
      const finished = await uploadSlotFile({
        sessionId: session.upload_session_id,
        slotId: slot.slot,
        file,
        partSizeBytes: session.part_size_bytes,
        onProgress: onSlotProgress
      });
      // After upload completes, register the session into the registry.
      const registered = await postJson<UploadSessionStatus>(
        sourceFilesPaths.registerSession(session.upload_session_id),
        {}
      );
      setLastResult({
        source_file_group_id: registered.source_file_group_id,
        state: registered.state,
        registration_state: registered.registration_state,
        finished_state: finished.state
      });
      void queryClient.invalidateQueries({ queryKey: ["upload-sessions"] });
    } catch (error) {
      setLastResult({ error: error instanceof Error ? error.message : String(error) });
      void queryClient.invalidateQueries({ queryKey: ["upload-sessions"] });
    }
  }

  return (
    <div className="grid two">
      <Panel
        title="카테고리별 업로드"
        actions={
          <button className="icon-button" onClick={() => void refetchSessions()} title="새로고침" type="button">
            <RefreshCw size={16} />
          </button>
        }
      >
        <div className="source-card-grid">
          {categories.map((category) => (
            <CategoryCard
              category={category}
              isActive={activeCategory === category.category}
              key={category.category}
              onSelect={() =>
                setActiveCategory(activeCategory === category.category ? null : category.category)
              }
              onEpostFetch={(yyyymm) =>
                void epostFetch.mutate({
                  category: category.category,
                  userYyyymm: yyyymm
                })
              }
              onUpload={(yyyymm, file) => void startUpload(category, yyyymm, file)}
              progress={progress}
              fetchingEpost={epostFetch.isPending}
              uploading={createSession.isPending}
            />
          ))}
          {categories.length === 0 ? <p className="form-note">카테고리 카탈로그를 불러오는 중…</p> : null}
        </div>
      </Panel>

      <div className="source-side-column">
        <ResumableSessions sessions={resumable} />
        {lastResult ? (
          <Panel title="최근 결과">
            <pre className="json-box">{JSON.stringify(lastResult, null, 2)}</pre>
          </Panel>
        ) : null}
      </div>

      {conflict ? (
        <DuplicateSessionDialog
          conflict={conflict}
          onClose={() => setConflict(null)}
          onResume={(session) => {
            setConflict(null);
            setActiveCategory(session.category);
            setLastResult({
              resumed_session: session.upload_session_id,
              state: session.state,
              hint: "위 카테고리 카드에서 같은 파일을 다시 선택하면 이어서 업로드합니다."
            });
          }}
        />
      ) : null}
    </div>
  );
}

function CategoryCard({
  category,
  fetchingEpost,
  isActive,
  onEpostFetch,
  onSelect,
  onUpload,
  progress,
  uploading
}: {
  category: SourceFileCategoryInfo;
  fetchingEpost: boolean;
  isActive: boolean;
  onEpostFetch: (userYyyymm: string) => void;
  onSelect: () => void;
  onUpload: (userYyyymm: string, file: File) => void;
  progress: Record<string, SlotUploadProgress>;
  uploading: boolean;
}) {
  const [userYyyymm, setUserYyyymm] = useState(() => suggestYyyymm());
  const [file, setFile] = useState<File | null>(null);
  const epost = isEpostCategory(category.category);
  const slotProgress = useMemo(() => Object.values(progress), [progress]);
  const yyyymmValid = isValidYyyymm(userYyyymm);

  return (
    <article className={isActive ? "source-card active" : "source-card"}>
      <header className="source-card-head">
        <button className="source-card-title" onClick={onSelect} type="button">
          <strong>{category.label}</strong>
          <span>{category.category}</span>
        </button>
        <StatusBadge value={sourceRoleLabels[category.role]} />
      </header>
      <dl className="source-card-meta">
        <div>
          <dt>그룹 종류</dt>
          <dd>{category.group_kind}</dd>
        </div>
        <div>
          <dt>선택 여부</dt>
          <dd>{category.optional ? "선택(optional)" : "필수"}</dd>
        </div>
        {category.expected_member_kinds.length > 0 ? (
          <div>
            <dt>기대 멤버</dt>
            <dd>{category.expected_member_kinds.join(", ")}</dd>
          </div>
        ) : null}
      </dl>

      {epost ? (
        <EpostFetchControls
          fetching={fetchingEpost}
          onFetch={() => onEpostFetch(userYyyymm)}
          onYyyymmChange={setUserYyyymm}
          userYyyymm={userYyyymm}
          yyyymmValid={yyyymmValid}
        />
      ) : (
        <div className="source-card-upload">
          <label className="field">
            <span>기준년월 (user_yyyymm)</span>
            <input
              maxLength={6}
              onChange={(event) => setUserYyyymm(event.target.value.replace(/[^\d]/g, ""))}
              placeholder="예: 202606"
              value={userYyyymm}
            />
          </label>
          {!yyyymmValid ? <p className="form-note warn">YYYYMM 6자리를 입력하세요.</p> : null}
          <input
            aria-label={`${category.label} 파일 선택`}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            type="file"
          />
          <button
            className="button"
            disabled={!file || !yyyymmValid || uploading}
            onClick={() => file && onUpload(userYyyymm, file)}
            type="button"
          >
            <Upload size={16} />
            업로드
          </button>
          {slotProgress.length > 0 ? (
            <div className="source-progress-list">
              {slotProgress.map((item) => (
                <SlotProgressBar key={item.slot} progress={item} />
              ))}
            </div>
          ) : null}
        </div>
      )}
    </article>
  );
}

function SlotProgressBar({ progress }: { progress: SlotUploadProgress }) {
  const pct =
    progress.totalBytes > 0
      ? Math.min(100, Math.round((progress.uploadedBytes / progress.totalBytes) * 100))
      : 0;
  return (
    <div className="progress-line">
      <div className="progress-label">
        <strong>{progress.slot}</strong>
        <span>
          {progress.state === "done" ? (
            <>
              <CheckCircle2 size={13} /> 완료
            </>
          ) : progress.state === "error" ? (
            <>
              <AlertTriangle size={13} /> 실패
            </>
          ) : (
            `${pct}% · 파트 ${progress.partsDone}/${progress.partsTotal}`
          )}
        </span>
      </div>
      <div className="progress-shell">
        <div className="progress-bar" style={{ width: `${progress.state === "done" ? 100 : pct}%` }} />
      </div>
      {progress.error ? <p className="form-note warn">{progress.error}</p> : null}
    </div>
  );
}

function EpostFetchControls({
  fetching,
  onFetch,
  onYyyymmChange,
  userYyyymm,
  yyyymmValid
}: {
  fetching: boolean;
  onFetch: () => void;
  onYyyymmChange: (value: string) => void;
  userYyyymm: string;
  yyyymmValid: boolean;
}) {
  return (
    <div className="source-card-upload">
      <label className="field">
        <span>기준년월 (user_yyyymm)</span>
        <input
          maxLength={6}
          onChange={(event) => onYyyymmChange(event.target.value.replace(/[^\d]/g, ""))}
          placeholder="예: 202606"
          value={userYyyymm}
        />
      </label>
      {!yyyymmValid ? <p className="form-note warn">YYYYMM 6자리를 입력하세요.</p> : null}
      <button
        className="button secondary"
        disabled={!yyyymmValid || fetching}
        onClick={onFetch}
        title="epost 서버 fetch"
        type="button"
      >
        <Download size={16} />
        {fetching ? "받는 중" : "epost 받기"}
      </button>
    </div>
  );
}

function ResumableSessions({ sessions }: { sessions: UploadSessionStatus[] }) {
  return (
    <Panel title="재개 가능한 업로드">
      {sessions.length === 0 ? (
        <p className="form-note">재개할 수 있는 진행 중 세션이 없습니다.</p>
      ) : (
        <table className="table compact">
          <thead>
            <tr>
              <th>카테고리</th>
              <th>기준월</th>
              <th>상태</th>
              <th>업로드</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((session) => (
              <tr key={session.upload_session_id}>
                <td>{session.category}</td>
                <td>{session.user_yyyymm}</td>
                <td>
                  <StatusBadge value={session.state} />
                </td>
                <td>
                  {session.uploaded_file_count}/{session.expected_file_count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

function DuplicateSessionDialog({
  conflict,
  onClose,
  onResume
}: {
  conflict: DuplicateConflict;
  onClose: () => void;
  onResume: (session: UploadSessionStatus) => void;
}) {
  return (
    <div className="modal-backdrop">
      <dialog className="modal" open aria-label="중복 업로드 세션">
        <h2>이미 진행 중인 업로드 세션이 있습니다</h2>
        <p className="form-note">
          {conflict.category} · {conflict.userYyyymm} 조합의 비종료 세션이 이미 존재합니다 (409).
          중복 그룹과 대용량 orphan 객체를 막기 위해 새로 만들지 않고 기존 세션을 재개합니다.
        </p>
        {conflict.existing ? (
          <dl className="criteria-grid">
            <div>
              <dt>세션 ID</dt>
              <dd>{conflict.existing.upload_session_id}</dd>
            </div>
            <div>
              <dt>상태</dt>
              <dd>{conflict.existing.state}</dd>
            </div>
            <div>
              <dt>업로드 슬롯</dt>
              <dd>
                {conflict.existing.uploaded_file_count}/{conflict.existing.expected_file_count}
              </dd>
            </div>
          </dl>
        ) : (
          <pre className="json-box compact-json">{conflict.message}</pre>
        )}
        <div className="button-row">
          {conflict.existing ? (
            <button className="button" onClick={() => onResume(conflict.existing!)} type="button">
              기존 세션 재개
            </button>
          ) : null}
          <button className="button secondary" onClick={onClose} type="button">
            닫기
          </button>
        </div>
      </dialog>
    </div>
  );
}

function parseConflictSession(message: string): UploadSessionStatus | null {
  try {
    const parsed = JSON.parse(message) as { detail?: unknown } | UploadSessionStatus;
    const detail = (parsed as { detail?: unknown }).detail ?? parsed;
    if (detail && typeof detail === "object" && "upload_session_id" in detail) {
      return detail as UploadSessionStatus;
    }
    if (
      detail &&
      typeof detail === "object" &&
      "session" in detail &&
      (detail as { session?: unknown }).session
    ) {
      return (detail as { session: UploadSessionStatus }).session;
    }
  } catch {
    return null;
  }
  return null;
}
