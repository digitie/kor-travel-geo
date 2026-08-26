"""AdminRepository dataset-version projection against a real PostgreSQL (opt-in, T-291f).

T-291b+c's adversarial review found that `current_dataset_version`/`find_dataset_version`/
`dataset_version_history` had never been exercised against real SQL — only pure functions
(core) and a fake repo (router contract). The single highest-risk gap: does
`WHERE sr.state IN ('active','superseded','rolled_back')` actually exclude `pending`/`failed`
rows the way the docstrings claim? A typo in that IN-list, or a JOIN that silently drops rows
for schema reasons a fake repo can't reproduce, would leak un-served or failed releases into
the external `/v2/dataset/version` history — this is the one filter on this surface that is
actually safety-critical to get right.

Run with a disposable scratch database (see tests/integration/_pg_guard.py for the naming
rule — a whole `_`/`-` segment must read as "test"/"scratch"/"tmp"/"e2e"/etc.; bootstrap it
with `ktgctl init-db` + `alembic stamp head`, not `alembic upgrade head` from empty — see
docs/geocoding-readiness.md)::

    KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@127.0.0.1:12500/kor_travel_geo_test pytest \
        tests/integration/test_dataset_version_projection.py
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

from kortravelgeo.core.dataset_version import derive_version_token
from kortravelgeo.core.redaction import canonical_payload_hash
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database


def _dsn() -> str:
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostgreSQL scratch DB")
    return dsn


async def _insert_snapshot(
    conn,
    *,
    snapshot_id: str,
    source_set: dict,
    parent_dataset_snapshot_id: str | None = None,
) -> None:
    await conn.execute(
        text(
            "INSERT INTO ops.dataset_snapshots"
            "  (dataset_snapshot_id, state, parent_dataset_snapshot_id, source_set,"
            "   source_set_hash)"
            " VALUES (:id, 'released', :parent, :source_set, :hash)"
        ).bindparams(bindparam("source_set", type_=JSONB)),
        {
            "id": snapshot_id,
            "parent": parent_dataset_snapshot_id,
            "source_set": source_set,
            "hash": canonical_payload_hash(source_set),
        },
    )


async def _insert_release(
    conn,
    *,
    release_id: str,
    snapshot_id: str,
    state: str,
    release_kind: str = "full_load",
    activated_at: datetime | None = None,
) -> None:
    await conn.execute(
        text(
            "INSERT INTO ops.serving_releases"
            "  (serving_release_id, dataset_snapshot_id, state, release_kind, activated_at,"
            "   created_at)"
            " VALUES (:id, :snapshot, :state, :kind, :activated_at,"
            "         COALESCE(:activated_at, now()))"
        ),
        {
            "id": release_id,
            "snapshot": snapshot_id,
            "state": state,
            "kind": release_kind,
            "activated_at": activated_at,
        },
    )


async def _cleanup(conn, *, release_ids: list[str], snapshot_ids: list[str]) -> None:
    # Releases first — ops.serving_releases.dataset_snapshot_id is ON DELETE RESTRICT
    # against ops.dataset_snapshots.
    for release_id in release_ids:
        await conn.execute(
            text("DELETE FROM ops.serving_releases WHERE serving_release_id = :id"),
            {"id": release_id},
        )
    for snapshot_id in snapshot_ids:
        await conn.execute(
            text("DELETE FROM ops.dataset_snapshots WHERE dataset_snapshot_id = :id"),
            {"id": snapshot_id},
        )


@pytest.mark.asyncio
async def test_dataset_version_history_excludes_pending_and_failed_releases() -> None:
    """The safety-critical filter: pending/failed releases (never served, or a promotion
    that didn't happen) must never leak into the external dataset-version history, even
    though they're fully derivable (a version_token is a pure function of the release id —
    nothing stops find_dataset_version from computing one for an excluded row's id if the
    WHERE clause were wrong)."""
    engine = make_async_engine(Settings(pg_dsn=_dsn()))
    try:
        await require_disposable_database(engine)
    except BaseException:
        await engine.dispose()
        raise

    active_snap, active_rel = str(uuid4()), str(uuid4())
    pending_snap, pending_rel = str(uuid4()), str(uuid4())
    failed_snap, failed_rel = str(uuid4()), str(uuid4())
    release_ids = [active_rel, pending_rel, failed_rel]
    snapshot_ids = [active_snap, pending_snap, failed_snap]
    try:
        now = datetime.now(UTC)
        async with engine.begin() as conn:
            await _insert_snapshot(
                conn, snapshot_id=active_snap, source_set={"yyyymm_by_kind": {"juso": "202601"}}
            )
            await _insert_release(
                conn,
                release_id=active_rel,
                snapshot_id=active_snap,
                state="active",
                activated_at=now,
            )
            # pending: a restore candidate not yet promoted (record_restore_candidate's
            # default) — must never appear as "the" or "a" dataset version externally.
            await _insert_snapshot(
                conn,
                snapshot_id=pending_snap,
                source_set={"yyyymm_by_kind": {"juso": "202602"}},
            )
            await _insert_release(
                conn,
                release_id=pending_rel,
                snapshot_id=pending_snap,
                state="pending",
                release_kind="restore",
                activated_at=None,
            )
            # failed: a promotion attempt that didn't succeed.
            await _insert_snapshot(
                conn,
                snapshot_id=failed_snap,
                source_set={"yyyymm_by_kind": {"juso": "202603"}},
            )
            await _insert_release(
                conn,
                release_id=failed_rel,
                snapshot_id=failed_snap,
                state="failed",
                activated_at=None,
            )

        repo = AdminRepository(engine)

        current = await repo.current_dataset_version()
        assert current is not None
        assert current.version_token == derive_version_token(active_rel)

        # dataset_version_history must return only the active release — never the pending
        # or failed ones, however permissive a broken WHERE clause might otherwise be.
        page, has_more = await repo.dataset_version_history(limit=50)
        tokens = {entry.version_token for entry in page}
        assert derive_version_token(active_rel) in tokens
        assert derive_version_token(pending_rel) not in tokens
        assert derive_version_token(failed_rel) not in tokens
        assert has_more is False

        # find_dataset_version must report "not found" for pending/failed tokens even
        # though they're fully computable — the exclusion is by row visibility, not by
        # withholding the derivation.
        assert await repo.find_dataset_version(derive_version_token(pending_rel)) is None
        assert await repo.find_dataset_version(derive_version_token(failed_rel)) is None
        found = await repo.find_dataset_version(derive_version_token(active_rel))
        assert found is not None
        assert found.reference_months == {"juso": "202601"}
    finally:
        async with engine.begin() as conn:
            await _cleanup(conn, release_ids=release_ids, snapshot_ids=snapshot_ids)
        await engine.dispose()


@pytest.mark.asyncio
async def test_dataset_version_resolves_reference_months_via_snapshot_lineage() -> None:
    """A hot-swap/rollback release's own source_set is metadata-only (form C — no
    category/kind keys), so reference_months can only come from walking
    parent_dataset_snapshot_id up to an ancestor whose source_set DOES normalize (ADR-067
    "계보 1 hop 근거"). This proves the walk's JOIN/lookup actually works against the real
    ops.dataset_snapshots table, not just the pure normalizer function in isolation."""
    engine = make_async_engine(Settings(pg_dsn=_dsn()))
    try:
        await require_disposable_database(engine)
    except BaseException:
        await engine.dispose()
        raise

    parent_snap, parent_rel = str(uuid4()), str(uuid4())
    swap_snap, swap_rel = str(uuid4()), str(uuid4())
    release_ids = [parent_rel, swap_rel]
    snapshot_ids = [parent_snap, swap_snap]
    try:
        earlier = datetime.now(UTC) - timedelta(hours=1)
        later = datetime.now(UTC)
        async with engine.begin() as conn:
            # The pre-swap release — its snapshot's source_set is a real (form B) shape.
            await _insert_snapshot(
                conn,
                snapshot_id=parent_snap,
                source_set={"yyyymm_by_kind": {"juso": "202605", "locsum": "202604"}},
            )
            await _insert_release(
                conn,
                release_id=parent_rel,
                snapshot_id=parent_snap,
                # superseded, not active — the swap below is what's currently active.
                state="superseded",
                activated_at=earlier,
            )
            # The hot-swap release: metadata-only source_set (form C), lineage points back
            # at the pre-swap snapshot above.
            await _insert_snapshot(
                conn,
                snapshot_id=swap_snap,
                source_set={"hot_swap": {"current_database": "kor_travel_geo"}},
                parent_dataset_snapshot_id=parent_snap,
            )
            await _insert_release(
                conn,
                release_id=swap_rel,
                snapshot_id=swap_snap,
                state="active",
                release_kind="rollback",
                activated_at=later,
            )

        repo = AdminRepository(engine)
        current = await repo.current_dataset_version()
        assert current is not None
        assert current.version_token == derive_version_token(swap_rel)
        # The whole point: reference_months resolved via the PARENT's source_set, not the
        # swap row's own (which has no category/kind keys at all).
        assert current.reference_months == {"juso": "202605", "locsum": "202604"}
        assert current.reference_months_mixed is True
    finally:
        async with engine.begin() as conn:
            await _cleanup(conn, release_ids=release_ids, snapshot_ids=snapshot_ids)
        await engine.dispose()
