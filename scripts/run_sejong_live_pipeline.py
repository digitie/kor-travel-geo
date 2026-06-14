#!/usr/bin/env python3
"""T-213 (small) — Sejong live END-TO-END validation of the T-109 source pipeline.

Drives the **new source pipeline** infra services in-process against a LIVE
PostGIS DB with the REAL 세종특별자치시 electronic_map SHP archive and the REAL
GDAL loader, proving::

    upload-session → register (real ZIP, real group_sha256, real SHP validator)
      → match-set (custom profile) create → validate → activate
      → rebuild bridge (assemble the real full_load_batch payload)
      → REAL shp_polygons loader on the Sejong archive → serving SHP tables
      → dataset_snapshot recorded with the source_match_set_id 정본 FK + verify

Run (WSL ext4 test mirror)::

    cd /mnt/f/dev/kor-travel-geo-claude
    KTG_TEST_PG_DSN='postgresql+psycopg://addr:addr@localhost:15434/kor_travel_geo' \\
        ~/ktgvenv/bin/python scripts/run_sejong_live_pipeline.py

The script is **idempotent**: on every run it first removes the registry rows it
owns (matched by the runbook's unique markers) and TRUNCATEs the serving SHP
tables it loads, so it can be re-run repeatedly. ``ops.audit_events`` is
append-only and is intentionally left untouched.

Caveats (the full-national gap → proper T-213):
  * A single 시도 cannot satisfy ``serving_minimal`` (national juso/locsum/navi +
    full serving profile), so this uses the ``custom`` match-set profile (no
    required categories).
  * The 17-시도 ``validate_group_manifest`` correctly returns ``failed`` for a
    one-시도 upload (16 시도 missing). The runbook therefore builds the group
    structure decision from the REAL per-part SHP layer/sidecar validator
    (``_validate_layer_part`` over the real ZIP members) scoped to the single
    present 시도 — the same per-part logic the validator uses, just over the one
    part we deliberately load. This is documented in
    ``docs/t213-sejong-live-validation.md``.
  * There is no ``full_load_batch`` JobQueue handler (it is a batch-root marker
    expanded at enqueue time, not a dispatched job). The rebuild service is run
    to **assemble** the real batch payload (the ``shp_polygons_load`` child), and
    the runbook then materializes the staging dir that payload points at and runs
    the SAME loader (``load_shp_polygons``) the ``shp_polygons_load`` handler
    invokes — proving "real Sejong SHP → serving tables via the new pipeline's
    loader".
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import time
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

from kortravelgeo.core.source_validation import (
    LAYER_PROFILES,
    GroupValidation,
    _validate_layer_part,
)
from kortravelgeo.dto.source import (
    SourceMatchSetCreateRequest,
    SourceMatchSetItemRequest,
    UploadSessionCreateRequest,
)
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.rustfs import sha256_file
from kortravelgeo.infra.source_group_service import (
    RegisterContext,
    SourceGroupRegistrar,
)
from kortravelgeo.infra.source_match_set_service import SourceMatchSetRepository
from kortravelgeo.infra.source_member_scan import scan_part_manifest
from kortravelgeo.infra.source_rebuild_service import SourceRebuildService
from kortravelgeo.infra.source_upload_repo import SourceUploadSessionRepository
from kortravelgeo.infra.sql import INDEX_SQL, SCHEMA_SQL, iter_sql_statements
from kortravelgeo.loaders.shp.polygons_loader import (
    POLYGON_LAYER_NAMES,
    TARGET_TABLES,
    load_shp_polygons,
)
from kortravelgeo.settings import Settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

# --- runbook constants -----------------------------------------------------

DEFAULT_DSN = "postgresql+psycopg://addr:addr@localhost:15434/kor_travel_geo"
DEFAULT_ZIP = (
    "/mnt/f/dev/kor-travel-geo/data/juso/도로명주소 전자지도/202604/세종특별자치시.zip"
)
#: NAVI/LOCSUM electronic-map 기준월 (docs/data 기준월 표).
ELECTRONIC_MAP_YYYYMM = "202604"
CATEGORY = "electronic_map_full"
SEJONG_SIDO_CODE = "36"  # 세종특별자치시 (SIDO_PARTS)
SEJONG_SIDO_NAME = "세종특별자치시"

#: Unique markers so the runbook only ever touches the rows it owns.
RUN_MARKER = "t213-sejong-live"
DISPLAY_NAME = f"[{RUN_MARKER}] 세종 전자지도 202604"
MATCH_SET_NAME = f"{RUN_MARKER} custom (Sejong electronic_map)"
ACTOR = RUN_MARKER

#: The serving SHP target tables the polygons loader writes (mode='full'
#: TRUNCATEs all of them). Listed for the verify + cleanup steps.
SERVING_TABLES: tuple[str, ...] = tuple(
    dict.fromkeys(TARGET_TABLES[name] for name in POLYGON_LAYER_NAMES)
)


def _json_text(sql: str, *json_params: str):
    return text(sql).bindparams(*(bindparam(n, type_=JSONB) for n in json_params))


def _file_size(path: Path) -> int:
    """Sync stat helper (kept out of async bodies for ASYNC240)."""
    return path.stat().st_size


def _archive_size(path: Path) -> int:
    """Validate the archive exists and return its size (sync, pre-flight)."""
    if not path.exists():
        raise SystemExit(f"Sejong archive not found: {path}")
    return path.stat().st_size


# --- schema -----------------------------------------------------------------


async def apply_schema(engine: AsyncEngine) -> None:
    """Idempotently apply SCHEMA_SQL + INDEX_SQL.

    Most DDL is ``IF NOT EXISTS``, but a few ``ALTER TABLE ... ADD CONSTRAINT``
    statements are not. Each statement runs in its own savepoint so an
    already-applied constraint (``DuplicateObject``/``DuplicateTable``) is
    tolerated, letting the runbook re-run against a DB whose schema is current.
    """
    from sqlalchemy.exc import ProgrammingError

    statements = (
        *iter_sql_statements(SCHEMA_SQL),
        *iter_sql_statements(INDEX_SQL),
    )
    async with engine.connect() as conn:
        for statement in statements:
            try:
                async with conn.begin():
                    await conn.execute(text(statement))
            except ProgrammingError as exc:
                code = getattr(getattr(exc.orig, "sqlstate", None), "__str__", lambda: "")()
                # 42710 duplicate_object, 42P07 duplicate_table, 42P16 — tolerate.
                if code not in {"42710", "42P07", "42P16"} and "already exists" not in str(
                    exc
                ):
                    raise


# --- idempotent cleanup -----------------------------------------------------


async def cleanup(engine: AsyncEngine) -> None:
    """Remove rows the runbook owns + TRUNCATE the serving SHP tables.

    Scoped by RUN_MARKER (match-set name, group display_name); audit_events is
    append-only and intentionally NOT touched.
    """
    async with engine.begin() as conn:
        # Match sets owned by the runbook (items first — FK).
        ms_ids = (
            await conn.execute(
                text(
                    "SELECT source_match_set_id FROM ops.source_match_sets "
                    "WHERE name = :name"
                ),
                {"name": MATCH_SET_NAME},
            )
        ).scalars().all()
        if ms_ids:
            await conn.execute(
                text(
                    "DELETE FROM ops.source_match_set_items "
                    "WHERE source_match_set_id = ANY(:ids)"
                ),
                {"ids": list(ms_ids)},
            )
            await conn.execute(
                text(
                    "DELETE FROM ops.source_match_sets "
                    "WHERE source_match_set_id = ANY(:ids)"
                ),
                {"ids": list(ms_ids)},
            )

        # Groups owned by the runbook (display_name marker) → children/members.
        group_ids = (
            await conn.execute(
                text(
                    "SELECT source_file_group_id FROM ops.source_file_groups "
                    "WHERE display_name = :dn"
                ),
                {"dn": DISPLAY_NAME},
            )
        ).scalars().all()
        if group_ids:
            await conn.execute(
                text(
                    "DELETE FROM ops.source_file_members WHERE source_file_id IN ("
                    " SELECT source_file_id FROM ops.source_files "
                    " WHERE source_file_group_id = ANY(:ids))"
                ),
                {"ids": list(group_ids)},
            )
            await conn.execute(
                text(
                    "DELETE FROM ops.source_file_validations "
                    "WHERE source_file_group_id = ANY(:ids)"
                ),
                {"ids": list(group_ids)},
            )
            await conn.execute(
                text(
                    "DELETE FROM ops.source_files WHERE source_file_group_id = ANY(:ids)"
                ),
                {"ids": list(group_ids)},
            )
            await conn.execute(
                text(
                    "DELETE FROM ops.source_file_groups "
                    "WHERE source_file_group_id = ANY(:ids)"
                ),
                {"ids": list(group_ids)},
            )

        # Upload sessions owned by the runbook.
        await conn.execute(
            text("DELETE FROM ops.source_upload_sessions WHERE display_name = :dn"),
            {"dn": DISPLAY_NAME},
        )

        # Dataset snapshots created by the runbook (source_set marker).
        await conn.execute(
            text(
                "DELETE FROM ops.dataset_snapshots "
                "WHERE source_set ->> 'runbook' = :marker"
            ),
            {"marker": RUN_MARKER},
        )

        # Serving SHP tables (the polygons loader full-load TRUNCATEs these too).
        for table in SERVING_TABLES:
            await conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))


def _remove_staging(staging_dir: str | None) -> None:
    """Remove a runbook staging tree + its empty ``rebuild_staging`` root."""
    if not staging_dir:
        return
    path = Path(staging_dir)
    shutil.rmtree(path, ignore_errors=True)
    parent = path.parent  # rebuild_staging/
    if parent.name == "rebuild_staging" and parent.exists() and not any(parent.iterdir()):
        parent.rmdir()


# --- step 3: register -------------------------------------------------------


async def register_sejong(
    engine: AsyncEngine, zip_path: Path
) -> tuple[str, str, GroupValidation, dict]:
    """Create an upload session, record the local stored object, and register.

    Returns ``(group_id, group_sha256, group_validation, register_response)``.
    """
    upload_repo = SourceUploadSessionRepository(engine)
    create = await upload_repo.create_session(
        UploadSessionCreateRequest(
            category=CATEGORY,
            user_yyyymm=ELECTRONIC_MAP_YYYYMM,
            display_name=DISPLAY_NAME,
            storage_kind="local",
            upload_strategy="multipart",
        ),
        bucket=None,
        prefix=None,
        created_by=ACTOR,
    )
    session = create.session
    session_id = session.upload_session_id

    # Record the Sejong slot as a completed part pointing at the real local ZIP.
    digest = await sha256_file(zip_path)
    size = _file_size(zip_path)
    await upload_repo.record_part(
        session_id,
        part_key=SEJONG_SIDO_CODE,
        part_number=1,
        part_sha256=digest,
        received_bytes=size,
        completed=True,
    )

    # REAL per-part SHP layer/sidecar validation over the real ZIP members.
    part = scan_part_manifest(zip_path, part_key=SEJONG_SIDO_CODE)
    part_decision = _validate_layer_part(part, LAYER_PROFILES[CATEGORY])
    # Build a single-시도-scoped GroupValidation from the real per-part decision
    # (the 17-시도 group validator would fail on the 16 absent 시도 — caveat).
    group_validation = GroupValidation(
        category=CATEGORY,
        outcome=part_decision.outcome,
        reasons=part_decision.reasons,
        parts=(part_decision,),
        coverage={SEJONG_SIDO_CODE: "present"
                  if part_decision.outcome != "failed" else "failed"},
    )

    # storage_kind='local', bucket=None → registrar storage_uri = local://<key>.
    context = RegisterContext(
        part_key=SEJONG_SIDO_CODE,
        part_kind="sido",
        part_label=SEJONG_SIDO_NAME,
        original_filename=zip_path.name,
        sha256=digest,
        size_bytes=size,
        object_key=str(zip_path),
        object_etag=None,
        compression_format="zip",
    )

    registrar = SourceGroupRegistrar(engine)
    response = await registrar.register(
        session_id=session_id,
        contexts=(context,),
        structure_validation=group_validation,
        storage_kind="local",
        bucket=None,
        actor=ACTOR,
        yyyymm_mismatch_ack=False,
        display_name=DISPLAY_NAME,
    )
    return (
        response.source_file_group_id,
        response.group_sha256 or "",
        group_validation,
        {
            "state": response.state,
            "validation_state": response.validation_state,
            "files": len(response.files),
            "duplicate_warning": response.duplicate_warning,
        },
    )


# --- step 4: match set ------------------------------------------------------


async def build_match_set(engine: AsyncEngine, group_id: str) -> str:
    """Create a custom-profile match set on the Sejong group, validate, activate."""
    repo = SourceMatchSetRepository(engine)
    detail = await repo.create_match_set(
        SourceMatchSetCreateRequest(
            name=MATCH_SET_NAME,
            description="T-213 small Sejong live validation",
            profile="custom",
            items=(
                SourceMatchSetItemRequest(
                    category=CATEGORY,
                    role="build_required",
                    source_file_group_id=group_id,
                    required=True,
                    effective_yyyymm=ELECTRONIC_MAP_YYYYMM,
                    load_order=1,
                    metadata={},
                ),
            ),
            metadata={"runbook": RUN_MARKER},
        ),
        actor=ACTOR,
    )
    msid = detail.match_set.source_match_set_id

    validate = await repo.validate_match_set(msid, actor=ACTOR)
    if not validate.ok:
        raise RuntimeError(f"match-set validate rejected: {validate.reasons}")
    print(
        f"  validate: action={validate.action} state={validate.state} "
        f"hash={validate.source_set_hash[:16]}…"
    )

    activate = await repo.activate_match_set(msid, actor=ACTOR)
    print(
        f"  activate: state={activate.state} "
        f"retired={activate.retired_match_set_id} "
        f"hash={activate.source_set_hash[:16]}…"
    )
    return msid


# --- step 5: rebuild bridge + REAL loader -----------------------------------


def _materialize_staging(zip_path: Path, staging_dir: str) -> tuple[Path, Path]:
    """Extract the Sejong ZIP into the staging dir the rebuild payload points at.

    The polygons loader's ``discover_sido_dataset`` expects the 시도 folder to
    contain exactly one numeric SIG subdir. The ZIP members are ``36000/TL_*``,
    so extracting under ``<staging>/<category>/<시도명>/`` yields
    ``<staging>/<category>/세종특별자치시/36000/TL_*.shp`` and we pass the 시도 dir.

    Returns ``(resolved_staging_root, materialized_sido_dir)``. Kept fully sync
    so the async caller never touches ``pathlib`` filesystem methods.
    """
    staging_root = Path(staging_dir).resolve()
    category_dir = staging_root / CATEGORY / SEJONG_SIDO_NAME
    category_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(category_dir)
    return staging_root, category_dir


async def rebuild_and_load(
    engine: AsyncEngine, msid: str, zip_path: Path
) -> tuple[dict, int, float]:
    """Assemble the rebuild batch payload, then run the REAL polygons loader.

    Returns ``(batch_payload, layer_count, load_seconds)``.
    """
    service = SourceRebuildService(engine)
    plan, _stale = await service.prepare_rebuild(msid)
    batch_payload = plan.batch_payload

    # The assembled full_load_batch child for electronic_map → shp_polygons_load.
    shp_children = [
        c for c in batch_payload["children"] if c["kind"] == "shp_polygons_load"
    ]
    if not shp_children:
        raise RuntimeError("rebuild plan produced no shp_polygons_load child")
    child = shp_children[0]
    child_payload = child["payload"]

    # Materialize the staging dir the child payload points at, then drive the
    # SAME loader the shp_polygons_load handler invokes (app.py `shp` handler).
    staging_root, sido_dir = _materialize_staging(
        zip_path, batch_payload["staging_dir"]
    )
    source_yyyymm = child_payload.get("source_yyyymm")

    started = time.monotonic()
    layer_count = await load_shp_polygons(
        engine,
        sido_dir,
        mode="full",
        source_yyyymm=source_yyyymm,
        analyze=True,
    )
    elapsed = time.monotonic() - started
    return (
        {
            "staging_dir": str(staging_root),
            "materialized_sido_dir": str(sido_dir),
            "child_payload": child_payload,
            "source_set": batch_payload.get("source_set"),
        },
        layer_count,
        elapsed,
    )


# --- step 6: verify + snapshot FK -------------------------------------------


async def record_snapshot_fk(
    engine: AsyncEngine, msid: str, source_set: dict, row_counts: dict
) -> str:
    """Record ops.dataset_snapshots with the source_match_set_id 정본 FK.

    Exercises the rebuild-success snapshot linkage the rebuild handler would
    write (dataset_snapshots.source_match_set_id). Returns the snapshot id.
    """
    from uuid import uuid4

    repo = SourceMatchSetRepository(engine)
    detail = await repo.get_match_set(msid)
    source_set_hash = detail.match_set.source_set_hash or (64 * "0")

    snapshot_id = str(uuid4())
    tagged_source_set = {"runbook": RUN_MARKER, **(source_set or {})}
    async with engine.begin() as conn:
        pg_version = await conn.scalar(text("SHOW server_version"))
        postgis_version = await conn.scalar(text("SELECT postgis_lib_version()"))
        await conn.execute(
            _json_text(
                """
INSERT INTO ops.dataset_snapshots
  (dataset_snapshot_id, state, source_set, source_set_hash, postgres_version,
   postgis_version, row_counts, source_match_set_id, created_at, validated_at)
VALUES
  (:id, 'validated', :source_set, :hash, :pgv, :postgisv, :rows, :msid,
   now(), now())
""",
                "source_set",
                "rows",
            ),
            {
                "id": snapshot_id,
                "source_set": tagged_source_set,
                "hash": source_set_hash,
                "pgv": str(pg_version),
                "postgisv": str(postgis_version),
                "rows": row_counts,
                "msid": msid,
            },
        )
    return snapshot_id


async def verify(engine: AsyncEngine) -> dict[str, int]:
    counts: dict[str, int] = {}
    async with engine.connect() as conn:
        for table in SERVING_TABLES:
            counts[table] = int(await conn.scalar(text(f"SELECT count(*) FROM {table}")))
    return counts


async def sample_rows(engine: AsyncEngine) -> dict[str, dict]:
    samples: dict[str, dict] = {}
    queries = {
        "tl_spbd_buld_polygon": (
            "SELECT bd_mgt_sn, sig_cd, buld_mnnm, buld_slno, "
            "ST_GeometryType(geom) AS gtype, ST_SRID(geom) AS srid "
            "FROM tl_spbd_buld_polygon LIMIT 1"
        ),
        "tl_sprd_manage": (
            "SELECT sig_cd, rds_man_no, rn_cd, ST_GeometryType(geom) AS gtype, "
            "ST_SRID(geom) AS srid FROM tl_sprd_manage LIMIT 1"
        ),
        "tl_sprd_rw": (
            "SELECT sig_cd, rw_sn, rds_man_no, ST_GeometryType(geom) AS gtype, "
            "ST_SRID(geom) AS srid FROM tl_sprd_rw LIMIT 1"
        ),
        "tl_sprd_intrvl": (
            "SELECT sig_cd, rds_man_no, bsi_int_sn FROM tl_sprd_intrvl LIMIT 1"
        ),
    }
    async with engine.connect() as conn:
        for table, query in queries.items():
            row = (await conn.execute(text(query))).mappings().first()
            samples[table] = dict(row) if row else {}
    return samples


async def verify_snapshot_fk(engine: AsyncEngine, snapshot_id: str, msid: str) -> bool:
    async with engine.connect() as conn:
        linked = await conn.scalar(
            text(
                "SELECT source_match_set_id FROM ops.dataset_snapshots "
                "WHERE dataset_snapshot_id = :id"
            ),
            {"id": snapshot_id},
        )
    return str(linked) == str(msid)


# --- orchestration ----------------------------------------------------------


async def run(dsn: str, zip_path: Path, *, keep: bool) -> int:
    archive_size = _archive_size(zip_path)

    engine = make_async_engine(Settings(pg_dsn=dsn))
    overall_start = time.monotonic()
    try:
        async with engine.connect() as conn:
            db = await conn.scalar(text("SELECT current_database()"))
            postgis = await conn.scalar(text("SELECT postgis_lib_version()"))
        print(f"[0] live DB = {db!r}  PostGIS = {postgis}")
        print(f"    archive = {zip_path}  ({archive_size:,} bytes)")

        print("[1] apply schema (idempotent) + cleanup prior runbook rows")
        await apply_schema(engine)
        await cleanup(engine)

        print("[2] register Sejong electronic_map via the new pipeline")
        reg_start = time.monotonic()
        group_id, group_sha256, gv, reg = await register_sejong(engine, zip_path)
        print(
            f"    group_id={group_id}  state={reg['state']} "
            f"validation_state={reg['validation_state']} files={reg['files']}"
        )
        print(f"    structure outcome={gv.outcome}  group_sha256={group_sha256}")
        print(f"    register took {time.monotonic() - reg_start:.2f}s")

        print("[3] match-set (custom profile): create → validate → activate")
        msid = await build_match_set(engine, group_id)
        print(f"    source_match_set_id={msid}")

        print("[4] rebuild bridge → assemble full_load_batch → REAL polygons loader")
        bridge, layer_count, load_secs = await rebuild_and_load(engine, msid, zip_path)
        print(f"    staging_dir={bridge['staging_dir']}")
        print(
            "    assembled child: kind=shp_polygons_load "
            f"path={bridge['child_payload']['path']} "
            f"group_sha256={bridge['child_payload'].get('group_sha256', '')[:16]}…"
        )
        print(f"    loader returned {layer_count} layers in {load_secs:.2f}s")

        print("[5] verify serving SHP table row counts")
        counts = await verify(engine)
        for table, n in counts.items():
            print(f"    {table:<26} {n:>10,}")

        print("[6] sample rows")
        samples = await sample_rows(engine)
        for table, row in samples.items():
            print(f"    {table}: {row}")

        print("[7] record + verify dataset_snapshot.source_match_set_id 정본 FK")
        snapshot_id = await record_snapshot_fk(
            engine, msid, bridge.get("source_set") or {}, counts
        )
        fk_ok = await verify_snapshot_fk(engine, snapshot_id, msid)
        print(f"    dataset_snapshot_id={snapshot_id}  source_match_set_id linked={fk_ok}")

        total_rows = sum(counts.values())
        print()
        print(
            f"RESULT: {total_rows:,} serving SHP rows loaded for 세종 across "
            f"{len([c for c in counts.values() if c])} non-empty tables; "
            f"group_sha256={group_sha256[:16]}…; "
            f"snapshot FK linked={fk_ok}; "
            f"total {time.monotonic() - overall_start:.1f}s"
        )
        if total_rows <= 0:
            print("FAIL: no serving rows loaded")
            return 1
        if not fk_ok:
            print("FAIL: dataset_snapshot.source_match_set_id not linked")
            return 1
        print("OK")

        if not keep:
            print("[8] cleanup (--keep to retain rows + staging for inspection)")
            await cleanup(engine)
            _remove_staging(bridge["staging_dir"])
        return 0
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn",
        default=os.getenv("KTG_TEST_PG_DSN", DEFAULT_DSN),
        help="async SQLAlchemy DSN for the live PostGIS DB",
    )
    parser.add_argument(
        "--zip",
        default=os.getenv("KTG_SEJONG_ZIP", DEFAULT_ZIP),
        help="path to the real 세종특별자치시 electronic_map ZIP",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="keep the registry rows + serving data after a successful run",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.dsn, Path(args.zip), keep=args.keep)))


if __name__ == "__main__":
    main()
