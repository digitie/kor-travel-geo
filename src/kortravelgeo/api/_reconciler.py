"""Dagster 확인 장애를 격리하고 관측한 run·lease가 그대로일 때만 load_jobs를 회수한다.

활성 행과 과거 terminal 행을 교대로 100건씩 조회해 과거 실패가 활성 실행을 굶기지
않도록 한다. 각 순회의 생존 확인 대기는 5초이며 cursor는 실제 확인한 행까지만 전진한다.
도메인 batch 집계와 leaf 게시 transaction은 소비자 실행 경로의 책임이다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from time import monotonic
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.core.job_recovery import (
    OrchestratorCancelHook,
    OrchestratorRunState,
    ReconcileAction,
    ReconcileOutcome,
    RunLivenessProbe,
    is_lease_valid,
    reconcile_load_job,
)
from kortravelgeo.dto.admin import LoadJobState
from kortravelgeo.infra.load_job_executor import LoadJobExecutor

logger = logging.getLogger(__name__)


class DagsterJobReconciler:
    """활성/과거 실행의 독립 cursor를 유지하고 startup·주기 호출을 직렬화한다.

    생존 확인은 DB transaction 밖에서 수행하고, 관측 뒤 변경된 소유권은 덮어쓰지 않는다.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        executor: LoadJobExecutor,
        liveness_probe: RunLivenessProbe,
        orchestrator_cancel: OrchestratorCancelHook,
    ) -> None:
        self._engine = engine
        self._executor = executor
        self._liveness_probe = liveness_probe
        self._orchestrator_cancel = orchestrator_cancel
        self._cursors: dict[bool, tuple[datetime, str] | None] = {False: None, True: None}
        self._scan_terminal = False
        self._tick_lock = asyncio.Lock()

    async def reconcile_once(self) -> list[tuple[str, ReconcileAction]]:
        """Snapshot the reconcilable dagster rows, probe each run, and apply the decision.

        Returns the ``(job_id, action)`` decisions for observability/testing.
        """

        async with self._tick_lock:
            try:
                return await self._reconcile_page()
            finally:
                # 과거 실패가 많아도 활성 실행은 두 tick마다 반드시 조회한다.
                self._scan_terminal = not self._scan_terminal

    async def _reconcile_page(self) -> list[tuple[str, ReconcileAction]]:
        # 과거 terminal 행 전체를 매 tick에 적재하거나 RPC 대기열을 무한히 늘리지 않는다.
        deadline = monotonic() + 5.0
        try:
            rows = await asyncio.wait_for(self._reconcile_rows(), timeout=5.0)
        except Exception:
            logger.warning("회수 대상 조회 실패: 다음 순회에서 다시 확인합니다.", exc_info=True)
            return []
        now = datetime.now(UTC)
        results: list[tuple[str, ReconcileAction]] = []
        for row in rows:
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            job_id = str(row["job_id"])
            job_state = cast("LoadJobState", row["state"])
            lease_valid = is_lease_valid(lease_expires_at=row.get("lease_expires_at"), now=now)
            try:
                run_state = await asyncio.wait_for(
                    self._liveness_probe(
                        orchestrator_run_id=row.get("orchestrator_run_id"),
                        lease_valid=lease_valid,
                    ),
                    timeout=remaining,
                )
            except Exception:
                logger.warning("Dagster 생존 확인 실패: 회수를 보류합니다.", exc_info=True)
                run_state = OrchestratorRunState.UNKNOWN
            action = reconcile_load_job(
                run_state=run_state,
                job_state=job_state,
                lease_valid=lease_valid,
            )
            remaining = deadline - monotonic()
            applied = True
            if action.outcome not in {ReconcileOutcome.KEEP_RUNNING, ReconcileOutcome.NOOP}:
                if remaining <= 0:
                    action = ReconcileAction(
                        ReconcileOutcome.NOOP, "순회 예산 소진; 다음 회차 재확인"
                    )
                else:
                    try:
                        applied = await asyncio.wait_for(
                            self._apply(
                                job_id,
                                action,
                                orchestrator_run_id=row.get("orchestrator_run_id"),
                                lease_expires_at=row.get("lease_expires_at"),
                            ),
                            timeout=remaining,
                        )
                    except Exception:
                        logger.warning("실행 상태 회수 실패: 다음 회차 재확인", exc_info=True)
                        action = ReconcileAction(
                            ReconcileOutcome.NOOP, "변경 실패; 다음 회차 재확인"
                        )
            if not applied:
                action = ReconcileAction(
                    ReconcileOutcome.NOOP,
                    "조회 후 소유권 또는 lease가 변경되어 회수를 보류합니다.",
                )
            results.append((job_id, action))
            if row.get("created_at") is not None:
                self._cursors[self._scan_terminal] = (row["created_at"], job_id)
            # 시간 상한에 걸린 행도 checkpoint하여 뒤의 실행을 영구적으로 굶기지 않는다.
            if remaining <= 0:
                break
        if len(results) == len(rows) and len(rows) < 100:
            self._cursors[self._scan_terminal] = None
        return results

    async def _reconcile_rows(self) -> list[dict[str, Any]]:
        cursor = self._cursors[self._scan_terminal]
        async with self._engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            """
SELECT job_id, state, orchestrator_run_id, lease_expires_at, created_at
  FROM load_jobs
 WHERE executor = 'dagster'
   AND (
     (NOT :scan_terminal AND state = 'running')
     OR (
       :scan_terminal AND state IN ('failed','cancelled')
       AND orchestrator_run_id IS NOT NULL
     )
   )
   AND (CAST(:cursor_time AS timestamptz) IS NULL
        OR (created_at, job_id) > (CAST(:cursor_time AS timestamptz), :cursor_id))
 ORDER BY created_at, job_id
 LIMIT 100
"""
                        ),
                        {
                            "scan_terminal": self._scan_terminal,
                            "cursor_time": cursor[0] if cursor else None,
                            "cursor_id": cursor[1] if cursor else "",
                        },
                    )
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    async def _apply(
        self,
        job_id: str,
        action: ReconcileAction,
        *,
        orchestrator_run_id: str | None,
        lease_expires_at: datetime | None,
    ) -> bool:
        """Apply a :class:`ReconcileAction`. ``KEEP_RUNNING``/``NOOP`` write nothing."""

        terminal = {
            ReconcileOutcome.CONVERGE_DONE: "done",
            ReconcileOutcome.CONVERGE_FAILED: "failed",
            ReconcileOutcome.CONVERGE_CANCELLED: "cancelled",
        }.get(action.outcome)
        if terminal:
            return await self._executor.reconcile_transition(
                job_id,
                state=terminal,
                orchestrator_run_id=orchestrator_run_id,
                lease_expires_at=lease_expires_at,
                reason=f"reconciled: {action.reason}",
            )
        elif action.outcome is ReconcileOutcome.FLAG_ORPHAN:
            # Reverse split-brain: Dagster run alive but load_jobs already terminal. Record it
            # and terminate the run so both sides agree (the boundary doc's forbidden state).
            await self._executor.set_progress(job_id, message=f"orphan: {action.reason}")
            await self._orchestrator_cancel(job_id=job_id, orchestrator_run_id=orchestrator_run_id)
        return True
