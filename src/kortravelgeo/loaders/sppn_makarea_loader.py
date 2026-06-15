"""Loader for TL_SPPN_MAKAREA national point-number marking areas."""

from __future__ import annotations

import asyncio
import json
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.core.source_layers import ZONE_MAKAREA_LAYER_NAME
from kortravelgeo.exceptions import LoaderError

ProgressCallback = Callable[[float], None]

#: Re-exported from kortravelgeo.core.source_layers (single source of truth) so
#: core.source_validation can reference the zone makarea layer name without
#: importing this loader. Kept as ``LAYER_NAME`` for existing references.
LAYER_NAME = ZONE_MAKAREA_LAYER_NAME
TARGET_TABLE = "tl_sppn_makarea"
STAGE_TABLE = "_staging_sppn_makarea"
STAGE_LOCK_KEY = "kortravelgeo.loaders.sppn_makarea_loader.stage"

_LAYER_SUFFIXES = (".shp", ".shx", ".dbf")


@dataclass(frozen=True, slots=True)
class SppnMakareaSource:
    source_file: str
    zip_path: Path | None = None
    shp_path: Path | None = None
    zip_prefix: str | None = None


def _clean_sql(value: str) -> str:
    return f"NULLIF(BTRIM({value}), '')"


async def load_sppn_makarea(
    engine: AsyncEngine,
    path: Path | str,
    *,
    mode: str = "full",
    source_yyyymm: str | None = None,
    analyze: bool = True,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> int:
    sources = discover_sppn_makarea_sources(path)
    return await asyncio.to_thread(
        _load_sources_sync,
        engine.url.render_as_string(hide_password=False),
        sources,
        mode,
        source_yyyymm,
        analyze,
        on_progress,
        cancel_event,
    )


def discover_sppn_makarea_sources(path: Path | str) -> tuple[SppnMakareaSource, ...]:
    root = Path(path).expanduser().resolve()
    if not root.exists():
        msg = f"SPPN makarea source path does not exist: {root}"
        raise LoaderError(msg)
    if root.is_file() and root.suffix.lower() == ".zip":
        return (_zip_source(root),)
    if root.is_file() and root.name.upper() == f"{LAYER_NAME}.SHP":
        return (_shp_source(root, base=root.parent),)
    if root.is_dir():
        shp_files = sorted(root.rglob(f"{LAYER_NAME}.shp"))
        if shp_files:
            return tuple(_shp_source(shp_path, base=root) for shp_path in shp_files)
        zip_files = sorted(root.glob("*.zip"))
        if zip_files:
            return tuple(_zip_source(zip_path) for zip_path in zip_files)
    msg = f"no {LAYER_NAME} shapefile or zone zip found under: {root}"
    raise LoaderError(msg)


def _zip_source(zip_path: Path) -> SppnMakareaSource:
    with zipfile.ZipFile(zip_path) as zip_file:
        shp_members = [
            name
            for name in zip_file.namelist()
            if Path(name).name.upper() == f"{LAYER_NAME}.SHP"
        ]
    if len(shp_members) != 1:
        msg = f"expected one {LAYER_NAME}.shp in {zip_path}, found {len(shp_members)}"
        raise LoaderError(msg)
    shp_member = shp_members[0]
    prefix = str(PurePosixPath(shp_member).with_suffix(""))
    return SppnMakareaSource(
        source_file=f"{zip_path.name}:{shp_member}",
        zip_path=zip_path,
        zip_prefix=prefix,
    )


def _shp_source(shp_path: Path, *, base: Path) -> SppnMakareaSource:
    missing = [
        shp_path.with_suffix(suffix)
        for suffix in _LAYER_SUFFIXES
        if not shp_path.with_suffix(suffix).is_file()
    ]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        msg = f"missing {LAYER_NAME} sidecar files: {joined}"
        raise LoaderError(msg)
    try:
        source_file = shp_path.relative_to(base).as_posix()
    except ValueError:
        source_file = shp_path.name
    return SppnMakareaSource(source_file=source_file, shp_path=shp_path)


def _load_sources_sync(
    pg_url: str,
    sources: tuple[SppnMakareaSource, ...],
    mode: str,
    source_yyyymm: str | None,
    analyze: bool,
    on_progress: ProgressCallback | None,
    cancel_event: asyncio.Event | None,
) -> int:
    try:
        from osgeo import gdal  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - depends on optional system GDAL
        msg = "GDAL Python binding is required for SPPN makarea loading"
        raise LoaderError(msg) from exc
    gdal.UseExceptions()

    if mode not in {"full", "append", "delta"}:
        msg = f"unsupported SPPN makarea load mode: {mode}"
        raise LoaderError(msg)

    lock_engine, lock_conn = _acquire_stage_lock(pg_url)
    try:
        if mode == "full":
            _truncate_target(pg_url)

        total_rows = 0
        for index, source in enumerate(sources):
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError("sppn makarea loader cancelled")

            def callback(
                complete: float,
                _message: str,
                _data: object,
                *,
                source_index: int = index,
            ) -> int:
                if cancel_event and cancel_event.is_set():
                    return 0
                if on_progress:
                    on_progress((source_index + complete) / len(sources))
                return 1

            with tempfile.TemporaryDirectory(prefix="kortravel-sppn-makarea-") as temp_dir:
                shp_path = _materialize_source(source, Path(temp_dir))
                _drop_stage(pg_url)
                try:
                    _vector_translate_to_stage(
                        gdal,
                        pg_url,
                        shp_path,
                        callback=callback,
                    )
                    total_rows += _insert_stage(
                        pg_url,
                        source_file=source.source_file,
                        source_yyyymm=source_yyyymm,
                    )
                finally:
                    _drop_stage(pg_url)
        if analyze:
            _analyze_target(pg_url)
        _record_manifest(
            pg_url,
            sources=sources,
            mode=mode,
            source_yyyymm=source_yyyymm,
        )
        if on_progress:
            on_progress(1.0)
        return total_rows
    finally:
        _release_stage_lock(lock_engine, lock_conn)


def _acquire_stage_lock(pg_url: str) -> tuple[Engine, Connection]:
    engine = create_engine(pg_url)
    conn = engine.connect()
    try:
        locked = conn.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:lock_key))"),
            {"lock_key": STAGE_LOCK_KEY},
        ).scalar_one()
        if not bool(locked):
            msg = (
                "another TL_SPPN_MAKAREA staging load is already running in this DB; "
                "retry after it finishes"
            )
            raise LoaderError(msg)
        return engine, conn
    except Exception:
        conn.close()
        engine.dispose()
        raise


def _release_stage_lock(engine: Engine, conn: Connection) -> None:
    try:
        conn.execute(
            text("SELECT pg_advisory_unlock(hashtext(:lock_key))"),
            {"lock_key": STAGE_LOCK_KEY},
        )
    finally:
        conn.close()
        engine.dispose()


def _materialize_source(source: SppnMakareaSource, temp_dir: Path) -> Path:
    if source.shp_path is not None:
        return source.shp_path
    if source.zip_path is None or source.zip_prefix is None:
        msg = "invalid SPPN makarea source"
        raise LoaderError(msg)
    with zipfile.ZipFile(source.zip_path) as zip_file:
        for suffix in _LAYER_SUFFIXES:
            member = f"{source.zip_prefix}{suffix}"
            try:
                data = zip_file.read(member)
            except KeyError as exc:
                msg = f"missing {member} in {source.zip_path}"
                raise LoaderError(msg) from exc
            (temp_dir / f"{LAYER_NAME}{suffix}").write_bytes(data)
    return temp_dir / f"{LAYER_NAME}.shp"


def _vector_translate_to_stage(
    gdal_module: Any,
    pg_url: str,
    shp_path: Path,
    *,
    callback: Callable[[float, str, object], int],
) -> None:
    options = gdal_module.VectorTranslateOptions(
        format="PostgreSQL",
        layerName=STAGE_TABLE,
        SQLStatement=_stage_select_sql(),
        layerCreationOptions=["GEOMETRY_NAME=geom", "SPATIAL_INDEX=NONE"],
        srcSRS="EPSG:5179",
        dstSRS="EPSG:5179",
        accessMode="overwrite",
        geometryType="PROMOTE_TO_MULTI",
        callback=callback,
    )
    with gdal_module.config_options({"PG_USE_COPY": "YES", "SHAPE_ENCODING": "CP949"}):
        result = gdal_module.VectorTranslate(
            _gdal_pg_destination(pg_url),
            str(shp_path),
            options=options,
        )
    if result is None:
        msg = f"GDAL VectorTranslate failed for {LAYER_NAME}"
        raise LoaderError(msg)


def _stage_select_sql() -> str:
    return f"""
SELECT SIG_CD AS sig_cd,
       MAKAREA_ID AS makarea_id,
       NTFC_YN AS ntfc_yn,
       MAKAREA_NM AS makarea_nm,
       NTFC_DE AS ntfc_de,
       MVM_RES_CD AS mvm_res_cd,
       MVMN_RESN AS mvmn_resn,
       OPERT_DE AS opert_de,
       MAKAREA_AR AS makarea_ar,
       MVMN_DESC AS mvmn_desc
  FROM {LAYER_NAME}
"""


def _insert_stage(pg_url: str, *, source_file: str, source_yyyymm: str | None) -> int:
    engine = create_engine(pg_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL search_path = public, x_extension"))
            result = conn.execute(
                text(
                    f"""
WITH normalized AS (
  SELECT
    {_clean_sql("sig_cd::text")} AS sig_cd,
    {_clean_sql("makarea_id::text")} AS makarea_id,
    {_clean_sql("ntfc_yn::text")} AS ntfc_yn,
    {_clean_sql("makarea_nm::text")} AS makarea_nm,
    {_clean_sql("ntfc_de::text")} AS ntfc_de,
    {_clean_sql("mvm_res_cd::text")} AS mvm_res_cd,
    {_clean_sql("mvmn_resn::text")} AS mvmn_resn,
    {_clean_sql("opert_de::text")} AS opert_de,
    NULLIF(BTRIM(makarea_ar::text), '')::numeric AS makarea_ar,
    {_clean_sql("mvmn_desc::text")} AS mvmn_desc,
    ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Force2D(geom)), 3))
      ::geometry(MultiPolygon, 5179) AS geom
  FROM {STAGE_TABLE}
)
INSERT INTO {TARGET_TABLE} (
  sig_cd, makarea_id, ntfc_yn, makarea_nm, ntfc_de, mvm_res_cd,
  mvmn_resn, opert_de, makarea_ar, mvmn_desc, geom, source_file,
  source_yyyymm
)
SELECT sig_cd, makarea_id, ntfc_yn, makarea_nm, ntfc_de, mvm_res_cd,
       mvmn_resn, opert_de, makarea_ar, mvmn_desc, geom, :source_file,
       :source_yyyymm
  FROM normalized
 WHERE sig_cd IS NOT NULL
   AND makarea_id IS NOT NULL
   AND geom IS NOT NULL
   AND NOT ST_IsEmpty(geom)
ON CONFLICT (sig_cd, makarea_id) DO UPDATE
   SET ntfc_yn = EXCLUDED.ntfc_yn,
       makarea_nm = EXCLUDED.makarea_nm,
       ntfc_de = EXCLUDED.ntfc_de,
       mvm_res_cd = EXCLUDED.mvm_res_cd,
       mvmn_resn = EXCLUDED.mvmn_resn,
       opert_de = EXCLUDED.opert_de,
       makarea_ar = EXCLUDED.makarea_ar,
       mvmn_desc = EXCLUDED.mvmn_desc,
       geom = EXCLUDED.geom,
       source_file = EXCLUDED.source_file,
       source_yyyymm = EXCLUDED.source_yyyymm,
       loaded_at = now()
"""
                ),
                {"source_file": source_file, "source_yyyymm": source_yyyymm},
            )
            return max(result.rowcount or 0, 0)
    finally:
        engine.dispose()


def _truncate_target(pg_url: str) -> None:
    engine = create_engine(pg_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {TARGET_TABLE}"))
    finally:
        engine.dispose()


def _drop_stage(pg_url: str) -> None:
    engine = create_engine(pg_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {STAGE_TABLE}"))
    finally:
        engine.dispose()


def _analyze_target(pg_url: str) -> None:
    engine = create_engine(pg_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ANALYZE {TARGET_TABLE}"))
    finally:
        engine.dispose()


def _record_manifest(
    pg_url: str,
    *,
    sources: tuple[SppnMakareaSource, ...],
    mode: str,
    source_yyyymm: str | None,
) -> None:
    engine = create_engine(pg_url)
    source_files = [source.source_file for source in sources]
    try:
        with engine.begin() as conn:
            row_count = conn.execute(text(f"SELECT count(*) FROM {TARGET_TABLE}")).scalar_one()
            conn.execute(
                text(
                    """
INSERT INTO load_manifest (
  table_name, last_full_load_at, last_delta_at, row_count, source_zip,
  source_checksum, source_yyyymm, source_set, updated_at
) VALUES (
  :table_name,
  CASE WHEN :mode = 'full' THEN now() ELSE NULL END,
  CASE WHEN :mode <> 'full' THEN now() ELSE NULL END,
  :row_count,
  :source_zip,
  NULL,
  :source_yyyymm,
  CAST(:source_set AS jsonb),
  now()
)
ON CONFLICT (table_name) DO UPDATE
   SET last_full_load_at = COALESCE(EXCLUDED.last_full_load_at, load_manifest.last_full_load_at),
       last_delta_at = COALESCE(EXCLUDED.last_delta_at, load_manifest.last_delta_at),
       row_count = EXCLUDED.row_count,
       source_zip = EXCLUDED.source_zip,
       source_yyyymm = EXCLUDED.source_yyyymm,
       source_set = EXCLUDED.source_set,
       updated_at = now()
"""
                ),
                {
                    "table_name": TARGET_TABLE,
                    "mode": mode,
                    "row_count": row_count,
                    "source_zip": ", ".join(source_files),
                    "source_yyyymm": source_yyyymm,
                    "source_set": json.dumps(
                        {
                            "kind": "sppn_makarea",
                            "mode": mode,
                            "source_files": source_files,
                        },
                        ensure_ascii=False,
                    ),
                },
            )
    finally:
        engine.dispose()


def _gdal_pg_destination(pg_url: str) -> str:
    url = make_url(pg_url)
    return (
        "PG:"
        f"host={url.host or 'localhost'} "
        f"port={url.port or 5432} "
        f"dbname={url.database or ''} "
        f"user={url.username or ''} "
        f"password={url.password or ''}"
    )
