"""T-325a/b data fingerprint, data_token and geo_cache invalidation against real PostGIS (opt-in).

Every sensitivity case below is bound to an effect, and each was run red once on purpose
(table removed from ``DATA_FINGERPRINT_TABLE_SPECS`` / the activation cache clear removed) —
see the PR body for the recorded red runs (ADR-069 T-325a acceptance (1)).

Needs an empty-ish disposable scratch DB bootstrapped with ``ktgctl init-db`` +
``alembic stamp head`` (tests/integration/_pg_guard.py naming rule). Rows this module inserts
use the sig_cd/code prefix ``99`` and are removed afterwards; releases it records stay (scratch
ledger)::

    KTG_TEST_PG_DSN=postgresql+psycopg://<user>:<pw>@127.0.0.1:<port>/kor_travel_geo_t325_test \
        pytest tests/integration/test_t325_data_fingerprint.py
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kortravelgeo.api.app import create_app
from kortravelgeo.api.dataset_ref import DatasetRefCache
from kortravelgeo.api.deps import get_client
from kortravelgeo.api.public_api_key import require_public_api_key
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.infra import data_fingerprint
from kortravelgeo.infra.admin_repo import AdminRepository, _insert_dataset_snapshot_and_release
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.loaders.postload import refresh_mv
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database

pytestmark = pytest.mark.asyncio

# EPSG:5179 square well inside the national grid; "다바 6925 4045" (969255, 1840455) is inside.
_SQUARE = (
    "ST_GeomFromText('MULTIPOLYGON(((969000 1840000, 969500 1840000, 969500 1840500,"
    " 969000 1840500, 969000 1840000)))', 5179)"
)
# Same bbox, one extra (collinear) vertex on the bottom edge.
_SQUARE_PLUS_VERTEX = (
    "ST_GeomFromText('MULTIPOLYGON(((969000 1840000, 969250 1840000, 969500 1840000,"
    " 969500 1840500, 969000 1840500, 969000 1840000)))', 5179)"
)
_LINE = "ST_GeomFromText('MULTILINESTRING((969000 1840000, 969500 1840500))', 5179)"
_SPPN_QUERY = "다바 6925 4045"
_BD_MGT_SN = "9911010100100010000000001"

_CLEANUP_SQL = (
    "DELETE FROM tl_scco_ctprvn WHERE ctprvn_cd LIKE '99%'",
    "DELETE FROM tl_scco_sig WHERE sig_cd LIKE '99%'",
    "DELETE FROM tl_scco_emd WHERE emd_cd LIKE '99%'",
    "DELETE FROM tl_scco_li WHERE li_cd LIKE '99%'",
    "DELETE FROM region_radius_parts WHERE code LIKE '99%'",
    "DELETE FROM tl_kodis_bas WHERE bas_mgt_sn LIKE '99%'",
    "DELETE FROM postal_bulk_delivery WHERE bd_mgt_sn LIKE '99%'",
    "DELETE FROM tl_sppn_makarea WHERE sig_cd LIKE '99%'",
    "DELETE FROM tl_spbd_buld_polygon WHERE bd_mgt_sn LIKE '99%'",
    "DELETE FROM tl_sprd_manage WHERE sig_cd LIKE '99%'",
    "DELETE FROM tl_juso_text WHERE bd_mgt_sn LIKE '99%'",
    "DELETE FROM load_manifest WHERE source_zip = 't325'",
    "DELETE FROM geo_cache",
)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostgreSQL scratch DB")
    eng = make_async_engine(Settings(pg_dsn=dsn))
    try:
        await require_disposable_database(eng)
        async with eng.connect() as conn:
            if await conn.scalar(text("SELECT to_regclass('ops.dataset_snapshots')")) is None:
                pytest.skip("scratch DB needs `ktgctl init-db` + `alembic stamp head`")
        await _cleanup(eng)
        async with eng.connect() as conn:
            started_at = await conn.scalar(text("SELECT clock_timestamp()"))
        yield eng
        await _cleanup(eng)
        await _drop_ledger_rows_since(eng, started_at)
    finally:
        await eng.dispose()


async def _drop_ledger_rows_since(engine: AsyncEngine, started_at: Any) -> None:
    """Releases this test recorded would otherwise outrank other modules' fixtures in the
    shared scratch ledger (test_dataset_version_projection reads the whole history)."""
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM ops.serving_releases WHERE created_at >= :t"), {"t": started_at}
        )
        await conn.execute(
            text(
                "DELETE FROM ops.dataset_snapshots s WHERE s.created_at >= :t"
                " AND NOT EXISTS (SELECT 1 FROM ops.serving_releases r"
                "                  WHERE r.dataset_snapshot_id = s.dataset_snapshot_id)"
            ),
            {"t": started_at},
        )


async def _cleanup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for sql in _CLEANUP_SQL:
            await conn.execute(text(sql))
    await refresh_mv(engine)


async def _exec(engine: AsyncEngine, *statements: str) -> None:
    async with engine.begin() as conn:
        for sql in statements:
            await conn.execute(text(sql))


async def _activate(engine: AsyncEngine, **kwargs: Any) -> str | None:
    """A standalone-load style activation (no refresh_mv, so no refresh_mv cache clear)."""
    kwargs.setdefault("release_kind", "manual_rebuild")
    _, release = await AdminRepository(engine).record_mv_refresh_release(**kwargs)
    return release.data_token


async def _current(engine: AsyncEngine) -> tuple[str, str | None]:
    ref = await AdminRepository(engine).current_dataset_ref()
    assert ref is not None
    return ref


async def _cache_rows(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return int(await conn.scalar(text("SELECT count(*) FROM geo_cache")) or 0)


async def _seed_cache_row(engine: AsyncEngine) -> None:
    await _exec(
        engine,
        "INSERT INTO geo_cache (cache_key, service, payload, expires_at)"
        " VALUES ('t325:seed', 'reverse', '{}'::jsonb, now() + interval '1 day')"
        " ON CONFLICT (cache_key) DO NOTHING",
    )


# --- column lists against the live schema --------------------------------------------------------


async def test_fingerprint_column_lists_match_the_live_schema(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        for spec in data_fingerprint.DATA_FINGERPRINT_TABLE_SPECS:
            names = (
                await conn.execute(
                    text(
                        "SELECT attname FROM pg_attribute"
                        " WHERE attrelid = to_regclass(:name) AND attnum > 0"
                        "   AND NOT attisdropped"
                    ),
                    {"name": f"public.{spec.name}"},
                )
            ).scalars().all()
            expected = set(names) - data_fingerprint.EXCLUDED_COLUMNS
            assert spec.accounted_columns == expected, spec.name


# --- token stability ---------------------------------------------------------------------------


async def test_same_data_reactivation_keeps_the_token(engine: AsyncEngine) -> None:
    first = await _activate(engine)
    second = await _activate(engine)
    assert first is not None and first == second
    assert (await _current(engine))[1] == second


async def test_bulk_delivery_reload_with_new_surrogate_keys_keeps_the_token(
    engine: AsyncEngine,
) -> None:
    rows = (
        "INSERT INTO postal_bulk_delivery (zip_no, bd_mgt_sn, bulk_name, detail, loaded_at)"
        " VALUES ('99001', '9900000000000000000000001', '대량A', '1동', now()),"
        "        ('99002', '9900000000000000000000002', '대량B', NULL, now())"
    )
    await _exec(engine, rows)
    before = await _activate(engine)
    # the "same file loaded twice": rows deleted and re-inserted, bulk_id/loaded_at re-assigned
    await _exec(
        engine,
        "DELETE FROM postal_bulk_delivery WHERE bd_mgt_sn LIKE '99%'",
        rows.replace("now()", "now() + interval '1 hour'"),
    )
    after = await _activate(engine)
    assert before is not None and before == after


# --- token sensitivity, one table at a time ------------------------------------------------------

_SENSITIVITY_CASES: dict[str, tuple[str, str]] = {
    "tl_scco_ctprvn": (
        "INSERT INTO tl_scco_ctprvn (ctprvn_cd, ctp_kor_nm, geom)"
        f" VALUES ('99', '구시도', {_SQUARE})",
        "UPDATE tl_scco_ctprvn SET ctp_kor_nm = '신시도' WHERE ctprvn_cd = '99'",
    ),
    "tl_scco_sig": (
        f"INSERT INTO tl_scco_sig (sig_cd, sig_kor_nm, geom) VALUES ('99110', '구군', {_SQUARE})",
        "UPDATE tl_scco_sig SET sig_kor_nm = '신군' WHERE sig_cd = '99110'",
    ),
    "tl_scco_emd": (
        "INSERT INTO tl_scco_emd (emd_cd, emd_kor_nm, geom)"
        f" VALUES ('99110101', '구동', {_SQUARE})",
        "UPDATE tl_scco_emd SET emd_kor_nm = '신동' WHERE emd_cd = '99110101'",
    ),
    "tl_scco_li": (
        f"INSERT INTO tl_scco_li (li_cd, li_kor_nm, geom) VALUES ('9911010121', '구리', {_SQUARE})",
        "UPDATE tl_scco_li SET li_kor_nm = '신리' WHERE li_cd = '9911010121'",
    ),
    "region_radius_parts": (
        "INSERT INTO region_radius_parts (level, code, name, part_no, geom)"
        f" VALUES ('sigungu', '99110', '구군', 1, {_SQUARE})",
        "UPDATE region_radius_parts SET name = '신군' WHERE code = '99110'",
    ),
    "tl_kodis_bas": (
        "INSERT INTO tl_kodis_bas (bas_mgt_sn, bas_id, geom)"
        f" VALUES ('99000001', '99001', {_SQUARE})",
        "UPDATE tl_kodis_bas SET bas_id = '99002' WHERE bas_mgt_sn = '99000001'",
    ),
    "postal_bulk_delivery": (
        "INSERT INTO postal_bulk_delivery (zip_no, bd_mgt_sn, bulk_name)"
        " VALUES ('99001', '9900000000000000000000001', '대량A')",
        "UPDATE postal_bulk_delivery SET zip_no = '99009' WHERE bd_mgt_sn LIKE '99%'",
    ),
    "tl_sppn_makarea": (
        "INSERT INTO tl_sppn_makarea (sig_cd, makarea_id, makarea_nm, geom, source_file)"
        f" VALUES ('99110', 'M1', '구구역', {_SQUARE}, 't325.shp')",
        "UPDATE tl_sppn_makarea SET makarea_nm = '신구역' WHERE sig_cd = '99110'",
    ),
    "tl_spbd_buld_polygon": (
        "INSERT INTO tl_spbd_buld_polygon (bd_mgt_sn, sig_cd, emd_cd, buld_mnnm, geom)"
        f" VALUES ('9900000000000000000000001', '99110', '101', 1, {_SQUARE})",
        "UPDATE tl_spbd_buld_polygon SET buld_mnnm = 2 WHERE bd_mgt_sn LIKE '99%'",
    ),
    "tl_sprd_manage": (
        "INSERT INTO tl_sprd_manage (sig_cd, rds_man_no, rn_cd, rn, geom)"
        f" VALUES ('99110', '1', '1234567', '구로', {_LINE})",
        "UPDATE tl_sprd_manage SET rn = '신로' WHERE sig_cd = '99110'",
    ),
}


@pytest.mark.parametrize("table", sorted(_SENSITIVITY_CASES))
async def test_one_row_change_in_each_serving_table_changes_the_token(
    engine: AsyncEngine, table: str
) -> None:
    seed, change = _SENSITIVITY_CASES[table]
    await _exec(engine, seed)
    before = await _activate(engine)
    await _exec(engine, change)
    after = await _activate(engine)
    assert before is not None and after is not None
    assert before != after, f"{table}: a one-row change left data_token unchanged"


async def test_polygon_vertex_added_inside_the_same_bbox_changes_the_token(
    engine: AsyncEngine,
) -> None:
    await _exec(
        engine,
        f"INSERT INTO tl_scco_sig (sig_cd, sig_kor_nm, geom) VALUES ('99110', '군', {_SQUARE})",
    )
    before = await _activate(engine)
    await _exec(
        engine, f"UPDATE tl_scco_sig SET geom = {_SQUARE_PLUS_VERTEX} WHERE sig_cd = '99110'"
    )
    after = await _activate(engine)
    assert before is not None and before != after


async def _insert_juso(
    engine: AsyncEngine, *, bd_mgt_sn: str = _BD_MGT_SN, buld_mnnm: int = 1
) -> None:
    await _exec(
        engine,
        "INSERT INTO tl_juso_text (bd_mgt_sn, sig_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, bjd_cd,"
        " rn_cd, rn, buld_mnnm, buld_slno, mntn_yn, lnbr_mnnm, lnbr_slno, zip_no)"
        f" VALUES ('{bd_mgt_sn}', '99110', '시험도', '시험군', '시험동', '9911010100',"
        f" '1234567', '시험로', {buld_mnnm}, 0, '0', {buld_mnnm}, 0, '99001')",
    )


async def test_mv_geocode_target_change_after_refresh_changes_the_token(
    engine: AsyncEngine,
) -> None:
    before = await _activate(engine)
    await _insert_juso(engine)
    await refresh_mv(engine)
    after = await _activate(engine)
    assert before is not None and before != after


async def test_daily_delta_on_the_inferred_source_set_branch_changes_only_the_data_token(
    engine: AsyncEngine,
) -> None:
    """MVM 63 (폐지) style: a juso row disappears, the reference month does not move. With no
    load batch and no consistency report the release's source_set comes from the
    month-inference branch, so source_set_hash stays — data_token must not."""
    await _exec(
        engine,
        "INSERT INTO load_manifest (table_name, source_yyyymm, source_zip)"
        " VALUES ('tl_juso_text', '202609', 't325')"
        " ON CONFLICT (table_name) DO NOTHING",
    )
    await _insert_juso(engine)
    await _insert_juso(engine, bd_mgt_sn="9911010100100020000000002", buld_mnnm=2)
    await refresh_mv(engine)
    _, before_release = await AdminRepository(engine).record_mv_refresh_release(
        load_batch_id=None, release_kind="daily_delta"
    )
    await _exec(engine, f"DELETE FROM tl_juso_text WHERE bd_mgt_sn = '{_BD_MGT_SN}'")
    await refresh_mv(engine)
    _, after_release = await AdminRepository(engine).record_mv_refresh_release(
        load_batch_id=None, release_kind="daily_delta"
    )
    async with engine.connect() as conn:
        hashes = (
            await conn.execute(
                text(
                    "SELECT ds.source_set_hash, ds.source_set->>'source' AS source"
                    "  FROM ops.serving_releases sr JOIN ops.dataset_snapshots ds"
                    "    USING (dataset_snapshot_id)"
                    " WHERE sr.serving_release_id IN (:a, :b)"
                ),
                {"a": before_release.serving_release_id, "b": after_release.serving_release_id},
            )
        ).mappings().all()
    assert {row["source"] for row in hashes} == {"database_manifest_inference"}
    assert len({row["source_set_hash"] for row in hashes}) == 1
    assert before_release.data_token is not None
    assert before_release.data_token != after_release.data_token


# --- fail-open --------------------------------------------------------------------------------

_SLOW_SQL = (
    "SELECT 'mv_geocode_target'::text AS table_name, 0::numeric AS h,"
    " md5('t325') AS fingerprint FROM pg_sleep({seconds})"
)


async def test_fingerprint_timeout_fails_open_with_a_notes_suffix(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(data_fingerprint, "DATA_FINGERPRINT_SQL", _SLOW_SQL.format(seconds=2))
    monkeypatch.setattr(data_fingerprint, "DATA_FINGERPRINT_STATEMENT_TIMEOUT", "200ms")
    await _seed_cache_row(engine)

    _, release = await AdminRepository(engine).record_mv_refresh_release(
        release_kind="manual_rebuild", notes="t325 timeout case"
    )

    assert release.state == "active"
    assert release.data_token is None
    assert release.notes == "t325 timeout case; data_fingerprint_failed: timeout"
    assert (await _current(engine))[1] is None
    assert await _cache_rows(engine) == 0  # the clear still ran


async def test_after_a_failed_fingerprint_the_paths_own_timeout_is_back(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(data_fingerprint, "DATA_FINGERPRINT_SQL", _SLOW_SQL.format(seconds=2))
    monkeypatch.setattr(data_fingerprint, "DATA_FINGERPRINT_STATEMENT_TIMEOUT", "200ms")
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL statement_timeout = '30min'"))
        _, release = await _insert_dataset_snapshot_and_release(
            conn,
            snapshot_state="released",
            release_state="active",
            release_kind="manual_rebuild",
            source_set={},
            row_counts={},
        )
        timeout_after = await conn.scalar(text("SHOW statement_timeout"))
    assert release.data_token is None
    assert release.notes == "data_fingerprint_failed: timeout"
    assert timeout_after == "30min"


async def test_after_a_successful_fingerprint_the_paths_own_timeout_is_back(
    engine: AsyncEngine,
) -> None:
    """``SET LOCAL`` inside a RELEASEd savepoint would outlive it; the savepoint is rolled back
    on success too, so the path's 30 min (not the fingerprint's 10 min) governs what follows."""
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL statement_timeout = '30min'"))
        _, release = await _insert_dataset_snapshot_and_release(
            conn,
            snapshot_state="released",
            release_state="active",
            release_kind="manual_rebuild",
            source_set={},
            row_counts={},
        )
        timeout_after = await conn.scalar(text("SHOW statement_timeout"))
    assert release.data_token is not None
    assert timeout_after == "30min"


# --- all four activation paths: token + cache clear --------------------------------------------


async def test_every_activation_path_fingerprints_and_clears_the_cache(
    engine: AsyncEngine,
) -> None:
    repo = AdminRepository(engine)
    async def mv_refresh() -> str | None:
        return (await repo.record_mv_refresh_release(release_kind="manual_rebuild"))[1].data_token

    async def restore() -> str | None:
        _, release = await repo.record_restore_candidate(
            restore_artifact_id="t325-restore",
            target_database="kor_travel_geo_t325_test",
            source_manifest={"source_set": {"juso": "202609"}, "row_counts": {}},
            activate=True,
        )
        return release.data_token

    async def hot_swap() -> str | None:
        release = await repo.record_hot_swap_release(
            current_database="kor_travel_geo_t325_test",
            restore_database="kor_travel_geo_t325_restore",
            previous_alias="kor_travel_geo_t325_prev",
        )
        return release.data_token

    async def rollback() -> str | None:
        release = await repo.record_hot_swap_rollback_release(
            current_database="kor_travel_geo_t325_test",
            restore_database="kor_travel_geo_t325_restore",
            previous_alias="kor_travel_geo_t325_prev",
        )
        return release.data_token

    paths: dict[str, Callable[[], Awaitable[str | None]]] = {
        "mv_refresh": mv_refresh,
        "restore": restore,
        "hot_swap": hot_swap,
        "rollback": rollback,
    }
    tokens: dict[str, str | None] = {}
    for name, activate in paths.items():
        await _seed_cache_row(engine)
        assert await _cache_rows(engine) == 1
        tokens[name] = await activate()
        assert await _cache_rows(engine) == 0, f"{name}: geo_cache not cleared on activation"
    # same data on every path ⇒ one token, and it is not NULL
    assert None not in tokens.values(), tokens
    assert len(set(tokens.values())) == 1, tokens
    # the same backup restored twice ⇒ same token
    assert await restore() == tokens["restore"]


async def test_cache_is_cleared_even_when_the_caller_supplies_the_fingerprint(
    engine: AsyncEngine,
) -> None:
    """ADR-069 D4: the clear is tied to "active", not to whether the fingerprint was computed."""
    await _seed_cache_row(engine)
    async with engine.begin() as conn:
        _, release = await _insert_dataset_snapshot_and_release(
            conn,
            snapshot_state="released",
            release_state="active",
            release_kind="manual_rebuild",
            source_set={},
            row_counts={},
            data_fingerprint="c" * 32,
        )
    assert release.data_token is not None
    assert await _cache_rows(engine) == 0


async def test_pending_candidate_neither_fingerprints_nor_clears_the_cache(
    engine: AsyncEngine,
) -> None:
    await _seed_cache_row(engine)
    _, release = await AdminRepository(engine).record_restore_candidate(
        restore_artifact_id="t325-pending",
        target_database="kor_travel_geo_t325_pending",
        source_manifest={"source_set": {}, "row_counts": {}},
        activate=False,
    )
    assert release.state == "pending"
    assert release.data_token is None
    assert await _cache_rows(engine) == 1
    await AdminRepository(engine).delete_pending_restore_candidate_by_target_database(
        "kor_travel_geo_t325_pending"
    )


# --- lock ordering (ADR-069 D4 / T-325a acceptance (8)) ------------------------------------------


async def test_fingerprint_runs_before_the_activation_lock(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slow fingerprint in activation A must not hold up a concurrent activation B."""
    monkeypatch.setattr(data_fingerprint, "DATA_FINGERPRINT_SQL", _SLOW_SQL.format(seconds=3))
    finished: dict[str, float] = {}

    async def activate(name: str, **kwargs: Any) -> None:
        conn: AsyncConnection
        async with engine.begin() as conn:
            await _insert_dataset_snapshot_and_release(
                conn,
                snapshot_state="released",
                release_state="active",
                release_kind="manual_rebuild",
                source_set={},
                row_counts={},
                **kwargs,
            )
        finished[name] = time.monotonic()

    started = time.monotonic()
    task_a = asyncio.ensure_future(activate("a"))
    await asyncio.sleep(0.5)  # A is now inside its 3 s fingerprint
    await activate("b", data_fingerprint="b" * 32)
    await task_a
    assert finished["b"] - started < 2.0, "B waited for A's fingerprint: it ran under the lock"
    assert finished["a"] > finished["b"]


# --- cache invalidation through the v2 API (T-325a acceptance (1), T-325b (5)) -----------------


async def _v2(engine: AsyncEngine, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    client = AsyncAddressClient(
        engine=engine, settings=Settings(_env_file=None, cache_enabled=True)
    )
    app = create_app()
    app.dependency_overrides[get_client] = lambda: client
    app.dependency_overrides[require_public_api_key] = lambda: None
    app.state.dataset_ref_cache = DatasetRefCache(ttl_s=0.0)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.post(path, json=payload)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _sppn_point_4326(engine: AsyncEngine) -> tuple[float, float]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT ST_X(p) AS lon, ST_Y(p) AS lat FROM ("
                    " SELECT ST_Transform(ST_SetSRID(ST_MakePoint(969255, 1840455), 5179), 4326)"
                    " AS p) s"
                )
            )
        ).mappings().one()
    return float(row["lon"]), float(row["lat"])


async def _seed_makarea(engine: AsyncEngine) -> None:
    await _exec(
        engine,
        "INSERT INTO tl_sppn_makarea (sig_cd, makarea_id, makarea_nm, geom, source_file)"
        f" VALUES ('99110', 'M1', '구구역', {_SQUARE}, 't325.shp')",
    )


async def _rename_makarea_and_release(engine: AsyncEngine) -> str | None:
    """A standalone auxiliary load: data changes, a release is recorded, refresh_mv (and its own
    cache clear) never runs."""
    await _exec(engine, "UPDATE tl_sppn_makarea SET makarea_nm = '신구역' WHERE sig_cd = '99110'")
    return await _activate(engine)


async def test_standalone_release_invalidates_cached_reverse_and_restamps_v2(
    engine: AsyncEngine,
) -> None:
    await _seed_makarea(engine)
    first_token = await _activate(engine)
    lon, lat = await _sppn_point_4326(engine)
    payload = {"lon": lon, "lat": lat}

    first = await _v2(engine, "/v2/reverse", payload)
    assert "구구역" in str(first["candidates"])
    assert first["dataset"]["data_token"] == first_token
    assert await _cache_rows(engine) >= 1

    second_token = await _rename_makarea_and_release(engine)
    assert await _cache_rows(engine) == 0

    second = await _v2(engine, "/v2/reverse", payload)
    assert "신구역" in str(second["candidates"]), "stale cached reverse served after release"
    assert second["dataset"]["data_token"] == second_token != first_token

    # a geo_cache hit is stamped with the *current* token too (T-325b (5))
    third = await _v2(engine, "/v2/reverse", payload)
    assert await _cache_rows(engine) >= 1
    assert third["candidates"] == second["candidates"]
    assert third["dataset"]["data_token"] == second_token


async def test_standalone_release_invalidates_cached_geocode(engine: AsyncEngine) -> None:
    """The geocode result cache (shared by v1 and v2 geocode) carries the SPPN area context read
    from tl_sppn_makarea; v2 geocode does not surface the area name, so the cached v1 layer is
    asserted directly, and the v2 stamp separately."""
    await _seed_makarea(engine)
    first_token = await _activate(engine)
    client = AsyncAddressClient(
        engine=engine, settings=Settings(_env_file=None, cache_enabled=True)
    )

    async def area_name() -> str | None:
        response = await client._geocode_v1(_SPPN_QUERY)
        area = response.x_extension.sppn_makarea if response.x_extension else None
        return area.makarea_nm if area is not None else None

    assert await area_name() == "구구역"
    assert await _cache_rows(engine) == 1
    v2_first = await _v2(engine, "/v2/geocode", {"query": _SPPN_QUERY})
    assert v2_first["dataset"]["data_token"] == first_token

    second_token = await _rename_makarea_and_release(engine)
    assert await _cache_rows(engine) == 0
    assert await area_name() == "신구역", "stale cached geocode served after release"
    v2_second = await _v2(engine, "/v2/geocode", {"query": _SPPN_QUERY})
    assert v2_second["dataset"]["data_token"] == second_token != first_token


# --- backfill CLI path --------------------------------------------------------------------------


async def test_backfill_stores_the_fingerprint_and_clears_the_cache_dry_run_does_neither(
    engine: AsyncEngine,
) -> None:
    repo = AdminRepository(engine)
    _, release = await _insert_release_without_fingerprint(engine)
    assert (await _current(engine))[1] is None
    await _seed_cache_row(engine)

    dry = await repo.fingerprint_active_release(dry_run=True)
    assert dry is not None and dry.fingerprint is not None
    assert (await _current(engine))[1] is None
    assert await _cache_rows(engine) == 1

    stored = await repo.fingerprint_active_release(dry_run=False)
    assert stored is not None and stored.fingerprint == dry.fingerprint
    assert (await _current(engine))[1] is not None
    assert await _cache_rows(engine) == 0
    assert release.serving_release_id


async def _insert_release_without_fingerprint(engine: AsyncEngine) -> Any:
    """An active release as it looks before the backfill: snapshot fingerprint NULL."""
    async with engine.begin() as conn:
        snapshot, release = await _insert_dataset_snapshot_and_release(
            conn,
            snapshot_state="released",
            release_state="active",
            release_kind="manual_rebuild",
            source_set={},
            row_counts={},
        )
        await conn.execute(
            text(
                "UPDATE ops.dataset_snapshots SET data_fingerprint = NULL"
                " WHERE dataset_snapshot_id = :id"
            ),
            {"id": snapshot.dataset_snapshot_id},
        )
    return snapshot, release
