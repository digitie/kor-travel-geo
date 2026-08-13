"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Upload, XCircle } from "lucide-react";
import { useReducer, useState } from "react";
import { HelpTip } from "@/components/admin/shared/HelpTip";
import { WizardSteps } from "@/components/admin/shared/WizardSteps";
import { YyyymmField } from "@/components/admin/shared/YyyymmField";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Field, FieldContent, FieldDescription, FieldLabel, FieldTitle } from "@/components/ui/field";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError, getErrorMessage, postJson } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { uploadSlotFile, type SlotUploadProgress } from "@/lib/multipart-upload";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import {
  isValidYyyymm,
  servingUsageLabels,
  servingUsageNote,
  servingUsageTones,
  sourceFilesPaths,
  sourceRoleLabels,
  suggestYyyymm,
  validationOutcomeLabel,
  validationOutcomeTone,
  type SourceFileCategoryInfo,
  type UploadSessionPreviewValidationResult,
  type UploadSessionStatus
} from "@/lib/source-files";

type WizardStep = 1 | 2 | 3 | 4;

const STEP_LABELS: Record<WizardStep, string> = {
  1: "1. 카테고리 선택",
  2: "2. 기준월 입력",
  3: "3. 파일 업로드 · 사전 점검",
  4: "4. 확인 · 등록"
};

type WizardState = {
  step: WizardStep;
  categoryKey: string | null;
  userYyyymm: string;
  file: File | null;
  progress: SlotUploadProgress | null;
  preview: UploadSessionPreviewValidationResult | null;
  session: UploadSessionStatus | null;
  busy: boolean;
  error: string | null;
  registered: UploadSessionStatus | null;
};

function createInitialState(): WizardState {
  return {
    step: 1,
    categoryKey: null,
    userYyyymm: suggestYyyymm(),
    file: null,
    progress: null,
    preview: null,
    session: null,
    busy: false,
    error: null,
    registered: null
  };
}

function wizardReducer(state: WizardState, patch: Partial<WizardState>): WizardState {
  return { ...state, ...patch };
}

export function UploadWizardDialog({
  categories,
  maxBytesByCategory,
  open,
  onOpenChange,
  onCompleted
}: {
  categories: SourceFileCategoryInfo[];
  maxBytesByCategory: Map<string, number>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCompleted: () => void;
}) {
  const queryClient = useQueryClient();
  const [state, dispatch] = useReducer(wizardReducer, undefined, createInitialState);
  const { step, categoryKey, userYyyymm, file, progress, preview, session, busy, error, registered } =
    state;

  const category = categories.find((item) => item.category === categoryKey) ?? null;
  const yyyymmValid = isValidYyyymm(userYyyymm);
  const maxBytes = categoryKey ? maxBytesByCategory.get(categoryKey) : undefined;

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
    }
  });

  const previewValidate = useMutation({
    mutationFn: (sessionId: string) =>
      postJson<UploadSessionPreviewValidationResult>(
        sourceFilesPaths.previewValidateSession(sessionId),
        {}
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["upload-sessions"] });
    }
  });

  const registerSession = useMutation({
    mutationFn: ({ sessionId, userYyyymm }: { sessionId: string; userYyyymm: string }) =>
      postJson<UploadSessionStatus>(sourceFilesPaths.registerSession(sessionId), {
        confirm_user_yyyymm: userYyyymm
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["upload-sessions"] });
    }
  });

  function handleOpenChange(next: boolean) {
    if (!next) {
      const wasRegistered = registered !== null;
      dispatch(createInitialState());
      onOpenChange(next);
      if (wasRegistered) {
        onCompleted();
      }
      return;
    }
    onOpenChange(next);
  }

  async function handleFileSelected(selectedFile: File) {
    dispatch({ file: selectedFile, error: null, preview: null, progress: null, session: null });
    if (!category) return;
    if (maxBytes && selectedFile.size > maxBytes) {
      dispatch({
        error: `파일이 크기 한도 ${formatBytes(maxBytes)}를 초과합니다 — 더 작은 파일을 선택하세요.`
      });
      return;
    }
    dispatch({ busy: true });
    try {
      const newSession = await createSession.mutateAsync({
        category: category.category,
        userYyyymm,
        displayName: selectedFile.name
      });
      dispatch({ session: newSession });
      const slot = newSession.file_slots[0];
      if (!slot) {
        dispatch({ busy: false, error: "세션에 업로드 슬롯이 없습니다" });
        return;
      }
      await uploadSlotFile({
        sessionId: newSession.upload_session_id,
        slotId: slot.slot,
        file: selectedFile,
        partSizeBytes: newSession.part_size_bytes,
        onProgress: (next) => dispatch({ progress: next })
      });
      const result = await previewValidate.mutateAsync(newSession.upload_session_id);
      dispatch({ busy: false, preview: result });
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 409
          ? "이미 같은 카테고리·기준월의 업로드 세션이 진행 중입니다 — 카테고리 카드에서 이어서 진행하세요."
          : getErrorMessage(err);
      dispatch({ busy: false, error: message });
    }
  }

  async function handleRetryPreview() {
    if (!session) return;
    dispatch({ busy: true, error: null });
    try {
      const result = await previewValidate.mutateAsync(session.upload_session_id);
      dispatch({ busy: false, preview: result });
    } catch (err) {
      dispatch({ busy: false, error: getErrorMessage(err) });
    }
  }

  async function handleRegister() {
    if (!session) return;
    dispatch({ busy: true, error: null });
    try {
      const result = await registerSession.mutateAsync({
        sessionId: session.upload_session_id,
        userYyyymm: session.user_yyyymm
      });
      dispatch({ busy: false, registered: result });
      toast.success("업로드 완료", "세션이 등록되었습니다.");
    } catch (err) {
      dispatch({ busy: false, error: getErrorMessage(err) });
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent aria-label="업로드 마법사" size="lg">
        <DialogHeader>
          <DialogTitle>업로드 마법사</DialogTitle>
          <DialogDescription>
            카테고리 → 기준월 → 파일 업로드(사전 점검) → 확인 순서로 안내합니다.
          </DialogDescription>
        </DialogHeader>

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

        {category && step > 1 ? <CategoryImpactSummaryCard category={category} /> : null}

        {step === 1 ? (
          <CategoryPickerStep
            categories={categories}
            onSelect={(key) => dispatch({ categoryKey: key, step: 2 })}
            selected={categoryKey}
          />
        ) : step === 2 && category ? (
          <div className="wizard-preview">
            <Field>
              <YyyymmField
                id="upload-wizard-yyyymm"
                onChange={(value) => dispatch({ userYyyymm: value })}
                value={userYyyymm}
                help={
                  <>
                    API 필드 <code>user_yyyymm</code> — {category.label}의 기준 년월입니다.
                  </>
                }
              />
            </Field>
            <div className="button-row">
              <Button onClick={() => dispatch({ step: 1 })} type="button" variant="outline">
                이전
              </Button>
              <Button disabled={!yyyymmValid} onClick={() => dispatch({ step: 3 })} type="button">
                다음
              </Button>
            </div>
          </div>
        ) : step === 3 && category ? (
          <div className="wizard-preview">
            <FileDropZone
              disabled={busy}
              file={file}
              maxBytes={maxBytes}
              onFileSelected={(selected) => void handleFileSelected(selected)}
            />
            {progress ? <UploadProgressBar progress={progress} /> : null}
            {previewValidate.isPending ? (
              <p className="form-note">구조/멤버/기준월 사전 점검 중…</p>
            ) : null}
            {preview ? <ValidationPreviewResult preview={preview} /> : null}
            {session && !preview && error && !busy ? (
              <div className="button-row">
                <Button onClick={() => void handleRetryPreview()} type="button" variant="outline">
                  사전 점검 다시 시도
                </Button>
              </div>
            ) : null}
            <div className="button-row">
              <Button onClick={() => dispatch({ step: 2 })} type="button" variant="outline">
                이전
              </Button>
              <Button
                disabled={!preview || busy}
                onClick={() => dispatch({ step: 4 })}
                type="button"
              >
                다음
              </Button>
            </div>
          </div>
        ) : step === 4 && category && session ? (
          <div className="wizard-confirm">
            {registered ? (
              <div className="wizard-done">
                <p>
                  <CheckCircle2 size={16} /> 업로드가 등록됐습니다 — {registered.state}
                </p>
                <Button onClick={() => handleOpenChange(false)} type="button">
                  닫기
                </Button>
              </div>
            ) : (
              <>
                <p className="wizard-hint">
                  {category.label} · {userYyyymm} · {file?.name} 을(를) 등록합니다. 등록 후에도
                  활성 매칭 세트에 포함되기 전까지는 서빙에 반영되지 않습니다.
                </p>
                {preview && preview.outcome !== "passed" ? (
                  <Alert role="alert" variant="warning">
                    <AlertTriangle aria-hidden="true" />
                    <AlertDescription>
                      사전 점검 결과가 {validationOutcomeLabel(preview.outcome)}입니다 — 그래도
                      등록을 진행할 수 있으나, 위 사전 점검 사유를 먼저 확인하세요.
                    </AlertDescription>
                  </Alert>
                ) : null}
                <div className="button-row">
                  <Button onClick={() => dispatch({ step: 3 })} type="button" variant="outline">
                    이전
                  </Button>
                  <Button disabled={busy} onClick={() => void handleRegister()} type="button">
                    등록
                  </Button>
                </div>
              </>
            )}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function CategoryPickerStep({
  categories,
  selected,
  onSelect
}: {
  categories: SourceFileCategoryInfo[];
  selected: string | null;
  onSelect: (category: string) => void;
}) {
  return (
    <div className="wizard-category-list" role="listbox" aria-label="업로드할 카테고리 선택">
      {categories.map((item) => (
        <button
          aria-selected={selected === item.category}
          className={cn("wizard-category-option", selected === item.category && "active")}
          key={item.category}
          onClick={() => onSelect(item.category)}
          role="option"
          type="button"
        >
          <FieldContent>
            <FieldTitle>
              {item.label}
              <StatusBadge
                tone={servingUsageTones[item.serving_usage]}
                value={servingUsageLabels[item.serving_usage]}
              />
            </FieldTitle>
            <FieldDescription>
              {sourceRoleLabels[item.role]} · {item.category}
            </FieldDescription>
          </FieldContent>
        </button>
      ))}
    </div>
  );
}

function CategoryImpactSummaryCard({ category }: { category: SourceFileCategoryInfo }) {
  return (
    <div className="wizard-list">
      <div className="wizard-verdict">
        <StatusBadge
          tone={servingUsageTones[category.serving_usage]}
          value={servingUsageLabels[category.serving_usage]}
        />
        <span className="flex items-center gap-1">
          예상 DB 입력 영향
          <HelpTip label={`${category.label} rebuild 영향 도움말`}>
            <p className="m-0">
              구성 역할: {sourceRoleLabels[category.role]} · 그룹 종류: {category.group_kind}
            </p>
          </HelpTip>
        </span>
      </div>
      <p className="wizard-hint m-0">{servingUsageNote(category.category, category.serving_usage)}</p>
      {category.expected_member_kinds.length > 0 ? (
        <p className="form-note m-0">기대 멤버: {category.expected_member_kinds.join(", ")}</p>
      ) : null}
    </div>
  );
}

function FileDropZone({
  file,
  maxBytes,
  disabled,
  onFileSelected
}: {
  file: File | null;
  maxBytes?: number;
  disabled: boolean;
  onFileSelected: (file: File) => void;
}) {
  const [dragOver, setDragOverState] = useState(false);
  const oversize = Boolean(file && maxBytes && file.size > maxBytes);

  return (
    <div
      className={cn("upload-dropzone", dragOver && "drag-over", disabled && "disabled")}
      onDragLeave={() => setDragOverState(false)}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setDragOverState(true);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDragOverState(false);
        if (disabled) return;
        const dropped = event.dataTransfer.files?.[0];
        if (dropped) onFileSelected(dropped);
      }}
    >
      <label className="upload-dropzone-label">
        <input
          aria-label="업로드할 파일 선택"
          disabled={disabled}
          onChange={(event) => {
            const selected = event.target.files?.[0];
            if (selected) onFileSelected(selected);
          }}
          type="file"
        />
        <Upload aria-hidden="true" />
        {file ? (
          <span>
            {file.name} · {formatBytes(file.size)}
            {maxBytes ? <> (한도 {formatBytes(maxBytes)})</> : null}
          </span>
        ) : (
          <span>파일을 여기로 끌어다 놓거나 클릭해서 선택하세요</span>
        )}
      </label>
      {oversize ? (
        <p className="form-note warn">파일이 크기 한도 {maxBytes ? formatBytes(maxBytes) : ""}를 초과합니다.</p>
      ) : null}
    </div>
  );
}

function UploadProgressBar({ progress }: { progress: SlotUploadProgress }) {
  const pct =
    progress.totalBytes > 0
      ? Math.min(100, Math.round((progress.uploadedBytes / progress.totalBytes) * 100))
      : 0;
  return (
    <div className="progress-line">
      <div className="progress-label">
        <strong>{progress.slot}</strong>
        <span>
          {progress.state === "done"
            ? "업로드 완료 · 사전 점검 준비"
            : progress.state === "error"
              ? "업로드 실패"
              : `${pct}% · 파트 ${progress.partsDone}/${progress.partsTotal}`}
        </span>
      </div>
      <Progress value={progress.state === "done" ? 100 : pct} />
      {progress.error ? <p className="form-note warn">{progress.error}</p> : null}
    </div>
  );
}

function ValidationPreviewResult({ preview }: { preview: UploadSessionPreviewValidationResult }) {
  return (
    <div className="wizard-preview">
      <div className="wizard-verdict">
        <StatusBadge tone={validationOutcomeTone(preview.outcome)} value={validationOutcomeLabel(preview.outcome)} />
        <span>구조/멤버/기준월 사전 점검 결과</span>
      </div>
      {preview.parts.map((part) => (
        <div
          className={part.outcome !== "passed" ? "wizard-list warn" : "wizard-list"}
          key={part.part_key}
        >
          <div className="wizard-verdict">
            <strong>{part.part_key}</strong>
            <StatusBadge tone={validationOutcomeTone(part.outcome)} value={validationOutcomeLabel(part.outcome)} />
          </div>
          {part.reasons.length > 0 ? (
            <ul>
              {part.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : null}
          {part.warnings.length > 0 ? (
            <ul>
              {part.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ))}
    </div>
  );
}
