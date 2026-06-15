"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Hammer, Play, RefreshCw, ShieldCheck, XCircle } from "lucide-react";
import { useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { postJson, requestJson } from "@/lib/api";
import {
  matchSetStateLabels,
  rebuildPromoteConfirmation,
  sourceFilesPaths,
  type SourceMatchSet,
  type SourceMatchSetDetail
} from "@/lib/source-files";

const EMPTY_SETS: SourceMatchSet[] = [];

export function MatchSetsTab() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<unknown>(null);

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
    onSuccess: (data) => {
      setLastResult(data);
      void queryClient.invalidateQueries({ queryKey: ["source-match-sets"] });
      void queryClient.invalidateQueries({ queryKey: ["source-match-set"] });
    },
    onError: (error) => setLastResult({ error: error instanceof Error ? error.message : String(error) })
  });

  return (
    <div className="source-split">
      <Panel
        title="매칭 세트"
        actions={
          <button className="icon-button" onClick={() => void refetch()} title="새로고침" type="button">
            <RefreshCw size={16} />
          </button>
        }
      >
        <div className="report-list">
          {matchSets.map((set) => (
            <button
              className={set.source_match_set_id === effectiveId ? "report-row active" : "report-row"}
              key={set.source_match_set_id}
              onClick={() => setSelectedId(set.source_match_set_id)}
              type="button"
            >
              <span>{set.name}</span>
              <span className="report-row-meta">
                {set.integrity_alert ? (
                  <span className="status error" title="integrity_alert">
                    <AlertTriangle size={12} /> 무결성 경보
                  </span>
                ) : null}
                <StatusBadge value={matchSetStateLabels[set.state]} />
              </span>
            </button>
          ))}
          {matchSets.length === 0 ? <p className="form-note">매칭 세트가 없습니다.</p> : null}
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
            <p className="form-note">매칭 세트를 선택하세요.</p>
          </Panel>
        )}
        {lastResult ? (
          <Panel title="최근 결과">
            <pre className="json-box">{JSON.stringify(lastResult, null, 2)}</pre>
          </Panel>
        ) : null}
      </div>
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
      actions={<StatusBadge value={matchSetStateLabels[set.state]} />}
    >
      {set.integrity_alert ? (
        <div className="confirm-box" role="alert">
          <div className="confirm-title">무결성 경보 (integrity_alert)</div>
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

      <dl className="criteria-grid">
        <div>
          <dt>profile</dt>
          <dd>{set.profile}</dd>
        </div>
        <div>
          <dt>source_set_hash</dt>
          <dd>{set.source_set_hash ? `${set.source_set_hash.slice(0, 12)}…` : "-"}</dd>
        </div>
        <div>
          <dt>혼합 기준월</dt>
          <dd>{set.mixed_yyyymm ? "예" : "아니오"}</dd>
        </div>
        <div>
          <dt>검증 시각</dt>
          <dd>{set.validated_at ?? "-"}</dd>
        </div>
      </dl>

      <table className="table compact">
        <thead>
          <tr>
            <th>카테고리</th>
            <th>역할</th>
            <th>생략</th>
            <th>기준월</th>
            <th>그룹 ID</th>
          </tr>
        </thead>
        <tbody>
          {detail.items.map((item) => (
            <tr key={item.source_match_set_item_id}>
              <td>{item.category}</td>
              <td>{item.role}</td>
              <td>{item.omitted ? "생략" : "포함"}</td>
              <td>{item.effective_yyyymm ?? "-"}</td>
              <td>{item.source_file_group_id ? `${item.source_file_group_id.slice(0, 12)}…` : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="button-row">
        <button className="button secondary" disabled={pending} onClick={() => onAction("validate")} type="button">
          <CheckCircle2 size={16} />
          validate
        </button>
        <button className="button" disabled={pending} onClick={() => onAction("activate")} type="button">
          <ShieldCheck size={16} />
          activate
        </button>
        <button className="button secondary" disabled={pending} onClick={() => onAction("run-validation")} type="button">
          <Play size={16} />
          run-validation
        </button>
        <button className="button danger" disabled={pending} onClick={() => onAction("retire")} type="button">
          <XCircle size={16} />
          retire
        </button>
      </div>

      <RebuildDbForm
        matchSetId={set.source_match_set_id}
        onRebuild={(body) => onAction("rebuild-db", body)}
        pending={pending}
      />
    </Panel>
  );
}

function RebuildDbForm({
  matchSetId,
  onRebuild,
  pending
}: {
  matchSetId: string;
  onRebuild: (body: unknown) => void;
  pending: boolean;
}) {
  const [force, setForce] = useState(false);
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const requiredPhrase = rebuildPromoteConfirmation(matchSetId);
  const confirmationOk = !force || confirmation === requiredPhrase;

  return (
    <div className="rebuild-form">
      <h3>DB 재구성 (rebuild-db)</h3>
      <label className="checkbox-row">
        <input checked={force} onChange={(event) => setForce(event.target.checked)} type="checkbox" />
        consistency ERROR 강제 승급 (force_promotion)
      </label>
      <label className="field">
        <span>사유 (reason)</span>
        <input onChange={(event) => setReason(event.target.value)} value={reason} />
      </label>
      {force ? (
        <div className="confirm-box">
          <label>확인 문구 입력: {requiredPhrase}</label>
          <input
            aria-label="rebuild 강제 승급 확인 문구"
            onChange={(event) => setConfirmation(event.target.value)}
            placeholder={requiredPhrase}
            value={confirmation}
          />
          {!confirmationOk ? <p className="form-note warn">확인 문구가 일치해야 합니다.</p> : null}
        </div>
      ) : null}
      <button
        className="button"
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
        <Hammer size={16} />
        rebuild-db 실행
      </button>
    </div>
  );
}
