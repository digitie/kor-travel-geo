"""T-233 post-restore data reconcile.

After a restore, compares the backup ``manifest`` against the restored database —
per-object row counts (``ROW_COUNT_OBJECTS``), MV non-emptiness/parity, ``sppn``
zone count, ``pt_source`` distribution, and source-set reference months — so a
silent partial restore is caught instead of looking successful. ``run_restore_job``
records the result in the restore-log manifest (mismatch = warning by default).

``diff_restore_row_counts`` is pure so the comparison policy is unit-tested without
a database; legacy backups without ``row_counts`` (or a restored DB missing the MVs)
degrade gracefully.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from kortravelgeo.dto.admin import RestoreReconcileResult, RestoreRowCountDiff
from kortravelgeo.infra.backup import (
    ROW_COUNT_OBJECTS,
    collect_row_counts,
    database_name_from_dsn,
)


def diff_restore_row_counts(
    expected: Mapping[str, int] | None,
    actual: Mapping[str, int],
) -> list[RestoreRowCountDiff]:
    """Per-object row-count diff. Unknown ``expected`` (legacy) is not a mismatch."""
    diffs: list[RestoreRowCountDiff] = []
    for name in ROW_COUNT_OBJECTS:
        exp = expected.get(name) if expected else None
        act = int(actual.get(name, 0))
        match = exp is None or exp == act
        diffs.append(RestoreRowCountDiff(object=name, expected=exp, actual=act, match=match))
    return diffs


async def compare_restore_against_manifest(
    manifest: Mapping[str, Any],
    target_dsn: str,
) -> RestoreReconcileResult:
    expected = manifest.get("row_counts") or {}
    manifest_source_set = manifest.get("source_set") or {}
    warnings: list[str] = []
    pt_source_distribution: dict[str, int] | None = None
    engine = create_async_engine(target_dsn)
    try:
        async with engine.connect() as conn:
            actual = await collect_row_counts(conn)
            mv_target = actual.get("mv_geocode_target")
            if mv_target:
                rows = (
                    await conn.execute(
                        text(
                            "SELECT coalesce(pt_source, '(null)') AS source, "
                            "count(*)::bigint AS n FROM mv_geocode_target GROUP BY pt_source"
                        )
                    )
                ).mappings().all()
                pt_source_distribution = {r["source"]: int(r["n"]) for r in rows}
    finally:
        await engine.dispose()

    mv_target = actual.get("mv_geocode_target")
    mv_text = actual.get("mv_geocode_text_search")
    sppn = actual.get("tl_sppn_makarea")
    diffs = diff_restore_row_counts(expected, actual)

    mv_nonempty_ok = bool(mv_target and mv_target > 0)
    if not mv_nonempty_ok:
        warnings.append("mv_geocode_target is empty or missing")
    if mv_target is not None and mv_text is not None and mv_target != mv_text:
        warnings.append(
            f"mv_geocode_target ({mv_target}) != mv_geocode_text_search ({mv_text})"
        )
    if not expected:
        warnings.append("manifest has no row_counts; row-count reconcile skipped")
    mismatched = [d.object for d in diffs if not d.match]
    if mismatched:
        warnings.append(f"row_count mismatch: {', '.join(mismatched)}")

    source_set_yyyymm = manifest_source_set.get("yyyymm_by_kind")
    row_ok = all(d.match for d in diffs)
    ok = row_ok and (mv_nonempty_ok or not expected)
    return RestoreReconcileResult(
        ok=ok,
        target_database=database_name_from_dsn(target_dsn),
        row_count_diffs=tuple(diffs),
        mv_geocode_target_rows=mv_target,
        mv_geocode_text_search_rows=mv_text,
        mv_nonempty_ok=mv_nonempty_ok,
        sppn_rows=sppn,
        pt_source_distribution=pt_source_distribution,
        source_set_yyyymm=source_set_yyyymm if isinstance(source_set_yyyymm, dict) else None,
        warnings=tuple(warnings),
    )
