"""Analysis helpers for the road-address building shape bundle."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from kortravelgeo.loaders.juso_map import discover_sido_dataset
from kortravelgeo.loaders.shape_dbf import (
    DbfKeySet,
    KeyOverlap,
    LayerSummary,
    file_key_set,
    file_layer_summary,
    key_set_from_buffer,
    overlap,
    project_key_set,
    zip_key_set,
    zip_layer_summary,
)

ADDRESS_BUNDLE_LAYER = "TL_SGCO_RNADR_MST"
BUNDLE_ENTRANCE_LAYER = "TL_SPBD_ENTRC"
BUNDLE_CONNECTION_LAYER = "TL_SPOT_CNTC"
ELECTRONIC_BUILDING_LAYER = "TL_SPBD_BULD"
ELECTRONIC_ENTRANCE_LAYER = "TL_SPBD_ENTRC"

ADDRESS_KEY_FIELDS: tuple[str, ...] = (
    "SIG_CD",
    "RN_CD",
    "BULD_SE_CD",
    "BULD_MNNM",
    "BULD_SLNO",
    "BUL_MAN_NO",
    "EQB_MAN_SN",
)
ENTRANCE_KEY_FIELDS: tuple[str, ...] = ("SIG_CD", "BUL_MAN_NO", "ENT_MAN_NO", "EQB_MAN_SN")
CONNECTION_ENTRANCE_REF_FIELDS: tuple[str, ...] = ("SIG_CD", "ENT_MAN_NO")


@dataclass(frozen=True, slots=True)
class BuildingShapeBundleComparison:
    sido_name: str
    bundle_zip: str
    electronic_map_dir: str
    bundle_address_layer: LayerSummary
    electronic_building_layer: LayerSummary
    bundle_entrance_layer: LayerSummary
    electronic_entrance_layer: LayerSummary
    bundle_connection_layer: LayerSummary
    address_key_overlap: KeyOverlap
    entrance_key_overlap: KeyOverlap
    connection_entrance_ref_overlap: KeyOverlap


_key_set_from_buffer = key_set_from_buffer


def compare_building_shape_bundle(
    bundle_zip: Path | str,
    electronic_map_sido_dir: Path | str,
) -> BuildingShapeBundleComparison:
    """Compare the 202605 address building bundle with the electronic map layers."""

    bundle_path = Path(bundle_zip)
    electronic_root = Path(electronic_map_sido_dir)
    dataset = discover_sido_dataset(electronic_root)
    with zipfile.ZipFile(bundle_path) as zip_file:
        bundle_address_layer = _zip_layer_summary(zip_file, ADDRESS_BUNDLE_LAYER)
        bundle_entrance_layer = _zip_layer_summary(zip_file, BUNDLE_ENTRANCE_LAYER)
        bundle_connection_layer = _zip_layer_summary(zip_file, BUNDLE_CONNECTION_LAYER)
        bundle_address = _zip_key_set(zip_file, ADDRESS_BUNDLE_LAYER, ADDRESS_KEY_FIELDS)
        bundle_entrance = _zip_key_set(zip_file, BUNDLE_ENTRANCE_LAYER, ENTRANCE_KEY_FIELDS)
        bundle_connection_refs = _zip_key_set(
            zip_file,
            BUNDLE_CONNECTION_LAYER,
            CONNECTION_ENTRANCE_REF_FIELDS,
        )

    electronic_building = dataset.layer(ELECTRONIC_BUILDING_LAYER)
    electronic_entrance = dataset.layer(ELECTRONIC_ENTRANCE_LAYER)
    electronic_building_layer = file_layer_summary(
        electronic_building.shp_path,
        electronic_building.dbf_path,
    )
    electronic_entrance_layer = file_layer_summary(
        electronic_entrance.shp_path,
        electronic_entrance.dbf_path,
    )
    electronic_building_keys = file_key_set(electronic_building.dbf_path, ADDRESS_KEY_FIELDS)
    electronic_entrance_keys = file_key_set(electronic_entrance.dbf_path, ENTRANCE_KEY_FIELDS)
    bundle_entrance_refs = _project_entrance_refs(bundle_entrance)

    return BuildingShapeBundleComparison(
        sido_name=dataset.sido_name,
        bundle_zip=str(bundle_path),
        electronic_map_dir=str(electronic_root),
        bundle_address_layer=bundle_address_layer,
        electronic_building_layer=electronic_building_layer,
        bundle_entrance_layer=bundle_entrance_layer,
        electronic_entrance_layer=electronic_entrance_layer,
        bundle_connection_layer=bundle_connection_layer,
        address_key_overlap=overlap(bundle_address, electronic_building_keys),
        entrance_key_overlap=overlap(bundle_entrance, electronic_entrance_keys),
        connection_entrance_ref_overlap=overlap(bundle_connection_refs, bundle_entrance_refs),
    )


def _project_entrance_refs(entrance_keys: DbfKeySet) -> DbfKeySet:
    return project_key_set(entrance_keys, (0, 2))


def _zip_layer_summary(zip_file: zipfile.ZipFile, layer_name: str) -> LayerSummary:
    return zip_layer_summary(zip_file, layer_name)


def _zip_key_set(
    zip_file: zipfile.ZipFile,
    layer_name: str,
    key_fields: tuple[str, ...],
) -> DbfKeySet:
    return zip_key_set(zip_file, layer_name, key_fields)
