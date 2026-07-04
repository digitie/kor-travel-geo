"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Hammer, Play, ShieldCheck, XCircle } from "lucide-react";
import { useId, useState } from "react";
import { ActionResultPanel } from "@/components/admin/shared/ActionResultPanel";
import { EmptyState } from "@/components/admin/shared/EmptyState";
import { HelpTip } from "@/components/admin/shared/HelpTip";
import { KeyValueGrid } from "@/components/admin/shared/KeyValueGrid";
import { RefreshButton } from "@/components/admin/shared/RefreshButton";
import { TypedConfirmField } from "@/components/admin/shared/TypedConfirmField";
import { RoleRequirementNote } from "@/components/admin/RoleRequirementNote";
import { JobProgress } from "@/components/admin/backups/JobProgress";
import { MatchSetComparePanel } from "@/components/admin/source-files/MatchSetComparePanel";
import { MatchSetItemsTable } from "@/components/admin/source-files/MatchSetItemsTable";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type PreflightSeverity,
  summarizeRebuildPreflight
} from "@/lib/rebuild-preflight";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { getErrorMessage, type LoadJobStatus, postJson, requestJson } from "@/lib/api";
import { terminalJobState } from "@/lib/backup-workflow";
import { toast } from "@/lib/toast";
import {
  matchSetStateLabels,
  rebuildPromoteConfirmation,
  sourceFilesPaths,
  type SourceMatchSet,
  type SourceMatchSetDetail
} from "@/lib/source-files";

const EMPTY_SETS: SourceMatchSet[] = [];

const LIFECYCLE_LABELS: Record<string, string> = {
  validate: "검증(validate)",
  activate: "활성화(activate)",
  retire: "은퇴(retire)",
  "run-validation": "검증 실행(run-validation)",
  "rebuild-db": "DB 재구성(rebuild-db)"
};

export function MatchSetsTab() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<unknown>(null);
  const [lastRebuildJobId, setLastRebuildJobId] = useState<string | null>(null);

  const { data: matchSets = EMPTY_SETS, refetch } = useQuery({
    queryKey: ["source-match-sets"],
    queryFn: () => requestJson<SourceMatchSet[]>(sourceFilesPaths.matchSets())
  });
  const effectiveId = selectedId ?? matchSets[0]?.source_match_set_id ?? null;

  const { data: detail } = useQuery({
    queryKey: ["source-match-set", effectiveId],
    queryFn: () => requestJson<SourceMatchSetDetail>(sourceFilesPaths.matchSet(effectiveId!)),
    enabled: effectiveId !== null
  });

  const lifecycle = useMutation({
    mutationFn: ({ id, kind, body }: { id: string; kind: string; body?: unknown }) => {
      const path =
        kind === "validate"
          ? sourceFilesPaths.matchSetValidate(id)
          : kind === "activate"
            ? sourceFilesPaths.matchSetActivate(id)
            : kind === "retire"
              ? sourceFilesPaths.matchSetRetire(id)
              : kind === "run-validation"
                ? sourceFilesPaths.matchSetRunValidation(id)
                : sourceFilesPaths.matchSetRebuildDb(id);
      return postJson(path, body ?? {});
    },
    onSuccess: (data, variables) => {
      toast.success(`${LIFECYCLE_LABELS[variables.kind] ?? variables.kind} 요청 완료`);
      setLastResult(data);
      setLastRebuildJobId(
        variables.kind === "rebuild-db" ? rebuildJobIdFromResponse(data) : null
      );
      void queryClient.invalidateQueries({ queryKey: ["source-match-sets"] });
      void queryClient.invalidateQueries({ queryKey: ["source-match-set"] });
    },
    onError: (error, variables) => {
      const message = getErrorMessage(error);
      toast.error(`${LIFECYCLE_LABELS[variables.kind] ?? variables.kind} 실패`, message);
      setLastResult({ error: message });
      if (variables.kind === "rebuild-db") {
        setLastRebuildJobId(null);
      }
    }
  });

  return (
    <div className="source-stack">
      <div className="source-split">
      <Panel
        title="매칭 세트"
        actions={<RefreshButton iconOnly onClick={() => void refetch()} />}
      >
        <div className="report-list">
          {matchSets.map((set) => (
            <button
              className={set.source_match_set_id === effectiveId ? "report-row active" : "report-row"}
              data-testid={`source-match-set-${set.source_match_set_id}`}
              key={set.source_match_set_id}
              onClick={() => setSelectedId(set.source_match_set_id)}
              type="button"
            >
              <span>{set.name}</span>
              <span className="report-row-meta">
                {set.integrity_alert ? (
                  <StatusBadge tone="error" value="무결성 경보" />
                ) : null}
                <StatusBadge value={matchSetStateLabels[set.state]} />
              </span>
            </button>
          ))}
          {matchSets.length === 0 ? <EmptyState>매칭 세트가 없습니다.</EmptyState> : null}
        </div>
      </Panel>

      <div className="source-stack">
        {detail ? (
          <MatchSetDetail
            detail={detail}
            onAction={(kind, body) =>
              lifecycle.mutate({ id: detail.match_set.source_match_set_id, kind, body })
            }
            pending={lifecycle.isPending}
          />
        ) : (
          <Panel title="세부 정보">
            <EmptyState>매칭 세트를 선택하세요.</EmptyState>
          </Panel>
        )}
        <ActionResultPanel result={lastResult} />
        {lastRebuildJobId ? <RebuildJobStatus jobId={lastRebuildJobId} /> : null}
      </div>
      </div>
      <MatchSetComparePanel matchSets={matchSets} />
    </div>
  );
}

function rebuildJobIdFromResponse(data: unknown): string | null {
  if (!data || typeof data !== "object" || !("job_id" in data)) {
    return null;
  }
  const jobId = (data as { job_id?: unknown }).job_id;
  return typeof jobId === "string" && jobId ? jobId : null;
}

function RebuildJobStatus({ jobId }: { jobId: string }) {
  const { data: job, refetch } = useQuery({
    queryKey: ["admin-job", jobId],
    queryFn: () => requestJson<LoadJobStatus>(`/admin/jobs/${jobId}`),
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state && terminalJobState(state) ? false : 5_000;
    }
  });

  return (
    <Panel title="rebuild-db 진행 상태">
      {job ? (
        <>
          <JobProgress job={job} onTerminal={() => void refetch()} />
          <KeyValueGrid
            items={[
              {
                label: "작업 ID",
                value: <span data-testid="rebuild-control-job-id">{job.job_id}</span>,
                help: (
                  <>
                    API 필드 <code>job_id</code>
                  </>
                ),
                helpLabel: "작업 ID 도움말"
              },
              { label: "상태", value: job.state },
              ...(job.load_batch_id
                ? [
                    {
                      label: "적재 배치 ID",
                      value: (
                        <span data-testid="rebuild-load-batch-id">{job.load_batch_id}</span>
                      ),
                      help: (
                        <>
                          API 필드 <code>load_batch_id</code> — 하위 full_load_batch 작업
                        </>
                      ),
                      helpLabel: "적재 배치 ID 도움말"
                    }
                  ]
                : []),
              { label: "단계", value: job.current_stage ?? "-" },
              { label: "완료 시각", value: job.finished_at ?? "-" }
            ]}
          />
          {job.load_batch_id && job.load_batch_id !== job.job_id ? (
            <DownstreamBatchStatus batchJobId={job.load_batch_id} />
          ) : null}
          {job.error_message ? <p className="form-note warn">{job.error_message}</p> : null}
        </>
      ) : (
        <div className="grid gap-2">
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-2/3" />
        </div>
      )}
    </Panel>
  );
}

function DownstreamBatchStatus({ batchJobId }: { batchJobId: string }) {
  const { data: batchJob, refetch } = useQuery({
    queryKey: ["admin-job", batchJobId],
    queryFn: () => requestJson<LoadJobStatus>(`/admin/jobs/${batchJobId}`),
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state && terminalJobState(state) ? false : 5_000;
    }
  });

  return (
    <div className="source-stack" data-testid="rebuild-load-batch-status">
      <h3>full_load_batch 진행 상태</h3>
      {batchJob ? (
        <>
          <JobProgress job={batchJob} onTerminal={() => void refetch()} />
          <KeyValueGrid
            items={[
              { label: "작업 ID", value: batchJob.job_id },
              { label: "상태", value: batchJob.state },
              { label: "단계", value: batchJob.current_stage ?? "-" },
              { label: "완료 시각", value: batchJob.finished_at ?? "-" }
            ]}
          />
          {batchJob.error_message ? <p className="form-note warn">{batchJob.error_message}</p> : null}
        </>
      ) : (
        <div className="grid gap-2">
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-2/3" />
        </div>
      )}
    </div>
  );
}

function MatchSetDetail({
  detail,
  onAction,
  pending
}: {
  detail: SourceMatchSetDetail;
  onAction: (kind: string, body?: unknown) => void;
  pending: boolean;
}) {
  const set = detail.match_set;
  return (
    <Panel
      title={set.name}
      badges={<StatusBadge value={matchSetStateLabels[set.state]} />}
    >
      {set.integrity_alert ? (
        <div className="confirm-box" role="alert">
          <div className="confirm-title flex items-center gap-1">
            무결성 경보
            <HelpTip label="무결성 경보 도움말">
              API 필드 <code>integrity_alert</code> — 활성 세트가 참조하는 원천의 무결성 이상
              신호입니다.
            </HelpTip>
          </div>
          <p className="form-note">
            {set.integrity_alert_at ? `발생: ${set.integrity_alert_at}` : "활성 세트의 원천 무결성에 문제가 감지되었습니다."}
          </p>
          {set.integrity_alert_detail ? (
            <pre className="json-box compact-json">
              {JSON.stringify(set.integrity_alert_detail, null, 2)}
            </pre>
          ) : null}
        </div>
      ) : null}

      <KeyValueGrid
        items={[
          {
            label: "프로파일",
            value: set.profile,
            help: (
              <>
                API 필드 <code>profile</code> — 매칭 세트 구성 프로파일
              </>
            ),
            helpLabel: "프로파일 도움말"
          },
          {
            label: "구성 해시",
            value: set.source_set_hash ? `${set.source_set_hash.slice(0, 12)}…` : "-",
            help: (
              <>
                API 필드 <code>source_set_hash</code>
              </>
            ),
            helpLabel: "구성 해시 도움말"
          },
          { label: "혼합 기준월", value: set.mixed_yyyymm ? "예" : "아니오" },
          { label: "검증 시각", value: set.validated_at ?? "-" }
        ]}
      />

      <MatchSetItemsTable items={detail.items} variant="detail" />

      <div className="button-row">
        <Button disabled={pending} onClick={() => onAction("validate")} type="button" variant="outline">
          <CheckCircle2 aria-hidden="true" />
          validate
        </Button>
        <Button disabled={pending} onClick={() => onAction("activate")} type="button">
          <ShieldCheck aria-hidden="true" />
          activate
        </Button>
        <Button disabled={pending} onClick={() => onAction("run-validation")} type="button" variant="outline">
          <Play aria-hidden="true" />
          run-validation
        </Button>
        <Button disabled={pending} onClick={() => onAction("retire")} type="button" variant="destructive">
          <XCircle aria-hidden="true" />
          retire
        </Button>
      </div>

      <RebuildDbForm
        detail={detail}
        matchSetId={set.source_match_set_id}
        onRebuild={(body) => onAction("rebuild-db", body)}
        pending={pending}
      />
    </Panel>
  );
}

const PREFLIGHT_TONE: Record<PreflightSeverity, "ok" | "warn" | "error"> = {
  ok: "ok",
  warn: "warn",
  blocker: "error"
};
const PREFLIGHT_LABEL: Record<PreflightSeverity, string> = {
  ok: "정상",
  warn: "주의",
  blocker: "차단"
};

function RebuildDbForm({
  matchSetId,
  detail,
  onRebuild,
  pending
}: {
  matchSetId: string;
  detail: SourceMatchSetDetail;
  onRebuild: (body: unknown) => void;
  pending: boolean;
}) {
  const [force, setForce] = useState(false);
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const requiredPhrase = rebuildPromoteConfirmation(matchSetId);
  const confirmationOk = !force || confirmation === requiredPhrase;
  const preflight = summarizeRebuildPreflight(detail);
  const forceId = useId();
  const reasonId = useId();

  return (
    <div className="rebuild-form">
      <h3 className="flex items-center gap-1">
        DB 재구성
        <HelpTip label="DB 재구성 도움말">
          rebuild-db — 이 매칭 세트의 원천으로 serving DB를 다시 구성하는 위험 작업입니다.
        </HelpTip>
      </h3>
      <RoleRequirementNote
        note={force ? "force_promotion(consistency ERROR 우회)은 destructive_admin 필요" : undefined}
        roles={force ? ["rebuild_operator", "destructive_admin"] : ["rebuild_operator"]}
      />
      <div className="preflight">
        <strong className="flex items-center gap-1">
          사전 점검
          <HelpTip label="사전 점검 도움말">
            preflight — 실행 전 자동 점검 결과입니다. 차단 항목이 있으면 백엔드 promotion
            gate에서 거부될 수 있습니다.
          </HelpTip>
        </strong>
        <ul className="preflight-list">
          {preflight.items.map((check) => (
            <li className="preflight-item" key={check.key}>
              <StatusBadge tone={PREFLIGHT_TONE[check.severity]} value={PREFLIGHT_LABEL[check.severity]} />
              <span>
                {check.label}: {check.detail}
              </span>
            </li>
          ))}
        </ul>
        {preflight.blockerCount > 0 ? (
          <p className="form-note warn">
            차단 {preflight.blockerCount}건 — 백엔드 promotion gate에서 막힐 수 있습니다.
            <HelpTip label="차단 도움말">
              force_promotion으로도 무결성·필수 그룹 게이트는 우회할 수 없습니다.
            </HelpTip>
          </p>
        ) : null}
      </div>
      <div className="checkbox-row">
        <Checkbox
          checked={force}
          id={forceId}
          onCheckedChange={(checked) => setForce(checked === true)}
        />
        <label className="m-0 text-sm" htmlFor={forceId}>
          consistency ERROR 강제 승급 (force_promotion)
        </label>
      </div>
      <Field>
        <span className="flex items-center gap-1">
          <FieldLabel htmlFor={reasonId}>사유</FieldLabel>
          <HelpTip label="사유 도움말">
            API 필드 <code>reason</code> — 감사 기록에 남는 선택 입력입니다.
          </HelpTip>
        </span>
        <Input
          id={reasonId}
          onChange={(event) => setReason(event.target.value)}
          placeholder="예: 202605 원천 갱신 재적재"
          value={reason}
        />
      </Field>
      {force ? (
        <TypedConfirmField
          description={`이 작업은 영향 카테고리 ${preflight.affectedCategories.length}개로 serving DB를 재구성하고, force_promotion은 consistency ERROR 게이트만 우회합니다(무결성·필수 그룹 게이트는 우회 안 됨). 완료 시 새 release/snapshot으로 swap되며 이전 release로의 rollback은 별도 작업입니다.`}
          heading="위험작업 미리보기"
          label="rebuild 강제 승급 확인 문구"
          onChange={setConfirmation}
          phrase={requiredPhrase}
          value={confirmation}
        />
      ) : null}
      <Button
        disabled={pending || !confirmationOk}
        onClick={() =>
          onRebuild({
            force_promotion: force,
            reason: reason || null,
            typed_confirmation: force ? confirmation : null,
            download_concurrency: 3,
            materialize_concurrency: 2
          })
        }
        type="button"
      >
        <Hammer aria-hidden="true" />
        rebuild-db 실행
      </Button>
    </div>
  );
}
