from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from kraddr.geo.infra.engine import make_async_engine
from kraddr.geo.infra.sql import INDEX_SQL, SCHEMA_SQL, iter_sql_statements
from kraddr.geo.settings import Settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
    from sqlalchemy.sql.elements import TextClause


@pytest.mark.asyncio
async def test_real_postgres_ops_constraints_when_dsn_is_set() -> None:
    dsn = os.getenv("KRADDR_GEO_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KRADDR_GEO_TEST_PG_DSN to run actual PostgreSQL ops constraints")

    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        await _apply_schema(engine)
        async with engine.connect() as conn:
            outer = await conn.begin()
            try:
                await _assert_audit_fk_and_append_only_trigger(conn)
                await _assert_serving_release_partial_unique(conn)
                await _assert_table_stats_snapshot_fk(conn)
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()


async def _apply_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for sql in iter_sql_statements(SCHEMA_SQL):
            await conn.execute(text(sql))
        for sql in iter_sql_statements(INDEX_SQL):
            await conn.execute(text(sql))


async def _assert_audit_fk_and_append_only_trigger(conn: AsyncConnection) -> None:
    job_id = f"ops-it-{uuid4().hex}"
    event_id = uuid4()
    await conn.execute(
        text(
            """
INSERT INTO load_jobs (job_id, kind, payload, state, progress)
VALUES (:job_id, 'ops_integration_test', '{}'::jsonb, 'done', 1.0)
"""
        ),
        {"job_id": job_id},
    )
    await conn.execute(
        text(
            """
INSERT INTO ops.audit_events (
  event_id, actor_type, action, job_id, outcome, payload_redacted, payload_hash
) VALUES (
  :event_id, 'system', 'ops.integration_test', :job_id, 'succeeded',
  '{"secret":"[REDACTED]"}'::jsonb, :payload_hash
)
"""
        ),
        {"event_id": event_id, "job_id": job_id, "payload_hash": "0" * 64},
    )

    await _expect_integrity_error(
        conn,
        text("DELETE FROM load_jobs WHERE job_id = :job_id"),
        {"job_id": job_id},
    )
    await _expect_dbapi_error(
        conn,
        text(
            """
UPDATE ops.audit_events
   SET action = 'ops.integration_test.updated'
 WHERE event_id = :event_id
"""
        ),
        {"event_id": event_id},
    )
    await _expect_dbapi_error(
        conn,
        text("DELETE FROM ops.audit_events WHERE event_id = :event_id"),
        {"event_id": event_id},
    )


async def _assert_serving_release_partial_unique(conn: AsyncConnection) -> None:
    snapshot_id = uuid4()
    conflicting_snapshot_id = uuid4()
    await _insert_dataset_snapshot(conn, snapshot_id)
    await _insert_dataset_snapshot(conn, conflicting_snapshot_id)

    active_count = await conn.scalar(
        text("SELECT count(*) FROM ops.serving_releases WHERE state = 'active'")
    )
    if active_count == 0:
        await _insert_serving_release(conn, uuid4(), snapshot_id, state="active")

    await _expect_integrity_error(
        conn,
        _serving_release_insert_sql(),
        {
            "release_id": uuid4(),
            "snapshot_id": conflicting_snapshot_id,
            "state": "active",
        },
    )

    await _insert_serving_release(
        conn,
        uuid4(),
        conflicting_snapshot_id,
        state="pending",
    )


async def _assert_table_stats_snapshot_fk(conn: AsyncConnection) -> None:
    snapshot_id = uuid4()
    await _insert_dataset_snapshot(conn, snapshot_id)

    await _expect_integrity_error(
        conn,
        text(
            """
INSERT INTO ops.table_stats_snapshots (
  stats_id, snapshot_id, schema_name, object_name, object_kind
) VALUES (
  :stats_id, :snapshot_id, 'public', 'mv_geocode_target', 'materialized_view'
)
"""
        ),
        {"stats_id": uuid4(), "snapshot_id": uuid4()},
    )

    stats_id = uuid4()
    await conn.execute(
        text(
            """
INSERT INTO ops.table_stats_snapshots (
  stats_id, snapshot_id, schema_name, object_name, object_kind,
  estimated_rows, total_bytes, stats
) VALUES (
  :stats_id, :snapshot_id, 'public', 'mv_geocode_target', 'materialized_view',
  0, 0, '{"snapshot_link":"explicit"}'::jsonb
)
"""
        ),
        {"stats_id": stats_id, "snapshot_id": snapshot_id},
    )
    saved = await conn.scalar(
        text("SELECT count(*) FROM ops.table_stats_snapshots WHERE stats_id = :stats_id"),
        {"stats_id": stats_id},
    )
    assert saved == 1


async def _insert_dataset_snapshot(conn: AsyncConnection, snapshot_id: UUID) -> None:
    await conn.execute(
        text(
            """
INSERT INTO ops.dataset_snapshots (
  snapshot_id, state, source_set, source_set_hash, row_counts
) VALUES (
  :snapshot_id, 'released', '{"kind":"ops_integration_test"}'::jsonb,
  :source_set_hash, jsonb_build_object('mv_geocode_target', 0)
)
"""
        ),
        {"snapshot_id": snapshot_id, "source_set_hash": "1" * 64},
    )


async def _insert_serving_release(
    conn: AsyncConnection,
    release_id: UUID,
    snapshot_id: UUID,
    *,
    state: str,
) -> None:
    await conn.execute(
        _serving_release_insert_sql(),
        {
            "release_id": release_id,
            "snapshot_id": snapshot_id,
            "state": state,
        },
    )


def _serving_release_insert_sql() -> TextClause:
    return text(
        """
INSERT INTO ops.serving_releases (
  release_id, snapshot_id, state, release_kind, mv_name, activated_at
) VALUES (
  :release_id, :snapshot_id, :state, 'manual_rebuild', 'mv_geocode_target', now()
)
"""
    )


async def _expect_integrity_error(
    conn: AsyncConnection,
    statement: TextClause,
    params: dict[str, object],
) -> None:
    with pytest.raises(IntegrityError):
        async with conn.begin_nested():
            await conn.execute(statement, params)


async def _expect_dbapi_error(
    conn: AsyncConnection,
    statement: TextClause,
    params: dict[str, object],
) -> None:
    with pytest.raises(DBAPIError):
        async with conn.begin_nested():
            await conn.execute(statement, params)
