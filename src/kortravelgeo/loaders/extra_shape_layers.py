"""Analysis helpers for detail-dong and zone shape bundles."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from kortravelgeo.core.source_layers import (
    DETAIL_DONG_ENTRANCE_LAYER as DETAIL_DONG_ENTRANCE_LAYER,
)
from kortravelgeo.core.source_layers import (
    DETAIL_DONG_POLYGON_LAYER as DETAIL_DONG_POLYGON_LAYER,
)
from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders.shape_dbf import (
    KeyOverlap,
    KeySetStats,
    LayerSummary,
    file_key_set,
    file_layer_summary,
    overlap,
    zip_key_set,
    zip_layer_summary,
)

# DETAIL_DONG_POLYGON_LAYER and DETAIL_DONG_ENTRANCE_LAYER are re-exported from
# kortravelgeo.core.source_layers (single source of truth) so
# core.source_validation can reference them without importing this loader.
ELECTRONIC_BUILDING_LAYER = "TL_SPBD_BULD"

DETAIL_DONG_BUILDING_KEY_FIELDS: tuple[str, ...] = ("BD_MGT_SN", "EQB_MAN_SN")
DETAIL_DONG_ADDRESS_MANAGEMENT_FIELDS: tuple[str, ...] = ("ADR_MNG_NO",)
DETAIL_DONG_BUILDING_REF_FIELDS: tuple[str, ...] = ("SIG_CD", "BUL_MAN_NO")

ZONE_DUPLICATE_LAYER_KEYS: dict[str, tuple[str, ...]] = {
    "TL_SCCO_CTPRVN": ("CTPRVN_CD",),
    "TL_SCCO_SIG": ("SIG_CD",),
    "TL_SCCO_EMD": ("EMD_CD",),
    "TL_SCCO_LI": ("LI_CD",),
    "TL_KODIS_BAS": ("BAS_ID",),
}
ZONE_GEMD_LAYER = "TL_SCCO_GEMD"
ZONE_MAKAREA_LAYER = "TL_SPPN_MAKAREA"
ZONE_GEMD_KEY_FIELDS: tuple[str, ...] = ("EMD_CD",)
ZONE_MAKAREA_KEY_FIELDS: tuple[str, ...] = ("SIG_CD", "MAKAREA_ID")


@dataclass(frozen=True, slots=True)
class DetailDongShapeComparison:
    sido_name: str
    detail_dong_zip: str
    electronic_map_dir: str
    detail_dong_layer: LayerSummary
    detail_entrance_layer: LayerSummary
    electronic_building_layer: LayerSummary
    detail_building_overlap: KeyOverlap
    address_management_stats: KeySetStats
    entrance_building_ref_overlap: KeyOverlap


@dataclass(frozen=True, slots=True)
class ZoneLayerOverlap:
    layer_name: str
    key_fields: tuple[str, ...]
    zone_layer: LayerSummary
    electronic_layer: LayerSummary
    key_overlap: KeyOverlap


@dataclass(frozen=True, slots=True)
class ZoneShapeComparison:
    sido_name: str
    zone_zip: str
    electronic_map_dir: str
    duplicate_layer_overlaps: tuple[ZoneLayerOverlap, ...]
    gemd_layer: LayerSummary
    makarea_layer: LayerSummary
    gemd_emd_key_overlap: KeyOverlap
    makarea_key_stats: KeySetStats


def compare_detail_dong_shape_bundle(
    detail_dong_zip: Path | str,
    electronic_map_sido_dir: Path | str,
) -> DetailDongShapeComparison:
    """Compare detail-dong polygons with electronic map building polygons."""

    detail_path = Path(detail_dong_zip)
    electronic_root = Path(electronic_map_sido_dir)
    electronic_building = _layer_files(electronic_root, ELECTRONIC_BUILDING_LAYER)
    with zipfile.ZipFile(detail_path) as zip_file:
        detail_dong_layer = zip_layer_summary(zip_file, DETAIL_DONG_POLYGON_LAYER)
        detail_entrance_layer = zip_layer_summary(zip_file, DETAIL_DONG_ENTRANCE_LAYER)
        detail_building_keys = zip_key_set(
            zip_file,
            DETAIL_DONG_POLYGON_LAYER,
            DETAIL_DONG_BUILDING_KEY_FIELDS,
        )
        address_management_keys = zip_key_set(
            zip_file,
            DETAIL_DONG_POLYGON_LAYER,
            DETAIL_DONG_ADDRESS_MANAGEMENT_FIELDS,
        )
        detail_building_refs = zip_key_set(
            zip_file,
            DETAIL_DONG_POLYGON_LAYER,
            DETAIL_DONG_BUILDING_REF_FIELDS,
        )
        entrance_building_refs = zip_key_set(
            zip_file,
            DETAIL_DONG_ENTRANCE_LAYER,
            DETAIL_DONG_BUILDING_REF_FIELDS,
        )

    electronic_building_layer = file_layer_summary(
        electronic_building.shp_path,
        electronic_building.dbf_path,
    )
    electronic_building_keys = file_key_set(
        electronic_building.dbf_path,
        DETAIL_DONG_BUILDING_KEY_FIELDS,
    )

    return DetailDongShapeComparison(
        sido_name=electronic_root.name,
        detail_dong_zip=str(detail_path),
        electronic_map_dir=str(electronic_root),
        detail_dong_layer=detail_dong_layer,
        detail_entrance_layer=detail_entrance_layer,
        electronic_building_layer=electronic_building_layer,
        detail_building_overlap=overlap(detail_building_keys, electronic_building_keys),
        address_management_stats=address_management_keys.stats,
        entrance_building_ref_overlap=overlap(entrance_building_refs, detail_building_refs),
    )


def compare_zone_shape_bundle(
    zone_zip: Path | str,
    electronic_map_sido_dir: Path | str,
) -> ZoneShapeComparison:
    """Compare zone bundle duplicate layers with electronic map layers."""

    zone_path = Path(zone_zip)
    electronic_root = Path(electronic_map_sido_dir)
    duplicate_overlaps: list[ZoneLayerOverlap] = []
    with zipfile.ZipFile(zone_path) as zip_file:
        for layer_name, key_fields in ZONE_DUPLICATE_LAYER_KEYS.items():
            electronic_layer = _layer_files(electronic_root, layer_name)
            zone_keys = zip_key_set(zip_file, layer_name, key_fields)
            electronic_keys = file_key_set(electronic_layer.dbf_path, key_fields)
            duplicate_overlaps.append(
                ZoneLayerOverlap(
                    layer_name=layer_name,
                    key_fields=key_fields,
                    zone_layer=zip_layer_summary(zip_file, layer_name),
                    electronic_layer=file_layer_summary(
                        electronic_layer.shp_path,
                        electronic_layer.dbf_path,
                    ),
                    key_overlap=overlap(zone_keys, electronic_keys),
                )
            )

        gemd_layer = zip_layer_summary(zip_file, ZONE_GEMD_LAYER)
        makarea_layer = zip_layer_summary(zip_file, ZONE_MAKAREA_LAYER)
        gemd_keys = zip_key_set(zip_file, ZONE_GEMD_LAYER, ZONE_GEMD_KEY_FIELDS)
        emd_keys = zip_key_set(zip_file, "TL_SCCO_EMD", ZONE_GEMD_KEY_FIELDS)
        makarea_keys = zip_key_set(zip_file, ZONE_MAKAREA_LAYER, ZONE_MAKAREA_KEY_FIELDS)

    return ZoneShapeComparison(
        sido_name=electronic_root.name,
        zone_zip=str(zone_path),
        electronic_map_dir=str(electronic_root),
        duplicate_layer_overlaps=tuple(duplicate_overlaps),
        gemd_layer=gemd_layer,
        makarea_layer=makarea_layer,
        gemd_emd_key_overlap=overlap(gemd_keys, emd_keys),
        makarea_key_stats=makarea_keys.stats,
    )


@dataclass(frozen=True, slots=True)
class _LayerFiles:
    shp_path: Path
    dbf_path: Path


def _layer_files(root: Path, layer_name: str) -> _LayerFiles:
    candidates = sorted(root.glob(f"*/{layer_name}.shp"))
    if len(candidates) != 1:
        msg = f"expected one {layer_name}.shp under {root}, found {len(candidates)}"
        raise LoaderError(msg)
    shp_path = candidates[0]
    dbf_path = shp_path.with_suffix(".dbf")
    if not dbf_path.is_file():
        msg = f"missing DBF for {layer_name}: {dbf_path}"
        raise LoaderError(msg)
    return _LayerFiles(shp_path=shp_path, dbf_path=dbf_path)
