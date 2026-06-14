"""C12 connection-line adjacency prototype for the road-address building bundle."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders.augment_harness import (
    AugmentGroupPayload,
    AugmentGroupResult,
    AugmentReport,
    DistanceMeasurement,
    JoinKey,
    KeyOverlapMeasurement,
    ShapeStagingSpec,
    SidoPathPattern,
    SidoSourceGroup,
    StagingColumn,
    copy_shape_file_to_staging,
    copy_zip_shape_layer_to_staging,
    discover_sido_source_groups,
    measure_key_overlap,
    measure_keyed_distance,
    recreate_shape_staging_table,
)
from kortravelgeo.loaders.building_shape_bundle import (
    BUNDLE_CONNECTION_LAYER,
    compare_building_shape_bundle,
)
from kortravelgeo.loaders.juso_map import discover_sido_dataset
from kortravelgeo.loaders.shape_dbf import KeyOverlap

C12_BUNDLE_SOURCE_KEY = "bundle"
C12_ELECTRONIC_SOURCE_KEY = "electronic"

C12_CONNECTION_TABLE = "_ktg_c12_spot_cntc"
C12_ROAD_MANAGE_TABLE = "_ktg_c12_sprd_manage"
ELECTRONIC_ROAD_MANAGE_LAYER = "TL_SPRD_MANAGE"

CONNECTION_ROAD_KEY_FIELDS: tuple[str, ...] = ("RDS_SIG_CD", "RDS_MAN_NO")
CONNECTION_SOURCE_FIELDS: tuple[str, ...] = (
    "SIG_CD",
    "ENT_MAN_NO",
    "RDS_SIG_CD",
    "RDS_MAN_NO",
    "BSI_INT_SN",
    "CNT_DRC_LN",
    "CNT_DST_LN",
)
ROAD_MANAGE_SOURCE_FIELDS: tuple[str, ...] = ("SIG_CD", "RDS_MAN_NO", "RN_CD", "RN")
CONNECTION_ROAD_JOIN_KEYS: tuple[JoinKey, ...] = (
    JoinKey("rds_sig_cd", "sig_cd"),
    JoinKey("rds_man_no", "rds_man_no"),
)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class RoadAdjacencyMeasurement:
    total_connections: int
    road_key_matched: int
    road_key_missing: int
    within_tolerance: int
    over_tolerance: int
    dangling: int
    dangling_ratio: float | None
    p50_m: float | None
    p95_m: float | None
    max_m: float | None
    sample: tuple[Mapping[str, object], ...]


@dataclass(frozen=True, slots=True)
class C12ConnectionComparison:
    sido_name: str
    bundle_zip: str
    electronic_map_dir: str
    source_yyyymm: str | None
    tolerance_m: float
    connection_rows: int
    road_rows: int
    entrance_ref_overlap: KeyOverlap
    road_key_overlap: KeyOverlapMeasurement
    road_distance: DistanceMeasurement
    road_adjacency: RoadAdjacencyMeasurement

    def metrics(self) -> dict[str, object]:
        return {
            "sido_name": self.sido_name,
            "bundle_zip": self.bundle_zip,
            "electronic_map_dir": self.electronic_map_dir,
            "source_yyyymm": self.source_yyyymm,
            "tolerance_m": self.tolerance_m,
            "staging_rows": {
                "bundle_tl_spot_cntc": self.connection_rows,
                "electronic_tl_sprd_manage": self.road_rows,
            },
            "connection_entrance_ref_overlap": _dbf_key_overlap_metrics(
                self.entrance_ref_overlap
            ),
            "road_key_overlap": _table_key_overlap_metrics(self.road_key_overlap),
            "road_distance_m": _distance_metrics(self.road_distance),
            "road_adjacency": _road_adjacency_metrics(self.road_adjacency),
            "serving_promotion": False,
        }

    def sample(self) -> tuple[Mapping[str, object], ...]:
        return tuple(
            {
                "sample_kind": "road_dangling",
                **row,
            }
            for row in self.road_adjacency.sample
        )

    def to_payload(self) -> AugmentGroupPayload:
        return AugmentGroupPayload(
            metrics=self.metrics(),
            sample=self.sample(),
            source_yyyymm=self.source_yyyymm,
        )


def connection_staging_spec(table_name: str) -> ShapeStagingSpec:
    return ShapeStagingSpec(
        table_name=table_name,
        columns=(
            StagingColumn("sig_cd", source_field="SIG_CD"),
            StagingColumn("ent_man_no", source_field="ENT_MAN_NO"),
            StagingColumn("rds_sig_cd", source_field="RDS_SIG_CD"),
            StagingColumn("rds_man_no", source_field="RDS_MAN_NO"),
            StagingColumn("bsi_int_sn", source_field="BSI_INT_SN"),
            StagingColumn("cnt_drc_ln", source_field="CNT_DRC_LN"),
            StagingColumn("cnt_dst_ln", source_field="CNT_DST_LN"),
        ),
        geometry_type="Geometry",
    )


def road_manage_staging_spec(table_name: str) -> ShapeStagingSpec:
    return ShapeStagingSpec(
        table_name=table_name,
        columns=(
            StagingColumn("sig_cd", source_field="SIG_CD"),
            StagingColumn("rds_man_no", source_field="RDS_MAN_NO"),
            StagingColumn("rn_cd", source_field="RN_CD"),
            StagingColumn("rn", source_field="RN"),
        ),
        geometry_type="Geometry",
    )


def discover_c12_connection_source_groups(
    *,
    bundle_root: Path | str,
    electronic_map_root: Path | str,
    sido_names: Sequence[str] | None = None,
) -> tuple[SidoSourceGroup, ...]:
    patterns = (
        SidoPathPattern(
            C12_BUNDLE_SOURCE_KEY,
            Path(bundle_root),
            "*{sido}*.zip",
        ),
        SidoPathPattern(
            C12_ELECTRONIC_SOURCE_KEY,
            Path(electronic_map_root),
            "{sido}",
        ),
    )
    if sido_names is None:
        return discover_sido_source_groups(patterns)
    return discover_sido_source_groups(patterns, sido_names=sido_names)


async def compare_c12_connection_lines(
    engine: AsyncEngine,
    bundle_zip: Path | str,
    electronic_map_sido_dir: Path | str,
    *,
    source_yyyymm: str | None = None,
    sample_limit: int = 20,
    tolerance_m: float = 1.0,
    connection_table: str = C12_CONNECTION_TABLE,
    road_table: str = C12_ROAD_MANAGE_TABLE,
) -> C12ConnectionComparison:
    bundle_path = Path(bundle_zip)
    electronic_root = Path(electronic_map_sido_dir)
    key_comparison = compare_building_shape_bundle(bundle_path, electronic_root)
    dataset = discover_sido_dataset(electronic_root)
    road_layer = dataset.layer(ELECTRONIC_ROAD_MANAGE_LAYER)

    connection_spec = connection_staging_spec(connection_table)
    road_spec = road_manage_staging_spec(road_table)
    await recreate_shape_staging_table(engine, connection_spec)
    await recreate_shape_staging_table(engine, road_spec)
    connection_rows = await copy_zip_shape_layer_to_staging(
        engine,
        connection_spec,
        bundle_path,
        BUNDLE_CONNECTION_LAYER,
        fields=CONNECTION_SOURCE_FIELDS,
    )
    road_rows = await copy_shape_file_to_staging(
        engine,
        road_spec,
        road_layer.shp_path,
        road_layer.dbf_path,
        fields=ROAD_MANAGE_SOURCE_FIELDS,
    )

    road_key_overlap = await measure_key_overlap(
        engine,
        connection_table,
        road_table,
        CONNECTION_ROAD_JOIN_KEYS,
    )
    road_distance = await measure_keyed_distance(
        engine,
        connection_table,
        road_table,
        CONNECTION_ROAD_JOIN_KEYS,
        sample_limit=sample_limit,
    )
    road_adjacency = await measure_road_adjacency(
        engine,
        connection_table,
        road_table,
        tolerance_m=tolerance_m,
        sample_limit=sample_limit,
    )
    return C12ConnectionComparison(
        sido_name=key_comparison.sido_name,
        bundle_zip=str(bundle_path),
        electronic_map_dir=str(electronic_root),
        source_yyyymm=source_yyyymm,
        tolerance_m=tolerance_m,
        connection_rows=connection_rows,
        road_rows=road_rows,
        entrance_ref_overlap=key_comparison.connection_entrance_ref_overlap,
        road_key_overlap=road_key_overlap,
        road_distance=road_distance,
        road_adjacency=road_adjacency,
    )


async def build_c12_connection_report(
    engine: AsyncEngine,
    groups: Iterable[SidoSourceGroup],
    *,
    source_yyyymm: str | None = None,
    sample_limit: int = 20,
    tolerance_m: float = 1.0,
    generated_at: datetime | None = None,
) -> AugmentReport:
    results: list[AugmentGroupResult] = []
    for group in groups:
        if group.missing_keys:
            results.append(
                AugmentGroupResult(
                    group_id=group.sido_name,
                    sido_name=group.sido_name,
                    status="skipped",
                    metrics={},
                    error="missing required source(s): " + ", ".join(group.missing_keys),
                )
            )
            continue
        try:
            comparison = await compare_c12_connection_lines(
                engine,
                group.path(C12_BUNDLE_SOURCE_KEY),
                group.path(C12_ELECTRONIC_SOURCE_KEY),
                source_yyyymm=source_yyyymm,
                sample_limit=sample_limit,
                tolerance_m=tolerance_m,
            )
        except Exception as exc:
            results.append(
                AugmentGroupResult(
                    group_id=group.sido_name,
                    sido_name=group.sido_name,
                    status="failed",
                    metrics={},
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        payload = comparison.to_payload()
        results.append(
            AugmentGroupResult(
                group_id=group.sido_name,
                sido_name=group.sido_name,
                status="used",
                metrics=payload.metrics,
                sample=payload.sample,
                source_yyyymm=payload.source_yyyymm or source_yyyymm,
            )
        )
    return AugmentReport(
        task_id="T-112",
        title="C12 connection-line road adjacency comparison",
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        groups=tuple(results),
        source_yyyymm=source_yyyymm,
    )


async def measure_road_adjacency(
    engine: AsyncEngine,
    connection_table: str,
    road_table: str,
    *,
    tolerance_m: float = 1.0,
    sample_limit: int = 20,
) -> RoadAdjacencyMeasurement:
    sql = road_adjacency_sql(connection_table, road_table)
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(sql),
                {"sample_limit": sample_limit, "tolerance_m": tolerance_m},
            )
        ).mappings().one()
    return RoadAdjacencyMeasurement(
        total_connections=int(row["total_connections"] or 0),
        road_key_matched=int(row["road_key_matched"] or 0),
        road_key_missing=int(row["road_key_missing"] or 0),
        within_tolerance=int(row["within_tolerance"] or 0),
        over_tolerance=int(row["over_tolerance"] or 0),
        dangling=int(row["dangling"] or 0),
        dangling_ratio=_optional_float(row["dangling_ratio"]),
        p50_m=_optional_float(row["p50_m"]),
        p95_m=_optional_float(row["p95_m"]),
        max_m=_optional_float(row["max_m"]),
        sample=_jsonb_sample(row["sample"]),
    )


def road_adjacency_sql(connection_table: str, road_table: str) -> str:
    return f"""
WITH joined AS (
  SELECT
    c.sig_cd::text AS connection_sig_cd,
    c.ent_man_no::text AS connection_ent_man_no,
    c.rds_sig_cd::text AS connection_rds_sig_cd,
    c.rds_man_no::text AS connection_rds_man_no,
    c.bsi_int_sn::text AS connection_bsi_int_sn,
    r.sig_cd IS NOT NULL AS road_key_matched,
    CASE
      WHEN r.geom IS NULL THEN NULL
      ELSE ST_Distance(c.geom, r.geom)::float8
    END AS distance_m
  FROM {_quote_ident_path(connection_table)} c
  LEFT JOIN {_quote_ident_path(road_table)} r
    ON c.rds_sig_cd = r.sig_cd
   AND c.rds_man_no = r.rds_man_no
 WHERE c.geom IS NOT NULL
),
stats AS (
  SELECT
    count(*)::bigint AS total_connections,
    count(*) FILTER (WHERE road_key_matched)::bigint AS road_key_matched,
    count(*) FILTER (WHERE NOT road_key_matched)::bigint AS road_key_missing,
    count(*) FILTER (
      WHERE road_key_matched AND distance_m <= :tolerance_m
    )::bigint AS within_tolerance,
    count(*) FILTER (
      WHERE road_key_matched AND distance_m > :tolerance_m
    )::bigint AS over_tolerance,
    count(*) FILTER (
      WHERE NOT road_key_matched
         OR (road_key_matched AND distance_m > :tolerance_m)
    )::bigint AS dangling,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY distance_m)
      FILTER (WHERE road_key_matched)::float8 AS p50_m,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY distance_m)
      FILTER (WHERE road_key_matched)::float8 AS p95_m,
    max(distance_m) FILTER (WHERE road_key_matched)::float8 AS max_m
  FROM joined
),
sample AS (
  SELECT *
    FROM joined
   WHERE NOT road_key_matched
      OR (road_key_matched AND distance_m > :tolerance_m)
   ORDER BY road_key_matched ASC, distance_m DESC NULLS FIRST
   LIMIT :sample_limit
)
SELECT
  stats.total_connections,
  stats.road_key_matched,
  stats.road_key_missing,
  stats.within_tolerance,
  stats.over_tolerance,
  stats.dangling,
  CASE
    WHEN stats.total_connections = 0 THEN NULL
    ELSE stats.dangling::float8 / stats.total_connections::float8
  END AS dangling_ratio,
  stats.p50_m,
  stats.p95_m,
  stats.max_m,
  COALESCE((SELECT jsonb_agg(to_jsonb(sample)) FROM sample), '[]'::jsonb) AS sample
FROM stats
"""


async def drop_c12_connection_staging_tables(
    engine: AsyncEngine,
    *,
    tables: Sequence[str] = (C12_CONNECTION_TABLE, C12_ROAD_MANAGE_TABLE),
) -> None:
    async with engine.begin() as conn:
        for table in tables:
            await conn.execute(text(f"DROP TABLE IF EXISTS {_quote_ident_path(table)}"))


def _distance_metrics(value: DistanceMeasurement) -> dict[str, object]:
    return {
        "samples": value.samples,
        "p50_m": value.p50_m,
        "p95_m": value.p95_m,
        "max_m": value.max_m,
    }


def _road_adjacency_metrics(value: RoadAdjacencyMeasurement) -> dict[str, object]:
    return {
        "total_connections": value.total_connections,
        "road_key_matched": value.road_key_matched,
        "road_key_missing": value.road_key_missing,
        "within_tolerance": value.within_tolerance,
        "over_tolerance": value.over_tolerance,
        "dangling": value.dangling,
        "dangling_ratio": value.dangling_ratio,
        "p50_m": value.p50_m,
        "p95_m": value.p95_m,
        "max_m": value.max_m,
    }


def _table_key_overlap_metrics(value: KeyOverlapMeasurement) -> dict[str, int]:
    return {
        "left_rows": value.left_rows,
        "right_rows": value.right_rows,
        "left_distinct": value.left_distinct,
        "right_distinct": value.right_distinct,
        "left_duplicate_count": value.left_duplicate_count,
        "right_duplicate_count": value.right_duplicate_count,
        "intersection_count": value.intersection_count,
        "left_only_count": value.left_only_count,
        "right_only_count": value.right_only_count,
    }


def _dbf_key_overlap_metrics(value: KeyOverlap) -> dict[str, int]:
    return {
        "left_rows": value.left.row_count,
        "right_rows": value.right.row_count,
        "left_distinct": value.left.distinct_count,
        "right_distinct": value.right.distinct_count,
        "left_duplicate_count": value.left.duplicate_count,
        "right_duplicate_count": value.right.duplicate_count,
        "intersection_count": value.intersection_count,
        "left_only_count": value.left_only_count,
        "right_only_count": value.right_only_count,
    }


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float, str)):
        msg = f"expected numeric value, got {type(value).__name__}"
        raise LoaderError(msg)
    return float(value)


def _jsonb_sample(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        return ()
    rows: list[Mapping[str, object]] = []
    for item in value:
        if isinstance(item, dict):
            rows.append(item)
    return tuple(rows)


def _quote_ident_path(value: str) -> str:
    return ".".join(_quote_ident(part) for part in value.split("."))


def _quote_ident(value: str) -> str:
    if not _IDENT_RE.fullmatch(value):
        msg = f"invalid SQL identifier: {value!r}"
        raise LoaderError(msg)
    return f'"{value}"'
