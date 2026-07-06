"use client";

import { AlertTriangle, CheckCircle2, RotateCcw, XCircle } from "lucide-react";
import { useCallback, useEffect, useId, useReducer, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { HelpTip } from "@/components/admin/shared/HelpTip";
import { IssueList } from "@/components/admin/shared/IssueList";
import { JsonDetails } from "@/components/admin/shared/JsonDetails";
import { KeyValueGrid } from "@/components/admin/shared/KeyValueGrid";
import { TypedConfirmField } from "@/components/admin/shared/TypedConfirmField";
import { nestedRecord, textValue } from "@/components/admin/backups/manifest-utils";
import {
  MaintenanceWindow,
  type OpsArtifact,
  RestoreHotSwapPlan,
  RestoreHotSwapResult,
  RestoreHotSwapRollbackResult,
  RestoreSourceVerificationResult,
  getErrorMessage,
  postJson,
  requestJson
} from "@/lib/api";
import { toast } from "@/lib/toast";

type HotSwapState = {
  restoreDatabase: string;
  previousAlias: string;
  reason: string;
  plan: RestoreHotSwapPlan | null;
  windowOpened: MaintenanceWindow | null;
  execConfirmation: string;
  rollbackConfirmation: string;
  result: RestoreHotSwapResult | null;
  sourceVerify: RestoreSourceVerificationResult | null;
  rollbackResult: RestoreHotSwapRollbackResult | null;
  busy: string | null;
  error: string | null;
};

const INITIAL_HOTSWAP_STATE: HotSwapState = {
  restoreDatabase: "",
  previousAlias: "",
  reason: "restore hot-swap",
  plan: null,
  windowOpened: null,
  execConfirmation: "",
  rollbackConfirmation: "",
  result: null,
  sourceVerify: null,
  rollbackResult: null,
  busy: null,
  error: null
};

function hotSwapReducer(state: HotSwapState, patch: Partial<HotSwapState>): HotSwapState {
  return { ...state, ...patch };
}

export function HotSwapTab() {
  const [state, dispatchState] = useReducer(hotSwapReducer, INITIAL_HOTSWAP_STATE);
  const {
    restoreDatabase,
    previousAlias,
    reason,
    plan,
    windowOpened,
    execConfirmation,
    rollbackConfirmation,
    result,
    sourceVerify,
    rollbackResult,
    busy,
    error
  } = state;
  // 복원 이력(db_restore_log)의 target_database들 — restore_database datalist 자동 완성.
  const [restoreDbOptions, setRestoreDbOptions] = useState<string[]>([]);
  const restoreDbListId = useId();

  useEffect(() => {
    let cancelled = false;
    async function loadRestoreHistory() {
      try {
        const artifacts = await requestJson<OpsArtifact[]>(
          "/admin/ops/artifacts?artifact_type=db_restore_log&limit=20"
        );
        if (cancelled || !Array.isArray(artifacts)) return;
        const names = new Set<string>();
        for (const artifact of artifacts) {
          const direct = textValue(artifact.manifest?.["target_database"]);
          const fromReconcile = textValue(
            nestedRecord(artifact.manifest, "row_count_verification")?.["target_database"]
          );
          if (direct) names.add(direct);
          if (fromReconcile) names.add(fromReconcile);
        }
        setRestoreDbOptions([...names]);
      } catch {
        // datalist는 입력 보조일 뿐 — 실패해도 조용히 자유 입력으로 진행한다.
      }
    }
    void loadRestoreHistory();
    return () => {
      cancelled = true;
    };
  }, []);

  const run = useCallback(async (label: string, fn: () => Promise<void>) => {
    dispatchState({ busy: label, error: null });
    try {
      await fn();
    } catch (err) {
      const message = getErrorMessage(err);
      dispatchState({ error: message });
      toast.error(`${label} 실패`, message);
    } finally {
      dispatchState({ busy: null });
    }
  }, []);

  const buildPlan = () =>
    run("plan 생성", async () => {
      const next = await postJson<RestoreHotSwapPlan>("/restores/hot-swap-plan", {
        restore_database: restoreDatabase,
        previous_alias: previousAlias || undefined
      });
      dispatchState({ plan: next, windowOpened: null, result: null, rollbackResult: null });
      toast.success("hot-swap plan을 생성했습니다");
    });

  const openWindow = () =>
    run("maintenance window 열기", async () => {
      if (!plan) return;
      const win = await postJson<MaintenanceWindow>("/ops/maintenance-windows", {
        kind: "restore",
        reason,
        confirmation: plan.typed_confirmation
      });
      dispatchState({ windowOpened: win });
      toast.success("maintenance window를 열었습니다");
    });

  const execute = () =>
    run("hot-swap 실행", async () => {
      if (!plan) return;
      const next = await postJson<RestoreHotSwapResult>("/restores/hot-swap", {
        restore_database: plan.restore_database,
        typed_confirmation: execConfirmation,
        previous_alias: plan.previous_alias
      });
      dispatchState({ result: next });
      if (next.swapped) {
        toast.success("hot-swap 완료");
      } else if (next.rolled_back) {
        toast.error("hot-swap 실패 — 자동 rollback됨");
      } else {
        toast.error("hot-swap 실패");
      }
    });

  const verifySource = () =>
    run("source 재검증", async () => {
      const next = await postJson<RestoreSourceVerificationResult>(
        "/restores/hot-swap-source-verify",
        {}
      );
      dispatchState({ sourceVerify: next });
      toast.success("source 재검증 완료");
    });

  const rollback = () =>
    run("rollback 실행", async () => {
      if (!plan) return;
      const next = await postJson<RestoreHotSwapRollbackResult>("/restores/hot-swap-rollback", {
        previous_alias: plan.previous_alias,
        restore_database: plan.restore_database,
        rollback_confirmation: rollbackConfirmation
      });
      dispatchState({ rollbackResult: next });
      if (next.rolled_back) {
        toast.success("rollback 완료");
      } else {
        toast.error("rollback 실패");
      }
    });

  const execReady =
    Boolean(plan?.can_execute) &&
    Boolean(windowOpened) &&
    plan?.typed_confirmation === execConfirmation;
  const rollbackReady = plan?.rollback_confirmation === rollbackConfirmation;

  return (
    <div className="grid two">
      <Panel
        title="1 · Hot-swap plan"
        description={
          <>
            운영 serving DB를 즉시 교체하는 위험 작업입니다.
            <HelpTip label="Hot-swap 도움말">
              Hot-swap은 <code>ALTER DATABASE RENAME</code>으로 운영 serving DB를 교체합니다. plan
              → maintenance window → typed confirmation 순서로만 실행됩니다.
            </HelpTip>
          </>
        }
      >
        {error ? (
          <Alert role="alert" variant="destructive">
            <XCircle aria-hidden="true" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
        <div className="form-grid">
          <Field>
            <span className="flex items-center gap-1">
              <FieldLabel htmlFor="hs-restore">복원된 DB 이름</FieldLabel>
              <HelpTip label="복원된 DB 이름 도움말">
                API 필드 <code>restore_database</code> — [복원] 위저드로 만든 DB 이름. 최근 복원
                이력에서 자동 완성됩니다.
              </HelpTip>
            </span>
            <Input
              id="hs-restore"
              list={restoreDbListId}
              onChange={(e) => dispatchState({ restoreDatabase: e.target.value })}
              value={restoreDatabase}
            />
            <datalist id={restoreDbListId}>
              {restoreDbOptions.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </datalist>
          </Field>
          <Field>
            <span className="flex items-center gap-1">
              <FieldLabel htmlFor="hs-prev">previous alias</FieldLabel>
              <HelpTip label="previous alias 도움말">
                API 필드 <code>previous_alias</code> — 교체 전 운영 DB에 붙일 별칭 (선택).
              </HelpTip>
            </span>
            <Input
              id="hs-prev"
              onChange={(e) => dispatchState({ previousAlias: e.target.value })}
              placeholder="비우면 자동 생성"
              value={previousAlias}
            />
          </Field>
          <div className="button-row">
            <Button
              disabled={!restoreDatabase || busy === "plan 생성"}
              onClick={buildPlan}
              type="button"
            >
              plan 생성
            </Button>
          </div>
        </div>
        {plan ? (
          <div className="hotswap-plan">
            <KeyValueGrid
              items={[
                { label: "current", value: plan.current_database },
                { label: "restore", value: plan.restore_database },
                { label: "previous alias", value: plan.previous_alias },
                {
                  label: "실행 가능",
                  value: (
                    <StatusBadge
                      tone={plan.can_execute ? "ok" : "error"}
                      value={plan.can_execute ? "가능" : "불가"}
                    />
                  )
                }
              ]}
            />
            {!plan.can_execute && plan.blockers && plan.blockers.length > 0 ? (
              <IssueList items={plan.blockers} title="blockers" tone="error" />
            ) : null}
            {plan.steps && plan.steps.length > 0 ? (
              <ol className="hotswap-steps">
                {plan.steps.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ol>
            ) : null}
          </div>
        ) : null}
      </Panel>

      <div className="hotswap-side">
        <Panel title="2 · Maintenance window">
          {plan ? (
            <div className="form-grid">
              <Field>
                <span className="flex items-center gap-1">
                  <FieldLabel htmlFor="hs-reason">사유</FieldLabel>
                  <HelpTip label="사유 도움말">
                    API 필드 <code>reason</code> — maintenance window 감사 기록에 남습니다.
                  </HelpTip>
                </span>
                <Input
                  id="hs-reason"
                  onChange={(e) => dispatchState({ reason: e.target.value })}
                  value={reason}
                />
              </Field>
              <Button
                disabled={!plan.can_execute || busy === "maintenance window 열기"}
                onClick={openWindow}
                type="button"
              >
                maintenance window 열기 (kind=restore)
              </Button>
              {windowOpened ? (
                <p className="wizard-hint">
                  <CheckCircle2 size={14} /> window {windowOpened.maintenance_window_id} ·{" "}
                  <StatusBadge value={windowOpened.state} />
                </p>
              ) : null}
            </div>
          ) : (
            <p className="wizard-hint">먼저 plan을 생성하세요.</p>
          )}
        </Panel>

        <Panel title="3 · 실행 (위험)">
          {plan ? (
            <div className="form-grid">
              <TypedConfirmField
                heading="실행 확인"
                label="typed confirmation"
                onChange={(value) => dispatchState({ execConfirmation: value })}
                phrase={plan.typed_confirmation}
                value={execConfirmation}
              />
              <Button
                disabled={!execReady || busy === "hot-swap 실행"}
                onClick={execute}
                type="button"
                variant="destructive"
              >
                <AlertTriangle aria-hidden="true" size={15} /> hot-swap 실행
              </Button>
              {!windowOpened ? (
                <small className="wizard-hint">active maintenance window가 필요합니다.</small>
              ) : null}
              {result ? (
                <div className="wizard-done">
                  <p>
                    {result.swapped ? (
                      <StatusBadge tone="ok" value="swap 완료" />
                    ) : result.rolled_back ? (
                      <StatusBadge tone="warn" value="자동 rollback" />
                    ) : (
                      <StatusBadge tone="error" value="실패" />
                    )}{" "}
                    smoke: {String(result.smoke_ok)}
                  </p>
                  <JsonDetails value={result} />
                </div>
              ) : null}
            </div>
          ) : (
            <p className="wizard-hint">먼저 plan과 maintenance window를 준비하세요.</p>
          )}
        </Panel>

        <Panel title="4 · source 재검증 / rollback">
          <div className="form-grid">
            <Button
              disabled={busy === "source 재검증"}
              onClick={verifySource}
              type="button"
              variant="outline"
            >
              source 재검증
            </Button>
            {sourceVerify ? (
              <p className="wizard-hint">
                {sourceVerify.reconstruct_unavailable ? (
                  <StatusBadge tone="error" value="재구성 불가" />
                ) : (
                  <StatusBadge tone="ok" value="검증됨" />
                )}{" "}
                mismatch {sourceVerify.mismatch_count}
              </p>
            ) : null}
            {plan ? (
              <>
                <TypedConfirmField
                  heading="rollback 확인"
                  label="rollback confirmation"
                  onChange={(value) => dispatchState({ rollbackConfirmation: value })}
                  phrase={plan.rollback_confirmation}
                  value={rollbackConfirmation}
                />
                <Button
                  disabled={!rollbackReady || busy === "rollback 실행"}
                  onClick={rollback}
                  type="button"
                  variant="outline"
                >
                  <RotateCcw aria-hidden="true" size={15} /> rollback 실행
                </Button>
                {rollbackResult ? <JsonDetails value={rollbackResult} /> : null}
              </>
            ) : null}
          </div>
        </Panel>
      </div>
    </div>
  );
}
