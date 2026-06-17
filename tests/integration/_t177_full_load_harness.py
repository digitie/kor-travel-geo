"""T-177 file-driven full-load e2e harness helpers."""

from __future__ import annotations

import json
import os
import re
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from kortravelgeo.exceptions import LoaderError
from kortravelgeo.infra.sql import INDEX_SQL, SCHEMA_SQL, iter_sql_statements
from kortravelgeo.loaders.juso_map import discover_sido_datasets
from kortravelgeo.loaders.manifest import infer_yyyymm
from kortravelgeo.loaders.shp.polygons_loader import build_shp_load_plan
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
CONFIRM_PREFIX = "RUN-T177-E2E"

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
            data_root / "구역의 도형",
            _discover_sppn_makarea,
        ),
    )
    return {
        "data_root": str(data_root),
        "sources": {summary.kind: asdict(summary) for summary in summaries},
    }


def write_json_artifact(artifact_dir: Path, filename: str, payload: Mapping[str, Any]) -> Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    destination = artifact_dir / filename
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


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


def _path_notes(path: Path) -> tuple[str, ...]:
    notes: list[str] = []
    if path.suffix.lower() == ".7z":
        notes.append("7z archives must be materialized before current text discovery")
    if path.is_dir():
        zip_count = sum(1 for _ in path.glob("*.zip"))
        if zip_count:
            notes.append(f"zip_files={zip_count}")
    return tuple(notes)
