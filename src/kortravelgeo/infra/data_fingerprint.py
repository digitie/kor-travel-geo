"""Serving-content fingerprint behind the dataset ``data_token`` (T-325a, ADR-069 D1~D5).

The fingerprint is a function of what the v2 responses actually read, not of the release row:
an activation that leaves the served data unchanged (manual rebuild, restore of the same
backup, rollback) keeps the fingerprint, while a daily delta or a standalone auxiliary-table
load changes it.

Which tables are hashed is *derived*, not chosen: ``DATA_FINGERPRINT_TABLES`` must equal the
``FROM``/``JOIN`` set of the five v2 infra repos minus ``DATA_FINGERPRINT_ALLOWLIST`` — the lint
``tests/unit/test_data_fingerprint_covers_serving_tables.py`` pins that equality both ways.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

_LOGGER = logging.getLogger(__name__)

#: Statement timeout for the fingerprint SELECT (ADR-069 D5). Applied with ``SET LOCAL`` inside
#: a savepoint that is always rolled back, so the caller's own timeout comes back afterwards.
#: 30 min (was 10 min, owner decision 2026-10-18): the odroid quiet measurement is 240 s, only
#: 2.5x under 10 min; contention slowed the link UPDATE >15x there, and a timeout fails open to a
#: NULL data_token that consumers must treat as "undecidable" (G-01 follow-up c).
DATA_FINGERPRINT_STATEMENT_TIMEOUT = "30min"

#: Columns never hashed (ADR-069 D2): load metadata, and the surrogate key re-assigned on every
#: reload (``postal_bulk_delivery.bulk_id``). Either would make an identical reload look changed.
EXCLUDED_COLUMNS: frozenset[str] = frozenset(
    {"source_file", "source_yyyymm", "loaded_at", "refreshed_at", "bulk_id"}
)


@dataclass(frozen=True, slots=True)
class FingerprintTable:
    """How one serving table is serialized into its per-row hash input (ADR-069 D1~D3).

    Columns are listed explicitly (ADR-069 D1 lever 1, taken after the 2026-10-13 prod dry-run:
    ``to_jsonb(row)`` serialized every polygon to GeoJSON before dropping it and timed out at
    10 min). The row hash input is ``ROW(columns)::text`` plus the geometry parts below. A new
    column is therefore NOT followed automatically — the unit lint and the integration schema
    check pin each list to the table's real columns minus :data:`EXCLUDED_COLUMNS`.

    - ``columns`` — non-geometry columns, hashed through the record text form.
    - ``point_columns`` — exact: ``md5(ST_AsBinary(col))``.
    - ``summary_columns`` — polygons/lines: ``ST_NPoints|Box2D`` summary (D3; a boundary move
      that keeps vertex count and bbox is a documented blind spot).
    - ``dropped_columns`` — not hashed, with no replacement (``mv_geocode_target.pt_4326`` is an
      ``ST_Transform`` product of ``pt_5179`` and would change on a PROJ/PostGIS upgrade alone).
    """

    name: str
    columns: tuple[str, ...]
    point_columns: tuple[str, ...] = ()
    summary_columns: tuple[str, ...] = ()
    dropped_columns: tuple[str, ...] = ()

    @property
    def accounted_columns(self) -> frozenset[str]:
        """Every column this spec decides about (hashed, summarized, or dropped)."""
        return frozenset(
            (*self.columns, *self.point_columns, *self.summary_columns, *self.dropped_columns)
        )


_SCCO = ("geom",)

#: ADR-069 D2 — the tables the v2 responses are built from (head 2026-10-13; 8 since the
#: 2026-10-18 amendment moved the derived ``region_radius_parts`` to the allow-list). Derived
#: from every ``infra/*_repo.py`` not on the non-v2 allow-list — ``postal_bulk_delivery`` and
#: ``tl_kodis_bas`` are read only by the v1 ``zip_repo`` and are therefore not hashed.
DATA_FINGERPRINT_TABLE_SPECS: tuple[FingerprintTable, ...] = (
    FingerprintTable(
        "mv_geocode_target",
        columns=(
            "bd_mgt_sn", "rncode_full", "rn", "rn_nrm", "buld_mnnm", "buld_slno", "buld_se_cd",
            "buld_nm", "buld_nm_nrm", "sigungu_buld_nm", "sigungu_buld_nm_nrm", "bjd_cd",
            "adm_cd", "adm_kor_nm", "mntn_yn", "lnbr_mnnm", "lnbr_slno", "zip_no", "si_nm",
            "sgg_nm", "emd_nm", "li_nm", "pnu", "pt_source",
        ),
        point_columns=("pt_5179",),
        dropped_columns=("pt_4326",),
    ),
    FingerprintTable(
        "tl_scco_ctprvn", columns=("ctprvn_cd", "ctp_kor_nm"), summary_columns=_SCCO
    ),
    FingerprintTable("tl_scco_emd", columns=("emd_cd", "emd_kor_nm"), summary_columns=_SCCO),
    FingerprintTable("tl_scco_li", columns=("li_cd", "li_kor_nm"), summary_columns=_SCCO),
    FingerprintTable("tl_scco_sig", columns=("sig_cd", "sig_kor_nm"), summary_columns=_SCCO),
    FingerprintTable(
        "tl_spbd_buld_polygon",
        columns=(
            "bd_mgt_sn", "sig_cd", "emd_cd", "li_cd", "bjd_cd", "rds_sig_cd", "rn_cd",
            "rncode_full", "buld_se_cd", "buld_mnnm", "buld_slno",
        ),
        summary_columns=_SCCO,
    ),
    FingerprintTable(
        "tl_sppn_makarea",
        columns=(
            "sig_cd", "makarea_id", "ntfc_yn", "makarea_nm", "ntfc_de", "mvm_res_cd",
            "mvmn_resn", "opert_de", "makarea_ar", "mvmn_desc",
        ),
        summary_columns=_SCCO,
    ),
    FingerprintTable(
        "tl_sprd_manage",
        columns=("sig_cd", "rds_man_no", "rn_cd", "rncode_full", "rn"),
        summary_columns=_SCCO,
    ),
)

DATA_FINGERPRINT_TABLES: frozenset[str] = frozenset(t.name for t in DATA_FINGERPRINT_TABLE_SPECS)

#: Tables the v2 repos read that are deliberately NOT hashed, with the reason (ADR-069 D2).
DATA_FINGERPRINT_ALLOWLIST: Mapping[str, str] = {
    "mv_geocode_text_search": (
        "derived from the same sources as mv_geocode_target by the same REFRESH; its "
        "definition only changes with a code release"
    ),
    "region_radius_parts": (
        "derived on every refresh from tl_scco_ctprvn/tl_scco_sig/tl_scco_emd (all hashed, geometry "
        "as the D3 summary) by ST_Subdivide + row_number() over ST_Area; its parts are rebuild "
        "noise that moved data_token with unchanged sources (ADR-069 amendment 2026-10-18). "
        "Relies on ADR-043: the parts are rebuilt in the same release as their sources"
    ),
}


def _row_expression(spec: FingerprintTable) -> str:
    parts = ["ROW(" + ", ".join(f"t.{col}" for col in spec.columns) + ")::text"]
    parts += [f"coalesce(md5(ST_AsBinary(t.{col})), '')" for col in spec.point_columns]
    parts += [
        f"concat(ST_NPoints(t.{col}), '|', Box2D(t.{col})::text)" for col in spec.summary_columns
    ]
    return " || '|' || ".join(parts)


def _build_fingerprint_sql(specs: tuple[FingerprintTable, ...]) -> str:
    branches = [
        f"  SELECT '{spec.name}'::text AS table_name,\n"
        f"         (SELECT sum(hashtextextended({_row_expression(spec)}, 0)::numeric)\n"
        f"            FROM public.{spec.name} t) AS h"
        for spec in sorted(specs, key=lambda s: s.name)
    ]
    union = "\n  UNION ALL\n".join(branches)
    return (
        "WITH parts AS MATERIALIZED (\n"
        f"{union}\n"
        "),\n"
        "fp AS (\n"
        "  SELECT md5(string_agg(table_name || ':' || coalesce(h, 0)::text, ','"
        " ORDER BY table_name COLLATE \"C\")) AS fingerprint\n"
        "    FROM parts\n"
        ")\n"
        "SELECT p.table_name, p.h, fp.fingerprint\n"
        "  FROM parts p CROSS JOIN fp\n"
        " ORDER BY p.table_name COLLATE \"C\""
    )


#: The one fingerprint query — used by the activation helper and by
#: ``ktgctl serving fingerprint-active [--dry-run]`` alike (ADR-069 D9: measured = accepted).
DATA_FINGERPRINT_SQL = _build_fingerprint_sql(DATA_FINGERPRINT_TABLE_SPECS)


@dataclass(frozen=True, slots=True)
class DataFingerprintResult:
    """Outcome of one fingerprint attempt. ``fingerprint is None`` ⇔ ``error_code`` is set."""

    fingerprint: str | None
    table_hashes: Mapping[str, str | None]
    elapsed_s: float
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class FingerprintAttempt:
    """A fingerprint computed for an activation, plus the active release seen before the scan.

    The activation helper compares ``active_release_id_before`` with the active release it reads
    under the activation lock: if another activation committed in between, this scan may predate
    that release's data and is discarded (``superseded_during_scan``, ADR-069 구현 기록).
    """

    result: DataFingerprintResult
    active_release_id_before: str | None


_ACTIVE_RELEASE_ID_SQL = """
SELECT serving_release_id::text
  FROM ops.serving_releases
 WHERE state = 'active'
 ORDER BY activated_at DESC NULLS LAST, created_at DESC
 LIMIT 1
"""

_TABLE_COLUMNS_SQL = """
SELECT c.relname::text AS table_name, array_agg(a.attname::text) AS columns
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
 WHERE n.nspname = 'public' AND c.relname = ANY(CAST(:names AS name[]))
 GROUP BY c.relname
"""


def schema_drift(actual: Mapping[str, Iterable[str]]) -> str | None:
    """First fingerprinted table whose live columns differ from its spec, else ``None``.

    A column the spec does not account for (neither hashed, summarized, dropped nor excluded)
    would silently stay out of the token; a spec column that no longer exists would fail the
    SQL. Either way the fingerprint is not trustworthy, so the caller fails open."""
    for spec in sorted(DATA_FINGERPRINT_TABLE_SPECS, key=lambda s: s.name):
        columns = actual.get(spec.name)
        if columns is None or set(columns) - EXCLUDED_COLUMNS != spec.accounted_columns:
            return spec.name
    return None


def _error_code(exc: BaseException) -> str:
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate == "57014":  # query_canceled — statement_timeout
        return "timeout"
    return f"exception:{type(orig or exc).__name__}"


class _SchemaDriftError(Exception):
    def __init__(self, table: str) -> None:
        super().__init__(table)
        self.table = table


async def compute_data_fingerprint(
    conn: Any, *, statement_timeout: str | None = None
) -> DataFingerprintResult:
    """Run :data:`DATA_FINGERPRINT_SQL` on ``conn`` without disturbing its transaction.

    Fail-open (ADR-069 D5): the SELECT runs inside a savepoint with its own
    ``SET LOCAL statement_timeout``; the savepoint is rolled back on success *and* failure, so
    a failure leaves the outer transaction usable and the caller's ``statement_timeout`` is in
    force again for whatever it runs next. Errors come back as ``error_code`` (``timeout`` |
    ``schema_drift:<table>`` | ``exception:<ClassName>``), never raised. Before scanning, the
    live columns of every fingerprinted table are checked against the specs.
    """

    timeout = statement_timeout or DATA_FINGERPRINT_STATEMENT_TIMEOUT
    started = time.monotonic()
    savepoint = await conn.begin_nested()
    try:
        await conn.execute(text(f"SET LOCAL statement_timeout = '{timeout}'"))
        live = (
            await conn.execute(
                text(_TABLE_COLUMNS_SQL), {"names": sorted(DATA_FINGERPRINT_TABLES)}
            )
        ).mappings().all()
        drifted = schema_drift({str(row["table_name"]): row["columns"] for row in live})
        if drifted is not None:
            raise _SchemaDriftError(drifted)
        rows = (await conn.execute(text(DATA_FINGERPRINT_SQL))).mappings().all()
    except Exception as exc:  # fail-open by design (ADR-069 D5)
        await savepoint.rollback()
        code = (
            f"schema_drift:{exc.table}" if isinstance(exc, _SchemaDriftError) else _error_code(exc)
        )
        _LOGGER.warning("data fingerprint failed (%s); activation proceeds without it", code)
        return DataFingerprintResult(
            fingerprint=None,
            table_hashes={},
            elapsed_s=time.monotonic() - started,
            error_code=code,
        )
    await savepoint.rollback()
    fingerprint = str(rows[0]["fingerprint"]) if rows and rows[0]["fingerprint"] else None
    return DataFingerprintResult(
        fingerprint=fingerprint,
        table_hashes={
            str(row["table_name"]): (None if row["h"] is None else str(row["h"])) for row in rows
        },
        elapsed_s=time.monotonic() - started,
        error_code=None if fingerprint else "exception:EmptyResult",
    )


async def active_release_id(conn: Any) -> str | None:
    value = await conn.scalar(text(_ACTIVE_RELEASE_ID_SQL))
    return None if value is None else str(value)


async def fingerprint_for_activation(
    conn: Any, *, statement_timeout: str | None = None
) -> FingerprintAttempt:
    """Read the active release, then fingerprint — the pair the activation helper re-checks
    under its lock. Run it BEFORE any lock the scan must not hold (the activation lock,
    ``publication_guard``'s ``load_jobs`` row lock)."""

    before = await active_release_id(conn)
    result = await compute_data_fingerprint(conn, statement_timeout=statement_timeout)
    return FingerprintAttempt(result=result, active_release_id_before=before)
