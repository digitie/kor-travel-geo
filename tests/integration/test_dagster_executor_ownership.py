"""기존 PostgreSQL의 독립 임시 schema에서 worker 소유권·회수 경쟁을 검증한다."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from kortravelgeo.api._reconciler import DagsterJobReconciler
from kortravelgeo.core.job_recovery import OrchestratorRunState
from kortravelgeo.infra.load_job_executor import LoadJobExecutor, LoadJobLeaseLostError


@pytest_asyncio.fixture
async def ownership_engine():
    dsn = os.environ.get("KTG_EXECUTOR_TEST_PG_DSN")
    if not dsn:
        pytest.skip("독립 schema 테스트용 기존 PostgreSQL DSN 미설정")
    schema = f"ktg_executor_test_{uuid4().hex}"
    admin = create_async_engine(dsn)
    async with admin.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_async_engine(dsn, connect_args={"options": f"-csearch_path={schema}"})
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("""
CREATE TABLE load_jobs (
  job_id text PRIMARY KEY, state text NOT NULL, executor text NOT NULL,
  orchestrator_run_id text, lease_expires_at timestamptz,
  created_at timestamptz DEFAULT now(), started_at timestamptz, finished_at timestamptz,
  heartbeat_at timestamptz, current_stage text, error_message text,
  progress double precision DEFAULT 0, log_tail jsonb DEFAULT '[]'::jsonb
)
""")
            )
            await conn.execute(
                text("""
INSERT INTO load_jobs (job_id,state,executor,orchestrator_run_id,lease_expires_at)
VALUES ('job', 'running', 'dagster', 'owner', now() + interval '5 minutes')
""")
            )
        yield engine
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            # 고정 접두사+UUID인 이 테스트 소유 schema만 제거한다.
            await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        await admin.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["done", "failed", "cancelled"])
async def test_terminal_job_cannot_be_resurrected_by_late_worker(
    ownership_engine: AsyncEngine,
    terminal: str,
) -> None:
    async with ownership_engine.begin() as conn:
        await conn.execute(text("UPDATE load_jobs SET state=:state"), {"state": terminal})
    worker = LoadJobExecutor(ownership_engine, orchestrator_run_id="owner")
    assert await worker.read_cancel_requested("job")
    with pytest.raises(LoadJobLeaseLostError):
        await worker.renew_lease("job")
    with pytest.raises(LoadJobLeaseLostError):
        await worker.set_progress("job", progress=0.9, stage="publishing", message="late")
    with pytest.raises(LoadJobLeaseLostError):
        await worker.mark_done("job")
    await worker.mark_failed("job", "late failure")
    await worker.mark_cancelled("job")
    async with ownership_engine.connect() as conn:
        row = (
            await conn.execute(text("SELECT state, current_stage, log_tail FROM load_jobs"))
        ).one()
    assert row.state == terminal
    assert row.current_stage is None
    assert row.log_tail == []


@pytest.mark.asyncio
async def test_old_owner_cannot_finish_reassigned_job(ownership_engine: AsyncEngine) -> None:
    async with ownership_engine.begin() as conn:
        await conn.execute(text("UPDATE load_jobs SET orchestrator_run_id='new-owner'"))
    old = LoadJobExecutor(ownership_engine, orchestrator_run_id="owner")
    with pytest.raises(LoadJobLeaseLostError):
        await old.mark_done("job")
    assert await old.read_cancel_requested("job")
    current = LoadJobExecutor(ownership_engine, orchestrator_run_id="new-owner")
    assert not await current.read_cancel_requested("job")
    await current.renew_lease("job")
    await current.set_progress("job", progress=0.5, stage="running", message="current")
    await current.mark_done("job")
    async with ownership_engine.connect() as conn:
        assert await conn.scalar(text("SELECT state FROM load_jobs")) == "done"


@pytest.mark.asyncio
async def test_reaper_checks_observed_lease_atomically(ownership_engine: AsyncEngine) -> None:
    expired = datetime.now(UTC) - timedelta(hours=1)
    async with ownership_engine.begin() as conn:
        await conn.execute(text("UPDATE load_jobs SET lease_expires_at=:lease"), {"lease": expired})
    worker = LoadJobExecutor(ownership_engine, orchestrator_run_id="owner")
    await worker.renew_lease("job")
    reaper = LoadJobExecutor(ownership_engine)
    assert not await reaper.reconcile_transition(
        "job",
        state="failed",
        orchestrator_run_id="owner",
        lease_expires_at=expired,
        reason="stale snapshot",
    )
    async with ownership_engine.connect() as conn:
        lease = await conn.scalar(text("SELECT lease_expires_at FROM load_jobs"))
    assert await reaper.reconcile_transition(
        "job",
        state="failed",
        orchestrator_run_id="owner",
        lease_expires_at=lease,
        reason="confirmed dead",
    )
    with pytest.raises(LoadJobLeaseLostError):
        await worker.mark_done("job")


@pytest.mark.asyncio
async def test_status_transactions_have_bounded_sql_and_lock_waits(
    ownership_engine: AsyncEngine,
) -> None:
    worker = LoadJobExecutor(ownership_engine)
    async with worker._begin_bounded() as conn:
        assert await conn.scalar(text("SHOW lock_timeout")) == "5s"
        assert await conn.scalar(text("SHOW statement_timeout")) == "1min"


@pytest.mark.asyncio
async def test_old_terminal_history_never_starves_active_jobs(
    ownership_engine: AsyncEngine,
) -> None:
    async with ownership_engine.begin() as conn:
        await conn.execute(
            text("""
INSERT INTO load_jobs (job_id,state,executor,orchestrator_run_id,created_at)
SELECT 'old-' || n, 'failed', 'dagster', 'old-run-' || n, now() - interval '1 year'
FROM generate_series(1,201) n
""")
        )

    async def probe(**kwargs):
        return OrchestratorRunState.UNKNOWN

    async def cancel(**kwargs):
        pytest.fail("UNKNOWN을 orphan으로 해석할 수 없다")

    reconciler = DagsterJobReconciler(
        ownership_engine,
        executor=LoadJobExecutor(ownership_engine),
        liveness_probe=probe,
        orchestrator_cancel=cancel,
    )
    first = await reconciler.reconcile_once()
    old_first = await reconciler.reconcile_once()
    active_again = await reconciler.reconcile_once()
    old_next = await reconciler.reconcile_once()
    assert [job_id for job_id, _ in first] == ["job"]
    assert [job_id for job_id, _ in active_again] == ["job"]
    assert len(old_first) == len(old_next) == 100
    assert {job_id for job_id, _ in old_first}.isdisjoint(job_id for job_id, _ in old_next)
