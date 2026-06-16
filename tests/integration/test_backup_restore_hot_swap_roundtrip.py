"""T-246 hot-swap·rollback round-trip live integration test (opt-in).

Closes the gap T-241/T-264 deferred to integration: a small DB goes through
backup → restore → **live ADR-036 rename hot-swap** → post-swap smoke → **manual rollback**,
and we assert the rename actually moved which physical DB serves (a marker row), the
``ops.serving_releases`` lineage (``restore`` then ``rollback`` active releases), and the audit
trail. Two guard paths are also exercised live: a rollback is rejected once retention has
dropped ``previous_alias``, and a concurrent hot-swap fails fast on the ``HOT_SWAP`` advisory
lock.

Opt-in via ``KTG_TEST_PG_DSN`` + the backup CLI tools; skips otherwise so CI stays green. The
DSN must point at an **isolated** cluster (e.g. the local Docker PostGIS on 15434) — the test
creates and renames its own throwaway DBs and never touches the configured database itself.

Run it with, e.g.:
    KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@localhost:15434/postgres \
        pytest tests/integration/test_backup_restore_hot_swap_roundtrip.py -q
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from kortravelgeo.dto.admin import (
    MaintenanceWindowCreate,
    RestoreHotSwapExecuteRequest,
    RestoreHotSwapRollbackRequest,
)
from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.concurrency import (
    AdvisoryLockKey,
    AdvisoryLockNamespace,
    ConcurrentExecutionError,
    cross_process_lock,
)
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.hotswap import (
    execute_hot_swap_rollback,
    execute_restore_hot_swap,
    hot_swap_confirmation,
    rollback_confirmation,
)
from tests.integration._backup_roundtrip import (
    _dsn_for_database,
    drop_database,
    missing_requirement,
)
from tests.integration._hotswap_roundtrip import (
    database_exists,
    hot_swap_harness,
    serving_has_marker,
)

if TYPE_CHECKING:
    from pathlib import Path


async def _open_window(engine, confirmation: str, reason: str) -> None:
    await AdminRepository(engine).create_maintenance_window(
        MaintenanceWindowCreate(kind="restore", reason=reason, confirmation=confirmation)
    )


@pytest.mark.asyncio
async def test_hot_swap_then_rollback_round_trip(tmp_path: Path) -> None:
    skip_reason = missing_requirement()
    if skip_reason:
        pytest.skip(skip_reason)
    pytest.importorskip("psycopg")

    async with hot_swap_harness(tmp_path) as h:
        engine = make_async_engine(h.settings)
        try:
            # --- forward hot-swap -------------------------------------------------
            swap_conf = hot_swap_confirmation(h.current_database, h.restore_database)
            await _open_window(engine, swap_conf, "t246 hot-swap")
            swap = await execute_restore_hot_swap(
                engine,
                h.settings,
                RestoreHotSwapExecuteRequest(
                    restore_database=h.restore_database,
                    previous_alias=h.previous_alias,
                    typed_confirmation=swap_conf,
                    run_smoke_test=True,
                ),
            )
            assert swap.swapped is True
            assert swap.rolled_back is False
            assert swap.smoke_ok is True
            # The rename actually moved the serving DB: the current name now resolves to the
            # restored (marker-tagged) DB, the old DB lives under previous_alias, and the
            # restore name is gone (it became current).
            assert await serving_has_marker(h.source_dsn, h.current_database) is True
            assert await database_exists(h.source_dsn, h.previous_alias) is True
            assert await database_exists(h.source_dsn, h.restore_database) is False
            # Lineage + audit recorded in the now-serving (restored) DB.
            active = await AdminRepository(engine).list_serving_releases(limit=5, state="active")
            assert active and active[0].release_kind == "restore"
            assert active[0].serving_release_id == swap.serving_release_id
            swap_audits = await AdminRepository(engine).list_audit_events(
                action="serving_release.hot_swap"
            )
            assert any(a.outcome == "succeeded" for a in swap_audits)

            # --- manual rollback --------------------------------------------------
            rb_conf = rollback_confirmation(h.current_database, h.previous_alias)
            await _open_window(engine, rb_conf, "t246 rollback")
            rollback = await execute_hot_swap_rollback(
                engine,
                h.settings,
                RestoreHotSwapRollbackRequest(
                    previous_alias=h.previous_alias,
                    restore_database=h.restore_database,
                    rollback_confirmation=rb_conf,
                    run_smoke_test=True,
                ),
            )
            assert rollback.rolled_back is True
            assert rollback.smoke_ok is True
            # The original DB serves again (no marker), previous_alias is consumed, and the
            # restored DB is parked back under the restore name.
            assert await serving_has_marker(h.source_dsn, h.current_database) is False
            assert await database_exists(h.source_dsn, h.previous_alias) is False
            assert await database_exists(h.source_dsn, h.restore_database) is True
            rb_active = await AdminRepository(engine).list_serving_releases(limit=5, state="active")
            assert rb_active and rb_active[0].release_kind == "rollback"
            assert rb_active[0].serving_release_id == rollback.serving_release_id
            rb_audits = await AdminRepository(engine).list_audit_events(
                action="serving_release.hot_swap_rollback"
            )
            assert any(a.outcome == "succeeded" for a in rb_audits)
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_rollback_rejected_after_retention_expired(tmp_path: Path) -> None:
    skip_reason = missing_requirement()
    if skip_reason:
        pytest.skip(skip_reason)
    pytest.importorskip("psycopg")

    async with hot_swap_harness(tmp_path) as h:
        engine = make_async_engine(h.settings)
        try:
            swap_conf = hot_swap_confirmation(h.current_database, h.restore_database)
            await _open_window(engine, swap_conf, "t246 hot-swap")
            await execute_restore_hot_swap(
                engine,
                h.settings,
                RestoreHotSwapExecuteRequest(
                    restore_database=h.restore_database,
                    previous_alias=h.previous_alias,
                    typed_confirmation=swap_conf,
                    run_smoke_test=True,
                ),
            )
            # Simulate retention dropping the rollback alias.
            await drop_database(h.source_dsn, h.previous_alias)
            assert await database_exists(h.source_dsn, h.previous_alias) is False

            rb_conf = rollback_confirmation(h.current_database, h.previous_alias)
            await _open_window(engine, rb_conf, "t246 rollback (retention expired)")
            with pytest.raises(InvalidInputError, match=r"previous alias|retention"):
                await execute_hot_swap_rollback(
                    engine,
                    h.settings,
                    RestoreHotSwapRollbackRequest(
                        previous_alias=h.previous_alias,
                        restore_database=h.restore_database,
                        rollback_confirmation=rb_conf,
                        run_smoke_test=True,
                    ),
                )
            # Rejected before any rename: the restored DB keeps serving (marker still present).
            assert await serving_has_marker(h.source_dsn, h.current_database) is True
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_hot_swap_fails_fast(tmp_path: Path) -> None:
    skip_reason = missing_requirement()
    if skip_reason:
        pytest.skip(skip_reason)
    pytest.importorskip("psycopg")

    async with hot_swap_harness(tmp_path) as h:
        engine = make_async_engine(h.settings)
        # A second session holding the HOT_SWAP advisory lock stands in for a concurrent swap.
        holder = create_async_engine(
            _dsn_for_database(h.source_dsn, "postgres"), isolation_level="AUTOCOMMIT"
        )
        try:
            swap_conf = hot_swap_confirmation(h.current_database, h.restore_database)
            await _open_window(engine, swap_conf, "t246 concurrent")
            lock_key = AdvisoryLockKey.global_key(AdvisoryLockNamespace.HOT_SWAP)
            async with cross_process_lock(holder, lock_key):
                with pytest.raises(ConcurrentExecutionError):
                    await execute_restore_hot_swap(
                        engine,
                        h.settings,
                        RestoreHotSwapExecuteRequest(
                            restore_database=h.restore_database,
                            previous_alias=h.previous_alias,
                            typed_confirmation=swap_conf,
                            run_smoke_test=True,
                        ),
                    )
            # Failed fast before any rename: both DBs intact, no previous_alias created.
            assert await database_exists(h.source_dsn, h.current_database) is True
            assert await database_exists(h.source_dsn, h.restore_database) is True
            assert await database_exists(h.source_dsn, h.previous_alias) is False
        finally:
            await holder.dispose()
            await engine.dispose()
