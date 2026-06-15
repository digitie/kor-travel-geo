"""Run the T-125 C11 serving preflight without changing active serving objects."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.loaders.augment_harness import (
    ShapeStagingSpec,
    StagingColumn,
    StagingKeyIndexSpec,
    analyze_table_sql,
    copy_zip_shape_layer_to_staging,
    recreate_shape_staging_table,
    staging_key_index_sql,
)
from kortravelgeo.loaders.building_shape_bundle import (
    ADDRESS_BUNDLE_LAYER,
    BUNDLE_ENTRANCE_LAYER,
)
from kortravelgeo.loaders.consistency import run_case
from kortravelgeo.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

type SidoCode = str

ADDRESS_TABLE = "_ktg_t125_c11_bundle_address"
ENTRANCE_TABLE = "_ktg_t125_c11_bundle_entrance"
CANDIDATE_RAW_TABLE = "_ktg_t125_c11_candidate_raw"
CANDIDATE_BEST_TABLE = "_ktg_t125_c11_candidate_best"

DEFAULT_SOURCE_YYYYMM = "202604"
DEFAULT_OUTPUT_DIR = Path("artifacts") / "t125-c11-serving-preflight"
DEFAULT_SIDO_CODES: tuple[SidoCode, ...] = (
    "11",
    "26",
    "27",
    "28",
    "29",
    "30",
    "31",
    "36",
    "41",
    "43",
    "44",
    "46",
    "47",
    "48",
    "50",
    "51",
    "52",
)
SIDO_CODE_TO_NAME: dict[SidoCode, str] = {
    "11": "서울특별시",
    "26": "부산광역시",
    "27": "대구광역시",
    "28": "인천광역시",
    "29": "광주광역시",
    "30": "대전광역시",
    "31": "울산광역시",
    "36": "세종특별자치시",
    "41": "경기도",
    "43": "충청북도",
    "44": "충청남도",
    "46": "전라남도",
    "47": "경상북도",
    "48": "경상남도",
    "50": "제주특별자치도",
    "51": "강원특별자치도",
    "52": "전북특별자치도",
}


def address_staging_spec(table_name: str = ADDRESS_TABLE) -> ShapeStagingSpec:
    return ShapeStagingSpec(
        table_name=table_name,
        columns=(
            StagingColumn("sig_cd", source_field="SIG_CD"),
            StagingColumn("bul_man_no", "bigint", "BUL_MAN_NO"),
            StagingColumn("eqb_man_sn", "bigint", "EQB_MAN_SN"),
            StagingColumn("adr_mng_no", source_field="ADR_MNG_NO"),
            StagingColumn("rn_cd", source_field="RN_CD"),
            StagingColumn("buld_se_cd", source_field="BULD_SE_CD"),
            StagingColumn("buld_mnnm", "integer", "BULD_MNNM"),
            StagingColumn("buld_slno", "integer", "BULD_SLNO"),
        ),
        geometry_type="Geometry",
    )


def entrance_staging_spec(table_name: str = ENTRANCE_TABLE) -> ShapeStagingSpec:
    return ShapeStagingSpec(
        table_name=table_name,
        columns=(
            StagingColumn("sig_cd", source_field="SIG_CD"),
            StagingColumn("bul_man_no", "bigint", "BUL_MAN_NO"),
            StagingColumn("ent_man_no", "bigint", "ENT_MAN_NO"),
            StagingColumn("eqb_man_sn", "bigint", "EQB_MAN_SN"),
            StagingColumn("entrc_se", source_field="ENTRC_SE"),
        ),
        geometry_type="Point",
    )


def candidate_table_sql() -> tuple[str, str]:
    raw_sql = f"""
DROP TABLE IF EXISTS {CANDIDATE_RAW_TABLE};
CREATE TABLE {CANDIDATE_RAW_TABLE} AS
SELECT
    a.adr_mng_no AS bd_mgt_sn,
    e.sig_cd,
    e.bul_man_no,
    e.ent_man_no,
    e.eqb_man_sn,
    e.entrc_se,
    a.rn_cd,
    a.buld_se_cd,
    a.buld_mnnm,
    a.buld_slno,
    e.geom AS candidate_pt_5179
FROM {ENTRANCE_TABLE} AS e
JOIN {ADDRESS_TABLE} AS a
  ON a.sig_cd = e.sig_cd
 AND a.bul_man_no = e.bul_man_no
 AND a.eqb_man_sn = e.eqb_man_sn
WHERE a.adr_mng_no IS NOT NULL
  AND a.adr_mng_no <> ''
  AND e.geom IS NOT NULL;

CREATE INDEX {CANDIDATE_RAW_TABLE}_bd_idx ON {CANDIDATE_RAW_TABLE} (bd_mgt_sn);
CREATE INDEX {CANDIDATE_RAW_TABLE}_weak_idx
    ON {CANDIDATE_RAW_TABLE} (sig_cd, ent_man_no);
CREATE INDEX {CANDIDATE_RAW_TABLE}_geom_idx
    ON {CANDIDATE_RAW_TABLE} USING gist (candidate_pt_5179);
ANALYZE {CANDIDATE_RAW_TABLE};
"""
    best_sql = f"""
DROP TABLE IF EXISTS {CANDIDATE_BEST_TABLE};
CREATE TABLE {CANDIDATE_BEST_TABLE} AS
WITH ranked AS (
    SELECT
        raw.*,
        COUNT(*) OVER (PARTITION BY raw.bd_mgt_sn) AS candidates_per_bd,
        ROW_NUMBER() OVER (
            PARTITION BY raw.bd_mgt_sn
            ORDER BY
                CASE WHEN raw.entrc_se = '0' THEN 0 ELSE 1 END,
                raw.ent_man_no NULLS LAST,
                raw.sig_cd,
                raw.bul_man_no,
                raw.eqb_man_sn
        ) AS rn
    FROM {CANDIDATE_RAW_TABLE} AS raw
)
SELECT
    bd_mgt_sn,
    sig_cd,
    bul_man_no,
    ent_man_no,
    eqb_man_sn,
    entrc_se,
    rn_cd,
    buld_se_cd,
    buld_mnnm,
    buld_slno,
    candidates_per_bd,
    candidate_pt_5179
FROM ranked
WHERE rn = 1;

CREATE UNIQUE INDEX {CANDIDATE_BEST_TABLE}_bd_idx
    ON {CANDIDATE_BEST_TABLE} (bd_mgt_sn);
CREATE INDEX {CANDIDATE_BEST_TABLE}_geom_idx
    ON {CANDIDATE_BEST_TABLE} USING gist (candidate_pt_5179);
ANALYZE {CANDIDATE_BEST_TABLE};
"""
    return raw_sql, best_sql


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run T-125 C11 serving preflight validation.",
    )
    parser.add_argument("--pg-dsn", help="PostgreSQL DSN. Defaults to KTG_PG_DSN/settings.")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=_default_data_root(),
        help="Juso data root that contains unused/도로명주소 건물 도형.",
    )
    parser.add_argument(
        "--source-yyyymm",
        default=DEFAULT_SOURCE_YYYYMM,
        help="Roadaddr building shape bundle yyyymm.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for JSON/CSV/GeoJSON artifacts.",
    )
    parser.add_argument(
        "--sido",
        action="append",
        choices=DEFAULT_SIDO_CODES,
        help="Sido code to load. Defaults to all 17 codes.",
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="Reuse existing staging tables and rebuild only candidate/metrics.",
    )
    parser.add_argument(
        "--keep-staging",
        action="store_true",
        help="Keep _ktg_t125_* tables after validation.",
    )
    parser.add_argument(
        "--outlier-limit",
        type=int,
        default=500,
        help="Maximum outlier rows to write.",
    )
    return parser.parse_args()


def _default_data_root() -> Path:
    env_value = os.getenv("KTG_JUSO_DATA_ROOT")
    if env_value:
        return Path(env_value)
    wsl_root = Path("/mnt/f/dev/geodata/juso")
    if wsl_root.exists():
        return wsl_root
    return Path("F:/dev/geodata/juso")


async def main() -> None:
    args = parse_args()
    settings = get_settings()
    if args.pg_dsn:
        settings = settings.model_copy(update={"pg_dsn": args.pg_dsn})

    started_at = datetime.now(UTC)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    sido_codes: Sequence[SidoCode] = tuple(args.sido or DEFAULT_SIDO_CODES)

    engine = make_async_engine(settings)
    run_started = time.monotonic()
    summary: dict[str, Any] = {
        "task": "T-125",
        "started_at": started_at.isoformat(),
        "source_yyyymm": args.source_yyyymm,
        "data_root": str(args.data_root),
        "sido_codes": list(sido_codes),
        "tables": {
            "address": ADDRESS_TABLE,
            "entrance": ENTRANCE_TABLE,
            "candidate_raw": CANDIDATE_RAW_TABLE,
            "candidate_best": CANDIDATE_BEST_TABLE,
        },
    }
    try:
        async with engine.begin() as conn:
            await set_no_statement_timeout(conn)
            summary["database"] = await collect_database_identity(conn)

        if not args.skip_load:
            load_started = time.monotonic()
            await load_staging(engine, args.data_root, args.source_yyyymm, sido_codes)
            summary["load_seconds"] = round(time.monotonic() - load_started, 3)
        else:
            await create_t125_staging_indexes(engine)

        async with engine.begin() as conn:
            await set_no_statement_timeout(conn)
            build_started = time.monotonic()
            await rebuild_candidate_tables(conn)
            summary["candidate_build_seconds"] = round(time.monotonic() - build_started, 3)

        async with engine.begin() as conn:
            await set_no_statement_timeout(conn)
            summary["source_gate"] = await collect_source_gate(conn, args.source_yyyymm)
            summary["candidate_coverage"] = await collect_candidate_coverage(conn)
            summary["namespace_risk"] = await collect_namespace_risk(conn)
            summary["impact"] = await collect_impact_metrics(conn)
            summary["consistency"] = await collect_consistency_metrics(engine)
            summary["performance_scope"] = collect_performance_scope()
            summary["feature_flag_and_rollback"] = collect_feature_flag_scope()
            summary["exposure_policy"] = collect_exposure_policy()
            summary["outliers"] = await write_outliers(conn, output_dir, args.outlier_limit)

        summary["finished_at"] = datetime.now(UTC).isoformat()
        summary["elapsed_seconds"] = round(time.monotonic() - run_started, 3)
        summary["gate_result"] = evaluate_gate(summary)
        write_json(output_dir / "summary.json", summary)
        print(json.dumps(summary["gate_result"], ensure_ascii=False, indent=2))
    finally:
        if not args.keep_staging:
            async with engine.begin() as conn:
                await drop_work_tables(conn)
        await engine.dispose()


async def load_staging(
    engine: AsyncEngine,
    data_root: Path,
    source_yyyymm: str,
    sido_codes: Sequence[SidoCode],
) -> None:
    address_spec = address_staging_spec()
    entrance_spec = entrance_staging_spec()
    await recreate_shape_staging_table(engine, address_spec)
    await recreate_shape_staging_table(engine, entrance_spec)

    bundle_root = data_root / "unused" / "도로명주소 건물 도형" / source_yyyymm
    for sido_code in sido_codes:
        zip_path = bundle_root / f"건물도형_전체분_{SIDO_CODE_TO_NAME[sido_code]}.zip"
        if not zip_path.exists():
            raise FileNotFoundError(zip_path)
        await copy_zip_shape_layer_to_staging(
            engine,
            address_spec,
            zip_path,
            ADDRESS_BUNDLE_LAYER,
        )
        await copy_zip_shape_layer_to_staging(
            engine,
            entrance_spec,
            zip_path,
            BUNDLE_ENTRANCE_LAYER,
        )

    await create_t125_staging_indexes(engine)


async def create_t125_staging_indexes(engine: AsyncEngine) -> None:
    specs = (
        StagingKeyIndexSpec(
            ADDRESS_TABLE,
            f"{ADDRESS_TABLE}_join_idx",
            ("sig_cd", "bul_man_no", "eqb_man_sn"),
        ),
        StagingKeyIndexSpec(ADDRESS_TABLE, f"{ADDRESS_TABLE}_adr_idx", ("adr_mng_no",)),
        StagingKeyIndexSpec(
            ENTRANCE_TABLE,
            f"{ENTRANCE_TABLE}_join_idx",
            ("sig_cd", "bul_man_no", "eqb_man_sn"),
        ),
        StagingKeyIndexSpec(
            ENTRANCE_TABLE,
            f"{ENTRANCE_TABLE}_weak_idx",
            ("sig_cd", "ent_man_no"),
        ),
    )
    async with engine.begin() as conn:
        await set_no_statement_timeout(conn)
        for spec in specs:
            exists = await conn.scalar(
                text("SELECT to_regclass(:index_name)"),
                {"index_name": spec.index_name},
            )
            if exists is None:
                await conn.execute(text(staging_key_index_sql(spec)))
        for table_name in (ADDRESS_TABLE, ENTRANCE_TABLE):
            await conn.execute(text(analyze_table_sql(table_name)))


async def rebuild_candidate_tables(conn: AsyncConnection) -> None:
    await set_no_statement_timeout(conn)
    raw_sql, best_sql = candidate_table_sql()
    await conn.execute(text(raw_sql))
    await conn.execute(text(best_sql))


async def collect_database_identity(conn: AsyncConnection) -> dict[str, Any]:
    current_database = await conn.scalar(text("SELECT current_database()"))
    release_row = await conn.execute(
        text(
            """
            SELECT
                r.serving_release_id::text AS serving_release_id,
                r.dataset_snapshot_id::text AS dataset_snapshot_id,
                r.release_kind,
                r.mv_name,
                r.mv_hash,
                r.consistency_gate,
                s.source_match_set_id::text AS source_match_set_id
            FROM ops.serving_releases AS r
            JOIN ops.dataset_snapshots AS s
              ON s.dataset_snapshot_id = r.dataset_snapshot_id
            WHERE r.state = 'active'
            ORDER BY r.activated_at DESC NULLS LAST, r.created_at DESC NULLS LAST
            LIMIT 1
            """
        )
    )
    release = dict(release_row.mappings().first() or {})
    counts = await one_mapping(
        conn,
        """
        SELECT
            (SELECT COUNT(*) FROM mv_geocode_target) AS mv_geocode_target,
            (SELECT COUNT(*) FROM tl_juso_text) AS tl_juso_text,
            (SELECT COUNT(*) FROM tl_locsum_entrc) AS tl_locsum_entrc,
            (SELECT COUNT(*) FROM tl_roadaddr_entrc) AS tl_roadaddr_entrc
        """,
    )
    return {
        "current_database": current_database,
        "active_release": release,
        "row_counts": counts,
    }


async def collect_source_gate(conn: AsyncConnection, source_yyyymm: str) -> dict[str, Any]:
    rows = await list_mappings(
        conn,
        """
        SELECT table_name, source_yyyymm, row_count
        FROM (
            SELECT 'tl_juso_text' AS table_name, source_yyyymm, COUNT(*) AS row_count
            FROM tl_juso_text
            GROUP BY source_yyyymm
            UNION ALL
            SELECT 'tl_locsum_entrc', source_yyyymm, COUNT(*)
            FROM tl_locsum_entrc
            GROUP BY source_yyyymm
            UNION ALL
            SELECT 'tl_roadaddr_entrc', source_yyyymm, COUNT(*)
            FROM tl_roadaddr_entrc
            GROUP BY source_yyyymm
        ) AS source_months
        ORDER BY table_name, source_yyyymm
        """,
    )
    distinct_months = sorted(
        {row["source_yyyymm"] for row in rows if row["source_yyyymm"] is not None}
    )
    return {
        "candidate_source_yyyymm": source_yyyymm,
        "loaded_source_months": rows,
        "distinct_loaded_months": distinct_months,
        "candidate_matches_loaded_month": source_yyyymm in distinct_months,
    }


async def collect_candidate_coverage(conn: AsyncConnection) -> dict[str, Any]:
    return await one_mapping(
        conn,
        f"""
        SELECT
            (SELECT COUNT(*) FROM {ADDRESS_TABLE}) AS bundle_address_rows,
            (SELECT COUNT(*) FROM {ENTRANCE_TABLE}) AS bundle_entrance_rows,
            (SELECT COUNT(*) FROM {CANDIDATE_RAW_TABLE}) AS candidate_raw_rows,
            (SELECT COUNT(DISTINCT bd_mgt_sn) FROM {CANDIDATE_RAW_TABLE}) AS candidate_distinct_bd,
            (SELECT COUNT(*) FROM {CANDIDATE_BEST_TABLE}) AS candidate_best_rows,
            (SELECT COUNT(*) FROM mv_geocode_target) AS current_mv_rows,
            (
                SELECT COUNT(*)
                FROM mv_geocode_target AS mv
                JOIN {CANDIDATE_BEST_TABLE} AS c USING (bd_mgt_sn)
            ) AS matched_mv_candidate_rows,
            (
                SELECT COUNT(*)
                FROM mv_geocode_target AS mv
                LEFT JOIN {CANDIDATE_BEST_TABLE} AS c USING (bd_mgt_sn)
                WHERE c.bd_mgt_sn IS NULL
            ) AS current_only_rows,
            (
                SELECT COUNT(*)
                FROM {CANDIDATE_BEST_TABLE} AS c
                LEFT JOIN mv_geocode_target AS mv USING (bd_mgt_sn)
                WHERE mv.bd_mgt_sn IS NULL
            ) AS candidate_only_rows,
            (
                SELECT COUNT(*)
                FROM {CANDIDATE_RAW_TABLE}
                WHERE bd_mgt_sn IS NULL OR bd_mgt_sn = ''
            ) AS candidate_raw_without_bd_mgt_sn
        """,
    )


async def collect_namespace_risk(conn: AsyncConnection) -> dict[str, Any]:
    weak_key = await one_mapping(
        conn,
        f"""
        WITH weak AS (
            SELECT
                sig_cd,
                ent_man_no,
                COUNT(*) AS row_count,
                COUNT(DISTINCT bd_mgt_sn) AS bd_count
            FROM {CANDIDATE_RAW_TABLE}
            GROUP BY sig_cd, ent_man_no
        )
        SELECT
            COUNT(*) AS weak_key_count,
            COUNT(*) FILTER (WHERE row_count > 1) AS duplicate_weak_key_count,
            COUNT(*) FILTER (WHERE bd_count > 1) AS weak_key_to_multiple_bd_count,
            COALESCE(MAX(row_count), 0) AS max_rows_per_weak_key,
            COALESCE(MAX(bd_count), 0) AS max_bd_per_weak_key
        FROM weak
        """,
    )
    candidates_per_bd = await one_mapping(
        conn,
        f"""
        WITH per_bd AS (
            SELECT bd_mgt_sn, COUNT(*) AS candidate_count
            FROM {CANDIDATE_RAW_TABLE}
            GROUP BY bd_mgt_sn
        )
        SELECT
            COUNT(*) AS bd_count,
            COUNT(*) FILTER (WHERE candidate_count > 1) AS bd_with_multiple_candidates,
            COALESCE(MAX(candidate_count), 0) AS max_candidates_per_bd,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY candidate_count) AS p50_candidates_per_bd,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY candidate_count) AS p95_candidates_per_bd,
            percentile_cont(0.99) WITHIN GROUP (ORDER BY candidate_count) AS p99_candidates_per_bd
        FROM per_bd
        """,
    )
    samples = await list_mappings(
        conn,
        f"""
        SELECT sig_cd, ent_man_no, COUNT(*) AS row_count, COUNT(DISTINCT bd_mgt_sn) AS bd_count
        FROM {CANDIDATE_RAW_TABLE}
        GROUP BY sig_cd, ent_man_no
        HAVING COUNT(DISTINCT bd_mgt_sn) > 1
        ORDER BY bd_count DESC, row_count DESC, sig_cd, ent_man_no
        LIMIT 20
        """,
    )
    return {
        "weak_key": weak_key,
        "candidates_per_bd": candidates_per_bd,
        "weak_key_to_multiple_bd_samples": samples,
    }


async def collect_impact_metrics(conn: AsyncConnection) -> dict[str, Any]:
    summary = await one_mapping(
        conn,
        f"""
        WITH matched AS MATERIALIZED (
            SELECT
                mv.bd_mgt_sn,
                mv.pt_source,
                ST_Distance(mv.pt_5179, c.candidate_pt_5179) AS distance_m
            FROM mv_geocode_target AS mv
            JOIN {CANDIDATE_BEST_TABLE} AS c USING (bd_mgt_sn)
            WHERE mv.pt_5179 IS NOT NULL
              AND c.candidate_pt_5179 IS NOT NULL
        )
        SELECT
            COUNT(*) AS matched_point_rows,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY distance_m) AS p50_m,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY distance_m) AS p95_m,
            percentile_cont(0.99) WITHIN GROUP (ORDER BY distance_m) AS p99_m,
            MAX(distance_m) AS max_m,
            COUNT(*) FILTER (WHERE distance_m > 10) AS over_10m,
            COUNT(*) FILTER (WHERE distance_m > 30) AS over_30m,
            COUNT(*) FILTER (WHERE distance_m > 100) AS over_100m,
            COUNT(*) FILTER (WHERE distance_m = 0) AS exactly_zero_m
        FROM matched
        """,
    )
    by_source = await list_mappings(
        conn,
        f"""
        WITH matched AS MATERIALIZED (
            SELECT
                mv.pt_source,
                ST_Distance(mv.pt_5179, c.candidate_pt_5179) AS distance_m
            FROM mv_geocode_target AS mv
            JOIN {CANDIDATE_BEST_TABLE} AS c USING (bd_mgt_sn)
            WHERE mv.pt_5179 IS NOT NULL
              AND c.candidate_pt_5179 IS NOT NULL
        )
        SELECT
            pt_source,
            COUNT(*) AS row_count,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY distance_m) AS p95_m,
            percentile_cont(0.99) WITHIN GROUP (ORDER BY distance_m) AS p99_m,
            MAX(distance_m) AS max_m,
            COUNT(*) FILTER (WHERE distance_m > 100) AS over_100m
        FROM matched
        GROUP BY pt_source
        ORDER BY row_count DESC, pt_source
        """,
    )
    return {"summary": summary, "by_current_pt_source": by_source}


async def collect_consistency_metrics(engine: Any) -> dict[str, Any]:
    baseline: dict[str, Any] = {}
    for code in ("C3", "C4", "C6", "C7"):
        result = await run_case(engine, code)
        baseline[code] = result.model_dump(mode="json")

    async with engine.begin() as conn:
        await set_no_statement_timeout(conn)
        candidate = {
            "C3": await collect_candidate_c3(conn),
            "C4": await collect_candidate_c4(conn),
            "C6": await collect_candidate_c6(conn),
            "C7": await collect_candidate_c7(conn),
        }
    return {"baseline_current_serving": baseline, "candidate_c11_bundle": candidate}


async def collect_candidate_c3(conn: AsyncConnection) -> dict[str, Any]:
    row = await one_mapping(
        conn,
        f"""
        WITH joined AS (
            SELECT j.bd_mgt_sn, c.bd_mgt_sn AS candidate_bd_mgt_sn
            FROM tl_juso_text AS j
            LEFT JOIN {CANDIDATE_BEST_TABLE} AS c USING (bd_mgt_sn)
        )
        SELECT
            COUNT(*) AS total_count,
            COUNT(*) FILTER (WHERE candidate_bd_mgt_sn IS NULL) AS unresolved_count,
            CASE WHEN COUNT(*) = 0 THEN 0::double precision
                 ELSE COUNT(*) FILTER (WHERE candidate_bd_mgt_sn IS NULL)
                      ::double precision / COUNT(*)
            END AS unresolved_ratio
        FROM joined
        """,
    )
    unresolved_count = int(row["unresolved_count"] or 0)
    unresolved_ratio = float(row["unresolved_ratio"] or 0)
    severity = "OK"
    if unresolved_count:
        severity = "WARN" if unresolved_ratio <= 0.05 else "ERROR"
    return {
        "case_code": "C3",
        "severity": severity,
        "count": unresolved_count,
        "metric": unresolved_ratio,
        "total_count": row["total_count"],
    }


async def collect_candidate_c4(conn: AsyncConnection) -> dict[str, Any]:
    row = await one_mapping(
        conn,
        f"""
        WITH distances AS MATERIALIZED (
            SELECT
                c.bd_mgt_sn,
                nearest.polygon_bd_mgt_sn,
                nearest.dist_m
            FROM {CANDIDATE_BEST_TABLE} AS c
            LEFT JOIN LATERAL (
                SELECT
                    p.bd_mgt_sn AS polygon_bd_mgt_sn,
                    ST_Distance(c.candidate_pt_5179, p.geom) AS dist_m
                FROM tl_spbd_buld_polygon AS p
                WHERE p.rncode_full = c.sig_cd || c.rn_cd
                  AND p.buld_se_cd IS NOT DISTINCT FROM c.buld_se_cd
                  AND p.buld_mnnm IS NOT DISTINCT FROM c.buld_mnnm
                  AND p.buld_slno IS NOT DISTINCT FROM c.buld_slno
                  AND p.geom IS NOT NULL
                ORDER BY c.candidate_pt_5179 <-> p.geom
                LIMIT 1
            ) AS nearest ON true
        )
        SELECT
            COUNT(*) AS total_count,
            COUNT(*) FILTER (WHERE polygon_bd_mgt_sn IS NULL) AS polygon_unmatched_count,
            COUNT(*) FILTER (WHERE dist_m > 500) AS over_500m_count,
            COUNT(*) FILTER (WHERE dist_m > 200) AS over_200m_count,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY dist_m) AS p95_m,
            percentile_cont(0.99) WITHIN GROUP (ORDER BY dist_m) AS p99_m,
            MAX(dist_m) AS max_m
        FROM distances
        """,
    )
    over_500m_count = int(row["over_500m_count"] or 0)
    over_200m_count = int(row["over_200m_count"] or 0)
    polygon_unmatched_count = int(row["polygon_unmatched_count"] or 0)
    severity = (
        "ERROR"
        if over_500m_count
        else "WARN"
        if over_200m_count or polygon_unmatched_count
        else "OK"
    )
    return {
        "case_code": "C4",
        "severity": severity,
        "count": over_500m_count,
        "warn_count": over_200m_count,
        "polygon_unmatched_count": polygon_unmatched_count,
        "metric": row["p95_m"],
        "total_count": row["total_count"],
        "p99_m": row["p99_m"],
        "max_m": row["max_m"],
    }


async def collect_candidate_c6(conn: AsyncConnection) -> dict[str, Any]:
    row = await one_mapping(
        conn,
        f"""
        WITH coverage AS MATERIALIZED (
            SELECT
                c.bd_mgt_sn,
                j.zip_no,
                EXISTS (
                    SELECT 1
                    FROM tl_kodis_bas AS z
                    WHERE z.bas_id = j.zip_no
                      AND z.geom IS NOT NULL
                      AND ST_Covers(z.geom, c.candidate_pt_5179)
                ) AS covered
            FROM {CANDIDATE_BEST_TABLE} AS c
            JOIN tl_juso_text AS j USING (bd_mgt_sn)
            WHERE j.zip_no IS NOT NULL
        )
        SELECT
            COUNT(*) AS total_count,
            COUNT(*) FILTER (WHERE NOT covered) AS outside_count,
            CASE WHEN COUNT(*) = 0 THEN 0::double precision
                 ELSE COUNT(*) FILTER (WHERE NOT covered)::double precision / COUNT(*)
            END AS outside_ratio
        FROM coverage
        """,
    )
    outside_count = int(row["outside_count"] or 0)
    return {
        "case_code": "C6",
        "severity": "ERROR" if outside_count else "OK",
        "count": outside_count,
        "metric": row["outside_ratio"],
        "total_count": row["total_count"],
    }


async def collect_candidate_c7(conn: AsyncConnection) -> dict[str, Any]:
    row = await one_mapping(
        conn,
        f"""
        WITH coverage AS MATERIALIZED (
            SELECT
                c.bd_mgt_sn,
                left(j.bjd_cd, 8) AS emd_cd,
                EXISTS (
                    SELECT 1
                    FROM tl_scco_emd AS e
                    WHERE e.emd_cd = left(j.bjd_cd, 8)
                      AND e.geom IS NOT NULL
                      AND ST_Covers(e.geom, c.candidate_pt_5179)
                ) AS covered
            FROM {CANDIDATE_BEST_TABLE} AS c
            JOIN tl_juso_text AS j USING (bd_mgt_sn)
            WHERE j.bjd_cd IS NOT NULL
        )
        SELECT
            COUNT(*) AS total_count,
            COUNT(*) FILTER (WHERE NOT covered) AS outside_count,
            CASE WHEN COUNT(*) = 0 THEN 0::double precision
                 ELSE COUNT(*) FILTER (WHERE NOT covered)::double precision / COUNT(*)
            END AS outside_ratio
        FROM coverage
        """,
    )
    outside_count = int(row["outside_count"] or 0)
    return {
        "case_code": "C7",
        "severity": "ERROR" if outside_count else "OK",
        "count": outside_count,
        "metric": row["outside_ratio"],
        "total_count": row["total_count"],
    }


def collect_performance_scope() -> dict[str, Any]:
    return {
        "baseline_artifacts": [
            "docs/t214-performance-benchmark.md",
            "docs/t217-t214-sql-rerun.md",
        ],
        "candidate_sql_rest_benchmark": "not_executable_before_t119_serving_flag_or_shadow_query",
        "note": (
            "T-125 builds the candidate table and measures point impact only. "
            "SQL/REST p95 regression must be rerun after T-119 adds a flag-controlled "
            "serving query path or shadow materialized view."
        ),
    }


def collect_feature_flag_scope() -> dict[str, Any]:
    return {
        "status": "not_implemented_before_t119",
        "required_t119_controls": [
            "feature flag default off",
            "no SQL/REST output change with flag off",
            "rollback by disabling flag without data reload",
            "explicit refresh path for any shadow serving object",
        ],
    }


def collect_exposure_policy() -> dict[str, Any]:
    return {
        "recommended_v1_policy": "do_not_add_top_level_fields",
        "pt_source": "keep_existing_compatible_values",
        "candidate_detail": (
            "x_extension.coord_source_detail may distinguish c11_bundle after approval"
        ),
    }


async def write_outliers(
    conn: AsyncConnection,
    output_dir: Path,
    limit: int,
) -> dict[str, Any]:
    rows = await list_mappings(
        conn,
        f"""
        WITH matched AS MATERIALIZED (
            SELECT
                mv.bd_mgt_sn,
                concat_ws(
                    ' ',
                    mv.si_nm,
                    mv.sgg_nm,
                    mv.emd_nm,
                    mv.rn,
                    CASE
                      WHEN mv.buld_mnnm IS NULL THEN NULL
                      WHEN COALESCE(mv.buld_slno, 0) > 0
                        THEN mv.buld_mnnm::text || '-' || mv.buld_slno::text
                      ELSE mv.buld_mnnm::text
                    END
                ) AS road_addr,
                mv.pt_source AS current_pt_source,
                c.ent_man_no,
                c.entrc_se,
                c.candidates_per_bd,
                ST_Distance(mv.pt_5179, c.candidate_pt_5179) AS distance_m,
                ST_X(ST_Transform(mv.pt_5179, 4326)) AS current_lon,
                ST_Y(ST_Transform(mv.pt_5179, 4326)) AS current_lat,
                ST_X(ST_Transform(c.candidate_pt_5179, 4326)) AS candidate_lon,
                ST_Y(ST_Transform(c.candidate_pt_5179, 4326)) AS candidate_lat
            FROM mv_geocode_target AS mv
            JOIN {CANDIDATE_BEST_TABLE} AS c USING (bd_mgt_sn)
            WHERE mv.pt_5179 IS NOT NULL
              AND c.candidate_pt_5179 IS NOT NULL
        )
        SELECT *
        FROM matched
        WHERE distance_m > 100
        ORDER BY distance_m DESC, bd_mgt_sn
        LIMIT :limit
        """,
        {"limit": limit},
    )
    csv_path = output_dir / "outliers_over_100m.csv"
    geojson_path = output_dir / "outliers_over_100m.geojson"
    write_csv(csv_path, rows)
    write_geojson(geojson_path, rows)
    return {
        "over_100m_csv": str(csv_path),
        "over_100m_geojson": str(geojson_path),
        "written_rows": len(rows),
        "limit": limit,
    }


def evaluate_gate(summary: Mapping[str, Any]) -> dict[str, Any]:
    impact = summary.get("impact", {}).get("summary", {})
    consistency = summary.get("consistency", {})
    candidate_cases = consistency.get("candidate_c11_bundle", {})
    source_gate = summary.get("source_gate", {})
    performance_scope = summary.get("performance_scope", {})
    feature_flag = summary.get("feature_flag_and_rollback", {})

    hard_blocks: list[str] = []
    warnings: list[str] = []
    if not source_gate.get("candidate_matches_loaded_month"):
        hard_blocks.append("candidate source yyyymm does not match loaded source months")
    if int(impact.get("over_100m") or 0) > 0:
        warnings.append("candidate point movement has >100m outliers")
    for code in ("C4", "C6", "C7"):
        case = candidate_cases.get(code, {})
        if case.get("severity") == "ERROR" and int(case.get("count") or 0) > 0:
            hard_blocks.append(f"candidate {code} has ERROR rows")
    if performance_scope.get("candidate_sql_rest_benchmark") != "passed":
        hard_blocks.append("candidate SQL/REST p95 benchmark is not executable before T-119")
    if feature_flag.get("status") != "passed":
        hard_blocks.append("feature flag and rollback rehearsal are not implemented before T-119")

    return {
        "status": "pass" if not hard_blocks else "blocked",
        "hard_blocks": hard_blocks,
        "warnings": warnings,
    }


async def drop_work_tables(conn: AsyncConnection) -> None:
    await set_no_statement_timeout(conn)
    await conn.execute(
        text(
            f"""
            DROP TABLE IF EXISTS {CANDIDATE_BEST_TABLE};
            DROP TABLE IF EXISTS {CANDIDATE_RAW_TABLE};
            DROP TABLE IF EXISTS {ENTRANCE_TABLE};
            DROP TABLE IF EXISTS {ADDRESS_TABLE};
            """
        )
    )


async def one_mapping(
    conn: AsyncConnection,
    sql: str,
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = await conn.execute(text(sql), params or {})
    row = result.mappings().one()
    return {key: normalize_json_value(value) for key, value in row.items()}


async def set_no_statement_timeout(conn: AsyncConnection) -> None:
    await conn.execute(text("SET LOCAL statement_timeout = 0"))
    await conn.execute(text("SET LOCAL max_parallel_workers_per_gather = 0"))
    await conn.execute(text("SET LOCAL work_mem = '32MB'"))


async def list_mappings(
    conn: AsyncConnection,
    sql: str,
    params: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    result = await conn.execute(text(sql), params or {})
    return [
        {key: normalize_json_value(value) for key, value in row.items()}
        for row in result.mappings()
    ]


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=json_default) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_geojson(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    features: list[dict[str, Any]] = []
    for row in rows:
        lon = row.get("candidate_lon")
        lat = row.get("candidate_lat")
        if lon is None or lat is None:
            continue
        properties = {
            key: value
            for key, value in row.items()
            if key not in {"candidate_lon", "candidate_lat"}
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": properties,
            }
        )
    payload = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def json_default(value: Any) -> Any:
    normalized = normalize_json_value(value)
    if normalized is not value:
        return normalized
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


if __name__ == "__main__":
    asyncio.run(main())
