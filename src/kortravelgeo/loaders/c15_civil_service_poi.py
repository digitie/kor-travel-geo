"""C15 civil-service institution POI distance validation prototype."""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import SupportsFloat

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.core.normalize import parse_address
from kortravelgeo.exceptions import InvalidAddressError, LoaderError
from kortravelgeo.loaders.augment_harness import (
    AugmentGroupPayload,
    AugmentGroupResult,
    AugmentReport,
    ShapeFeature,
    ShapeStagingSpec,
    StagingColumn,
    copy_shape_features_to_staging,
    iter_shape_features_from_buffers,
    recreate_shape_staging_table,
)

C15_CIVIL_SERVICE_SOURCE_KEY = "civil_service_institution_map"
C15_CIVIL_SERVICE_TABLE = "_ktg_c15_civil_service_poi"

CIVIL_SERVICE_POI_SOURCE_FIELDS: tuple[str, ...] = (
    "유형",
    "상세분류",
    "시군구코드",
    "도로명코드",
    "도로명주소",
    "기관명",
    "위치X",
    "위치Y",
    "전화번호",
)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class CivilServicePoiDistanceMeasurement:
    total_poi_rows: int
    parsed_address_rows: int
    unparsed_address_rows: int
    geocode_matched_rows: int
    geocode_missing_rows: int
    geocode_point_missing_rows: int
    measured_rows: int
    outlier_threshold_m: float
    outlier_rows: int
    p50_m: float | None
    p95_m: float | None
    max_m: float | None
    sample: tuple[Mapping[str, object], ...]

    @property
    def parsed_address_ratio(self) -> float | None:
        return _ratio(self.parsed_address_rows, self.total_poi_rows)

    @property
    def geocode_match_ratio(self) -> float | None:
        return _ratio(self.geocode_matched_rows, self.parsed_address_rows)

    @property
    def outlier_ratio(self) -> float | None:
        return _ratio(self.outlier_rows, self.measured_rows)


@dataclass(frozen=True, slots=True)
class C15CivilServicePoiComparison:
    civil_service_zip: str
    source_yyyymm: str | None
    poi_rows: int
    distance: CivilServicePoiDistanceMeasurement
    geocode_target_table: str
    outlier_threshold_m: float
    row_limit: int | None = None

    def metrics(self) -> dict[str, object]:
        return {
            "civil_service_zip": self.civil_service_zip,
            "source_yyyymm": self.source_yyyymm,
            "staging_rows": {
                "civil_service_institution": self.poi_rows,
            },
            "row_limit": self.row_limit,
            "address_parse": {
                "parsed_rows": self.distance.parsed_address_rows,
                "unparsed_rows": self.distance.unparsed_address_rows,
                "parsed_ratio": self.distance.parsed_address_ratio,
            },
            "geocode_distance_m": {
                "geocoder_contract": "batch_exact_road_lookup",
                "geocode_target_table": self.geocode_target_table,
                "matched_rows": self.distance.geocode_matched_rows,
                "missing_rows": self.distance.geocode_missing_rows,
                "point_missing_rows": self.distance.geocode_point_missing_rows,
                "measured_rows": self.distance.measured_rows,
                "match_ratio": self.distance.geocode_match_ratio,
                "p50_m": self.distance.p50_m,
                "p95_m": self.distance.p95_m,
                "max_m": self.distance.max_m,
                "outlier_threshold_m": self.outlier_threshold_m,
                "outlier_rows": self.distance.outlier_rows,
                "outlier_ratio": self.distance.outlier_ratio,
            },
            "notes": (
                "civil_service_institution_map is a POI validation source only. "
                "This prototype parses the road-address string and reproduces the "
                "exact road geocoder lookup against mv_geocode_target in batch; "
                "it does not add institution names or POI coordinates to normal "
                "address candidates."
            ),
            "serving_promotion": False,
        }

    def sample(self) -> tuple[Mapping[str, object], ...]:
        return self.distance.sample

    def to_payload(self) -> AugmentGroupPayload:
        return AugmentGroupPayload(
            metrics=self.metrics(),
            sample=self.sample(),
            source_yyyymm=self.source_yyyymm,
        )


def civil_service_poi_staging_spec(
    table_name: str = C15_CIVIL_SERVICE_TABLE,
) -> ShapeStagingSpec:
    return ShapeStagingSpec(
        table_name=table_name,
        columns=(
            StagingColumn("record_number", sql_type="bigint"),
            StagingColumn("institution_type"),
            StagingColumn("detail_class"),
            StagingColumn("sigungu_code"),
            StagingColumn("road_code"),
            StagingColumn("road_address"),
            StagingColumn("institution_name"),
            StagingColumn("source_x_5179", sql_type="double precision"),
            StagingColumn("source_y_5179", sql_type="double precision"),
            StagingColumn("phone_number"),
            StagingColumn("si_nm"),
            StagingColumn("sgg_nm"),
            StagingColumn("road_nrm"),
            StagingColumn("buld_mnnm", sql_type="integer"),
            StagingColumn("buld_slno", sql_type="integer"),
            StagingColumn("buld_se_cd"),
            StagingColumn("parse_error"),
        ),
        geometry_type="Point",
    )


def iter_civil_service_poi_features(
    zip_path: Path | str,
    *,
    row_limit: int | None = None,
) -> Iterator[ShapeFeature]:
    archive = Path(zip_path)
    with zipfile.ZipFile(archive) as zip_file:
        shp_member = _single_zip_member(zip_file, ".shp")
        dbf_member = _single_zip_member(zip_file, ".dbf")
        shp_data = zip_file.read(shp_member)
        dbf_data = zip_file.read(dbf_member)

    features = iter_shape_features_from_buffers(
        shp_data,
        dbf_data,
        fields=CIVIL_SERVICE_POI_SOURCE_FIELDS,
        encoding="cp949",
        field_name_encoding="cp949",
        source_name=f"{archive}:{dbf_member}",
    )
    for index, feature in enumerate(features):
        if row_limit is not None and index >= row_limit:
            break
        if feature.geometry.shape_kind != "Point":
            msg = (
                "civil_service_institution_map must contain Point geometry, "
                f"got {feature.geometry.shape_kind} at record {feature.record_number}"
            )
            raise LoaderError(msg)
        yield _feature_for_staging(feature)


async def compare_c15_civil_service_poi_distance(
    engine: AsyncEngine,
    civil_service_zip: Path | str,
    *,
    source_yyyymm: str | None = None,
    sample_limit: int = 20,
    outlier_threshold_m: float = 100.0,
    row_limit: int | None = None,
    poi_table: str = C15_CIVIL_SERVICE_TABLE,
    geocode_target_table: str = "mv_geocode_target",
) -> C15CivilServicePoiComparison:
    archive = Path(civil_service_zip)
    spec = civil_service_poi_staging_spec(poi_table)
    await recreate_shape_staging_table(engine, spec)
    poi_rows = await copy_shape_features_to_staging(
        engine,
        spec,
        iter_civil_service_poi_features(archive, row_limit=row_limit),
    )
    distance = await measure_civil_service_poi_geocode_distance(
        engine,
        poi_table=poi_table,
        geocode_target_table=geocode_target_table,
        sample_limit=sample_limit,
        outlier_threshold_m=outlier_threshold_m,
    )
    return C15CivilServicePoiComparison(
        civil_service_zip=str(archive),
        source_yyyymm=source_yyyymm,
        poi_rows=poi_rows,
        distance=distance,
        geocode_target_table=geocode_target_table,
        outlier_threshold_m=outlier_threshold_m,
        row_limit=row_limit,
    )


async def build_c15_civil_service_poi_report(
    engine: AsyncEngine,
    civil_service_zip: Path | str,
    *,
    source_yyyymm: str | None = None,
    sample_limit: int = 20,
    outlier_threshold_m: float = 100.0,
    row_limit: int | None = None,
    generated_at: datetime | None = None,
) -> AugmentReport:
    try:
        comparison = await compare_c15_civil_service_poi_distance(
            engine,
            civil_service_zip,
            source_yyyymm=source_yyyymm,
            sample_limit=sample_limit,
            outlier_threshold_m=outlier_threshold_m,
            row_limit=row_limit,
        )
    except Exception as exc:
        result = AugmentGroupResult(
            group_id="national",
            sido_name="전국",
            status="failed",
            metrics={},
            error=f"{type(exc).__name__}: {exc}",
            source_yyyymm=source_yyyymm,
        )
    else:
        payload = comparison.to_payload()
        result = AugmentGroupResult(
            group_id="national",
            sido_name="전국",
            status="used",
            metrics=payload.metrics,
            sample=payload.sample,
            source_yyyymm=payload.source_yyyymm,
        )
    return AugmentReport(
        task_id="T-115",
        title="C15 civil-service institution POI distance validation",
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        groups=(result,),
        source_yyyymm=source_yyyymm,
    )


async def measure_civil_service_poi_geocode_distance(
    engine: AsyncEngine,
    *,
    poi_table: str = C15_CIVIL_SERVICE_TABLE,
    geocode_target_table: str = "mv_geocode_target",
    sample_limit: int = 20,
    outlier_threshold_m: float = 100.0,
) -> CivilServicePoiDistanceMeasurement:
    sql = civil_service_poi_geocode_distance_sql(
        poi_table,
        geocode_target_table,
    )
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(sql),
                {
                    "sample_limit": sample_limit,
                    "outlier_threshold_m": outlier_threshold_m,
                },
            )
        ).mappings().one()
    return CivilServicePoiDistanceMeasurement(
        total_poi_rows=int(row["total_poi_rows"] or 0),
        parsed_address_rows=int(row["parsed_address_rows"] or 0),
        unparsed_address_rows=int(row["unparsed_address_rows"] or 0),
        geocode_matched_rows=int(row["geocode_matched_rows"] or 0),
        geocode_missing_rows=int(row["geocode_missing_rows"] or 0),
        geocode_point_missing_rows=int(row["geocode_point_missing_rows"] or 0),
        measured_rows=int(row["measured_rows"] or 0),
        outlier_threshold_m=outlier_threshold_m,
        outlier_rows=int(row["outlier_rows"] or 0),
        p50_m=_optional_float(row["p50_m"]),
        p95_m=_optional_float(row["p95_m"]),
        max_m=_optional_float(row["max_m"]),
        sample=_jsonb_sample(row["sample"]),
    )


def civil_service_poi_geocode_distance_sql(
    poi_table: str,
    geocode_target_table: str,
) -> str:
    poi = _quote_ident_path(poi_table)
    target = _quote_ident_path(geocode_target_table)
    return f"""
WITH source_counts AS (
  SELECT
    count(*)::bigint AS total_poi_rows,
    count(*) FILTER (WHERE parse_error IS NULL)::bigint AS parsed_address_rows,
    count(*) FILTER (WHERE parse_error IS NOT NULL)::bigint AS unparsed_address_rows
  FROM {poi}
),
parsed AS (
  SELECT *
    FROM {poi}
   WHERE parse_error IS NULL
     AND road_nrm IS NOT NULL
     AND buld_mnnm IS NOT NULL
     AND buld_slno IS NOT NULL
),
ranked AS (
  SELECT
    p.record_number,
    p.institution_type,
    p.detail_class,
    p.sigungu_code,
    p.road_code,
    p.road_address,
    p.institution_name,
    p.source_x_5179,
    p.source_y_5179,
    p.phone_number,
    p.si_nm,
    p.sgg_nm,
    p.road_nrm,
    p.buld_mnnm,
    p.buld_slno,
    t.bd_mgt_sn,
    t.pt_source,
    CASE
      WHEN t.pt_5179 IS NULL THEN NULL
      ELSE ST_Distance(p.geom, t.pt_5179)::float8
    END AS distance_m,
    row_number() OVER (
      PARTITION BY p.record_number
      ORDER BY
        CASE WHEN t.bd_mgt_sn IS NULL THEN 1 ELSE 0 END,
        CASE WHEN t.pt_source = 'entrance' THEN 0 ELSE 1 END,
        t.bd_mgt_sn
    ) AS candidate_rank
  FROM parsed p
  LEFT JOIN {target} t
    ON t.rn_nrm = p.road_nrm
   AND t.buld_mnnm = p.buld_mnnm
   AND t.buld_slno = p.buld_slno
   AND (p.buld_se_cd IS NULL OR t.buld_se_cd = p.buld_se_cd)
   AND (p.si_nm IS NULL OR t.si_nm = p.si_nm)
   AND (
     p.sgg_nm IS NULL
     OR t.sgg_nm = p.sgg_nm
     OR (
       position(' ' in p.sgg_nm) = 0
       AND p.sgg_nm LIKE '%구'
       AND right(t.sgg_nm, char_length(p.sgg_nm)) = p.sgg_nm
     )
   )
),
chosen AS (
  SELECT *
    FROM ranked
   WHERE candidate_rank = 1
),
stats AS (
  SELECT
    count(*) FILTER (WHERE bd_mgt_sn IS NOT NULL)::bigint AS geocode_matched_rows,
    count(*) FILTER (WHERE bd_mgt_sn IS NULL)::bigint AS geocode_missing_rows,
    count(*) FILTER (WHERE bd_mgt_sn IS NOT NULL AND distance_m IS NULL)::bigint
      AS geocode_point_missing_rows,
    count(distance_m)::bigint AS measured_rows,
    count(*) FILTER (WHERE distance_m > :outlier_threshold_m)::bigint AS outlier_rows,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY distance_m)::float8 AS p50_m,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY distance_m)::float8 AS p95_m,
    max(distance_m)::float8 AS max_m
  FROM chosen
),
sample_candidates AS (
  SELECT
    1 AS issue_rank,
    'distance_outlier'::text AS sample_kind,
    record_number,
    institution_type,
    detail_class,
    sigungu_code,
    road_code,
    road_address,
    institution_name,
    bd_mgt_sn,
    pt_source,
    distance_m,
    NULL::text AS parse_error
  FROM chosen
  WHERE distance_m > :outlier_threshold_m
  UNION ALL
  SELECT
    2 AS issue_rank,
    'geocode_missing'::text AS sample_kind,
    record_number,
    institution_type,
    detail_class,
    sigungu_code,
    road_code,
    road_address,
    institution_name,
    bd_mgt_sn,
    pt_source,
    distance_m,
    NULL::text AS parse_error
  FROM chosen
  WHERE bd_mgt_sn IS NULL
  UNION ALL
  SELECT
    3 AS issue_rank,
    'geocode_point_missing'::text AS sample_kind,
    record_number,
    institution_type,
    detail_class,
    sigungu_code,
    road_code,
    road_address,
    institution_name,
    bd_mgt_sn,
    pt_source,
    distance_m,
    NULL::text AS parse_error
  FROM chosen
  WHERE bd_mgt_sn IS NOT NULL
    AND distance_m IS NULL
  UNION ALL
  SELECT
    4 AS issue_rank,
    'address_parse_failed'::text AS sample_kind,
    record_number,
    institution_type,
    detail_class,
    sigungu_code,
    road_code,
    road_address,
    institution_name,
    NULL::text AS bd_mgt_sn,
    NULL::text AS pt_source,
    NULL::float8 AS distance_m,
    parse_error
  FROM {poi}
  WHERE parse_error IS NOT NULL
),
sample AS (
  SELECT
    sample_kind,
    record_number,
    institution_type,
    detail_class,
    sigungu_code,
    road_code,
    road_address,
    institution_name,
    bd_mgt_sn,
    pt_source,
    distance_m,
    parse_error
  FROM sample_candidates
  ORDER BY issue_rank, distance_m DESC NULLS LAST, record_number
  LIMIT :sample_limit
)
SELECT
  source_counts.total_poi_rows,
  source_counts.parsed_address_rows,
  source_counts.unparsed_address_rows,
  stats.geocode_matched_rows,
  stats.geocode_missing_rows,
  stats.geocode_point_missing_rows,
  stats.measured_rows,
  stats.outlier_rows,
  stats.p50_m,
  stats.p95_m,
  stats.max_m,
  COALESCE((SELECT jsonb_agg(to_jsonb(sample)) FROM sample), '[]'::jsonb) AS sample
FROM source_counts
CROSS JOIN stats
"""


async def drop_c15_civil_service_poi_staging_tables(
    engine: AsyncEngine,
    *,
    tables: Sequence[str] = (C15_CIVIL_SERVICE_TABLE,),
) -> None:
    async with engine.begin() as conn:
        for table in tables:
            await conn.execute(text(f"DROP TABLE IF EXISTS {_quote_ident_path(table)}"))


def _feature_for_staging(feature: ShapeFeature) -> ShapeFeature:
    attrs = feature.attributes
    road_address = attrs.get("도로명주소")
    si_nm = sgg_nm = road_nrm = buld_mnnm = buld_slno = buld_se_cd = None
    parse_error: str | None = None
    if not road_address:
        parse_error = "도로명주소 is empty"
    else:
        try:
            parts = parse_address(road_address)
        except InvalidAddressError as exc:
            parse_error = str(exc)
        else:
            if not parts.is_road:
                parse_error = "도로명주소 did not parse as a road address"
            else:
                si_nm = parts.si
                sgg_nm = parts.sgg
                road_nrm = parts.road_nrm
                buld_mnnm = str(parts.mnnm) if parts.mnnm is not None else None
                buld_slno = str(parts.slno)
                buld_se_cd = parts.buld_se_cd

    normalized: dict[str, str | None] = {
        "record_number": str(feature.record_number),
        "institution_type": attrs.get("유형"),
        "detail_class": attrs.get("상세분류"),
        "sigungu_code": attrs.get("시군구코드"),
        "road_code": attrs.get("도로명코드"),
        "road_address": road_address,
        "institution_name": attrs.get("기관명"),
        "source_x_5179": attrs.get("위치X"),
        "source_y_5179": attrs.get("위치Y"),
        "phone_number": attrs.get("전화번호"),
        "si_nm": si_nm,
        "sgg_nm": sgg_nm,
        "road_nrm": road_nrm,
        "buld_mnnm": buld_mnnm,
        "buld_slno": buld_slno,
        "buld_se_cd": buld_se_cd,
        "parse_error": parse_error,
    }
    return ShapeFeature(
        record_number=feature.record_number,
        attributes=normalized,
        geometry=feature.geometry,
    )


def _single_zip_member(zip_file: zipfile.ZipFile, suffix: str) -> str:
    candidates = [name for name in zip_file.namelist() if name.lower().endswith(suffix)]
    if len(candidates) != 1:
        msg = f"expected one {suffix} member, found {len(candidates)}"
        raise LoaderError(msg)
    return candidates[0]


def _jsonb_sample(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        return ()
    rows: list[Mapping[str, object]] = []
    for item in value:
        if isinstance(item, dict):
            rows.append(item)
    return tuple(rows)


def _optional_float(value: SupportsFloat | str | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _quote_ident_path(value: str) -> str:
    return ".".join(_quote_ident(part) for part in value.split("."))


def _quote_ident(value: str) -> str:
    if not _IDENT_RE.fullmatch(value):
        msg = f"invalid SQL identifier: {value!r}"
        raise LoaderError(msg)
    return f'"{value}"'
