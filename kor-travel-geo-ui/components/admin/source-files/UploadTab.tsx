"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Download, RefreshCw, Upload } from "lucide-react";
import { useMemo, useReducer, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { type VirtualColumn, VirtualTable } from "@/components/ui/VirtualTable";
import { ApiError, postJson, requestJson } from "@/lib/api";
import { uploadSlotFile, type SlotUploadProgress } from "@/lib/multipart-upload";
import { useUploadSessionEvents } from "@/lib/use-upload-session-events";
import {
  activeServingCategorySet,
  isEpostCategory,
  isResumableSession,
  isValidYyyymm,
  servingUsageLabels,
  servingUsageNote,
  servingUsageTones,
  sourceFilesPaths,
  sourceRoleLabels,
  suggestYyyymm,
  type EpostServerFetchResponse,
  type SourceFileCategoryCatalog,
  type SourceFileCategoryInfo,
  type SourceMatchSet,
  type SourceMatchSetDetail,
  type SourceUploadProgressEvent,
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

type UploadViewState = {
  activeCategory: string | null;
  progress: Record<string, SlotUploadProgress>;
  conflict: DuplicateConflict | null;
  lastResult: unknown;
  epostError: { category: string; message: string } | null;
};

type UploadViewAction =
  | { type: "patch"; patch: Partial<UploadViewState> }
  | { type: "select-category"; category: string }
  | { type: "slot-progress"; progress: SlotUploadProgress };

const INITIAL_UPLOAD_VIEW_STATE: UploadViewState = {
  activeCategory: null,
  progress: {},
  conflict: null,
  lastResult: null,
  epostError: null
};

function uploadViewReducer(
  state: UploadViewState,
  action: UploadViewAction
): UploadViewState {
  switch (action.type) {
    case "patch":
      return { ...state, ...action.patch };
    case "select-category":
      return {
        ...state,
        activeCategory: state.activeCategory === action.category ? null : action.category
      };
    case "slot-progress":
      return {
        ...state,
        progress: { ...state.progress, [action.progress.slot]: action.progress }
      };
  }
}

export function UploadTab() {
  const queryClient = useQueryClient();
  const [viewState, dispatchView] = useReducer(uploadViewReducer, INITIAL_UPLOAD_VIEW_STATE);
  const { activeCategory, progress, conflict, lastResult, epostError } = viewState;

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

  // Active match set → which categories are actually in serving now (T-224).
  const { data: matchSets = [] } = useQuery({
    queryKey: ["source-match-sets"],
    queryFn: () => requestJson<SourceMatchSet[]>(sourceFilesPaths.matchSets())
  });
  const activeSet = matchSets.find((set) => set.state === "active");
  const { data: activeDetail } = useQuery({
    queryKey: ["source-match-set", activeSet?.source_match_set_id],
    queryFn: () =>
      requestJson<SourceMatchSetDetail>(sourceFilesPaths.matchSet(activeSet!.source_match_set_id)),
    enabled: Boolean(activeSet?.source_match_set_id)
  });
  const activeServing = useMemo(
    () => activeServingCategorySet(activeDetail?.items ?? []),
    [activeDetail]
  );

  function onSlotProgress(next: SlotUploadProgress) {
    dispatchView({ type: "slot-progress", progress: next });
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
        dispatchView({
          type: "patch",
          patch: {
            conflict: {
              category: variables.category as SourceFileCategoryInfo["category"],
              userYyyymm: variables.userYyyymm,
              existing: parseConflictSession(error.message),
              message: error.message
            }
          }
        });
      } else {
        dispatchView({
          type: "patch",
          patch: { lastResult: { error: error instanceof Error ? error.message : String(error) } }
        });
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
      dispatchView({
        type: "patch",
        patch: {
          epostError: null,
          lastResult: {
            category: result.category,
            upload_session_id: result.upload_session.upload_session_id,
            source_file_group_id: result.registration?.source_file_group_id,
            load_job_id: result.load_job_id,
            load_job_kind: result.load_job_kind,
            warnings: result.warnings,
            validation: result.validation
          }
        }
      });
      void queryClient.invalidateQueries({ queryKey: ["upload-sessions"] });
    },
    onError: (error, variables) => {
      const message = parseApiErrorMessage(error);
      dispatchView({
        type: "patch",
        patch: {
          epostError: { category: variables.category, message },
          lastResult: { error: message }
        }
      });
      void queryClient.invalidateQueries({ queryKey: ["upload-sessions"] });
    }
  });

  async function startUpload(
    category: SourceFileCategoryInfo,
    userYyyymm: string,
    file: File
  ) {
    dispatchView({
      type: "patch",
      patch: { conflict: null, lastResult: null, progress: {} }
    });
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
      dispatchView({
        type: "patch",
        patch: { lastResult: { error: "세션에 업로드 슬롯이 없습니다" } }
      });
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
      dispatchView({
        type: "patch",
        patch: {
          lastResult: {
            source_file_group_id: registered.source_file_group_id,
            state: registered.state,
            registration_state: registered.registration_state,
            finished_state: finished.state
          }
        }
      });
      void queryClient.invalidateQueries({ queryKey: ["upload-sessions"] });
    } catch (error) {
      dispatchView({
        type: "patch",
        patch: { lastResult: { error: error instanceof Error ? error.message : String(error) } }
      });
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
              hasActiveSet={Boolean(activeSet)}
              isActiveServing={activeServing.has(category.category)}
              key={category.category}
              onSelect={() => dispatchView({ type: "select-category", category: category.category })}
              onEpostFetch={(yyyymm) =>
                void epostFetch.mutate({
                  category: category.category,
                  userYyyymm: yyyymm
                })
              }
              onUpload={(yyyymm, file) => void startUpload(category, yyyymm, file)}
              progress={progress}
              fetchingEpost={
                epostFetch.isPending && epostFetch.variables?.category === category.category
              }
              epostError={
                epostError?.category === category.category ? epostError.message : null
              }
              uploading={createSession.isPending}
            />
          ))}
          {categories.length === 0 ? <p className="form-note">카테고리 카탈로그를 불러오는 중…</p> : null}
        </div>
      </Panel>

      <div className="source-side-column">
        <ResumableSessions
          sessions={resumable}
          onSessionTerminal={() =>
            void queryClient.invalidateQueries({ queryKey: ["upload-sessions"] })
          }
        />
        {lastResult ? (
          <Panel title="최근 결과">
            <pre className="json-box">{JSON.stringify(lastResult, null, 2)}</pre>
          </Panel>
        ) : null}
      </div>

      {conflict ? (
        <DuplicateSessionDialog
          conflict={conflict}
          onClose={() => dispatchView({ type: "patch", patch: { conflict: null } })}
          onResume={(session) => {
            dispatchView({
              type: "patch",
              patch: {
                conflict: null,
                activeCategory: session.category,
                lastResult: {
                  resumed_session: session.upload_session_id,
                  state: session.state,
                  hint: "위 카테고리 카드에서 같은 파일을 다시 선택하면 이어서 업로드합니다."
                }
              }
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
  epostError,
  isActive,
  hasActiveSet,
  isActiveServing,
  onEpostFetch,
  onSelect,
  onUpload,
  progress,
  uploading
}: {
  category: SourceFileCategoryInfo;
  fetchingEpost: boolean;
  epostError: string | null;
  isActive: boolean;
  /** Whether an active serving match set exists (else membership is unknown). */
  hasActiveSet: boolean;
  /** Whether this category is a non-omitted item of the active match set. */
  isActiveServing: boolean;
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
        <div className="source-card-badges">
          <StatusBadge
            value={servingUsageLabels[category.serving_usage]}
            tone={servingUsageTones[category.serving_usage]}
          />
          {hasActiveSet ? (
            <StatusBadge
              value={isActiveServing ? "현재 서빙 포함" : "현재 서빙 미포함"}
              tone={isActiveServing ? "ok" : "warn"}
            />
          ) : null}
        </div>
      </header>
      <p className="source-card-serving-note">
        {servingUsageNote(category.category, category.serving_usage)}
        {hasActiveSet && !isActiveServing ? (
          <>
            {" "}
            <span className="source-card-serving-emphasis">
              등록해도 활성 매칭 세트에 포함·활성화되기 전에는 서빙에 반영되지 않습니다(등록됨 ≠ 활용 중).
            </span>
          </>
        ) : null}
      </p>
      <dl className="source-card-meta">
        <div>
          <dt>구성 역할</dt>
          <dd>{sourceRoleLabels[category.role]}</dd>
        </div>
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
          error={epostError}
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
  error,
  fetching,
  onFetch,
  onYyyymmChange,
  userYyyymm,
  yyyymmValid
}: {
  error: string | null;
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
      {error ? (
        <p className="form-note warn" role="alert">
          epost 서버 fetch 실패: {error}
        </p>
      ) : null}
    </div>
  );
}

function ResumableSessions({
  sessions,
  onSessionTerminal
}: {
  sessions: UploadSessionStatus[];
  onSessionTerminal: () => void;
}) {
  const columns = useMemo<VirtualColumn<UploadSessionStatus>[]>(
    () => [
      { key: "category", header: "카테고리", cell: (session) => session.category },
      { key: "yyyymm", header: "기준월", cell: (session) => session.user_yyyymm },
      {
        key: "state",
        header: "상태",
        cell: (session) => <StatusBadge value={session.state} />
      },
      {
        key: "progress",
        header: "진행",
        cell: (session) => (
          <SessionProgressCell onTerminal={onSessionTerminal} session={session} />
        )
      }
    ],
    [onSessionTerminal]
  );

  return (
    <Panel title="재개 가능한 업로드">
      <VirtualTable
        as="table"
        columns={columns}
        compact
        emptyHint="재개할 수 있는 진행 중 세션이 없습니다."
        rowKey={(session) => session.upload_session_id}
        rows={sessions}
      />
    </Panel>
  );
}

function SessionProgressCell({
  session,
  onTerminal
}: {
  session: UploadSessionStatus;
  onTerminal: () => void;
}) {
  const live = useUploadSessionEvents(session.upload_session_id, { onTerminal });
  return <SessionProgress live={live} session={session} />;
}

function SessionProgress({
  session,
  live
}: {
  session: UploadSessionStatus;
  live: SourceUploadProgressEvent | null;
}) {
  if (!live) {
    return <>{`${session.uploaded_file_count}/${session.expected_file_count}`}</>;
  }
  const pct =
    live.progress != null ? Math.min(100, Math.max(0, Math.round(live.progress * 100))) : null;
  return (
    <div className="source-live-progress">
      <span>
        {pct != null ? `${pct}%` : `${session.uploaded_file_count}/${session.expected_file_count}`}
      </span>
      {live.stage ? <span className="form-note">{live.stage}</span> : null}
    </div>
  );
}

function parseApiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    try {
      const parsed = JSON.parse(error.message) as { detail?: unknown };
      const detail = parsed.detail;
      if (typeof detail === "string") {
        return detail;
      }
      if (detail && typeof detail === "object" && "message" in detail) {
        return String((detail as { message: unknown }).message);
      }
    } catch {
      // error.message was not JSON; fall through to the raw message.
    }
    return error.message;
  }
  return error instanceof Error ? error.message : String(error);
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
