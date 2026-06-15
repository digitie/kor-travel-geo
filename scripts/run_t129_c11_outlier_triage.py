"""Run T-129 C11 outlier triage against T-213/T-125 baseline data."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kortravelgeo.infra.engine import make_async_engine  # noqa: E402
from kortravelgeo.settings import get_settings  # noqa: E402
from scripts import run_t125_c11_serving_preflight as t125  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

PrimaryTag = Literal[
    "candidate_coordinate_error",
    "current_representative_error",
    "key_mismatch",
    "crs_or_source_coordinate_error",
    "source_month_drift_possible",
    "manual_review",
]

TASK_ID = "T-129"
TRIAGE_SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = Path("artifacts") / "t129-c11-outlier-triage"

PRIMARY_TAG_DESCRIPTIONS: dict[PrimaryTag, str] = {
    "candidate_coordinate_error": "C11 후보점이 건물/우편번호/행정구역 문맥을 벗어난 경우",
    "current_representative_error": "현행 대표점이 문맥을 벗어나고 후보점이 더 그럴듯한 경우",
    "key_mismatch": "후보 key namespace 또는 natural-key 대응이 의심되는 경우",
    "crs_or_source_coordinate_error": "경도 약 2도 이동처럼 source/CRS 좌표 오류 패턴이 강한 경우",
    "source_month_drift_possible": "후보 원천 기준월과 텍스트 기준월 차이가 주된 단서인 경우",
    "manual_review": "자동 규칙만으로 판정하기 어려운 경우",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run T-129 C11 >100m outlier triage.",
    )
    parser.add_argument("--pg-dsn", help="PostgreSQL DSN. Defaults to KTG_PG_DSN/settings.")
    parser.add_argument(
        "--pg-database",
        help="Override only the database name from the configured PostgreSQL DSN.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=t125._default_data_root(),
        help="Juso data root that contains unused/도로명주소 건물 도형.",
    )
    parser.add_argument(
        "--source-yyyymm",
        default=t125.DEFAULT_SOURCE_YYYYMM,
        help="Roadaddr building shape bundle yyyymm used by T-125.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for T-129 JSON/CSV/GeoJSON artifacts.",
    )
    parser.add_argument(
        "--sido",
        action="append",
        choices=t125.DEFAULT_SIDO_CODES,
        help="Sido code to load. Defaults to all 17 codes.",
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="Reuse existing T-125 address/entrance staging tables.",
    )
    parser.add_argument(
        "--reuse-candidate",
        action="store_true",
        help="Reuse existing T-125 candidate table without rebuilding it.",
    )
    parser.add_argument(
        "--keep-staging",
        action="store_true",
        help="Keep _ktg_t125_* tables after triage.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    settings = get_settings()
    if args.pg_dsn:
        settings = settings.model_copy(update={"pg_dsn": args.pg_dsn})
    if args.pg_database:
        url = make_url(settings.pg_dsn).set(database=args.pg_database)
        settings = settings.model_copy(update={"pg_dsn": url.render_as_string(hide_password=False)})

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    sido_codes: Sequence[str] = tuple(args.sido or t125.DEFAULT_SIDO_CODES)
    started_at = datetime.now(UTC)
    run_started = time.monotonic()

    engine = make_async_engine(settings)
    summary: dict[str, Any] = {
        "task": TASK_ID,
        "schema_version": TRIAGE_SCHEMA_VERSION,
        "started_at": started_at.isoformat(),
        "source_yyyymm": args.source_yyyymm,
        "data_root": str(args.data_root),
        "sido_codes": list(sido_codes),
    }
    try:
        async with engine.begin() as conn:
            await t125.set_no_statement_timeout(conn)
            summary["database"] = await t125.collect_database_identity(conn)

        await ensure_candidate_tables(
            engine,
            data_root=args.data_root,
            source_yyyymm=args.source_yyyymm,
            sido_codes=sido_codes,
            skip_load=bool(args.skip_load),
            reuse_candidate=bool(args.reuse_candidate),
        )

        async with engine.begin() as conn:
            await t125.set_no_statement_timeout(conn)
            rows = await collect_triage_rows(conn, candidate_source_yyyymm=args.source_yyyymm)

        tagged_rows = [tag_row(row, candidate_source_yyyymm=args.source_yyyymm) for row in rows]
        artifacts = write_artifacts(
            output_dir,
            tagged_rows,
            candidate_source_yyyymm=args.source_yyyymm,
        )
        summary.update(build_summary(tagged_rows, artifacts))
        summary["finished_at"] = datetime.now(UTC).isoformat()
        summary["elapsed_seconds"] = round(time.monotonic() - run_started, 3)
        t125.write_json(output_dir / "summary.json", summary)
        print(json.dumps(summary["primary_tag_counts"], ensure_ascii=False, indent=2))
    finally:
        if not args.keep_staging:
            async with engine.begin() as conn:
                await t125.drop_work_tables(conn)
        await engine.dispose()


async def ensure_candidate_tables(
    engine: AsyncEngine,
    *,
    data_root: Path,
    source_yyyymm: str,
    sido_codes: Sequence[str],
    skip_load: bool,
    reuse_candidate: bool,
) -> None:
    if reuse_candidate:
        async with engine.begin() as conn:
            await t125.set_no_statement_timeout(conn)
            await require_table(conn, t125.CANDIDATE_BEST_TABLE)
        return

    if not skip_load:
        await t125.load_staging(engine, data_root, source_yyyymm, sido_codes)
    else:
        await t125.create_t125_staging_indexes(engine)

    async with engine.begin() as conn:
        await t125.set_no_statement_timeout(conn)
        await t125.rebuild_candidate_tables(conn)


async def require_table(conn: AsyncConnection, table_name: str) -> None:
    exists = await conn.scalar(text("SELECT to_regclass(:table_name)"), {"table_name": table_name})
    if exists is None:
        raise RuntimeError(f"{table_name} does not exist; rerun without --reuse-candidate")


async def collect_triage_rows(
    conn: AsyncConnection,
    *,
    candidate_source_yyyymm: str,
) -> list[dict[str, Any]]:
    return await t125.list_mappings(
        conn,
        triage_sql(),
        {"candidate_source_yyyymm": candidate_source_yyyymm},
    )


def triage_sql() -> str:
    return f"""
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
            c.sig_cd AS candidate_sig_cd,
            left(mv.bd_mgt_sn, 5) AS bd_sig_cd,
            left(mv.bjd_cd, 2) AS sido_cd,
            left(mv.bjd_cd, 8) AS emd_cd,
            mv.bjd_cd,
            mv.zip_no,
            j.source_yyyymm AS text_source_yyyymm,
            CAST(:candidate_source_yyyymm AS text) AS candidate_source_yyyymm,
            c.ent_man_no,
            c.entrc_se,
            c.candidates_per_bd,
            c.rn_cd,
            c.buld_se_cd,
            c.buld_mnnm,
            c.buld_slno,
            mv.pt_5179 AS current_pt_5179,
            c.candidate_pt_5179,
            ST_Distance(mv.pt_5179, c.candidate_pt_5179) AS distance_m,
            ST_X(ST_Transform(mv.pt_5179, 4326)) AS current_lon,
            ST_Y(ST_Transform(mv.pt_5179, 4326)) AS current_lat,
            ST_X(ST_Transform(c.candidate_pt_5179, 4326)) AS candidate_lon,
            ST_Y(ST_Transform(c.candidate_pt_5179, 4326)) AS candidate_lat
        FROM mv_geocode_target AS mv
        JOIN {t125.CANDIDATE_BEST_TABLE} AS c USING (bd_mgt_sn)
        JOIN tl_juso_text AS j USING (bd_mgt_sn)
        WHERE mv.pt_5179 IS NOT NULL
          AND c.candidate_pt_5179 IS NOT NULL
    ),
    outliers AS MATERIALIZED (
        SELECT *
        FROM matched
        WHERE distance_m > 100
    )
    SELECT
        o.bd_mgt_sn,
        o.road_addr,
        o.current_pt_source,
        o.candidate_sig_cd,
        o.bd_sig_cd,
        o.sido_cd,
        o.emd_cd,
        o.bjd_cd,
        o.zip_no,
        o.text_source_yyyymm,
        o.candidate_source_yyyymm,
        o.ent_man_no,
        o.entrc_se,
        o.candidates_per_bd,
        o.distance_m,
        o.current_lon,
        o.current_lat,
        o.candidate_lon,
        o.candidate_lat,
        abs(o.candidate_lon - o.current_lon) AS abs_lon_delta,
        abs(o.candidate_lat - o.current_lat) AS abs_lat_delta,
        COALESCE(bp.polygon_count, 0) AS natural_key_polygon_count,
        CASE WHEN bp.polygon_count > 0 THEN bp.current_in_building_polygon ELSE NULL END
            AS current_in_building_polygon,
        CASE WHEN bp.polygon_count > 0 THEN bp.candidate_in_building_polygon ELSE NULL END
            AS candidate_in_building_polygon,
        bp.current_building_distance_m,
        bp.candidate_building_distance_m,
        COALESCE(zp.zip_polygon_count, 0) AS zip_polygon_count,
        CASE WHEN zp.zip_polygon_count > 0 THEN zp.current_in_zip_polygon ELSE NULL END
            AS current_in_zip_polygon,
        CASE WHEN zp.zip_polygon_count > 0 THEN zp.candidate_in_zip_polygon ELSE NULL END
            AS candidate_in_zip_polygon,
        COALESCE(ep.emd_polygon_count, 0) AS emd_polygon_count,
        CASE WHEN ep.emd_polygon_count > 0 THEN ep.current_in_emd_polygon ELSE NULL END
            AS current_in_emd_polygon,
        CASE WHEN ep.emd_polygon_count > 0 THEN ep.candidate_in_emd_polygon ELSE NULL END
            AS candidate_in_emd_polygon
    FROM outliers AS o
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS polygon_count,
            bool_or(ST_Covers(p.geom, o.current_pt_5179)) AS current_in_building_polygon,
            bool_or(ST_Covers(p.geom, o.candidate_pt_5179)) AS candidate_in_building_polygon,
            MIN(ST_Distance(o.current_pt_5179, p.geom)) AS current_building_distance_m,
            MIN(ST_Distance(o.candidate_pt_5179, p.geom)) AS candidate_building_distance_m
        FROM tl_spbd_buld_polygon AS p
        WHERE p.rncode_full = o.candidate_sig_cd || o.rn_cd
          AND p.buld_se_cd IS NOT DISTINCT FROM o.buld_se_cd
          AND p.buld_mnnm IS NOT DISTINCT FROM o.buld_mnnm
          AND p.buld_slno IS NOT DISTINCT FROM o.buld_slno
          AND p.geom IS NOT NULL
    ) AS bp ON true
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS zip_polygon_count,
            bool_or(ST_Covers(z.geom, o.current_pt_5179)) AS current_in_zip_polygon,
            bool_or(ST_Covers(z.geom, o.candidate_pt_5179)) AS candidate_in_zip_polygon
        FROM tl_kodis_bas AS z
        WHERE z.bas_id = o.zip_no
          AND z.geom IS NOT NULL
    ) AS zp ON true
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS emd_polygon_count,
            bool_or(ST_Covers(e.geom, o.current_pt_5179)) AS current_in_emd_polygon,
            bool_or(ST_Covers(e.geom, o.candidate_pt_5179)) AS candidate_in_emd_polygon
        FROM tl_scco_emd AS e
        WHERE e.emd_cd = o.emd_cd
          AND e.geom IS NOT NULL
    ) AS ep ON true
    ORDER BY o.distance_m DESC, o.bd_mgt_sn
    """


def tag_row(
    row: Mapping[str, Any],
    *,
    candidate_source_yyyymm: str,
) -> dict[str, Any]:
    tagged = dict(row)
    secondary_tags = secondary_tags_for(row, candidate_source_yyyymm=candidate_source_yyyymm)
    primary_tag = choose_primary_tag(row, secondary_tags)
    tagged["primary_tag"] = primary_tag
    tagged["secondary_tags"] = ";".join(secondary_tags)
    tagged["triage_note"] = triage_note(primary_tag, secondary_tags)
    return tagged


def secondary_tags_for(
    row: Mapping[str, Any],
    *,
    candidate_source_yyyymm: str,
) -> list[str]:
    tags: list[str] = []
    if _float(row.get("distance_m")) >= 10_000:
        tags.append("very_large_distance_over_10km")
    elif _float(row.get("distance_m")) >= 1_000:
        tags.append("large_distance_over_1km")

    lon_delta = _float(row.get("abs_lon_delta"))
    lat_delta = _float(row.get("abs_lat_delta"))
    if abs(lon_delta - 2.0) <= 0.02 and lat_delta <= 0.02:
        tags.append("lon_shift_approx_2deg")

    if row.get("candidate_sig_cd") != row.get("bd_sig_cd"):
        tags.append("candidate_sig_cd_mismatch")
    if int(row.get("candidates_per_bd") or 0) > 1:
        tags.append("multiple_candidates_for_bd")
    if int(row.get("natural_key_polygon_count") or 0) == 0:
        tags.append("natural_key_polygon_unmatched")

    for prefix in ("current", "candidate"):
        for scope in ("building", "zip", "emd"):
            key = f"{prefix}_in_{scope}_polygon"
            value = row.get(key)
            if value is False:
                tags.append(f"{prefix}_outside_{scope}_polygon")
            elif value is True:
                tags.append(f"{prefix}_inside_{scope}_polygon")

    current_pt_source = str(row.get("current_pt_source") or "unknown")
    tags.append(f"current_pt_source_{current_pt_source}")

    text_month = row.get("text_source_yyyymm")
    if text_month and str(text_month) != candidate_source_yyyymm:
        tags.append("candidate_source_month_differs_from_text")
    return tags


def choose_primary_tag(row: Mapping[str, Any], secondary_tags: Sequence[str]) -> PrimaryTag:
    tag_set = set(secondary_tags)
    candidate_bad = any(tag.startswith("candidate_outside_") for tag in tag_set)
    current_bad = any(tag.startswith("current_outside_") for tag in tag_set)
    candidate_good = context_is_good("candidate", tag_set)
    current_good = context_is_good("current", tag_set)

    if "lon_shift_approx_2deg" in tag_set:
        return "crs_or_source_coordinate_error"
    if "candidate_sig_cd_mismatch" in tag_set:
        return "key_mismatch"
    if candidate_bad and not current_bad:
        return "candidate_coordinate_error"
    if current_bad and not candidate_bad:
        return "current_representative_error"
    if "multiple_candidates_for_bd" in tag_set and candidate_bad:
        return "key_mismatch"
    if "natural_key_polygon_unmatched" in tag_set and candidate_bad:
        return "key_mismatch"
    if candidate_good and str(row.get("current_pt_source") or "") == "centroid":
        return "current_representative_error"
    if "candidate_source_month_differs_from_text" in tag_set and (
        candidate_bad or current_bad or _float(row.get("distance_m")) >= 1_000
    ):
        return "source_month_drift_possible"
    if candidate_bad and current_bad:
        return "manual_review"
    if not candidate_good and not current_good:
        return "manual_review"
    return "manual_review"


def context_is_good(prefix: str, tag_set: set[str]) -> bool:
    outside = any(tag.startswith(f"{prefix}_outside_") for tag in tag_set)
    if outside:
        return False
    known_inside = {
        f"{prefix}_inside_building_polygon",
        f"{prefix}_inside_zip_polygon",
        f"{prefix}_inside_emd_polygon",
    }
    return len(tag_set & known_inside) >= 2


def triage_note(primary_tag: PrimaryTag, secondary_tags: Sequence[str]) -> str:
    if "lon_shift_approx_2deg" in secondary_tags:
        return "경도 차이가 약 2도이고 위도 차이가 작아 source/CRS 좌표 오류 패턴을 우선 의심한다."
    if primary_tag == "candidate_coordinate_error":
        return "후보점이 하나 이상의 공간 문맥 밖에 있고 현행 대표점은 같은 오류 신호가 약하다."
    if primary_tag == "current_representative_error":
        return "현행 대표점 오류 신호가 후보점보다 강하거나 후보점이 여러 문맥 안에 있다."
    if primary_tag == "key_mismatch":
        return "후보 key 또는 natural-key polygon 대응을 먼저 확인해야 한다."
    if primary_tag == "source_month_drift_possible":
        return "후보 원천과 텍스트 정본 기준월 차이를 분리 확인해야 한다."
    return "자동 규칙만으로 원인을 확정하기 어려워 수동 판정이 필요하다."


def build_summary(
    tagged_rows: Sequence[Mapping[str, Any]],
    artifacts: Mapping[str, str],
) -> dict[str, Any]:
    primary_counts = Counter(str(row["primary_tag"]) for row in tagged_rows)
    secondary_counts: Counter[str] = Counter()
    pt_source_counts = Counter(
        str(row.get("current_pt_source") or "unknown") for row in tagged_rows
    )
    sido_counts = Counter(str(row.get("sido_cd") or "unknown") for row in tagged_rows)
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    distances = sorted(_float(row.get("distance_m")) for row in tagged_rows)

    for row in tagged_rows:
        secondary_counts.update(
            tag for tag in str(row.get("secondary_tags") or "").split(";") if tag
        )
        primary = str(row["primary_tag"])
        if len(samples[primary]) < 10:
            samples[primary].append(
                {
                    "bd_mgt_sn": row.get("bd_mgt_sn"),
                    "road_addr": row.get("road_addr"),
                    "distance_m": row.get("distance_m"),
                    "current_lon": row.get("current_lon"),
                    "current_lat": row.get("current_lat"),
                    "candidate_lon": row.get("candidate_lon"),
                    "candidate_lat": row.get("candidate_lat"),
                    "secondary_tags": row.get("secondary_tags"),
                }
            )

    return {
        "outlier_count": len(tagged_rows),
        "primary_tag_counts": dict(sorted(primary_counts.items())),
        "secondary_tag_counts": dict(sorted(secondary_counts.items())),
        "current_pt_source_counts": dict(sorted(pt_source_counts.items())),
        "sido_counts": {
            code: {"name": t125.SIDO_CODE_TO_NAME.get(code), "count": count}
            for code, count in sorted(sido_counts.items())
        },
        "distance_distribution_m": distance_distribution(distances),
        "sample_rows_by_primary_tag": dict(samples),
        "primary_tag_definitions": PRIMARY_TAG_DESCRIPTIONS,
        "artifacts": dict(artifacts),
    }


def distance_distribution(distances: Sequence[float]) -> dict[str, float | None]:
    if not distances:
        return {"p50": None, "p95": None, "p99": None, "max": None}
    return {
        "p50": percentile(distances, 0.5),
        "p95": percentile(distances, 0.95),
        "p99": percentile(distances, 0.99),
        "max": distances[-1],
    }


def percentile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("sorted_values must not be empty")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def write_artifacts(
    output_dir: Path,
    tagged_rows: Sequence[Mapping[str, Any]],
    *,
    candidate_source_yyyymm: str = t125.DEFAULT_SOURCE_YYYYMM,
) -> dict[str, str]:
    csv_path = output_dir / "outlier_tags.csv"
    geojson_path = output_dir / "outlier_tags.geojson"
    sql_path = output_dir / "representative_samples.sql"
    t125.write_csv(csv_path, tagged_rows)
    t125.write_geojson(geojson_path, tagged_rows)
    sql_path.write_text(
        representative_sample_sql(candidate_source_yyyymm=candidate_source_yyyymm) + "\n",
        encoding="utf-8",
    )
    return {
        "outlier_tags_csv": str(csv_path),
        "outlier_tags_geojson": str(geojson_path),
        "representative_sample_sql": str(sql_path),
        "summary_json": str(output_dir / "summary.json"),
    }


def representative_sample_sql(*, candidate_source_yyyymm: str) -> str:
    source_literal = candidate_source_yyyymm.replace("'", "''")
    sql = triage_sql().replace(
        "CAST(:candidate_source_yyyymm AS text)",
        f"'{source_literal}'::text",
    )
    return f"""-- T-129 대표 샘플 재현 SQL
-- 전제: scripts/run_t129_c11_outlier_triage.py 또는 T-125 preflight가
--       {t125.CANDIDATE_BEST_TABLE}를 만든 상태에서 실행한다.
WITH triage AS MATERIALIZED (
{sql}
)
SELECT
    bd_mgt_sn,
    road_addr,
    current_pt_source,
    distance_m,
    current_lon,
    current_lat,
    candidate_lon,
    candidate_lat,
    current_in_building_polygon,
    candidate_in_building_polygon,
    current_in_zip_polygon,
    candidate_in_zip_polygon,
    current_in_emd_polygon,
    candidate_in_emd_polygon
FROM triage
WHERE abs(abs(candidate_lon - current_lon) - 2.0) <= 0.02
   OR candidate_in_zip_polygon IS false
   OR candidate_in_emd_polygon IS false
   OR current_in_zip_polygon IS false
   OR current_in_emd_polygon IS false
ORDER BY distance_m DESC, bd_mgt_sn
LIMIT 200;"""


def _float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


if __name__ == "__main__":
    asyncio.run(main())
