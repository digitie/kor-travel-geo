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
@pytest.mark.parametrize(
    "case", ["done", "failed", "cancelled", "new-owner", "cancel-event", "valid"]
)
async def test_publication_guard_protects_actual_mv_swap(
    ownership_engine: AsyncEngine, case: str
) -> None:
    import asyncio

    from kortravelgeo.infra.publication import load_job_publication_guard
    from kortravelgeo.loaders.postload import shadow_swap_mv

    async with ownership_engine.begin() as conn:
        for suffix, value in (("", "old"), ("_next", "new")):
            for name in ("mv_geocode_target", "mv_geocode_text_search"):
                await conn.execute(
                    text(f"CREATE MATERIALIZED VIEW {name}{suffix} AS SELECT '{value}' AS value")
                )
        if case in {"done", "failed", "cancelled"}:
            await conn.execute(text("UPDATE load_jobs SET state=:state"), {"state": case})
        elif case == "new-owner":
            await conn.execute(text("UPDATE load_jobs SET orchestrator_run_id='replacement'"))
    cancel_event = asyncio.Event()
    if case == "cancel-event":
        cancel_event.set()
    guard = load_job_publication_guard(
        job_id="job", owner_run_id="owner", cancel_event=cancel_event
    )
    if case == "valid":
        await shadow_swap_mv(ownership_engine, publication_guard=guard)
    else:
        with pytest.raises(LoadJobLeaseLostError):
            await shadow_swap_mv(ownership_engine, publication_guard=guard)
    async with ownership_engine.connect() as conn:
        assert await conn.scalar(text("SELECT value FROM mv_geocode_target")) == (
            "new" if case == "valid" else "old"
        )
        assert await conn.scalar(text("SELECT value FROM mv_geocode_text_search")) == (
            "new" if case == "valid" else "old"
        )


@pytest.mark.asyncio
async def test_cancel_during_swap_rolls_back_before_publication_commit(
    ownership_engine: AsyncEngine, monkeypatch
) -> None:
    import asyncio

    from kortravelgeo.infra.publication import load_job_publication_guard
    from kortravelgeo.loaders import postload

    async with ownership_engine.begin() as conn:
        for suffix, value in (("", "old"), ("_next", "new")):
            for name in ("mv_geocode_target", "mv_geocode_text_search"):
                await conn.execute(
                    text(f"CREATE MATERIALIZED VIEW {name}{suffix} AS SELECT '{value}' AS value")
                )
    cancelled = asyncio.Event()

    async def cancel_before_commit(conn):
        cancelled.set()

    monkeypatch.setattr(postload, "rename_mv_next_indexes_for_conn", cancel_before_commit)
    guard = load_job_publication_guard(job_id="job", owner_run_id="owner", cancel_event=cancelled)
    with pytest.raises(LoadJobLeaseLostError):
        await postload.shadow_swap_mv(ownership_engine, publication_guard=guard)
    async with ownership_engine.connect() as conn:
        assert await conn.scalar(text("SELECT value FROM mv_geocode_target")) == "old"
        assert await conn.scalar(text("SELECT value FROM mv_geocode_target_next")) == "new"


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
async def test_batch_child_losing_ownership_cannot_finish_or_publish_next_stage(
    ownership_engine: AsyncEngine,
) -> None:
    import asyncio

    from kortravelgeo.loaders.batch_dag import _drive_child

    async def leaf(cancel_event, progress):
        async with ownership_engine.begin() as conn:
            await conn.execute(text("UPDATE load_jobs SET state='failed', current_stage='reaped'"))
        await progress(progress=0.5, stage="late publish")
        pytest.fail("소유권을 잃은 child는 다음 게시 단계에 도달할 수 없다")

    with pytest.raises(LoadJobLeaseLostError):
        await _drive_child(
            LoadJobExecutor(ownership_engine, orchestrator_run_id="owner"),
            child_id="job",
            orchestrator_run_id="owner",
            cancel_event=asyncio.Event(),
            ttl_seconds=300,
            leaf=leaf,
        )
    async with ownership_engine.connect() as conn:
        row = (await conn.execute(text("SELECT state,current_stage FROM load_jobs"))).one()
    assert row == ("failed", "reaped")


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


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_radius_parts_commit_checks_owner_after_rebuild(
    ownership_engine: AsyncEngine, monkeypatch, cancelled: bool
) -> None:
    import asyncio

    from kortravelgeo.infra.publication import load_job_publication_guard
    from kortravelgeo.loaders import postload

    async with ownership_engine.begin() as conn:
        await conn.execute(text("CREATE TABLE region_radius_parts (value text)"))
        await conn.execute(text("INSERT INTO region_radius_parts VALUES ('old')"))
    # geometry SQL의 실행계획 대신 실제 TRUNCATE/INSERT transaction의 게시 경계를 검증한다.
    monkeypatch.setattr(
        postload,
        "REGION_RADIUS_PARTS_REFRESH_SQL",
        "TRUNCATE TABLE region_radius_parts; INSERT INTO region_radius_parts VALUES ('new');",
    )
    cancel_event = asyncio.Event()
    actual_guard = load_job_publication_guard(
        job_id="job", owner_run_id="owner", cancel_event=cancel_event
    )

    async def guard(conn):
        if cancelled:
            cancel_event.set()
        await actual_guard(conn)

    if cancelled:
        with pytest.raises(LoadJobLeaseLostError):
            await postload.refresh_region_radius_parts(ownership_engine, publication_guard=guard)
    else:
        await postload.refresh_region_radius_parts(ownership_engine, publication_guard=guard)
    async with ownership_engine.connect() as conn:
        assert await conn.scalar(text("SELECT value FROM region_radius_parts")) == (
            "old" if cancelled else "new"
        )
