"""GDAL-based SHP polygon/line loader limited to ADR-012 auxiliary layers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.exceptions import LoaderError
from kraddr.geo.loaders.juso_map import JusoLayerFiles, discover_sido_dataset

ProgressCallback = Callable[[float], None]

POLYGON_LAYER_NAMES: tuple[str, ...] = (
    "TL_SCCO_CTPRVN",
    "TL_SCCO_SIG",
    "TL_SCCO_EMD",
    "TL_SCCO_LI",
    "TL_KODIS_BAS",
    "TL_SPRD_MANAGE",
    "TL_SPRD_INTRVL",
    "TL_SPRD_RW",
    "TL_SPBD_BULD",
)

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


def build_shp_load_plan(
    path: Path | str,
    *,
    source_yyyymm: str | None = None,
) -> tuple[ShpLoadPlan, ...]:
    dataset = discover_sido_dataset(path)
    plans: list[ShpLoadPlan] = []
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
        from osgeo import gdal  # type: ignore[import-untyped]
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
        with gdal.config_options({"PG_USE_COPY": "YES", "SHAPE_ENCODING": "CP949"}):
            result = gdal.VectorTranslate(
                destination,
                str(plan.shp_path),
                options=options,
            )
        if result is None:
            msg = f"GDAL VectorTranslate failed for {plan.source_layer}"
            raise LoaderError(msg)
        loaded += 1
    if analyze:
        _analyze_target_tables(
            pg_url,
            tuple(dict.fromkeys(plan.target_table for plan in plans)),
        )
    if on_progress:
        on_progress(1.0)
    return loaded


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
        with engine.begin() as conn:
            for table_name in table_names:
                conn.execute(text(f"ANALYZE {table_name}"))
    finally:
        engine.dispose()


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
