"""GDAL-based SHP polygon/line loader limited to ADR-012 auxiliary layers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.core.source_layers import (
    POLYGON_LAYER_NAMES as POLYGON_LAYER_NAMES,
)
from kortravelgeo.core.source_layers import (
    ROAD_INTERVAL_LAYER_NAME as ROAD_INTERVAL_LAYER_NAME,
)
from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders.juso_map import (
    DbfHeader,
    JusoLayerFiles,
    discover_sido_datasets,
    read_dbf_header,
)

ProgressCallback = Callable[[float], None]

# POLYGON_LAYER_NAMES and ROAD_INTERVAL_LAYER_NAME are re-exported from
# kortravelgeo.core.source_layers (single source of truth) so that
# core.source_validation can reference them without importing this loader.

TARGET_TABLES: dict[str, str] = {
    "TL_SCCO_CTPRVN": "tl_scco_ctprvn",
    "TL_SCCO_SIG": "tl_scco_sig",
    "TL_SCCO_EMD": "tl_scco_emd",
    "TL_SCCO_LI": "tl_scco_li",
    "TL_KODIS_BAS": "tl_kodis_bas",
    "TL_SPRD_MANAGE": "tl_sprd_manage",
    "TL_SPRD_INTRVL": "tl_sprd_intrvl",
    "TL_SPRD_RW": "tl_sprd_rw",
    "TL_SPBD_BULD": "tl_spbd_buld_polygon",
}

GEOMETRY_REPAIR_SPECS: dict[str, tuple[str, int]] = {
    "tl_scco_ctprvn": ("MultiPolygon", 3),
    "tl_scco_sig": ("MultiPolygon", 3),
    "tl_scco_emd": ("MultiPolygon", 3),
    "tl_scco_li": ("MultiPolygon", 3),
    "tl_kodis_bas": ("MultiPolygon", 3),
    "tl_sprd_manage": ("MultiLineString", 2),
    "tl_sprd_rw": ("MultiPolygon", 3),
    "tl_spbd_buld_polygon": ("MultiPolygon", 3),
}

BUILDING_POLYGON_LAYER_NAME = "TL_SPBD_BULD"
BUILDING_POLYGON_STAGE_TABLE = "_ktg_stage_spbd_buld_polygon"
BUILDING_POLYGON_STAGE_LOCK_KEY = "kor_travel_geo:tl_spbd_buld_polygon_stage"
BUILDING_POLYGON_STAGE_TRANSLATE_ATTEMPTS = 2
ROAD_INTERVAL_SOURCE_FIELDS = (
    "SIG_CD",
    "RDS_MAN_NO",
    "BSI_INT_SN",
    "ODD_BSI_MN",
    "EVE_BSI_MN",
)
ROAD_INTERVAL_COPY_COLUMNS = (
    "sig_cd",
    "rds_man_no",
    "bsi_int_sn",
    "start_bsi_no",
    "end_bsi_no",
    "source_file",
    "source_yyyymm",
)
ROAD_INTERVAL_COPY_SQL = f"""
COPY tl_sprd_intrvl
({", ".join(ROAD_INTERVAL_COPY_COLUMNS)})
FROM STDIN
"""


@dataclass(frozen=True, slots=True)
class RoadIntervalRow:
    sig_cd: str | None
    rds_man_no: str | None
    bsi_int_sn: str | None
    start_bsi_no: str | None
    end_bsi_no: str | None
    source_file: str
    source_yyyymm: str | None

    def to_copy_tuple(
        self,
    ) -> tuple[str | None, str | None, str | None, str | None, str | None, str, str | None]:
        return (
            self.sig_cd,
            self.rds_man_no,
            self.bsi_int_sn,
            self.start_bsi_no,
            self.end_bsi_no,
            self.source_file,
            self.source_yyyymm,
        )


@dataclass(frozen=True, slots=True)
class ShpLoadPlan:
    source_layer: str
    target_table: str
    shp_path: Path
    dbf_path: Path
    source_file: str
    source_yyyymm: str | None = None
    sql_statement: str | None = None
    geometry_type: str = "PROMOTE_TO_MULTI"


def _reset_gdal_error(gdal_module: Any) -> None:
    reset = getattr(gdal_module, "ErrorReset", None)
    if callable(reset):
        reset()


def _last_gdal_error(gdal_module: Any) -> str:
    message_getter = getattr(gdal_module, "GetLastErrorMsg", None)
    type_getter = getattr(gdal_module, "GetLastErrorType", None)
    number_getter = getattr(gdal_module, "GetLastErrorNo", None)
    message = str(message_getter() or "") if callable(message_getter) else ""
    error_type = type_getter() if callable(type_getter) else None
    error_number = number_getter() if callable(number_getter) else None
    details = []
    if error_type not in (None, 0):
        details.append(f"type={error_type}")
    if error_number not in (None, 0):
        details.append(f"no={error_number}")
    if message:
        details.append(f"message={message}")
    return ", ".join(details)


def _vector_translate_failure_message(
    plan: ShpLoadPlan,
    gdal_module: Any,
    *,
    staging: bool = False,
    attempts: int = 1,
) -> str:
    suffix = " staging" if staging else ""
    message = (
        f"GDAL VectorTranslate failed for {plan.source_layer}{suffix}; "
        f"source_file={plan.source_file}; shp_path={plan.shp_path}; attempts={attempts}"
    )
    gdal_error = _last_gdal_error(gdal_module)
    if gdal_error:
        message = f"{message}; gdal_error=({gdal_error})"
    return message


def build_shp_load_plan(
    path: Path | str,
    *,
    source_yyyymm: str | None = None,
) -> tuple[ShpLoadPlan, ...]:
    plans: list[ShpLoadPlan] = []
    for dataset in discover_sido_datasets(path):
        for layer_name in POLYGON_LAYER_NAMES:
            layer = dataset.layer(layer_name)
            source_file = _source_file_label(dataset.sido_name, dataset.sig_code, layer)
            plans.append(
                ShpLoadPlan(
                    source_layer=layer.name,
                    target_table=TARGET_TABLES[layer.name],
                    shp_path=layer.shp_path,
                    dbf_path=layer.dbf_path,
                    source_file=source_file,
                    source_yyyymm=source_yyyymm,
                    sql_statement=_sql_statement(
                        layer,
                        source_file=source_file,
                        source_yyyymm=source_yyyymm,
                    ),
                    geometry_type=_geometry_type(layer),
                )
            )
    return tuple(plans)


async def load_shp_polygons(
    engine: AsyncEngine,
    path: Path | str,
    *,
    mode: str = "full",
    source_yyyymm: str | None = None,
    analyze: bool = True,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> int:
    """Load ADR-012 auxiliary SHP layers into their PostGIS target tables.

    Set analyze=False only when a higher-level batch loads several 시도 folders
    back-to-back and will call the final batch with analyze=True. That keeps
    planner statistics fresh while avoiding 17 시도 x 9 layers repeated ANALYZE
    work during nationwide loads.
    """
    plans = build_shp_load_plan(path, source_yyyymm=source_yyyymm)
    return await asyncio.to_thread(
        _load_plans_sync,
        engine.url.render_as_string(hide_password=False),
        plans,
        mode,
        analyze,
        on_progress,
        cancel_event,
    )


def _load_plans_sync(
    pg_url: str,
    plans: tuple[ShpLoadPlan, ...],
    mode: str,
    analyze: bool,
    on_progress: ProgressCallback | None,
    cancel_event: asyncio.Event | None,
) -> int:
    try:
        from osgeo import gdal  # type: ignore[import-not-found,import-untyped,unused-ignore]
    except ImportError as exc:  # pragma: no cover - depends on optional system GDAL
        msg = "GDAL Python binding is required for SHP polygon loading"
        raise LoaderError(msg) from exc

    loaded = 0
    destination = _gdal_pg_destination(pg_url)
    if mode == "full":
        _truncate_target_tables(pg_url, tuple(plan.target_table for plan in plans))

    for index, plan in enumerate(plans):
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError("shp polygon loader cancelled")

        def callback(
            complete: float,
            _message: str,
            _data: object,
            *,
            layer_index: int = index,
        ) -> int:
            if cancel_event and cancel_event.is_set():
                return 0
            if on_progress:
                on_progress((layer_index + complete) / len(plans))
            return 1

        if plan.source_layer == ROAD_INTERVAL_LAYER_NAME:
            def copy_progress(
                complete: float,
                *,
                layer_index: int = index,
            ) -> None:
                _emit_layer_progress(layer_index, len(plans), complete, on_progress)

            _copy_road_interval_dbf(
                pg_url,
                plan,
                on_layer_progress=copy_progress,
                cancel_event=cancel_event,
            )
            loaded += 1
            continue

        if plan.source_layer == BUILDING_POLYGON_LAYER_NAME:
            _copy_building_polygon_with_stage(
                pg_url,
                plan,
                gdal_module=gdal,
                callback=callback,
                cancel_event=cancel_event,
            )
            loaded += 1
            continue

        options = gdal.VectorTranslateOptions(
            format="PostgreSQL",
            layerName=plan.target_table,
            SQLStatement=plan.sql_statement,
            layerCreationOptions=["GEOMETRY_NAME=geom", "SPATIAL_INDEX=NONE"],
            srcSRS="EPSG:5179",
            dstSRS="EPSG:5179",
            accessMode="append",
            geometryType=plan.geometry_type,
            callback=callback,
        )
        _reset_gdal_error(gdal)
        with gdal.config_options({"PG_USE_COPY": "YES", "SHAPE_ENCODING": "CP949"}):
            result = gdal.VectorTranslate(
                destination,
                str(plan.shp_path),
                options=options,
            )
        if result is None:
            raise LoaderError(_vector_translate_failure_message(plan, gdal))
        loaded += 1
    if analyze:
        # Gate geometry repair on the same flag as ANALYZE so batched per-시도
        # loads (analyze=False until the final 시도) run the non-indexable
        # `NOT ST_IsValid(geom)` scan once over the fully-loaded tables instead
        # of re-validating every accumulated row after each 시도 (was O(N^2)).
        _repair_invalid_geometries(pg_url, _unique_target_tables(plans))
        _analyze_target_tables(
            pg_url,
            _unique_target_tables(plans),
        )
    if on_progress:
        on_progress(1.0)
    return loaded


def _repair_invalid_geometries(pg_url: str, table_names: Sequence[str]) -> None:
    repair_tables = [
        table_name for table_name in table_names if table_name in GEOMETRY_REPAIR_SPECS
    ]
    if not repair_tables:
        return

    engine = create_engine(pg_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL search_path = public, x_extension"))
            for table_name in repair_tables:
                geometry_type, collection_type = GEOMETRY_REPAIR_SPECS[table_name]
                result = conn.execute(
                    text(
                        f"""
UPDATE {table_name}
   SET geom = ST_Multi(
     ST_CollectionExtract(ST_MakeValid(geom), :collection_type)
   )::geometry({geometry_type}, 5179)
 WHERE geom IS NOT NULL
   AND NOT ST_IsValid(geom)
"""
                    ),
                    {"collection_type": collection_type},
                )
                repaired_count = result.rowcount if result.rowcount >= 0 else 0
                if repaired_count:
                    print(
                        "SHP geometry repair applied: "
                        f"table={table_name}, repaired={repaired_count}"
                    )
    finally:
        engine.dispose()


def _emit_layer_progress(
    layer_index: int,
    layer_count: int,
    complete: float,
    on_progress: ProgressCallback | None,
) -> None:
    if on_progress:
        on_progress((layer_index + complete) / layer_count)


def _copy_road_interval_dbf(
    pg_url: str,
    plan: ShpLoadPlan,
    *,
    on_layer_progress: ProgressCallback | None,
    cancel_event: asyncio.Event | None,
) -> int:
    copied = 0
    header = read_dbf_header(plan.dbf_path)
    libpq_url = make_url(pg_url).set(drivername="postgresql").render_as_string(
        hide_password=False
    )
    # psycopg opens an implicit transaction for the context manager. Keep
    # autocommit disabled and commit explicitly after COPY completes so a
    # cancellation/error rolls the partial layer back on context exit.
    with psycopg.connect(libpq_url, autocommit=False) as conn, conn.cursor() as cur:
        with cur.copy(ROAD_INTERVAL_COPY_SQL) as copy:
            for processed, row in enumerate(
                _iter_road_interval_copy_rows(plan, header=header),
                start=1,
            ):
                if cancel_event and cancel_event.is_set():
                    raise asyncio.CancelledError("shp road interval loader cancelled")
                copy.write_row(row.to_copy_tuple())
                copied += 1
                if on_layer_progress and processed % 100_000 == 0:
                    on_layer_progress(processed / max(header.record_count, 1))
        conn.commit()
    if on_layer_progress:
        on_layer_progress(1.0)
    return copied


def _copy_building_polygon_with_stage(
    pg_url: str,
    plan: ShpLoadPlan,
    *,
    gdal_module: Any,
    callback: Callable[[float, str, object], int],
    cancel_event: asyncio.Event | None,
) -> None:
    lock_engine, lock_conn = _acquire_building_polygon_stage_lock(pg_url)
    try:
        _drop_stage_table(pg_url, BUILDING_POLYGON_STAGE_TABLE)
        options = gdal_module.VectorTranslateOptions(
            format="PostgreSQL",
            layerName=BUILDING_POLYGON_STAGE_TABLE,
            SQLStatement=plan.sql_statement,
            layerCreationOptions=["GEOMETRY_NAME=geom", "SPATIAL_INDEX=NONE"],
            srcSRS="EPSG:5179",
            dstSRS="EPSG:5179",
            accessMode="overwrite",
            geometryType=plan.geometry_type,
            callback=callback,
        )
        result = None
        for attempt in range(1, BUILDING_POLYGON_STAGE_TRANSLATE_ATTEMPTS + 1):
            _reset_gdal_error(gdal_module)
            with gdal_module.config_options({"PG_USE_COPY": "YES", "SHAPE_ENCODING": "CP949"}):
                result = gdal_module.VectorTranslate(
                    _gdal_pg_destination(pg_url),
                    str(plan.shp_path),
                    options=options,
                )
            if result is not None:
                break
            if attempt < BUILDING_POLYGON_STAGE_TRANSLATE_ATTEMPTS:
                _drop_stage_table(pg_url, BUILDING_POLYGON_STAGE_TABLE)
        if result is None:
            raise LoaderError(
                _vector_translate_failure_message(
                    plan,
                    gdal_module,
                    staging=True,
                    attempts=BUILDING_POLYGON_STAGE_TRANSLATE_ATTEMPTS,
                )
            )
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError("shp building polygon loader cancelled")
        _insert_building_polygon_stage(pg_url, plan)
    finally:
        try:
            _drop_stage_table(pg_url, BUILDING_POLYGON_STAGE_TABLE)
        finally:
            _release_building_polygon_stage_lock(lock_engine, lock_conn)


def _insert_building_polygon_stage(pg_url: str, plan: ShpLoadPlan) -> None:
    engine = create_engine(pg_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL search_path = public, x_extension"))
            staged_count = int(
                conn.execute(
                    text(f"SELECT count(*) FROM {BUILDING_POLYGON_STAGE_TABLE}")
                ).scalar_one()
            )
            result = conn.execute(
                text(
                    f"""
INSERT INTO {plan.target_table} (
  bd_mgt_sn,
  sig_cd,
  emd_cd,
  li_cd,
  rds_sig_cd,
  rn_cd,
  buld_se_cd,
  buld_mnnm,
  buld_slno,
  geom,
  source_file,
  source_yyyymm
)
SELECT
  NULLIF(BTRIM(bd_mgt_sn::text), ''),
  NULLIF(BTRIM(sig_cd::text), ''),
  NULLIF(BTRIM(emd_cd::text), ''),
  NULLIF(BTRIM(li_cd::text), ''),
  NULLIF(BTRIM(rds_sig_cd::text), ''),
  NULLIF(BTRIM(rn_cd::text), ''),
  NULLIF(BTRIM(buld_se_cd::text), ''),
  NULLIF(BTRIM(buld_mnnm::text), '')::integer,
  NULLIF(BTRIM(buld_slno::text), '')::integer,
  ST_Multi(geom)::geometry(MultiPolygon, 5179),
  :source_file,
  :source_yyyymm
FROM {BUILDING_POLYGON_STAGE_TABLE}
WHERE NULLIF(BTRIM(bd_mgt_sn::text), '') IS NOT NULL
  AND geom IS NOT NULL
"""
                ),
                {
                    "source_file": plan.source_file,
                    "source_yyyymm": plan.source_yyyymm,
                },
            )
            inserted_count = result.rowcount if result.rowcount >= 0 else staged_count
            skipped_count = staged_count - inserted_count
            if skipped_count:
                print(
                    "SHP building polygon staging skipped invalid rows: "
                    f"source_layer={plan.source_layer}, "
                    f"source_file={plan.source_file}, "
                    f"staged={staged_count}, inserted={inserted_count}, "
                    f"skipped={skipped_count}"
                )
    finally:
        engine.dispose()


def _acquire_building_polygon_stage_lock(pg_url: str) -> tuple[Engine, Connection]:
    engine = create_engine(pg_url)
    conn = engine.connect()
    try:
        locked = conn.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:lock_key))"),
            {"lock_key": BUILDING_POLYGON_STAGE_LOCK_KEY},
        ).scalar_one()
        if not bool(locked):
            msg = (
                "another TL_SPBD_BULD staging load is already running in this DB; "
                "retry after it finishes"
            )
            raise LoaderError(msg)
        return engine, conn
    except Exception:
        conn.close()
        engine.dispose()
        raise


def _release_building_polygon_stage_lock(engine: Engine, conn: Connection) -> None:
    try:
        conn.execute(
            text("SELECT pg_advisory_unlock(hashtext(:lock_key))"),
            {"lock_key": BUILDING_POLYGON_STAGE_LOCK_KEY},
        )
    finally:
        conn.close()
        engine.dispose()


def _drop_stage_table(pg_url: str, table_name: str) -> None:
    engine = create_engine(pg_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
    finally:
        engine.dispose()


def _iter_road_interval_copy_rows(
    plan: ShpLoadPlan,
    *,
    header: DbfHeader | None = None,
) -> Iterator[RoadIntervalRow]:
    resolved_header = header or read_dbf_header(plan.dbf_path)
    offsets = _dbf_field_offsets(resolved_header, ROAD_INTERVAL_SOURCE_FIELDS)
    file_size = plan.dbf_path.stat().st_size
    with plan.dbf_path.open("rb") as file:
        file.seek(resolved_header.header_length)
        for record_no in range(1, resolved_header.record_count + 1):
            record = file.read(resolved_header.record_length)
            if len(record) != resolved_header.record_length:
                msg = (
                    f"{plan.dbf_path}:{record_no} truncated DBF record: "
                    f"expected {resolved_header.record_length} bytes, got {len(record)} "
                    f"(record_count={resolved_header.record_count}, file_size={file_size})"
                )
                raise LoaderError(msg)
            if record[:1] == b"*":
                continue
            yield RoadIntervalRow(
                sig_cd=_dbf_value(
                    record,
                    offsets["SIG_CD"],
                    plan=plan,
                    record_no=record_no,
                    field_name="SIG_CD",
                ),
                rds_man_no=_dbf_value(
                    record,
                    offsets["RDS_MAN_NO"],
                    plan=plan,
                    record_no=record_no,
                    field_name="RDS_MAN_NO",
                ),
                bsi_int_sn=_dbf_value(
                    record,
                    offsets["BSI_INT_SN"],
                    plan=plan,
                    record_no=record_no,
                    field_name="BSI_INT_SN",
                ),
                start_bsi_no=_dbf_value(
                    record,
                    offsets["ODD_BSI_MN"],
                    plan=plan,
                    record_no=record_no,
                    field_name="ODD_BSI_MN",
                ),
                end_bsi_no=_dbf_value(
                    record,
                    offsets["EVE_BSI_MN"],
                    plan=plan,
                    record_no=record_no,
                    field_name="EVE_BSI_MN",
                ),
                source_file=plan.source_file,
                source_yyyymm=plan.source_yyyymm,
            )


def _dbf_field_offsets(
    header: DbfHeader,
    required_fields: tuple[str, ...],
) -> dict[str, tuple[int, int]]:
    offsets: dict[str, tuple[int, int]] = {}
    offset = 1
    for field in header.fields:
        offsets[field.name] = (offset, offset + field.length)
        offset += field.length
    missing = [field for field in required_fields if field not in offsets]
    if missing:
        msg = f"DBF is missing required field(s): {', '.join(missing)}"
        raise LoaderError(msg)
    return offsets


def _dbf_value(
    record: bytes,
    offset: tuple[int, int],
    *,
    plan: ShpLoadPlan,
    record_no: int,
    field_name: str,
) -> str | None:
    raw = record[offset[0] : offset[1]].rstrip(b"\x00")
    try:
        value = raw.decode("cp949").strip()
    except UnicodeDecodeError as exc:
        msg = (
            f"{plan.dbf_path}:{record_no} field {field_name} failed CP949 decode "
            f"at byte slice {offset[0]}:{offset[1]}: {exc}"
        )
        raise LoaderError(msg) from exc
    return value or None


def _sql_statement(
    layer: JusoLayerFiles,
    *,
    source_file: str,
    source_yyyymm: str | None,
) -> str | None:
    metadata = _metadata_projection(
        source_file=source_file,
        source_yyyymm=source_yyyymm,
    )
    statements = {
        "TL_SCCO_CTPRVN": (
            "SELECT CTPRVN_CD AS ctprvn_cd, CTP_KOR_NM AS ctp_kor_nm"
            f"{metadata} "
            "FROM TL_SCCO_CTPRVN"
        ),
        "TL_SCCO_SIG": (
            "SELECT SIG_CD AS sig_cd, SIG_KOR_NM AS sig_kor_nm"
            f"{metadata} FROM TL_SCCO_SIG"
        ),
        "TL_SCCO_EMD": (
            "SELECT EMD_CD AS emd_cd, EMD_KOR_NM AS emd_kor_nm"
            f"{metadata} FROM TL_SCCO_EMD"
        ),
        "TL_SCCO_LI": (
            "SELECT LI_CD AS li_cd, LI_KOR_NM AS li_kor_nm"
            f"{metadata} FROM TL_SCCO_LI"
        ),
        "TL_KODIS_BAS": (
            "SELECT BAS_MGT_SN AS bas_mgt_sn, BAS_ID AS bas_id"
            f"{metadata} FROM TL_KODIS_BAS"
        ),
        "TL_SPRD_MANAGE": (
            "SELECT SIG_CD AS sig_cd, RDS_MAN_NO AS rds_man_no, RN_CD AS rn_cd, RN AS rn"
            f"{metadata} "
            "FROM TL_SPRD_MANAGE"
        ),
        "TL_SPRD_INTRVL": (
            "SELECT SIG_CD AS sig_cd, RDS_MAN_NO AS rds_man_no, "
            "BSI_INT_SN AS bsi_int_sn, ODD_BSI_MN AS start_bsi_no, "
            f"EVE_BSI_MN AS end_bsi_no{metadata} FROM TL_SPRD_INTRVL"
        ),
        "TL_SPRD_RW": f"SELECT SIG_CD AS sig_cd, RW_SN AS rw_sn{metadata} FROM TL_SPRD_RW",
        "TL_SPBD_BULD": (
            "SELECT BD_MGT_SN AS bd_mgt_sn, SIG_CD AS sig_cd, EMD_CD AS emd_cd, "
            "LI_CD AS li_cd, RDS_SIG_CD AS rds_sig_cd, RN_CD AS rn_cd, "
            "BULD_SE_CD AS buld_se_cd, BULD_MNNM AS buld_mnnm, "
            f"BULD_SLNO AS buld_slno{metadata} FROM TL_SPBD_BULD"
        ),
    }
    return statements[layer.name]


def _geometry_type(layer: JusoLayerFiles) -> str:
    if layer.name == "TL_SPRD_INTRVL":
        return "NONE"
    if layer.name == "TL_SPRD_MANAGE":
        return "PROMOTE_TO_MULTI"
    return "PROMOTE_TO_MULTI"


def _truncate_target_tables(pg_url: str, table_names: tuple[str, ...]) -> None:
    if not table_names:
        return
    engine = create_engine(pg_url)
    try:
        tables = ", ".join(table_names)
        with engine.begin() as conn:
            snapshot = _table_count_snapshot(conn, table_names)
            if snapshot:
                print(
                    "SHP full reset: approximate row counts before TRUNCATE: "
                    + ", ".join(f"{table}={count}" for table, count in snapshot)
                )
            conn.execute(text(f"TRUNCATE TABLE {tables}"))
    finally:
        engine.dispose()


def _analyze_target_tables(pg_url: str, table_names: tuple[str, ...]) -> None:
    if not table_names:
        return
    engine = create_engine(pg_url)
    try:
        for table_name in table_names:
            with engine.begin() as conn:
                conn.execute(text(f"ANALYZE {table_name}"))
    finally:
        engine.dispose()


def _unique_target_tables(plans: tuple[ShpLoadPlan, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(plan.target_table for plan in plans))


def _table_count_snapshot(
    conn: Connection, table_names: tuple[str, ...]
) -> tuple[tuple[str, int], ...]:
    rows: list[tuple[str, int]] = []
    for table_name in table_names:
        reltuples = conn.execute(
            text(
                """
SELECT GREATEST(COALESCE(c.reltuples, 0), 0)::bigint
  FROM pg_class c
 WHERE c.oid = to_regclass(:table_name)
"""
            ),
            {"table_name": table_name},
        ).scalar()
        rows.append((table_name, int(reltuples or 0)))
    return tuple(rows)


def _gdal_pg_destination(pg_url: str) -> str:
    url = make_url(pg_url)
    connect_timeout = str(url.query.get("connect_timeout", "10"))
    parts = {
        "dbname": url.database,
        "host": url.host,
        "port": str(url.port) if url.port is not None else None,
        "user": url.username,
        "password": url.password,
        "connect_timeout": connect_timeout,
    }
    return "PG:" + " ".join(
        f"{key}={_quote_pg_conninfo(value)}" for key, value in parts.items() if value
    )


def _quote_pg_conninfo(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _source_file_label(
    sido_name: str,
    sig_code: str,
    layer: JusoLayerFiles,
) -> str:
    return f"{sido_name}/{sig_code}/{layer.shp_path.name}"


def _metadata_projection(
    *,
    source_file: str,
    source_yyyymm: str | None,
) -> str:
    return (
        f", {_sql_literal(source_file)} AS source_file, "
        f"{_sql_literal(source_yyyymm)} AS source_yyyymm"
    )


def _sql_literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"
