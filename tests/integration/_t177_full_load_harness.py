"""T-177 file-driven full-load e2e harness helpers."""

from __future__ import annotations

import json
import os
import re
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from kortravelgeo.core.source_layers import POLYGON_LAYER_NAMES
from kortravelgeo.exceptions import LoaderError
from kortravelgeo.infra.sql import INDEX_SQL, SCHEMA_SQL, iter_sql_statements
from kortravelgeo.loaders.juso_map import discover_sido_datasets
from kortravelgeo.loaders.manifest import infer_yyyymm
from kortravelgeo.loaders.shp.polygons_loader import build_shp_load_plan, load_shp_polygons
from kortravelgeo.loaders.sppn_makarea_loader import discover_sppn_makarea_sources
from kortravelgeo.loaders.text.daily_juso_loader import discover_daily_juso_sources
from kortravelgeo.loaders.text.juso_hangul_loader import discover_juso_hangul_files
from kortravelgeo.loaders.text.locsum_loader import discover_locsum_files
from kortravelgeo.loaders.text.navi_loader import (
    discover_navi_build_files,
    discover_navi_entrance_files,
)
from kortravelgeo.loaders.text.parcel_link_loader import (
    discover_daily_lnbr_sources,
    discover_jibun_rnaddrkor_files,
)
from kortravelgeo.loaders.text.roadaddr_entrance_loader import (
    discover_roadaddr_entrance_sources,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from kortravelgeo.loaders.text.common import TextSource

ENV_ENABLED = "KTG_TEST_FULL_LOAD_E2E"
ENV_DSN = "KTG_TEST_PG_DSN"
ENV_CONFIRM = "KTG_TEST_FULL_LOAD_E2E_CONFIRM"
ENV_DATA_ROOT = "KTG_TEST_FULL_LOAD_E2E_DATA_ROOT"
ENV_ARTIFACT_DIR = "KTG_TEST_FULL_LOAD_E2E_ARTIFACT_DIR"
ENV_RUN_ID = "KTG_TEST_FULL_LOAD_E2E_RUN_ID"
ENV_ALLOW_NONEMPTY = "KTG_TEST_FULL_LOAD_E2E_ALLOW_NONEMPTY"
ENV_SAMPLE_LIMIT = "KTG_TEST_FULL_LOAD_E2E_SAMPLE_LIMIT"
CONFIRM_PREFIX = "RUN-T177-E2E"
DEFAULT_SAMPLE_LIMIT_PER_FILE = 2

DEFAULT_DATA_ROOTS = (
    Path("data/juso"),
    Path("/mnt/f/dev/geodata/juso"),
    Path("/mnt/f/dev/kor-travel-geo/data/juso"),
    Path("/home/digitie/kor-travel-geo-data/juso"),
)

REQUIRED_EXTENSION_PACKAGES = frozenset(
    {"postgis", "pg_trgm", "unaccent", "pg_stat_statements"}
)

SCHEMA_SMOKE_OBJECTS = (
    "public.tl_juso_text",
    "public.tl_juso_parcel_link",
    "public.tl_locsum_entrc",
    "public.tl_navi_buld_centroid",
    "public.tl_navi_entrc",
    "public.tl_roadaddr_entrc",
    "public.tl_sppn_makarea",
    "public.load_manifest",
    "ops.dataset_snapshots",
)

ROW_GUARD_TABLES = (
    "public.tl_juso_text",
    "public.tl_juso_parcel_link",
    "public.tl_locsum_entrc",
    "public.tl_navi_buld_centroid",
    "public.tl_navi_entrc",
    "public.tl_roadaddr_entrc",
    "public.tl_sppn_makarea",
    "public.load_manifest",
    "ops.dataset_snapshots",
    "ops.serving_releases",
)

T177C_TARGET_TABLES = (
    "public.tl_juso_parcel_link",
    "public.tl_locsum_entrc",
    "public.tl_navi_entrc",
    "public.tl_navi_buld_centroid",
    "public.tl_juso_text",
    "public.load_manifest",
)

T177C_MANIFEST_TABLES = ("tl_juso_text", "tl_juso_parcel_link")

T177D_TARGET_TABLES = (
    "public.tl_scco_ctprvn",
    "public.tl_scco_sig",
    "public.tl_scco_emd",
    "public.tl_scco_li",
    "public.tl_kodis_bas",
    "public.tl_sprd_manage",
    "public.tl_sprd_intrvl",
    "public.tl_sprd_rw",
    "public.tl_spbd_buld_polygon",
    "public.region_radius_parts",
)

T177D_REQUIRED_NONEMPTY_TABLES = (
    "public.tl_scco_ctprvn",
    "public.tl_scco_sig",
    "public.tl_scco_emd",
    "public.tl_kodis_bas",
    "public.tl_sprd_manage",
    "public.tl_sprd_intrvl",
    "public.tl_sprd_rw",
    "public.tl_spbd_buld_polygon",
)

T177D_GEOMETRY_TABLES: Mapping[str, str] = {
    "public.tl_scco_ctprvn": "ST_MultiPolygon",
    "public.tl_scco_sig": "ST_MultiPolygon",
    "public.tl_scco_emd": "ST_MultiPolygon",
    "public.tl_scco_li": "ST_MultiPolygon",
    "public.tl_kodis_bas": "ST_MultiPolygon",
    "public.tl_sprd_manage": "ST_MultiLineString",
    "public.tl_sprd_rw": "ST_MultiPolygon",
    "public.tl_spbd_buld_polygon": "ST_MultiPolygon",
}

T177D_NON_GEOMETRY_TABLES = ("public.tl_sprd_intrvl",)

T177E_TARGET_TABLES = (
    "public.tl_roadaddr_entrc",
    "public.tl_sppn_makarea",
    "public.load_manifest",
)

T177E_MANIFEST_TABLES = ("tl_roadaddr_entrc", "tl_sppn_makarea")

T177F_SERVING_OBJECTS = (
    "public.mv_geocode_target",
    "public.mv_geocode_text_search",
    "public.region_radius_parts",
    "public.load_consistency_reports",
)

T177F_CONSISTENCY_CASES = tuple(f"C{index}" for index in range(1, 11))

_T177F_LINK_EVIDENCE_SQL = """
WITH locsum_bd AS MATERIALIZED (
  SELECT DISTINCT bd_mgt_sn
    FROM public.tl_locsum_entrc
   WHERE bd_mgt_sn IS NOT NULL
),
base AS (
  SELECT
    (SELECT count(*) FROM public.tl_juso_text) AS text_rows,
    (SELECT count(*) FROM public.tl_locsum_entrc) AS locsum_rows,
    (SELECT count(*) FROM public.tl_locsum_entrc WHERE bd_mgt_sn IS NOT NULL)
      AS locsum_resolved_rows
),
linked AS (
  SELECT
    count(*) AS locsum_serving_rows,
    count(*) FILTER (
      WHERE target.pt_4326 IS NOT NULL
        AND target.pt_5179 IS NOT NULL
        AND target.rn_nrm IS NOT NULL
        AND target.rn_nrm <> ''
        AND target.zip_no IS NOT NULL
    ) AS locsum_smokeable_serving_rows
    FROM public.mv_geocode_target target
    JOIN locsum_bd USING (bd_mgt_sn)
)
SELECT
  base.text_rows,
  base.locsum_rows,
  base.locsum_resolved_rows,
  linked.locsum_serving_rows,
  linked.locsum_smokeable_serving_rows
  FROM base
  CROSS JOIN linked
"""


class T177SkipError(RuntimeError):
    """Raised when the opt-in T-177 e2e test should skip cleanly."""


class T177PreflightError(RuntimeError):
    """Raised when an explicit opt-in T-177 e2e run is unsafe."""


@dataclass(frozen=True, slots=True)
class T177Runtime:
    dsn: str
    data_root: Path
    artifact_dir: Path
    run_id: str


@dataclass(frozen=True, slots=True)
class T177TextDeltaSourcePaths:
    juso_hangul: Path
    jibun_rnaddrkor: Path
    daily_juso: Path
    daily_lnbr: Path
    locsum: Path
    navi: Path


@dataclass(frozen=True, slots=True)
class T177ShpGeometrySource:
    electronic_map_root: Path
    sido_path: Path
    sido_name: str
    sig_code: str
    source_yyyymm: str | None
    archive_path: Path | None = None
    materialized: bool = False


@dataclass(frozen=True, slots=True)
class T177SupplementalSourcePaths:
    roadaddr_entrance: Path
    roadaddr_entrance_plan_yyyymm: str | None
    sppn_makarea: Path
    sppn_makarea_source_yyyymm: str | None


@dataclass(frozen=True, slots=True)
class T177DatabasePreflight:
    database_name: str
    expected_confirmation: str
    destructive_confirmed: bool
    available_extensions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceDiscoverySummary:
    kind: str
    path: str | None
    exists: bool
    source_yyyymm: str | None
    source_count: int
    sample_names: tuple[str, ...]
    error: str | None = None
    notes: tuple[str, ...] = ()


SourceDiscoverer = Callable[[Path], tuple[int, tuple[str, ...], tuple[str, ...]]]


def runtime_from_env(
    environ: Mapping[str, str] | None = None,
    *,
    cwd: Path | None = None,
) -> T177Runtime:
    env = environ if environ is not None else os.environ
    if env.get(ENV_ENABLED) != "1":
        raise T177SkipError(f"set {ENV_ENABLED}=1 to run T-177 file-driven full-load e2e")
    dsn = env.get(ENV_DSN)
    if not dsn:
        raise T177SkipError(f"set {ENV_DSN} to a disposable PostgreSQL/PostGIS scratch DB")
    data_root = resolve_data_root(env)
    if data_root is None:
        candidates = ", ".join(str(path) for path in candidate_data_roots(env))
        raise T177SkipError(f"actual Juso data root is not available; checked: {candidates}")

    run_id = env.get(ENV_RUN_ID) or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = _artifact_dir(env, run_id=run_id, cwd=cwd or Path.cwd())
    return T177Runtime(
        dsn=dsn,
        data_root=data_root,
        artifact_dir=artifact_dir,
        run_id=run_id,
    )


def sample_limit_from_env(environ: Mapping[str, str] | None = None) -> int:
    env = environ if environ is not None else os.environ
    raw = env.get(ENV_SAMPLE_LIMIT)
    if raw is None:
        return DEFAULT_SAMPLE_LIMIT_PER_FILE
    try:
        value = int(raw)
    except ValueError as exc:
        raise T177PreflightError(f"{ENV_SAMPLE_LIMIT} must be a positive integer") from exc
    if value < 1:
        raise T177PreflightError(f"{ENV_SAMPLE_LIMIT} must be a positive integer")
    return value


def candidate_data_roots(environ: Mapping[str, str] | None = None) -> tuple[Path, ...]:
    env = environ if environ is not None else os.environ
    configured = env.get(ENV_DATA_ROOT)
    if configured:
        return (Path(configured).expanduser(),)
    return DEFAULT_DATA_ROOTS


def resolve_data_root(environ: Mapping[str, str] | None = None) -> Path | None:
    for root in candidate_data_roots(environ):
        if root.exists():
            return root
    return None


def looks_like_t177_scratch_database(database_name: str) -> bool:
    normalized = database_name.lower()
    return (
        "t177" in normalized
        or "test" in normalized
        or "scratch" in normalized
        or normalized.startswith("tmp_")
    )


def expected_confirmation(database_name: str) -> str:
    return f"{CONFIRM_PREFIX} {database_name}"


def validate_t177_confirmation(database_name: str, supplied: str | None) -> None:
    if not looks_like_t177_scratch_database(database_name):
        raise T177PreflightError(
            f"{ENV_DSN} must point to a scratch DB whose name includes "
            f"'t177', 'test', or 'scratch'; got {database_name!r}"
        )
    expected = expected_confirmation(database_name)
    if supplied != expected:
        raise T177PreflightError(f"set {ENV_CONFIRM}={expected!r} before destructive T-177 e2e")


async def validate_database_preflight(
    engine: AsyncEngine,
    *,
    confirmation: str | None,
) -> T177DatabasePreflight:
    async with engine.connect() as conn:
        database_name = await conn.scalar(text("SELECT current_database()"))
        rows = (
            await conn.execute(
                text(
                    """
SELECT name
  FROM pg_available_extensions
 WHERE name IN ('postgis', 'pg_trgm', 'unaccent', 'pg_stat_statements')
"""
                )
            )
        ).scalars()
        available_extensions = tuple(sorted(str(row) for row in rows))
    if database_name is None:
        raise T177PreflightError("could not resolve current PostgreSQL database name")
    database = str(database_name)
    validate_t177_confirmation(database, confirmation)
    missing = REQUIRED_EXTENSION_PACKAGES - set(available_extensions)
    if missing:
        joined = ", ".join(sorted(missing))
        raise T177PreflightError(f"PostgreSQL instance is missing required extensions: {joined}")
    return T177DatabasePreflight(
        database_name=database,
        expected_confirmation=expected_confirmation(database),
        destructive_confirmed=True,
        available_extensions=available_extensions,
    )


async def apply_schema_index_smoke(engine: AsyncEngine) -> None:
    for sql_block in (SCHEMA_SQL, INDEX_SQL):
        for sql in iter_sql_statements(sql_block):
            async with engine.connect() as conn:
                await conn.execution_options(isolation_level="AUTOCOMMIT")
                try:
                    await conn.execute(text(sql))
                except ProgrammingError as exc:
                    if "already exists" not in str(exc).lower():
                        raise


async def schema_smoke_report(engine: AsyncEngine) -> dict[str, Any]:
    async with engine.connect() as conn:
        objects: dict[str, bool] = {}
        for object_name in SCHEMA_SMOKE_OBJECTS:
            exists = await conn.scalar(
                text("SELECT to_regclass(:object_name) IS NOT NULL"),
                {"object_name": object_name},
            )
            objects[object_name] = bool(exists)
        extension_rows = (
            await conn.execute(
                text(
                    """
SELECT extname
  FROM pg_extension
 WHERE extname IN ('postgis', 'pg_trgm', 'unaccent', 'pg_stat_statements')
"""
                )
            )
        ).scalars()

    extensions = tuple(sorted(str(value) for value in extension_rows))
    return {
        "objects": objects,
        "missing_objects": [name for name, exists in objects.items() if not exists],
        "extensions": extensions,
    }


async def collect_existing_row_counts(engine: AsyncEngine) -> dict[str, int]:
    counts: dict[str, int] = {}
    async with engine.connect() as conn:
        for table_name in ROW_GUARD_TABLES:
            exists = await conn.scalar(
                text("SELECT to_regclass(:table_name) IS NOT NULL"),
                {"table_name": table_name},
            )
            if not exists:
                continue
            count = await conn.scalar(text(f"SELECT count(*) FROM {table_name}"))
            counts[table_name] = int(count or 0)
    return counts


def assert_no_existing_rows_without_confirmation(
    counts: Mapping[str, int],
    *,
    destructive_confirmed: bool,
    allow_nonempty: bool = False,
) -> None:
    nonempty = {table: count for table, count in counts.items() if count > 0}
    if nonempty and not (destructive_confirmed and allow_nonempty):
        raise T177PreflightError(
            f"existing T-177 load rows require {ENV_ALLOW_NONEMPTY}=1 after "
            "destructive confirmation: "
            + ", ".join(f"{table}={count}" for table, count in sorted(nonempty.items()))
        )


def build_discovery_plan(data_root: Path) -> dict[str, Any]:
    summaries = (
        _summarize_source(
            "juso_hangul",
            _newest(
                data_root,
                ("20????_도로명주소 한글_전체분", "20????_도로명주소 한글_전체분.zip"),
            ),
            _discover_juso_hangul,
        ),
        _summarize_source(
            "jibun_rnaddrkor",
            _newest(
                data_root,
                ("20????_도로명주소 한글_전체분", "20????_도로명주소 한글_전체분.zip"),
            ),
            _discover_jibun,
        ),
        _summarize_source("daily_juso", _daily_candidate(data_root), _discover_daily_juso),
        _summarize_source("daily_lnbr", _daily_candidate(data_root), _discover_daily_lnbr),
        _summarize_source(
            "locsum",
            _newest(
                data_root,
                ("20????_위치정보요약DB_전체분.zip", "20????_위치정보요약DB_전체분"),
            ),
            _discover_locsum,
        ),
        _summarize_source(
            "navi",
            _newest(
                data_root,
                (
                    "20????_내비게이션용DB_전체분",
                    "20????_내비게이션용DB_전체분.zip",
                    "20????_내비게이션용DB_전체분.7z",
                ),
            ),
            _discover_navi,
        ),
        _summarize_source("electronic_map", _electronic_map_candidate(data_root), _discover_shp),
        _summarize_source(
            "roadaddr_entrance",
            _yyyymm_child_or_root(data_root / "도로명주소 출입구 정보"),
            _discover_roadaddr_entrance,
        ),
        _summarize_source(
            "sppn_makarea",
            _sppn_makarea_candidate(data_root),
            _discover_sppn_makarea,
        ),
    )
    return {
        "data_root": str(data_root),
        "sources": {summary.kind: asdict(summary) for summary in summaries},
    }


def t177c_text_delta_source_paths(discovery_plan: Mapping[str, Any]) -> T177TextDeltaSourcePaths:
    return T177TextDeltaSourcePaths(
        juso_hangul=required_source_path(discovery_plan, "juso_hangul"),
        jibun_rnaddrkor=required_source_path(discovery_plan, "jibun_rnaddrkor"),
        daily_juso=required_source_path(discovery_plan, "daily_juso"),
        daily_lnbr=required_source_path(discovery_plan, "daily_lnbr"),
        locsum=required_source_path(discovery_plan, "locsum"),
        navi=required_source_path(discovery_plan, "navi"),
    )


def t177d_shp_geometry_source(
    discovery_plan: Mapping[str, Any],
    *,
    materialize_dir: Path | None = None,
) -> T177ShpGeometrySource:
    electronic_map_root = required_source_path(discovery_plan, "electronic_map")
    try:
        datasets = discover_sido_datasets(electronic_map_root)
    except LoaderError as exc:
        archives = _electronic_map_archives(electronic_map_root)
        if not archives:
            raise T177SkipError(f"T-177 electronic_map source is not loadable: {exc}") from exc
        if materialize_dir is None:
            raise T177SkipError(
                "T-177 electronic_map ZIP source requires a materialize_dir"
            ) from exc
        archive = _select_electronic_map_archive(archives)
        sido_root = _materialize_electronic_map_archive(archive, materialize_dir)
        try:
            datasets = discover_sido_datasets(sido_root)
        except LoaderError as zip_exc:
            raise T177SkipError(
                f"T-177 electronic_map ZIP source is not loadable after extraction: {zip_exc}"
            ) from zip_exc
        selected = _select_t177d_sido_dataset(datasets)
        return T177ShpGeometrySource(
            electronic_map_root=electronic_map_root,
            sido_path=selected.root,
            sido_name=selected.sido_name,
            sig_code=selected.sig_code,
            source_yyyymm=source_yyyymm(discovery_plan, "electronic_map"),
            archive_path=archive,
            materialized=True,
        )

    selected = _select_t177d_sido_dataset(datasets)
    return T177ShpGeometrySource(
        electronic_map_root=electronic_map_root,
        sido_path=selected.root,
        sido_name=selected.sido_name,
        sig_code=selected.sig_code,
        source_yyyymm=source_yyyymm(discovery_plan, "electronic_map"),
    )


def t177e_supplemental_source_paths(
    discovery_plan: Mapping[str, Any],
) -> T177SupplementalSourcePaths:
    roadaddr_root = required_source_path(discovery_plan, "roadaddr_entrance")
    sppn_root = required_source_path(discovery_plan, "sppn_makarea")
    return T177SupplementalSourcePaths(
        roadaddr_entrance=_select_preferred_zip(roadaddr_root),
        roadaddr_entrance_plan_yyyymm=source_yyyymm(
            discovery_plan,
            "roadaddr_entrance",
        ),
        sppn_makarea=_select_preferred_zip(sppn_root),
        sppn_makarea_source_yyyymm=source_yyyymm(discovery_plan, "sppn_makarea"),
    )


def required_source_path(discovery_plan: Mapping[str, Any], kind: str) -> Path:
    sources = discovery_plan.get("sources")
    if not isinstance(sources, Mapping):
        raise T177SkipError("T-177 discovery plan does not contain sources")
    summary = sources.get(kind)
    if not isinstance(summary, Mapping):
        raise T177SkipError(f"T-177 source discovery is missing required kind: {kind}")
    error = summary.get("error")
    if error:
        raise T177SkipError(f"T-177 source {kind} discovery failed: {error}")
    if not summary.get("exists"):
        raise T177SkipError(f"T-177 source {kind} path does not exist")
    source_count = summary.get("source_count")
    if not isinstance(source_count, int) or source_count < 1:
        raise T177SkipError(f"T-177 source {kind} has no discovered files")
    raw_path = summary.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise T177SkipError(f"T-177 source {kind} has no usable path")
    return Path(raw_path)


def source_yyyymm(discovery_plan: Mapping[str, Any], kind: str) -> str | None:
    sources = discovery_plan.get("sources")
    if not isinstance(sources, Mapping):
        return None
    summary = sources.get(kind)
    if not isinstance(summary, Mapping):
        return None
    value = summary.get("source_yyyymm")
    return value if isinstance(value, str) else None


def write_json_artifact(artifact_dir: Path, filename: str, payload: Mapping[str, Any]) -> Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    destination = artifact_dir / filename
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


async def reset_t177c_target_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
TRUNCATE TABLE
  public.tl_juso_parcel_link,
  public.tl_locsum_entrc,
  public.tl_navi_entrc,
  public.tl_navi_buld_centroid,
  public.tl_juso_text
RESTART IDENTITY CASCADE
"""
            )
        )
        await conn.execute(
            text(
                """
DELETE FROM public.load_manifest
 WHERE table_name IN ('tl_juso_text', 'tl_juso_parcel_link')
"""
            )
        )


async def reset_t177e_target_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
TRUNCATE TABLE
  public.tl_roadaddr_entrc,
  public.tl_sppn_makarea
RESTART IDENTITY CASCADE
"""
            )
        )
        await conn.execute(
            text(
                """
DELETE FROM public.load_manifest
 WHERE table_name IN ('tl_roadaddr_entrc', 'tl_sppn_makarea')
"""
            )
        )


async def collect_t177c_table_counts(engine: AsyncEngine) -> dict[str, int]:
    return await _collect_table_counts(engine, T177C_TARGET_TABLES)


async def collect_t177d_table_counts(engine: AsyncEngine) -> dict[str, int]:
    return await _collect_table_counts(engine, T177D_TARGET_TABLES)


async def collect_t177e_table_counts(engine: AsyncEngine) -> dict[str, int]:
    return await _collect_table_counts(engine, T177E_TARGET_TABLES)


async def collect_t177c_link_counts(engine: AsyncEngine) -> dict[str, int]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
SELECT
  (SELECT count(*) FROM public.tl_locsum_entrc) AS locsum_rows,
  (SELECT count(*) FROM public.tl_locsum_entrc WHERE bd_mgt_sn IS NOT NULL)
    AS locsum_resolved_rows,
  (SELECT count(*) FROM public.tl_navi_entrc) AS navi_entrance_rows,
  (SELECT count(*) FROM public.tl_navi_entrc WHERE bd_mgt_sn IS NOT NULL)
    AS navi_entrance_resolved_rows
"""
                )
            )
        ).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


async def collect_t177c_manifests(engine: AsyncEngine) -> dict[str, Any]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
SELECT table_name, last_mvmn_de, row_count, source_zip, source_yyyymm, source_set
  FROM public.load_manifest
 WHERE table_name IN ('tl_juso_text', 'tl_juso_parcel_link')
 ORDER BY table_name
"""
            )
        )
        rows = list(result.mappings())
    return {
        str(row["table_name"]): {
            "last_mvmn_de": row["last_mvmn_de"],
            "row_count": int(row["row_count"]),
            "source_zip": row["source_zip"],
            "source_yyyymm": row["source_yyyymm"],
            "source_set": _jsonable_source_set(row["source_set"]),
        }
        for row in rows
    }


async def collect_t177e_manifests(engine: AsyncEngine) -> dict[str, Any]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
SELECT table_name, last_full_load_at, last_delta_at, row_count, source_zip,
       source_yyyymm, source_set
  FROM public.load_manifest
 WHERE table_name IN ('tl_roadaddr_entrc', 'tl_sppn_makarea')
 ORDER BY table_name
"""
            )
        )
        rows = list(result.mappings())
    return {
        str(row["table_name"]): {
            "last_full_load_at": _jsonable_model_value(row["last_full_load_at"]),
            "last_delta_at": _jsonable_model_value(row["last_delta_at"]),
            "row_count": int(row["row_count"]),
            "source_zip": row["source_zip"],
            "source_yyyymm": row["source_yyyymm"],
            "source_set": _jsonable_source_set(row["source_set"]),
        }
        for row in rows
    }


async def collect_t177d_geometry_report(
    engine: AsyncEngine,
    *,
    source_yyyymm: str | None,
) -> dict[str, Any]:
    reports: dict[str, Any] = {}
    async with engine.connect() as conn:
        for table_name, expected_geometry_type in T177D_GEOMETRY_TABLES.items():
            row = (
                await conn.execute(
                    text(
                        f"""
SELECT
  count(*) AS row_count,
  count(*) FILTER (WHERE geom IS NOT NULL) AS geom_rows,
  count(*) FILTER (WHERE geom IS NOT NULL AND ST_SRID(geom) = 5179)
    AS srid_5179_rows,
  count(*) FILTER (WHERE geom IS NOT NULL AND ST_IsEmpty(geom))
    AS empty_geom_rows,
  count(*) FILTER (WHERE geom IS NOT NULL AND NOT ST_IsValid(geom))
    AS invalid_geom_rows,
  count(*) FILTER (WHERE source_file IS NOT NULL) AS source_file_rows,
  count(*) FILTER (WHERE source_yyyymm IS NOT DISTINCT FROM :source_yyyymm)
    AS source_yyyymm_rows,
  array_agg(DISTINCT ST_GeometryType(geom)) FILTER (WHERE geom IS NOT NULL)
    AS geometry_types,
  array_agg(DISTINCT source_file) FILTER (WHERE source_file IS NOT NULL)
    AS source_files,
  array_agg(DISTINCT source_yyyymm) FILTER (WHERE source_yyyymm IS NOT NULL)
    AS source_yyyymms
FROM {table_name}
"""
                    ),
                    {"source_yyyymm": source_yyyymm},
                )
            ).mappings().one()
            reports[table_name] = {
                "expected_geometry_type": expected_geometry_type,
                "row_count": _int_report_value(row, "row_count"),
                "geom_rows": _int_report_value(row, "geom_rows"),
                "srid_5179_rows": _int_report_value(row, "srid_5179_rows"),
                "empty_geom_rows": _int_report_value(row, "empty_geom_rows"),
                "invalid_geom_rows": _int_report_value(row, "invalid_geom_rows"),
                "source_file_rows": _int_report_value(row, "source_file_rows"),
                "source_yyyymm_rows": _int_report_value(row, "source_yyyymm_rows"),
                "geometry_types": _distinct_text_values(row["geometry_types"]),
                "source_files": _distinct_text_values(row["source_files"]),
                "source_yyyymms": _distinct_text_values(row["source_yyyymms"]),
            }
    return reports


async def collect_t177e_roadaddr_report(
    engine: AsyncEngine,
    *,
    source_yyyymm: str | None,
) -> dict[str, Any]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
SELECT
  count(*) AS row_count,
  count(*) FILTER (WHERE geom IS NOT NULL) AS geom_rows,
  count(*) FILTER (WHERE geom IS NOT NULL AND ST_SRID(geom) = 5179)
    AS srid_5179_rows,
  count(*) FILTER (WHERE geom IS NOT NULL AND ST_IsEmpty(geom))
    AS empty_geom_rows,
  count(*) FILTER (WHERE geom IS NOT NULL AND NOT ST_IsValid(geom))
    AS invalid_geom_rows,
  count(*) FILTER (WHERE source_file IS NOT NULL) AS source_file_rows,
  count(*) FILTER (WHERE source_yyyymm IS NOT DISTINCT FROM :source_yyyymm)
    AS source_yyyymm_rows,
  array_agg(DISTINCT ST_GeometryType(geom)) FILTER (WHERE geom IS NOT NULL)
    AS geometry_types,
  array_agg(DISTINCT source_file) FILTER (WHERE source_file IS NOT NULL)
    AS source_files,
  array_agg(DISTINCT source_yyyymm) FILTER (WHERE source_yyyymm IS NOT NULL)
    AS source_yyyymms
FROM public.tl_roadaddr_entrc
"""
                ),
                {"source_yyyymm": source_yyyymm},
            )
        ).mappings().one()
    return {
        "expected_geometry_type": "ST_Point",
        "row_count": _int_report_value(row, "row_count"),
        "geom_rows": _int_report_value(row, "geom_rows"),
        "srid_5179_rows": _int_report_value(row, "srid_5179_rows"),
        "empty_geom_rows": _int_report_value(row, "empty_geom_rows"),
        "invalid_geom_rows": _int_report_value(row, "invalid_geom_rows"),
        "source_file_rows": _int_report_value(row, "source_file_rows"),
        "source_yyyymm_rows": _int_report_value(row, "source_yyyymm_rows"),
        "geometry_types": _distinct_text_values(row["geometry_types"]),
        "source_files": _distinct_text_values(row["source_files"]),
        "source_yyyymms": _distinct_text_values(row["source_yyyymms"]),
    }


async def collect_t177e_sppn_report(
    engine: AsyncEngine,
    *,
    source_yyyymm: str | None,
) -> dict[str, Any]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
SELECT
  count(*) AS row_count,
  count(*) FILTER (WHERE geom IS NOT NULL) AS geom_rows,
  count(*) FILTER (WHERE geom IS NOT NULL AND ST_SRID(geom) = 5179)
    AS srid_5179_rows,
  count(*) FILTER (WHERE geom IS NOT NULL AND ST_IsEmpty(geom))
    AS empty_geom_rows,
  count(*) FILTER (WHERE geom IS NOT NULL AND NOT ST_IsValid(geom))
    AS invalid_geom_rows,
  count(*) FILTER (WHERE source_file IS NOT NULL) AS source_file_rows,
  count(*) FILTER (WHERE source_yyyymm IS NOT DISTINCT FROM :source_yyyymm)
    AS source_yyyymm_rows,
  array_agg(DISTINCT ST_GeometryType(geom)) FILTER (WHERE geom IS NOT NULL)
    AS geometry_types,
  array_agg(DISTINCT source_file) FILTER (WHERE source_file IS NOT NULL)
    AS source_files,
  array_agg(DISTINCT source_yyyymm) FILTER (WHERE source_yyyymm IS NOT NULL)
    AS source_yyyymms
FROM public.tl_sppn_makarea
"""
                ),
                {"source_yyyymm": source_yyyymm},
            )
        ).mappings().one()
    return {
        "expected_geometry_type": "ST_MultiPolygon",
        "row_count": _int_report_value(row, "row_count"),
        "geom_rows": _int_report_value(row, "geom_rows"),
        "srid_5179_rows": _int_report_value(row, "srid_5179_rows"),
        "empty_geom_rows": _int_report_value(row, "empty_geom_rows"),
        "invalid_geom_rows": _int_report_value(row, "invalid_geom_rows"),
        "source_file_rows": _int_report_value(row, "source_file_rows"),
        "source_yyyymm_rows": _int_report_value(row, "source_yyyymm_rows"),
        "geometry_types": _distinct_text_values(row["geometry_types"]),
        "source_files": _distinct_text_values(row["source_files"]),
        "source_yyyymms": _distinct_text_values(row["source_yyyymms"]),
    }


async def collect_t177d_non_geometry_report(
    engine: AsyncEngine,
    *,
    source_yyyymm: str | None,
) -> dict[str, Any]:
    reports: dict[str, Any] = {}
    async with engine.connect() as conn:
        for table_name in T177D_NON_GEOMETRY_TABLES:
            row = (
                await conn.execute(
                    text(
                        f"""
SELECT
  count(*) AS row_count,
  count(*) FILTER (WHERE source_file IS NOT NULL) AS source_file_rows,
  count(*) FILTER (WHERE source_yyyymm IS NOT DISTINCT FROM :source_yyyymm)
    AS source_yyyymm_rows,
  array_agg(DISTINCT source_file) FILTER (WHERE source_file IS NOT NULL)
    AS source_files,
  array_agg(DISTINCT source_yyyymm) FILTER (WHERE source_yyyymm IS NOT NULL)
    AS source_yyyymms
FROM {table_name}
"""
                    ),
                    {"source_yyyymm": source_yyyymm},
                )
            ).mappings().one()
            reports[table_name] = {
                "row_count": _int_report_value(row, "row_count"),
                "source_file_rows": _int_report_value(row, "source_file_rows"),
                "source_yyyymm_rows": _int_report_value(row, "source_yyyymm_rows"),
                "source_files": _distinct_text_values(row["source_files"]),
                "source_yyyymms": _distinct_text_values(row["source_yyyymms"]),
            }
    return reports


async def collect_t177e_sppn_smoke(engine: AsyncEngine) -> dict[str, Any]:
    from kortravelgeo.core.geocoder import geocode
    from kortravelgeo.core.sppn import format_national_point_number_from_5179
    from kortravelgeo.dto.common import Point
    from kortravelgeo.dto.geocode import GeocodeInput
    from kortravelgeo.infra.geocode_repo import GeocodeRepository
    from kortravelgeo.infra.reverse_repo import ReverseRepository

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
SELECT sig_cd, makarea_id, makarea_nm,
       ST_X(ST_PointOnSurface(geom)) AS x_5179,
       ST_Y(ST_PointOnSurface(geom)) AS y_5179
  FROM public.tl_sppn_makarea
 WHERE geom IS NOT NULL
   AND NOT ST_IsEmpty(geom)
   AND ST_IsValid(geom)
 ORDER BY ST_Area(geom) DESC, sig_cd, makarea_id
 LIMIT 1
"""
                )
            )
        ).mappings().first()
    if row is None:
        raise T177PreflightError("T-177E SPPN smoke requires at least one valid makarea")

    point_5179 = Point(x=float(row["x_5179"]), y=float(row["y_5179"]))
    geocode_repo = GeocodeRepository(engine)
    reverse_repo = ReverseRepository(engine)
    direct_area = await geocode_repo.lookup_sppn_area(point_5179)
    point_4326 = await geocode_repo.project_sppn_point_4326(point_5179)
    if direct_area is None or point_4326 is None:
        raise T177PreflightError("T-177E SPPN smoke could not resolve sample point")

    national_point = format_national_point_number_from_5179(point_5179)
    geocode_response = (
        await geocode(geocode_repo, GeocodeInput(address=national_point.text))
        if national_point is not None
        else None
    )
    reverse_areas = await reverse_repo.sppn_areas(point_4326, crs="EPSG:4326", limit=5)
    return {
        "sample": {
            "sig_cd": row["sig_cd"],
            "makarea_id": row["makarea_id"],
            "makarea_nm": row["makarea_nm"],
            "point_5179": _point_payload(point_5179),
            "point_4326": _point_payload(point_4326),
        },
        "national_point_number": national_point.text if national_point else None,
        "direct_lookup": _jsonable_model_value(direct_area),
        "geocode_status": geocode_response.status if geocode_response else None,
        "geocode_sppn_found": bool(
            geocode_response
            and geocode_response.x_extension
            and geocode_response.x_extension.sppn_makarea
        ),
        "reverse_area_count": len(reverse_areas),
        "reverse_sppn_found": bool(reverse_areas),
    }


async def collect_t177e_c10_report(engine: AsyncEngine) -> dict[str, Any]:
    from kortravelgeo.loaders.consistency import run_case

    return _jsonable_model_value(await run_case(engine, "C10"))


async def collect_t177f_serving_report(engine: AsyncEngine) -> dict[str, Any]:
    async with engine.connect() as conn:
        object_rows = []
        for object_name in T177F_SERVING_OBJECTS:
            exists = await conn.scalar(
                text("SELECT to_regclass(:object_name) IS NOT NULL"),
                {"object_name": object_name},
            )
            row_count = None
            if exists:
                row_count = await conn.scalar(text(f"SELECT count(*) FROM {object_name}"))
            object_rows.append(
                {
                    "object_name": object_name,
                    "exists": bool(exists),
                    "row_count": int(row_count or 0) if exists else None,
                }
            )
        index_rows = (
            await conn.execute(
                text(
                    """
SELECT schemaname, tablename, indexname
  FROM pg_indexes
 WHERE schemaname = 'public'
   AND tablename IN ('mv_geocode_target', 'mv_geocode_text_search')
 ORDER BY tablename, indexname
"""
                )
            )
        ).mappings()
    return {
        "objects": object_rows,
        "missing_objects": [
            row["object_name"] for row in object_rows if not row["exists"]
        ],
        "indexes": [dict(row) for row in index_rows],
    }


async def select_t177f_smoke_sample(engine: AsyncEngine) -> dict[str, Any]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
SELECT bd_mgt_sn,
       rn,
       rn_nrm,
       si_nm,
       sgg_nm,
       emd_nm,
       li_nm,
       buld_mnnm,
       buld_slno,
       zip_no,
       pt_source,
       ST_X(pt_4326) AS lon,
       ST_Y(pt_4326) AS lat,
       EXISTS (
         SELECT 1
           FROM public.tl_locsum_entrc l
          WHERE l.bd_mgt_sn = target.bd_mgt_sn
       ) AS has_locsum_link,
       EXISTS (
         SELECT 1
           FROM public.tl_roadaddr_entrc r
          WHERE r.bd_mgt_sn = target.bd_mgt_sn
       ) AS has_roadaddr_entrc_link,
       concat_ws(
         ' ',
         NULLIF(si_nm, ''),
         NULLIF(sgg_nm, ''),
         NULLIF(rn, ''),
         buld_mnnm::text ||
           CASE
             WHEN COALESCE(buld_slno, 0) > 0 THEN '-' || buld_slno::text
             ELSE ''
           END
       ) AS road_address
  FROM public.mv_geocode_target target
 WHERE pt_4326 IS NOT NULL
   AND pt_5179 IS NOT NULL
   AND bd_mgt_sn IS NOT NULL
   AND rn IS NOT NULL
   AND rn_nrm IS NOT NULL
   AND rn_nrm <> ''
   AND buld_mnnm IS NOT NULL
   AND buld_slno IS NOT NULL
   AND zip_no IS NOT NULL
 ORDER BY CASE
            WHEN EXISTS (
              SELECT 1
                FROM public.tl_locsum_entrc l
               WHERE l.bd_mgt_sn = target.bd_mgt_sn
            ) THEN 0
            ELSE 1
          END,
          CASE WHEN pt_source = 'entrance' THEN 0 ELSE 1 END,
          bd_mgt_sn,
          rncode_full,
          bjd_cd
 LIMIT 1
"""
                )
            )
        ).mappings().first()
    if row is None:
        raise T177SkipError("T-177F serving MV has no smokeable geocode target row")
    sample = dict(row)
    sample["lon"] = float(sample["lon"])
    sample["lat"] = float(sample["lat"])
    sample["has_locsum_link"] = bool(sample["has_locsum_link"])
    sample["has_roadaddr_entrc_link"] = bool(sample["has_roadaddr_entrc_link"])
    return sample


async def collect_t177f_smoke_report(engine: AsyncEngine) -> dict[str, Any]:
    from kortravelgeo.client import AsyncAddressClient
    from kortravelgeo.settings import get_settings

    sample = await select_t177f_smoke_sample(engine)
    settings = get_settings().model_copy(update={"cache_enabled": False})
    async with AsyncAddressClient(settings=settings, engine=engine) as client:
        geocode_response = await client._geocode_v1(
            str(sample["road_address"]),
            type="road",
            fallback="local_only",
        )
        reverse_response = await client._reverse_geocode_v1(
            float(sample["lon"]),
            float(sample["lat"]),
            radius_m=200,
        )
        search_response = await client.search(
            query=str(sample["rn"]),
            type="address",
            size=5,
        )
        zipcode_response = await client.zipcode(
            address=str(sample["road_address"]),
            include_bulk=True,
        )
    return {
        "sample": sample,
        "geocode": {
            "status": geocode_response.status,
            "point": _jsonable_model_value(
                geocode_response.result.point if geocode_response.result else None
            ),
            "source": (
                geocode_response.x_extension.source
                if geocode_response.x_extension
                else None
            ),
        },
        "reverse": {
            "status": reverse_response.status,
            "result_count": len(reverse_response.result),
            "sources": tuple(item.source for item in reverse_response.result),
            "sppn_found": bool(
                reverse_response.x_extension
                and reverse_response.x_extension.sppn_makarea
            ),
        },
        "search": {
            "status": search_response.status,
            "candidate_count": len(search_response.candidates),
        },
        "zipcode": {
            "status": zipcode_response.status,
            "result_count": len(zipcode_response.result),
            "zip_sources": tuple(item.source for item in zipcode_response.result),
        },
    }


async def collect_t177f_link_evidence(engine: AsyncEngine) -> dict[str, int]:
    async with engine.connect() as conn:
        row = (await conn.execute(text(_T177F_LINK_EVIDENCE_SQL))).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


async def collect_t177f_consistency_report(engine: AsyncEngine) -> dict[str, Any]:
    from kortravelgeo.loaders.consistency import run_all_cases

    report = await run_all_cases(
        engine,
        scope="t177f-fast-sample",
        cases=T177F_CONSISTENCY_CASES,
        generated_by="cli",
        source_set={"task": "T-177F", "mode": "postload_serving_fast_sample"},
    )
    return _jsonable_model_value(report)


async def collect_t177d_region_radius_report(engine: AsyncEngine) -> dict[str, Any]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    """
SELECT
  level,
  count(*) AS row_count,
  count(*) FILTER (WHERE geom IS NOT NULL) AS geom_rows,
  count(*) FILTER (WHERE geom IS NOT NULL AND ST_SRID(geom) = 5179)
    AS srid_5179_rows,
  count(*) FILTER (WHERE geom IS NOT NULL AND ST_IsEmpty(geom))
    AS empty_geom_rows,
  count(*) FILTER (WHERE geom IS NOT NULL AND NOT ST_IsValid(geom))
    AS invalid_geom_rows,
  array_agg(DISTINCT ST_GeometryType(geom)) FILTER (WHERE geom IS NOT NULL)
    AS geometry_types
FROM public.region_radius_parts
GROUP BY level
ORDER BY level
"""
                )
            )
        ).mappings()
    return {
        str(row["level"]): {
            "row_count": _int_report_value(row, "row_count"),
            "geom_rows": _int_report_value(row, "geom_rows"),
            "srid_5179_rows": _int_report_value(row, "srid_5179_rows"),
            "empty_geom_rows": _int_report_value(row, "empty_geom_rows"),
            "invalid_geom_rows": _int_report_value(row, "invalid_geom_rows"),
            "geometry_types": _distinct_text_values(row["geometry_types"]),
        }
        for row in rows
    }


async def run_t177e_supplemental_fast_sample_load(
    engine: AsyncEngine,
    *,
    source_paths: T177SupplementalSourcePaths,
    limit_per_file: int,
) -> dict[str, Any]:
    from kortravelgeo.loaders.sppn_makarea_loader import load_sppn_makarea
    from kortravelgeo.loaders.text.roadaddr_entrance_loader import load_roadaddr_entrances

    roadaddr_result = await load_roadaddr_entrances(
        engine,
        source_paths.roadaddr_entrance,
        source_yyyymm=None,
        limit_per_file=limit_per_file,
        replace=True,
    )
    sppn_rows = await load_sppn_makarea(
        engine,
        source_paths.sppn_makarea,
        mode="full",
        source_yyyymm=source_paths.sppn_makarea_source_yyyymm,
        analyze=True,
    )
    table_counts = await collect_t177e_table_counts(engine)
    manifests = await collect_t177e_manifests(engine)
    roadaddr_source_yyyymm = roadaddr_result.source_yyyymm
    roadaddr_report = await collect_t177e_roadaddr_report(
        engine,
        source_yyyymm=roadaddr_source_yyyymm,
    )
    sppn_report = await collect_t177e_sppn_report(
        engine,
        source_yyyymm=source_paths.sppn_makarea_source_yyyymm,
    )
    sppn_smoke = await collect_t177e_sppn_smoke(engine)
    c10_report = await collect_t177e_c10_report(engine)
    return {
        "limit_per_file": limit_per_file,
        "source_paths": {
            field: str(value) if isinstance(value, Path) else value
            for field, value in asdict(source_paths).items()
        },
        "source_months": {
            "roadaddr_entrance_plan": source_paths.roadaddr_entrance_plan_yyyymm,
            "roadaddr_entrance_loaded": roadaddr_source_yyyymm,
            "sppn_makarea": source_paths.sppn_makarea_source_yyyymm,
        },
        "loader_results": {
            "roadaddr_entrance": asdict(roadaddr_result),
            "sppn_makarea_rows": sppn_rows,
        },
        "table_counts": table_counts,
        "manifests": manifests,
        "roadaddr_report": roadaddr_report,
        "sppn_report": sppn_report,
        "sppn_smoke": sppn_smoke,
        "c10": c10_report,
    }


async def run_t177f_text_snapshot_fast_sample_load(
    engine: AsyncEngine,
    *,
    discovery_plan: Mapping[str, Any],
    limit_per_file: int,
) -> dict[str, Any]:
    from kortravelgeo.loaders.text.juso_hangul_loader import load_juso_hangul
    from kortravelgeo.loaders.text.locsum_loader import load_locsum

    juso_hangul = required_source_path(discovery_plan, "juso_hangul")
    locsum = required_source_path(discovery_plan, "locsum")
    source_months = {
        "juso_hangul": source_yyyymm(discovery_plan, "juso_hangul"),
        "locsum": source_yyyymm(discovery_plan, "locsum"),
    }
    juso_count = await load_juso_hangul(
        engine,
        juso_hangul,
        source_yyyymm=source_months["juso_hangul"],
        limit_per_file=limit_per_file,
    )
    locsum_count = await load_locsum(
        engine,
        locsum,
        source_yyyymm=source_months["locsum"],
        limit_per_file=limit_per_file,
    )
    return {
        "limit_per_file": limit_per_file,
        "source_paths": {
            "juso_hangul": str(juso_hangul),
            "locsum": str(locsum),
        },
        "source_months": source_months,
        "loader_results": {
            "juso_hangul_rows": juso_count,
            "locsum_rows": locsum_count,
        },
        "table_counts": await collect_t177c_table_counts(engine),
    }


async def run_t177f_postload_serving_smoke(
    engine: AsyncEngine,
    *,
    loaded_results: Mapping[str, Any],
) -> dict[str, Any]:
    from kortravelgeo.infra.cache import GeoCacheRepository
    from kortravelgeo.loaders.postload import (
        rebuild_mv,
        resolve_text_geometry_links,
    )

    await resolve_text_geometry_links(engine)
    await rebuild_mv(engine)
    cache_cleared_rows = await GeoCacheRepository(engine).clear()
    link_evidence = await collect_t177f_link_evidence(engine)
    smoke_report = await collect_t177f_smoke_report(engine)
    consistency_report = await collect_t177f_consistency_report(engine)
    serving_report = await collect_t177f_serving_report(engine)
    return {
        "loaded_results": dict(loaded_results),
        "cache_cleared_rows": cache_cleared_rows,
        "link_evidence": link_evidence,
        "serving": serving_report,
        "smoke": smoke_report,
        "consistency": consistency_report,
    }


async def run_t177c_text_delta_fast_sample_load(
    engine: AsyncEngine,
    *,
    source_paths: T177TextDeltaSourcePaths,
    source_months: Mapping[str, str | None],
    limit_per_file: int,
) -> dict[str, Any]:
    from kortravelgeo.loaders.postload import resolve_text_geometry_links
    from kortravelgeo.loaders.text.daily_juso_loader import load_daily_juso_delta
    from kortravelgeo.loaders.text.juso_hangul_loader import load_juso_hangul
    from kortravelgeo.loaders.text.locsum_loader import load_locsum
    from kortravelgeo.loaders.text.navi_loader import load_navi
    from kortravelgeo.loaders.text.parcel_link_loader import (
        load_daily_parcel_link_delta,
        load_juso_parcel_link_snapshot,
    )

    juso_count = await load_juso_hangul(
        engine,
        source_paths.juso_hangul,
        source_yyyymm=source_months.get("juso_hangul"),
        limit_per_file=limit_per_file,
    )
    daily_result = await load_daily_juso_delta(
        engine,
        source_paths.daily_juso,
        source_yyyymm=None,
        limit_per_file=limit_per_file,
    )
    parent_seed_count = await insert_t177c_parcel_link_parent_rows(
        engine,
        source_paths=source_paths,
        source_months=source_months,
        limit_per_file=limit_per_file,
    )
    parcel_snapshot = await load_juso_parcel_link_snapshot(
        engine,
        source_paths.jibun_rnaddrkor,
        source_yyyymm=source_months.get("jibun_rnaddrkor"),
        limit_per_file=limit_per_file,
        replace=True,
    )
    parcel_delta = await load_daily_parcel_link_delta(
        engine,
        source_paths.daily_lnbr,
        source_yyyymm=None,
        limit_per_file=limit_per_file,
    )
    locsum_count = await load_locsum(
        engine,
        source_paths.locsum,
        source_yyyymm=source_months.get("locsum"),
        limit_per_file=limit_per_file,
    )
    navi_build_count, navi_entrance_count = await load_navi(
        engine,
        source_paths.navi,
        source_yyyymm=source_months.get("navi"),
        limit_per_file=limit_per_file,
    )
    links_before = await collect_t177c_link_counts(engine)
    await resolve_text_geometry_links(engine)
    links_after = await collect_t177c_link_counts(engine)
    table_counts = await collect_t177c_table_counts(engine)
    manifests = await collect_t177c_manifests(engine)
    return {
        "limit_per_file": limit_per_file,
        "source_paths": {
            field: str(value) for field, value in asdict(source_paths).items()
        },
        "source_months": dict(source_months),
        "loader_results": {
            "juso_hangul_rows": juso_count,
            "daily_juso": asdict(daily_result),
            "parcel_parent_seed_rows": parent_seed_count,
            "juso_parcel_link_snapshot": asdict(parcel_snapshot),
            "daily_parcel_link": asdict(parcel_delta),
            "locsum_rows": locsum_count,
            "navi_build_rows": navi_build_count,
            "navi_entrance_rows": navi_entrance_count,
        },
        "links": {
            "before_resolve": links_before,
            "after_resolve": links_after,
        },
        "table_counts": table_counts,
        "manifests": manifests,
    }


async def run_t177d_shp_geometry_fast_sample_load(
    engine: AsyncEngine,
    *,
    source: T177ShpGeometrySource,
) -> dict[str, Any]:
    from kortravelgeo.loaders.postload import refresh_region_radius_parts

    try:
        plans = build_shp_load_plan(source.sido_path, source_yyyymm=source.source_yyyymm)
    except LoaderError as exc:
        raise T177SkipError(f"T-177 selected electronic_map source is not loadable: {exc}") from exc
    if len(plans) != len(POLYGON_LAYER_NAMES):
        raise T177SkipError(
            "T-177 selected electronic_map source does not expose all serving SHP layers: "
            f"expected {len(POLYGON_LAYER_NAMES)}, got {len(plans)}"
        )

    loaded_layers = await load_shp_polygons(
        engine,
        source.sido_path,
        mode="full",
        source_yyyymm=source.source_yyyymm,
        analyze=True,
    )
    await refresh_region_radius_parts(engine)
    table_counts = await collect_t177d_table_counts(engine)
    geometry_report = await collect_t177d_geometry_report(
        engine,
        source_yyyymm=source.source_yyyymm,
    )
    non_geometry_report = await collect_t177d_non_geometry_report(
        engine,
        source_yyyymm=source.source_yyyymm,
    )
    region_radius_parts = await collect_t177d_region_radius_report(engine)
    return {
        "source": {
            "electronic_map_root": str(source.electronic_map_root),
            "sido_path": str(source.sido_path),
            "sido_name": source.sido_name,
            "sig_code": source.sig_code,
            "source_yyyymm": source.source_yyyymm,
            "archive_path": str(source.archive_path) if source.archive_path else None,
            "materialized": source.materialized,
        },
        "plans": [
            {
                "source_layer": plan.source_layer,
                "target_table": plan.target_table,
                "source_file": plan.source_file,
                "source_yyyymm": plan.source_yyyymm,
            }
            for plan in plans
        ],
        "loaded_layers": loaded_layers,
        "table_counts": table_counts,
        "geometry_report": geometry_report,
        "non_geometry_report": non_geometry_report,
        "region_radius_parts": region_radius_parts,
    }


async def insert_t177c_parcel_link_parent_rows(
    engine: AsyncEngine,
    *,
    source_paths: T177TextDeltaSourcePaths,
    source_months: Mapping[str, str | None],
    limit_per_file: int,
) -> int:
    from kortravelgeo.loaders.text.parcel_link_loader import (
        discover_daily_lnbr_sources,
        discover_jibun_rnaddrkor_files,
        iter_daily_lnbr_rows,
        iter_jibun_parcel_link_rows,
    )

    rows = [
        row
        for source in discover_jibun_rnaddrkor_files(source_paths.jibun_rnaddrkor)
        for row in iter_jibun_parcel_link_rows(
            source,
            source_yyyymm=source_months.get("jibun_rnaddrkor"),
            limit=limit_per_file,
        )
    ]
    rows.extend(
        row
        for source in discover_daily_lnbr_sources(source_paths.daily_lnbr)
        for row in iter_daily_lnbr_rows(
            source,
            source_yyyymm=None,
            limit=limit_per_file,
        )
    )
    async with engine.begin() as conn:
        for row in rows:
            await conn.execute(
                text(
                    """
INSERT INTO public.tl_juso_text (
  bd_mgt_sn, sig_cd, rn_cd, bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno,
  source_file, source_yyyymm
) VALUES (
  :bd_mgt_sn, :sig_cd, :rn_cd, :bjd_cd, :mntn_yn, :lnbr_mnnm, :lnbr_slno,
  :source_file, :source_yyyymm
)
ON CONFLICT (bd_mgt_sn) DO NOTHING
"""
                ),
                {
                    "bd_mgt_sn": row.bd_mgt_sn,
                    "sig_cd": row.sig_cd,
                    "rn_cd": row.rn_cd,
                    "bjd_cd": row.bjd_cd,
                    "mntn_yn": row.mntn_yn,
                    "lnbr_mnnm": row.lnbr_mnnm,
                    "lnbr_slno": row.lnbr_slno,
                    "source_file": row.source_file,
                    "source_yyyymm": row.source_yyyymm,
                },
            )
    return len(rows)


def _artifact_dir(env: Mapping[str, str], *, run_id: str, cwd: Path) -> Path:
    configured = env.get(ENV_ARTIFACT_DIR)
    path = (
        Path(configured).expanduser()
        if configured
        else Path("artifacts") / "t177" / run_id
    )
    return path if path.is_absolute() else cwd / path


def _summarize_source(
    kind: str,
    path: Path | None,
    discover: SourceDiscoverer,
) -> SourceDiscoverySummary:
    if path is None:
        return SourceDiscoverySummary(
            kind=kind,
            path=None,
            exists=False,
            source_yyyymm=None,
            source_count=0,
            sample_names=(),
            notes=("no candidate path matched the T-177 discovery patterns",),
        )
    notes = list(_path_notes(path))
    if not path.exists():
        return SourceDiscoverySummary(
            kind=kind,
            path=str(path),
            exists=False,
            source_yyyymm=infer_yyyymm(path),
            source_count=0,
            sample_names=(),
            notes=tuple(notes),
        )
    try:
        count, sample_names, extra_notes = discover(path)
        notes.extend(extra_notes)
        return SourceDiscoverySummary(
            kind=kind,
            path=str(path),
            exists=True,
            source_yyyymm=infer_yyyymm(path),
            source_count=count,
            sample_names=sample_names,
            notes=tuple(notes),
        )
    except (LoaderError, OSError, ValueError, zipfile.BadZipFile) as exc:
        return SourceDiscoverySummary(
            kind=kind,
            path=str(path),
            exists=True,
            source_yyyymm=infer_yyyymm(path),
            source_count=0,
            sample_names=(),
            error=f"{type(exc).__name__}: {exc}",
            notes=tuple(notes),
        )


def _discover_juso_hangul(path: Path) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    return _text_sources(discover_juso_hangul_files(path))


def _discover_jibun(path: Path) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    return _text_sources(discover_jibun_rnaddrkor_files(path))


def _discover_daily_juso(path: Path) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    sources = discover_daily_juso_sources(path)
    return _text_sources(sources.mst + sources.lnbr)


def _discover_daily_lnbr(path: Path) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    return _text_sources(discover_daily_lnbr_sources(path))


def _discover_locsum(path: Path) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    return _text_sources(discover_locsum_files(path))


def _discover_navi(path: Path) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    build_sources = discover_navi_build_files(path)
    entrance_sources = discover_navi_entrance_files(path)
    count, sample_names, notes = _text_sources(build_sources + entrance_sources)
    return (
        count,
        sample_names,
        (f"build={len(build_sources)} entrance={len(entrance_sources)}", *notes),
    )


def _discover_roadaddr_entrance(path: Path) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    return _text_sources(discover_roadaddr_entrance_sources(path))


def _discover_shp(path: Path) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    try:
        plans = build_shp_load_plan(path)
        datasets = discover_sido_datasets(path)
        sample_names = tuple(
            f"{plan.source_file}:{plan.source_layer}" for plan in plans[:5]
        )
        notes = (
            f"sido_datasets={len(datasets)}",
            f"target_tables={len({plan.target_table for plan in plans})}",
        )
        return len(plans), sample_names, notes
    except LoaderError:
        archives = _electronic_map_archives(path)
        if not archives:
            raise
        sample_names = tuple(
            f"{archive.name}:{layer_name}"
            for archive in archives[:2]
            for layer_name in POLYGON_LAYER_NAMES[:3]
        )
        notes = (
            f"sido_archives={len(archives)}",
            "materialize_required=true",
            f"target_tables={len(POLYGON_LAYER_NAMES)}",
        )
        return len(archives) * len(POLYGON_LAYER_NAMES), sample_names, notes


def _discover_sppn_makarea(path: Path) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    sources = discover_sppn_makarea_sources(path)
    return (
        len(sources),
        tuple(source.source_file for source in sources[:5]),
        (),
    )


def _text_sources(sources: Sequence[TextSource]) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    return len(sources), tuple(source.name for source in sources[:5]), ()


def _newest(root: Path, patterns: tuple[str, ...]) -> Path | None:
    matches = [path for pattern in patterns for path in root.glob(pattern)]
    if not matches:
        return None
    return sorted(matches, key=lambda path: path.name)[-1]


def _daily_candidate(data_root: Path) -> Path | None:
    daily_root = data_root / "daily"
    if not daily_root.exists():
        return None
    return _newest(daily_root, ("*_dailyjusukrdata.zip", "*.zip")) or daily_root


def _electronic_map_candidate(data_root: Path) -> Path | None:
    return _yyyymm_child_or_root(data_root / "도로명주소 전자지도")


def _sppn_makarea_candidate(data_root: Path) -> Path | None:
    for dirname in ("구역의도형", "구역의 도형"):
        candidate = _yyyymm_child_or_root(data_root / dirname)
        if candidate is not None:
            return candidate
    return None


def _yyyymm_child_or_root(root: Path) -> Path | None:
    if not root.exists():
        return None
    yyyymm_dirs = [
        child
        for child in root.iterdir()
        if child.is_dir() and re.fullmatch(r"20\d{4}", child.name)
    ]
    if yyyymm_dirs:
        return sorted(yyyymm_dirs, key=lambda path: path.name)[-1]
    return root


def _electronic_map_archives(path: Path) -> tuple[Path, ...]:
    if path.is_file() and path.suffix.lower() == ".zip":
        return (path,)
    if not path.is_dir():
        return ()
    return tuple(sorted(path.glob("*.zip"), key=lambda item: item.name))


def _select_electronic_map_archive(archives: Sequence[Path]) -> Path:
    return sorted(
        archives,
        key=lambda archive: (
            0 if ("세종" in archive.stem or archive.stem.startswith("36")) else 1,
            archive.stem,
        ),
    )[0]


def _select_t177d_sido_dataset(datasets: Sequence[Any]) -> Any:
    if not datasets:
        raise T177SkipError("T-177 electronic_map source has no 시도 dataset")
    return sorted(
        datasets,
        key=lambda dataset: (
            0 if ("세종" in dataset.sido_name or dataset.sig_code.startswith("36")) else 1,
            dataset.sido_name,
            dataset.sig_code,
        ),
    )[0]


def _select_preferred_zip(path: Path) -> Path:
    if path.is_file():
        return path
    if path.is_dir():
        zip_files = sorted(path.glob("*.zip"), key=lambda item: item.name)
        if zip_files:
            return sorted(
                zip_files,
                key=lambda archive: (
                    0
                    if ("세종" in archive.stem or archive.stem.startswith("36"))
                    else 1,
                    archive.stem,
                ),
            )[0]
    return path


def _materialize_electronic_map_archive(archive: Path, materialize_dir: Path) -> Path:
    destination = materialize_dir / archive.stem
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as source_zip:
        for member in source_zip.infolist():
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise T177SkipError(
                    f"T-177 electronic_map ZIP contains unsafe member: {member.filename}"
                )
        source_zip.extractall(destination)
    return destination


def _path_notes(path: Path) -> tuple[str, ...]:
    notes: list[str] = []
    if path.suffix.lower() == ".7z":
        notes.append("7z archives must be materialized before current text discovery")
    if path.is_dir():
        zip_count = sum(1 for _ in path.glob("*.zip"))
        if zip_count:
            notes.append(f"zip_files={zip_count}")
    return tuple(notes)


async def _collect_table_counts(
    engine: AsyncEngine,
    table_names: Sequence[str],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    async with engine.connect() as conn:
        for table_name in table_names:
            exists = await conn.scalar(
                text("SELECT to_regclass(:table_name) IS NOT NULL"),
                {"table_name": table_name},
            )
            if not exists:
                continue
            count = await conn.scalar(text(f"SELECT count(*) FROM {table_name}"))
            counts[table_name] = int(count or 0)
    return counts


def _int_report_value(row: Any, key: str) -> int:
    return int(row[key] or 0)


def _distinct_text_values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(sorted(str(item) for item in value if item is not None))


def _jsonable_source_set(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _jsonable_model_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable_model_value(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable_model_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable_model_value(item) for item in value]
    if isinstance(value, list):
        return [_jsonable_model_value(item) for item in value]
    return value


def _point_payload(point: Any) -> dict[str, float]:
    return {"x": float(point.x), "y": float(point.y)}
