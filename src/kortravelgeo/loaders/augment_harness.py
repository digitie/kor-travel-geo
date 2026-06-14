"""Common harness pieces for phase-1 source augmentation validation."""

from __future__ import annotations

import math
import re
import struct
import zipfile
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Literal

import psycopg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders.shape_dbf import DbfLayout, parse_dbf_header, zip_member

SIDO_NAMES: tuple[str, ...] = (
    "서울특별시",
    "부산광역시",
    "대구광역시",
    "인천광역시",
    "광주광역시",
    "대전광역시",
    "울산광역시",
    "세종특별자치시",
    "경기도",
    "강원특별자치도",
    "충청북도",
    "충청남도",
    "전북특별자치도",
    "전라남도",
    "경상북도",
    "경상남도",
    "제주특별자치도",
)

ShapeKind = Literal["Null", "Point", "PolyLine", "Polygon"]
AugmentStatus = Literal["used", "skipped", "failed"]

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SQL_TYPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\s*\([^;]*\))?$")


@dataclass(frozen=True, slots=True)
class SidoPathPattern:
    key: str
    root: Path
    glob: str = "*{sido}*"
    required: bool = True


@dataclass(frozen=True, slots=True)
class SidoSourcePath:
    key: str
    path: Path


@dataclass(frozen=True, slots=True)
class SidoSourceGroup:
    sido_name: str
    sources: tuple[SidoSourcePath, ...]
    missing_keys: tuple[str, ...] = ()

    def path(self, key: str) -> Path:
        for source in self.sources:
            if source.key == key:
                return source.path
        msg = f"{self.sido_name} source path not found: {key}"
        raise LoaderError(msg)


@dataclass(frozen=True, slots=True)
class AugmentGroupPayload:
    metrics: Mapping[str, object]
    sample: tuple[Mapping[str, object], ...] = ()
    source_yyyymm: str | None = None


@dataclass(frozen=True, slots=True)
class AugmentGroupResult:
    group_id: str
    sido_name: str
    status: AugmentStatus
    metrics: Mapping[str, object]
    sample: tuple[Mapping[str, object], ...] = ()
    source_yyyymm: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class AugmentReport:
    task_id: str
    title: str
    generated_at: str
    groups: tuple[AugmentGroupResult, ...]
    source_yyyymm: str | None = None

    @property
    def used_count(self) -> int:
        return sum(1 for group in self.groups if group.status == "used")

    @property
    def skipped_count(self) -> int:
        return sum(1 for group in self.groups if group.status == "skipped")

    @property
    def failed_count(self) -> int:
        return sum(1 for group in self.groups if group.status == "failed")

    def summary(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "source_yyyymm": self.source_yyyymm,
            "used": self.used_count,
            "skipped": self.skipped_count,
            "failed": self.failed_count,
            "total": len(self.groups),
        }


@dataclass(frozen=True, slots=True)
class ShapeGeometry:
    record_number: int
    shape_kind: ShapeKind
    wkt: str | None
    bbox: tuple[float, float, float, float] | None
    part_count: int
    point_count: int

    @property
    def ewkt_5179(self) -> str | None:
        if self.wkt is None:
            return None
        return f"SRID=5179;{self.wkt}"


@dataclass(frozen=True, slots=True)
class ShapeFeature:
    record_number: int
    attributes: Mapping[str, str | None]
    geometry: ShapeGeometry


@dataclass(frozen=True, slots=True)
class StagingColumn:
    name: str
    sql_type: str = "text"
    source_field: str | None = None


@dataclass(frozen=True, slots=True)
class ShapeStagingSpec:
    table_name: str
    columns: tuple[StagingColumn, ...]
    geom_column: str = "geom"
    geometry_type: str = "Geometry"
    srid: int = 5179
    temporary: bool = False
    on_commit_drop: bool = False


@dataclass(frozen=True, slots=True)
class StagingKeyIndexSpec:
    """One post-COPY btree index for phase-1 validation staging tables."""

    table_name: str
    index_name: str
    columns: tuple[str, ...]
    where_not_null: bool = True


@dataclass(frozen=True, slots=True)
class JoinKey:
    left: str
    right: str


@dataclass(frozen=True, slots=True)
class DistanceMeasurement:
    samples: int
    p50_m: float | None
    p95_m: float | None
    max_m: float | None
    sample: tuple[Mapping[str, object], ...]


@dataclass(frozen=True, slots=True)
class KeyOverlapMeasurement:
    left_rows: int
    right_rows: int
    left_distinct: int
    right_distinct: int
    intersection_count: int
    left_only_count: int
    right_only_count: int

    @property
    def left_duplicate_count(self) -> int:
        return self.left_rows - self.left_distinct

    @property
    def right_duplicate_count(self) -> int:
        return self.right_rows - self.right_distinct


@dataclass(frozen=True, slots=True)
class CoversMeasurement:
    samples: int
    covered: int
    outside: int
    coverage_ratio: float | None
    sample: tuple[Mapping[str, object], ...]


def discover_sido_source_groups(
    patterns: Sequence[SidoPathPattern],
    *,
    sido_names: Sequence[str] = SIDO_NAMES,
) -> tuple[SidoSourceGroup, ...]:
    groups: list[SidoSourceGroup] = []
    for sido_name in sido_names:
        sources: list[SidoSourcePath] = []
        missing: list[str] = []
        for pattern in patterns:
            glob_pattern = pattern.glob.format(sido=sido_name)
            matches = sorted(Path(pattern.root).glob(glob_pattern))
            if len(matches) > 1:
                msg = (
                    f"{sido_name} source pattern {pattern.key!r} matched "
                    f"{len(matches)} paths under {pattern.root}: {glob_pattern}"
                )
                raise LoaderError(msg)
            if matches:
                sources.append(SidoSourcePath(pattern.key, matches[0]))
            elif pattern.required:
                missing.append(pattern.key)
        groups.append(
            SidoSourceGroup(
                sido_name=sido_name,
                sources=tuple(sources),
                missing_keys=tuple(missing),
            )
        )
    return tuple(groups)


def build_augment_report(
    *,
    task_id: str,
    title: str,
    groups: Iterable[SidoSourceGroup],
    analyze_group: Callable[[SidoSourceGroup], AugmentGroupPayload | None],
    source_yyyymm: str | None = None,
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
            payload = analyze_group(group)
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
        if payload is None:
            results.append(
                AugmentGroupResult(
                    group_id=group.sido_name,
                    sido_name=group.sido_name,
                    status="skipped",
                    metrics={},
                    error="analyzer skipped group",
                )
            )
            continue
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
        task_id=task_id,
        title=title,
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        source_yyyymm=source_yyyymm,
        groups=tuple(results),
    )


def iter_shp_geometries(path: Path | str) -> Iterator[ShapeGeometry]:
    shp_path = Path(path)
    yield from iter_shp_geometries_from_bytes(shp_path.read_bytes(), source_name=str(shp_path))


def iter_shp_geometries_from_bytes(
    data: bytes,
    *,
    source_name: str = "<buffer>",
) -> Iterator[ShapeGeometry]:
    if len(data) < 100:
        msg = f"invalid SHP header length: {source_name}"
        raise LoaderError(msg)
    file_code = struct.unpack(">i", data[0:4])[0]
    if file_code != 9994:
        msg = f"invalid SHP file code for {source_name}: {file_code}"
        raise LoaderError(msg)

    offset = 100
    while offset < len(data):
        if offset + 8 > len(data):
            msg = f"truncated SHP record header in {source_name} at byte {offset}"
            raise LoaderError(msg)
        record_number, content_words = struct.unpack(">2i", data[offset : offset + 8])
        offset += 8
        content_length = content_words * 2
        content = data[offset : offset + content_length]
        if len(content) != content_length:
            msg = f"truncated SHP record {record_number} in {source_name}"
            raise LoaderError(msg)
        offset += content_length
        yield _parse_shape_record(record_number, content, source_name=source_name)


def iter_shape_features(
    shp_path: Path | str,
    dbf_path: Path | str,
    *,
    fields: Sequence[str] | None = None,
    encoding: str = "cp949",
    field_name_encoding: str = "ascii",
) -> Iterator[ShapeFeature]:
    shp = Path(shp_path)
    dbf = Path(dbf_path)
    yield from iter_shape_features_from_buffers(
        shp.read_bytes(),
        dbf.read_bytes(),
        fields=fields,
        encoding=encoding,
        field_name_encoding=field_name_encoding,
        source_name=str(shp),
    )


def iter_zip_shape_features(
    zip_path: Path | str,
    layer_name: str,
    *,
    fields: Sequence[str] | None = None,
    encoding: str = "cp949",
    field_name_encoding: str = "ascii",
) -> Iterator[ShapeFeature]:
    archive = Path(zip_path)
    with zipfile.ZipFile(archive) as zip_file:
        shp_data = zip_file.read(zip_member(zip_file, layer_name, ".shp"))
        dbf_data = zip_file.read(zip_member(zip_file, layer_name, ".dbf"))
    yield from iter_shape_features_from_buffers(
        shp_data,
        dbf_data,
        fields=fields,
        encoding=encoding,
        field_name_encoding=field_name_encoding,
        source_name=f"{archive}:{layer_name}",
    )


def iter_shape_features_from_buffers(
    shp_data: bytes,
    dbf_data: bytes,
    *,
    fields: Sequence[str] | None = None,
    encoding: str = "cp949",
    field_name_encoding: str = "ascii",
    source_name: str = "<buffer>",
) -> Iterator[ShapeFeature]:
    layout = parse_dbf_header(dbf_data, field_name_encoding=field_name_encoding)
    selected = tuple(fields) if fields is not None else tuple(field.name for field in layout.fields)
    offsets = _dbf_offsets(layout, selected)
    geometries = iter_shp_geometries_from_bytes(shp_data, source_name=source_name)
    seen_records = 0
    for index, geometry in enumerate(geometries):
        if index >= layout.row_count:
            msg = f"SHP has more records than DBF in {source_name}"
            raise LoaderError(msg)
        record = _dbf_record(dbf_data, layout, index, source_name=source_name)
        seen_records += 1
        if record[:1] == b"*":
            continue
        yield ShapeFeature(
            record_number=geometry.record_number,
            attributes={
                field: _decode_dbf_value(
                    record[offset : offset + length],
                    encoding=encoding,
                    source_name=source_name,
                    field_name=field,
                    record_number=geometry.record_number,
                )
                for field, (offset, length) in offsets.items()
            },
            geometry=geometry,
        )
    if seen_records != layout.row_count:
        msg = f"DBF has more records than SHP in {source_name}"
        raise LoaderError(msg)


def staging_create_sql(spec: ShapeStagingSpec) -> str:
    table_name = _quote_ident_path(spec.table_name)
    table_kind = "TEMP TABLE" if spec.temporary else "TABLE"
    column_sql = [
        f"{_quote_ident(column.name)} {_sql_type(column.sql_type)}" for column in spec.columns
    ]
    column_sql.append(
        f"{_quote_ident(spec.geom_column)} "
        f"geometry({_geometry_type(spec.geometry_type)}, {spec.srid})"
    )
    suffix = " ON COMMIT DROP" if spec.temporary and spec.on_commit_drop else ""
    return f"CREATE {table_kind} {table_name} ({', '.join(column_sql)}){suffix}"


def staging_copy_sql(spec: ShapeStagingSpec) -> str:
    columns = (*(column.name for column in spec.columns), spec.geom_column)
    quoted = ", ".join(_quote_ident(column) for column in columns)
    return f"COPY {_quote_ident_path(spec.table_name)} ({quoted}) FROM STDIN"


def staging_key_index_sql(spec: StagingKeyIndexSpec) -> str:
    if not spec.columns:
        msg = "staging key index requires at least one column"
        raise LoaderError(msg)
    columns = tuple(_quote_ident(column) for column in spec.columns)
    where = ""
    if spec.where_not_null:
        where = " WHERE " + " AND ".join(
            f"{_quote_ident(column)} IS NOT NULL" for column in spec.columns
        )
    return (
        f"CREATE INDEX {_quote_ident(spec.index_name)} "
        f"ON {_quote_ident_path(spec.table_name)} ({', '.join(columns)}){where}"
    )


def analyze_table_sql(table_name: str) -> str:
    return f"ANALYZE {_quote_ident_path(table_name)}"


async def recreate_shape_staging_table(engine: AsyncEngine, spec: ShapeStagingSpec) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {_quote_ident_path(spec.table_name)}"))
        await conn.execute(text(staging_create_sql(spec)))


async def create_staging_key_indexes(
    engine: AsyncEngine,
    specs: Sequence[StagingKeyIndexSpec],
    *,
    analyze: bool = True,
) -> None:
    if not specs:
        return
    async with engine.begin() as conn:
        for spec in specs:
            await conn.execute(text(staging_key_index_sql(spec)))
        if analyze:
            for table_name in dict.fromkeys(spec.table_name for spec in specs):
                await conn.execute(text(analyze_table_sql(table_name)))


async def copy_shape_features_to_staging(
    engine: AsyncEngine,
    spec: ShapeStagingSpec,
    features: Iterable[ShapeFeature],
) -> int:
    copied = 0
    async with await psycopg.AsyncConnection.connect(
        _alchemy_to_libpq(engine),
        autocommit=False,
    ) as conn, conn.cursor() as cur:
        async with cur.copy(staging_copy_sql(spec)) as copy:
            for feature in features:
                ewkt = feature.geometry.ewkt_5179
                if ewkt is None:
                    continue
                row = (
                    *(
                        feature.attributes.get(column.source_field or column.name)
                        for column in spec.columns
                    ),
                    ewkt,
                )
                await copy.write_row(row)
                copied += 1
        await conn.commit()
    return copied


async def copy_shape_file_to_staging(
    engine: AsyncEngine,
    spec: ShapeStagingSpec,
    shp_path: Path | str,
    dbf_path: Path | str,
    *,
    fields: Sequence[str] | None = None,
) -> int:
    return await copy_shape_features_to_staging(
        engine,
        spec,
        iter_shape_features(shp_path, dbf_path, fields=fields),
    )


async def copy_zip_shape_layer_to_staging(
    engine: AsyncEngine,
    spec: ShapeStagingSpec,
    zip_path: Path | str,
    layer_name: str,
    *,
    fields: Sequence[str] | None = None,
) -> int:
    return await copy_shape_features_to_staging(
        engine,
        spec,
        iter_zip_shape_features(zip_path, layer_name, fields=fields),
    )


def keyed_distance_sql(
    left_table: str,
    right_table: str,
    key_pairs: Sequence[JoinKey],
    *,
    left_geom: str = "geom",
    right_geom: str = "geom",
) -> str:
    join_sql = _join_condition("l", "r", key_pairs)
    sample_columns = _sample_key_columns("l", "left", tuple(pair.left for pair in key_pairs))
    sample_columns += _sample_key_columns("r", "right", tuple(pair.right for pair in key_pairs))
    return f"""
WITH joined AS (
  SELECT
    {sample_columns}
    ST_Distance(l.{_quote_ident(left_geom)}, r.{_quote_ident(right_geom)})::float8 AS distance_m
  FROM {_quote_ident_path(left_table)} l
  JOIN {_quote_ident_path(right_table)} r
    ON {join_sql}
 WHERE l.{_quote_ident(left_geom)} IS NOT NULL
   AND r.{_quote_ident(right_geom)} IS NOT NULL
),
stats AS (
  SELECT
    count(*)::bigint AS samples,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY distance_m)::float8 AS p50_m,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY distance_m)::float8 AS p95_m,
    max(distance_m)::float8 AS max_m
  FROM joined
),
sample AS (
  SELECT *
    FROM joined
   ORDER BY distance_m DESC NULLS LAST
   LIMIT :sample_limit
)
SELECT
  stats.samples,
  stats.p50_m,
  stats.p95_m,
  stats.max_m,
  COALESCE((SELECT jsonb_agg(to_jsonb(sample)) FROM sample), '[]'::jsonb) AS sample
FROM stats
"""


def key_overlap_sql(
    left_table: str,
    right_table: str,
    key_pairs: Sequence[JoinKey],
) -> str:
    _validate_key_pairs(key_pairs)
    left_select = _key_alias_columns("l", tuple(pair.left for pair in key_pairs))
    right_select = _key_alias_columns("r", tuple(pair.right for pair in key_pairs))
    left_where = _nonnull_key_condition("l", tuple(pair.left for pair in key_pairs))
    right_where = _nonnull_key_condition("r", tuple(pair.right for pair in key_pairs))
    using_columns = ", ".join(_quote_ident(f"k{index}") for index in range(len(key_pairs)))
    return f"""
WITH left_source AS (
  SELECT {left_select}
    FROM {_quote_ident_path(left_table)} l
   WHERE {left_where}
),
right_source AS (
  SELECT {right_select}
    FROM {_quote_ident_path(right_table)} r
   WHERE {right_where}
),
left_keys AS (
  SELECT DISTINCT * FROM left_source
),
right_keys AS (
  SELECT DISTINCT * FROM right_source
),
intersection_keys AS (
  SELECT left_keys.*
    FROM left_keys
    JOIN right_keys USING ({using_columns})
)
SELECT
  (SELECT count(*)::bigint FROM left_source) AS left_rows,
  (SELECT count(*)::bigint FROM right_source) AS right_rows,
  (SELECT count(*)::bigint FROM left_keys) AS left_distinct,
  (SELECT count(*)::bigint FROM right_keys) AS right_distinct,
  (SELECT count(*)::bigint FROM intersection_keys) AS intersection_count,
  (
    (SELECT count(*)::bigint FROM left_keys)
    - (SELECT count(*)::bigint FROM intersection_keys)
  ) AS left_only_count,
  (
    (SELECT count(*)::bigint FROM right_keys)
    - (SELECT count(*)::bigint FROM intersection_keys)
  ) AS right_only_count
"""


def keyed_covers_sql(
    covering_table: str,
    covered_table: str,
    key_pairs: Sequence[JoinKey],
    *,
    covering_geom: str = "geom",
    covered_geom: str = "geom",
) -> str:
    join_sql = _join_condition("c", "p", key_pairs)
    sample_columns = _sample_key_columns("c", "covering", tuple(pair.left for pair in key_pairs))
    sample_columns += _sample_key_columns("p", "covered", tuple(pair.right for pair in key_pairs))
    return f"""
WITH joined AS (
  SELECT
    {sample_columns}
    ST_Covers(c.{_quote_ident(covering_geom)}, p.{_quote_ident(covered_geom)}) AS covered
  FROM {_quote_ident_path(covering_table)} c
  JOIN {_quote_ident_path(covered_table)} p
    ON {join_sql}
 WHERE c.{_quote_ident(covering_geom)} IS NOT NULL
   AND p.{_quote_ident(covered_geom)} IS NOT NULL
),
stats AS (
  SELECT
    count(*)::bigint AS samples,
    count(*) FILTER (WHERE covered)::bigint AS covered,
    count(*) FILTER (WHERE NOT covered)::bigint AS outside
  FROM joined
),
sample AS (
  SELECT *
    FROM joined
   WHERE NOT covered
   LIMIT :sample_limit
)
SELECT
  stats.samples,
  stats.covered,
  stats.outside,
  CASE
    WHEN stats.samples = 0 THEN NULL
    ELSE stats.covered::float8 / stats.samples::float8
  END AS coverage_ratio,
  COALESCE((SELECT jsonb_agg(to_jsonb(sample)) FROM sample), '[]'::jsonb) AS sample
FROM stats
"""


async def measure_keyed_distance(
    engine: AsyncEngine,
    left_table: str,
    right_table: str,
    key_pairs: Sequence[JoinKey],
    *,
    sample_limit: int = 20,
    left_geom: str = "geom",
    right_geom: str = "geom",
) -> DistanceMeasurement:
    sql = keyed_distance_sql(
        left_table,
        right_table,
        key_pairs,
        left_geom=left_geom,
        right_geom=right_geom,
    )
    async with engine.connect() as conn:
        row = (
            await conn.execute(text(sql), {"sample_limit": sample_limit})
        ).mappings().one()
    return DistanceMeasurement(
        samples=int(row["samples"] or 0),
        p50_m=_optional_float(row["p50_m"]),
        p95_m=_optional_float(row["p95_m"]),
        max_m=_optional_float(row["max_m"]),
        sample=_jsonb_sample(row["sample"]),
    )


async def measure_key_overlap(
    engine: AsyncEngine,
    left_table: str,
    right_table: str,
    key_pairs: Sequence[JoinKey],
) -> KeyOverlapMeasurement:
    sql = key_overlap_sql(left_table, right_table, key_pairs)
    async with engine.connect() as conn:
        row = (await conn.execute(text(sql))).mappings().one()
    return KeyOverlapMeasurement(
        left_rows=int(row["left_rows"] or 0),
        right_rows=int(row["right_rows"] or 0),
        left_distinct=int(row["left_distinct"] or 0),
        right_distinct=int(row["right_distinct"] or 0),
        intersection_count=int(row["intersection_count"] or 0),
        left_only_count=int(row["left_only_count"] or 0),
        right_only_count=int(row["right_only_count"] or 0),
    )


async def measure_keyed_covers(
    engine: AsyncEngine,
    covering_table: str,
    covered_table: str,
    key_pairs: Sequence[JoinKey],
    *,
    sample_limit: int = 20,
    covering_geom: str = "geom",
    covered_geom: str = "geom",
) -> CoversMeasurement:
    sql = keyed_covers_sql(
        covering_table,
        covered_table,
        key_pairs,
        covering_geom=covering_geom,
        covered_geom=covered_geom,
    )
    async with engine.connect() as conn:
        row = (
            await conn.execute(text(sql), {"sample_limit": sample_limit})
        ).mappings().one()
    return CoversMeasurement(
        samples=int(row["samples"] or 0),
        covered=int(row["covered"] or 0),
        outside=int(row["outside"] or 0),
        coverage_ratio=_optional_float(row["coverage_ratio"]),
        sample=_jsonb_sample(row["sample"]),
    )


def _parse_shape_record(
    record_number: int,
    content: bytes,
    *,
    source_name: str,
) -> ShapeGeometry:
    if len(content) < 4:
        msg = f"truncated SHP record {record_number} in {source_name}"
        raise LoaderError(msg)
    shape_type = struct.unpack("<i", content[:4])[0]
    if shape_type == 0:
        return ShapeGeometry(record_number, "Null", None, None, 0, 0)
    if shape_type == 1:
        if len(content) < 20:
            msg = f"truncated point SHP record {record_number} in {source_name}"
            raise LoaderError(msg)
        x, y = struct.unpack("<2d", content[4:20])
        point = (_fmt_num(x), _fmt_num(y))
        return ShapeGeometry(
            record_number=record_number,
            shape_kind="Point",
            wkt=f"POINT ({point[0]} {point[1]})",
            bbox=(x, y, x, y),
            part_count=1,
            point_count=1,
        )
    if shape_type in {3, 5}:
        return _parse_parted_shape(record_number, content, shape_type, source_name=source_name)
    msg = f"unsupported SHP shape type {shape_type} in {source_name} record {record_number}"
    raise LoaderError(msg)


def _parse_parted_shape(
    record_number: int,
    content: bytes,
    shape_type: int,
    *,
    source_name: str,
) -> ShapeGeometry:
    if len(content) < 44:
        msg = f"truncated SHP record {record_number} in {source_name}"
        raise LoaderError(msg)
    bbox = struct.unpack("<4d", content[4:36])
    part_count, point_count = struct.unpack("<2i", content[36:44])
    if part_count < 0 or point_count < 0:
        msg = f"invalid SHP counts in {source_name} record {record_number}"
        raise LoaderError(msg)
    parts_offset = 44
    points_offset = parts_offset + part_count * 4
    expected_length = points_offset + point_count * 16
    if len(content) < expected_length:
        msg = f"truncated SHP points in {source_name} record {record_number}"
        raise LoaderError(msg)
    parts = (
        struct.unpack(f"<{part_count}i", content[parts_offset:points_offset])
        if part_count
        else ()
    )
    points = [
        struct.unpack("<2d", content[points_offset + index * 16 : points_offset + (index + 1) * 16])
        for index in range(point_count)
    ]
    sequences = _part_sequences(parts, points, source_name=source_name, record_number=record_number)
    if shape_type == 3:
        wkt = _polyline_wkt(sequences)
        shape_kind: ShapeKind = "PolyLine"
    else:
        wkt = _polygon_wkt(sequences)
        shape_kind = "Polygon"
    return ShapeGeometry(
        record_number=record_number,
        shape_kind=shape_kind,
        wkt=wkt,
        bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
        part_count=part_count,
        point_count=point_count,
    )


def _part_sequences(
    parts: Sequence[int],
    points: Sequence[tuple[float, float]],
    *,
    source_name: str,
    record_number: int,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    if not parts and points:
        return (tuple(points),)
    if not parts:
        return ()
    indexes = (*tuple(parts), len(points))
    sequences: list[tuple[tuple[float, float], ...]] = []
    previous = 0
    for index in indexes:
        if index < previous or index > len(points):
            msg = f"invalid SHP part index in {source_name} record {record_number}"
            raise LoaderError(msg)
        if index > previous:
            sequences.append(tuple(points[previous:index]))
        previous = index
    return tuple(sequences)


def _polyline_wkt(sequences: Sequence[Sequence[tuple[float, float]]]) -> str:
    lines = tuple(_coords_wkt(sequence) for sequence in sequences if len(sequence) >= 2)
    if not lines:
        return "LINESTRING EMPTY"
    if len(lines) == 1:
        return f"LINESTRING ({lines[0]})"
    return "MULTILINESTRING (" + ", ".join(f"({line})" for line in lines) + ")"


def _polygon_wkt(sequences: Sequence[Sequence[tuple[float, float]]]) -> str:
    rings = tuple(_closed_ring(sequence) for sequence in sequences if len(sequence) >= 3)
    if not rings:
        return "POLYGON EMPTY"
    shells = [ring for ring in rings if _ring_area(ring) < 0]
    holes = [ring for ring in rings if _ring_area(ring) >= 0]
    if not shells:
        shells = list(rings)
        holes = []
    shell_holes: list[
        tuple[tuple[tuple[float, float], ...], list[tuple[tuple[float, float], ...]]]
    ] = [
        (shell, []) for shell in shells
    ]
    for hole in holes:
        point = hole[0]
        target = next(
            (
                index
                for index, (shell, _assigned) in enumerate(shell_holes)
                if _point_in_ring(point, shell)
            ),
            None,
        )
        if target is None:
            shell_holes.append((hole, []))
        else:
            shell_holes[target][1].append(hole)

    polygons = tuple(
        "(" + ", ".join(_ring_wkt(ring) for ring in (shell, *assigned_holes)) + ")"
        for shell, assigned_holes in shell_holes
    )
    if len(polygons) == 1:
        return f"POLYGON {polygons[0]}"
    return "MULTIPOLYGON (" + ", ".join(polygons) + ")"


def _closed_ring(points: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    ring = tuple(points)
    if ring[0] == ring[-1]:
        return ring
    return (*ring, ring[0])


def _ring_wkt(points: Sequence[tuple[float, float]]) -> str:
    return f"({_coords_wkt(points)})"


def _coords_wkt(points: Sequence[tuple[float, float]]) -> str:
    return ", ".join(f"{_fmt_num(x)} {_fmt_num(y)}" for x, y in points)


def _fmt_num(value: float) -> str:
    if not math.isfinite(value):
        msg = f"non-finite SHP coordinate: {value}"
        raise LoaderError(msg)
    return format(value, ".15g")


def _ring_area(points: Sequence[tuple[float, float]]) -> float:
    return sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in pairwise(points)
    ) / 2.0


def _point_in_ring(point: tuple[float, float], ring: Sequence[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in pairwise(ring):
        if (y1 > y) == (y2 > y):
            continue
        x_intersect = (x2 - x1) * (y - y1) / (y2 - y1) + x1
        if x < x_intersect:
            inside = not inside
    return inside


def _dbf_offsets(
    layout: DbfLayout,
    fields: Sequence[str],
) -> dict[str, tuple[int, int]]:
    by_name = {field.name: (field.offset, field.length) for field in layout.fields}
    missing = [field for field in fields if field not in by_name]
    if missing:
        msg = "missing DBF field(s): " + ", ".join(missing)
        raise LoaderError(msg)
    return {field: by_name[field] for field in fields}


def _dbf_record(
    data: bytes,
    layout: DbfLayout,
    index: int,
    *,
    source_name: str,
) -> bytes:
    start = layout.header_length + index * layout.record_length
    record = data[start : start + layout.record_length]
    if len(record) != layout.record_length:
        msg = f"truncated DBF record {index + 1} in {source_name}"
        raise LoaderError(msg)
    return record


def _decode_dbf_value(
    raw: bytes,
    *,
    encoding: str,
    source_name: str,
    field_name: str,
    record_number: int,
) -> str | None:
    try:
        value = raw.rstrip(b"\x00").decode(encoding).strip()
    except UnicodeDecodeError as exc:
        msg = f"{source_name}:{record_number} field {field_name} failed {encoding} decode: {exc}"
        raise LoaderError(msg) from exc
    return value or None


def _alchemy_to_libpq(engine: AsyncEngine) -> str:
    return engine.url.set(drivername="postgresql").render_as_string(hide_password=False)


def _join_condition(left_alias: str, right_alias: str, key_pairs: Sequence[JoinKey]) -> str:
    _validate_key_pairs(key_pairs)
    return " AND ".join(
        f"{left_alias}.{_quote_ident(pair.left)} = {right_alias}.{_quote_ident(pair.right)}"
        for pair in key_pairs
    )


def _validate_key_pairs(key_pairs: Sequence[JoinKey]) -> None:
    if not key_pairs:
        msg = "at least one join key is required"
        raise LoaderError(msg)


def _key_alias_columns(alias: str, columns: Sequence[str]) -> str:
    return ", ".join(
        f"{alias}.{_quote_ident(column)}::text AS {_quote_ident(f'k{index}')}"
        for index, column in enumerate(columns)
    )


def _nonnull_key_condition(alias: str, columns: Sequence[str]) -> str:
    return " AND ".join(f"{alias}.{_quote_ident(column)} IS NOT NULL" for column in columns)


def _sample_key_columns(alias: str, prefix: str, columns: Sequence[str]) -> str:
    if not columns:
        return ""
    return "".join(
        f"{alias}.{_quote_ident(column)}::text AS {_quote_ident(prefix + '_' + column)}, "
        for column in columns
    )


def _quote_ident_path(value: str) -> str:
    return ".".join(_quote_ident(part) for part in value.split("."))


def _quote_ident(value: str) -> str:
    if not _IDENT_RE.fullmatch(value):
        msg = f"invalid SQL identifier: {value!r}"
        raise LoaderError(msg)
    return f'"{value}"'


def _sql_type(value: str) -> str:
    normalized = " ".join(value.split())
    if not _SQL_TYPE_RE.fullmatch(normalized):
        msg = f"invalid staging SQL type: {value!r}"
        raise LoaderError(msg)
    return normalized


def _geometry_type(value: str) -> str:
    if not _IDENT_RE.fullmatch(value):
        msg = f"invalid geometry type: {value!r}"
        raise LoaderError(msg)
    return value


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
