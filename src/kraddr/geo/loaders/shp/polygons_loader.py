"""GDAL-based SHP polygon/line loader limited to ADR-012 auxiliary layers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

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
    sql_statement: str | None = None


def build_shp_load_plan(path: Path | str) -> tuple[ShpLoadPlan, ...]:
    dataset = discover_sido_dataset(path)
    plans: list[ShpLoadPlan] = []
    for layer_name in POLYGON_LAYER_NAMES:
        layer = dataset.layer(layer_name)
        plans.append(
            ShpLoadPlan(
                source_layer=layer.name,
                target_table=TARGET_TABLES[layer.name],
                shp_path=layer.shp_path,
                dbf_path=layer.dbf_path,
                sql_statement=_sql_statement(layer),
            )
        )
    return tuple(plans)


async def load_shp_polygons(
    engine: AsyncEngine,
    path: Path | str,
    *,
    mode: str = "full",
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> int:
    plans = build_shp_load_plan(path)
    return await asyncio.to_thread(
        _load_plans_sync,
        engine.url.render_as_string(hide_password=False),
        plans,
        mode,
        on_progress,
        cancel_event,
    )


def _load_plans_sync(
    pg_url: str,
    plans: tuple[ShpLoadPlan, ...],
    mode: str,
    on_progress: ProgressCallback | None,
    cancel_event: asyncio.Event | None,
) -> int:
    try:
        from osgeo import gdal  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - depends on optional system GDAL
        msg = "GDAL Python binding is required for SHP polygon loading"
        raise LoaderError(msg) from exc

    loaded = 0
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
            openOptions=["ENCODING=CP949"],
            layerCreationOptions=["GEOMETRY_NAME=geom", "SPATIAL_INDEX=NONE"],
            srcSRS="EPSG:5179",
            dstSRS="EPSG:5179",
            accessMode="overwrite" if mode == "full" else "append",
            callback=callback,
        )
        with gdal.config_options({"PG_USE_COPY": "YES"}):
            result = gdal.VectorTranslate(
                f"PG:{pg_url}",
                str(plan.shp_path),
                options=options,
            )
        if result is None:
            msg = f"GDAL VectorTranslate failed for {plan.source_layer}"
            raise LoaderError(msg)
        loaded += 1
    if on_progress:
        on_progress(1.0)
    return loaded


def _sql_statement(layer: JusoLayerFiles) -> str | None:
    if layer.name == "TL_SPBD_BULD":
        return "SELECT BD_MGT_SN AS bd_mgt_sn, GEOMETRY AS geom FROM TL_SPBD_BULD"
    return None
