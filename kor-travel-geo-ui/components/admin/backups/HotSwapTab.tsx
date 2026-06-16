"use client";

import { AlertTriangle, CheckCircle2, RotateCcw, ShieldAlert, XCircle } from "lucide-react";
import { useCallback, useState } from "react";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  MaintenanceWindow,
  RestoreHotSwapPlan,
  RestoreHotSwapResult,
  RestoreHotSwapRollbackResult,
  RestoreSourceVerificationResult,
  postJson
} from "@/lib/api";

export function HotSwapTab() {
  const [restoreDatabase, setRestoreDatabase] = useState("");
  const [previousAlias, setPreviousAlias] = useState("");
  const [reason, setReason] = useState("restore hot-swap");
  const [plan, setPlan] = useState<RestoreHotSwapPlan | null>(null);
  const [windowOpened, setWindowOpened] = useState<MaintenanceWindow | null>(null);
  const [execConfirmation, setExecConfirmation] = useState("");
  const [rollbackConfirmation, setRollbackConfirmation] = useState("");
  const [result, setResult] = useState<RestoreHotSwapResult | null>(null);
  const [sourceVerify, setSourceVerify] = useState<RestoreSourceVerificationResult | null>(null);
  const [rollbackResult, setRollbackResult] = useState<RestoreHotSwapRollbackResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }, []);

  const buildPlan = () =>
    run("plan", async () => {
      const next = await postJson<RestoreHotSwapPlan>("/restores/hot-swap-plan", {
        restore_database: restoreDatabase,
        previous_alias: previousAlias || undefined
      });
      setPlan(next);
      setWindowOpened(null);
      setResult(null);
      setRollbackResult(null);
    });

  const openWindow = () =>
    run("window", async () => {
      if (!plan) return;
      const win = await postJson<MaintenanceWindow>("/ops/maintenance-windows", {
        kind: "restore",
        reason,
        confirmation: plan.typed_confirmation
      });
      setWindowOpened(win);
    });

  const execute = () =>
    run("execute", async () => {
      if (!plan) return;
      const next = await postJson<RestoreHotSwapResult>("/restores/hot-swap", {
        restore_database: plan.restore_database,
        typed_confirmation: execConfirmation,
        previous_alias: plan.previous_alias
      });
      setResult(next);
    });

  const verifySource = () =>
    run("verify", async () => {
      const next = await postJson<RestoreSourceVerificationResult>(
        "/restores/hot-swap-source-verify",
        {}
      );
      setSourceVerify(next);
    });

  const rollback = () =>
    run("rollback", async () => {
      if (!plan) return;
      const next = await postJson<RestoreHotSwapRollbackResult>("/restores/hot-swap-rollback", {
        previous_alias: plan.previous_alias,
        restore_database: plan.restore_database,
        rollback_confirmation: rollbackConfirmation
      });
      setRollbackResult(next);
    });

  const planBlocked = Boolean(plan && !plan.can_execute);
  const execReady =
    Boolean(plan?.can_execute) &&
    Boolean(windowOpened) &&
    plan?.typed_confirmation === execConfirmation;
  const rollbackReady = plan?.rollback_confirmation === rollbackConfirmation;

  return (
    <div className="grid two">
      <Panel title="1 · Hot-swap plan">
        <p className="wizard-hint">
          <ShieldAlert size={14} /> Hot-swap은 <code>ALTER DATABASE RENAME</code>으로 운영 serving
          DB를 교체합니다. plan → maintenance window → typed confirmation 순서로만 실행됩니다.
        </p>
        {error ? (
          <p className="wizard-error" role="alert">
            <XCircle size={15} /> {error}
          </p>
        ) : null}
        <div className="form-grid">
          <div className="field">
            <label htmlFor="hs-restore">복원된 DB 이름 (restore_database)</label>
            <input
              id="hs-restore"
              onChange={(e) => setRestoreDatabase(e.target.value)}
              value={restoreDatabase}
            />
          </div>
          <div className="field">
            <label htmlFor="hs-prev">previous alias (선택 — 비우면 자동 생성)</label>
            <input
              id="hs-prev"
              onChange={(e) => setPreviousAlias(e.target.value)}
              value={previousAlias}
            />
          </div>
          <div className="button-row">
            <button
              className="button"
              disabled={!restoreDatabase || busy === "plan"}
              onClick={buildPlan}
              type="button"
            >
              plan 생성
            </button>
          </div>
        </div>
        {plan ? (
          <div className="hotswap-plan">
            <dl className="wizard-meta">
              <div>
                <dt>current</dt>
                <dd>{plan.current_database}</dd>
              </div>
              <div>
                <dt>restore</dt>
                <dd>{plan.restore_database}</dd>
              </div>
              <div>
                <dt>previous alias</dt>
                <dd>{plan.previous_alias}</dd>
              </div>
              <div>
                <dt>실행 가능</dt>
                <dd>
                  <StatusBadge
                    tone={plan.can_execute ? "ok" : "error"}
                    value={plan.can_execute ? "가능" : "불가"}
                  />
                </dd>
              </div>
            </dl>
            {planBlocked && plan.blockers && plan.blockers.length > 0 ? (
              <div className="wizard-list blocker">
                <strong>blockers</strong>
                <ul>
                  {plan.blockers.map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
              </div>
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
              <div className="field">
                <label htmlFor="hs-reason">사유 (reason)</label>
                <input id="hs-reason" onChange={(e) => setReason(e.target.value)} value={reason} />
              </div>
              <button
                className="button"
                disabled={!plan.can_execute || busy === "window"}
                onClick={openWindow}
                type="button"
              >
                maintenance window 열기 (kind=restore)
              </button>
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
              <div className="confirm-box">
                <span className="confirm-title">
                  정확히 <code>{plan.typed_confirmation}</code> 를 입력하세요
                </span>
                <input
                  aria-label="typed confirmation"
                  onChange={(e) => setExecConfirmation(e.target.value)}
                  value={execConfirmation}
                />
              </div>
              <button
                className="button danger"
                disabled={!execReady || busy === "execute"}
                onClick={execute}
                type="button"
              >
                <AlertTriangle size={15} /> hot-swap 실행
              </button>
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
                  <JsonBlock value={result} />
                </div>
              ) : null}
            </div>
          ) : (
            <p className="wizard-hint">먼저 plan과 maintenance window를 준비하세요.</p>
          )}
        </Panel>

        <Panel title="4 · source 재검증 / rollback">
          <div className="form-grid">
            <button
              className="button secondary"
              disabled={busy === "verify"}
              onClick={verifySource}
              type="button"
            >
              source 재검증
            </button>
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
                <div className="confirm-box">
                  <span className="confirm-title">
                    rollback 확인 — 정확히 <code>{plan.rollback_confirmation}</code>
                  </span>
                  <input
                    aria-label="rollback confirmation"
                    onChange={(e) => setRollbackConfirmation(e.target.value)}
                    value={rollbackConfirmation}
                  />
                </div>
                <button
                  className="button secondary"
                  disabled={!rollbackReady || busy === "rollback"}
                  onClick={rollback}
                  type="button"
                >
                  <RotateCcw size={15} /> rollback 실행
                </button>
                {rollbackResult ? <JsonBlock value={rollbackResult} /> : null}
              </>
            ) : null}
          </div>
        </Panel>
      </div>
    </div>
  );
}
