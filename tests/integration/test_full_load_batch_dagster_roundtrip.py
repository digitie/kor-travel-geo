"""Real-Postgres round-trip for the T-290j Dagster batch DAG (opt-in: ``KTG_TEST_PG_DSN``).

Complements the fake-driven ``tests/unit/test_batch_dag.py`` (control flow) with the actual
DB writes it cannot cover:

* ``insert_load_batch(executor='dagster')`` leaves the root ``queued`` (adoptable) with
  ``started_at IS NULL`` and stamps ``executor='dagster'`` on every child.
* ``run_full_load_batch`` adopts + converges every child row (source loaders → consistency →
  mv) against real SQL — ``adopt_dagster`` / ``set_progress`` / ``mark_done`` /
  ``insert_load_job`` for the dynamically-created consistency + mv children.
* the ERROR promotion GATE blocks the mv child from ever being created.

The leaves themselves are stubbed (no data files / GDAL), so this isolates the orchestration
SQL. Point ``KTG_TEST_PG_DSN`` at a DISPOSABLE PostgreSQL/PostGIS scratch DB — the schema is
applied and ``load_jobs`` is truncated per test.
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text

from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.batch import batch_children
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.sql import SCHEMA_SQL, iter_sql_statements
from kortravelgeo.loaders import batch_dag
from kortravelgeo.settings import Settings

pytestmark = pytest.mark.asyncio

_BATCH_PAYLOAD: dict[str, Any] = {
    "children": [
        {"kind": "juso_text_load", "payload": {"path": "/tmp/juso"}},
        {"kind": "locsum_load", "payload": {"path": "/tmp/locsum"}},
    ]
}


async def _fresh_engine():  # noqa: ANN202 - AsyncEngine, kept unannotated to avoid an import
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostgreSQL/PostGIS scratch DB")
    engine = make_async_engine(Settings(pg_dsn=dsn))
    async with engine.begin() as conn:
        for statement in iter_sql_statements(SCHEMA_SQL):
            await conn.execute(text(statement))
        await conn.execute(text("TRUNCATE load_jobs CASCADE"))
    return engine


def _stub_leaves(monkeypatch: pytest.MonkeyPatch, *, severity: str = "WARN") -> SimpleNamespace:
    calls = SimpleNamespace(sources=[], consistency=[], mv=[])

    async def fake_source(engine, *, kind, payload, cancel_event, progress):
        calls.sources.append(kind)
        await progress(progress=1.0, stage=kind, message=f"{kind} stub done")

    async def fake_consistency(engine, *, payload, progress):
        calls.consistency.append(payload)
        return SimpleNamespace(severity_max=severity, report_id="rep-stub")

    async def fake_mv(engine, *, payload, job_id, progress):
        calls.mv.append(payload)

    monkeypatch.setattr(batch_dag, "run_source_loader", fake_source)
    monkeypatch.setattr(batch_dag, "run_consistency_check", fake_consistency)
    monkeypatch.setattr(batch_dag, "run_mv_refresh", fake_mv)
    return calls


async def _rows(engine, batch_id: str) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT job_id, kind, state, executor, orchestrator_run_id, started_at "
                    "FROM load_jobs WHERE load_batch_id = :b ORDER BY created_at"
                ),
                {"b": batch_id},
            )
        ).mappings().all()
    return [dict(row) for row in rows]


async def _noop_progress(*, progress=None, stage=None, message=None):
    return None


async def test_dagster_batch_roundtrip_converges_all_children(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = await _fresh_engine()
    calls = _stub_leaves(monkeypatch)
    try:
        children = batch_children(_BATCH_PAYLOAD)
        root = await AdminRepository(engine).insert_load_batch(
            payload=_BATCH_PAYLOAD, children=children, executor="dagster"
        )

        before = await _rows(engine, root.job_id)
        root_row = next(r for r in before if r["job_id"] == root.job_id)
        assert root_row["state"] == "queued"  # adoptable by the Dagster op
        assert root_row["executor"] == "dagster"
        assert root_row["started_at"] is None
        assert all(r["executor"] == "dagster" for r in before)

        progressed: list[tuple[str | None, float | None]] = []

        async def progress(*, progress=None, stage=None, message=None):
            progressed.append((stage, progress))

        result = await batch_dag.run_full_load_batch(
            engine,
            batch_id=root.job_id,
            payload=_BATCH_PAYLOAD,
            cancel_event=asyncio.Event(),
            progress=progress,
            orchestrator_run_id="run-int-1",
            lease_ttl_seconds=300.0,
        )

        assert calls.sources == ["juso_text_load", "locsum_load"]
        assert len(calls.mv) == 1
        after = {r["kind"]: r for r in await _rows(engine, root.job_id) if r["job_id"] != root.job_id}
        assert after["juso_text_load"]["state"] == "done"
        assert after["locsum_load"]["state"] == "done"
        assert after["consistency_check"]["state"] == "done"
        assert after["mv_refresh"]["state"] == "done"
        # every child was adopted under the batch's Dagster run id (real adopt_dagster SQL).
        assert after["juso_text_load"]["orchestrator_run_id"] == "run-int-1"
        assert after["mv_refresh"]["orchestrator_run_id"] == "run-int-1"
        assert result["consistency_report_id"] == "rep-stub"
        assert ("done", 1.0) in progressed
    finally:
        await engine.dispose()


async def test_dagster_batch_gate_blocks_mv_on_consistency_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = await _fresh_engine()
    calls = _stub_leaves(monkeypatch, severity="ERROR")
    try:
        children = batch_children(_BATCH_PAYLOAD)
        root = await AdminRepository(engine).insert_load_batch(
            payload=_BATCH_PAYLOAD, children=children, executor="dagster"
        )

        with pytest.raises(batch_dag.FullLoadBatchGateError):
            await batch_dag.run_full_load_batch(
                engine,
                batch_id=root.job_id,
                payload=_BATCH_PAYLOAD,
                cancel_event=asyncio.Event(),
                progress=_noop_progress,
                orchestrator_run_id="run-int-2",
                lease_ttl_seconds=300.0,
            )

        assert calls.mv == []
        kinds = {r["kind"] for r in await _rows(engine, root.job_id)}
        assert "mv_refresh" not in kinds  # the gate blocked the mv child entirely
        assert "consistency_check" in kinds
    finally:
        await engine.dispose()
