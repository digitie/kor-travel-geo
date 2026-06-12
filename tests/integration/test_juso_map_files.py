from pathlib import Path

import pytest

from kortravelgeo.loaders.juso_map import MASTER_LAYER_NAMES, discover_sido_dataset

JUSO_MAP_ROOT = Path("data/juso/도로명주소 전자지도")
REQUIRED_BULD_FIELDS = {
    "BD_MGT_SN",
    "BULD_MNNM",
    "BULD_SLNO",
    "LNBR_MNNM",
    "LNBR_SLNO",
    "MVM_RES_CD",
    "RN_CD",
    "SIG_CD",
}


def test_actual_juso_map_dataset_opens_master_layers() -> None:
    sido_dir = JUSO_MAP_ROOT / "강원특별자치도"
    if not sido_dir.exists():
        pytest.skip(f"actual juso map data is not available: {sido_dir}")

    dataset = discover_sido_dataset(sido_dir)

    assert dataset.sido_name == "강원특별자치도"
    assert dataset.sig_code == "51000"
    assert tuple(layer.name for layer in dataset.layers) == MASTER_LAYER_NAMES

    for layer in dataset.layers:
        shp_header = layer.read_shp_header()
        dbf_header = layer.read_dbf_header()

        assert shp_header.file_code == 9994
        assert shp_header.version == 1000
        assert shp_header.file_length_bytes == layer.shp_path.stat().st_size
        assert dbf_header.record_count > 0
        assert dbf_header.fields


def test_actual_juso_map_building_layer_has_required_fields() -> None:
    sido_dir = JUSO_MAP_ROOT / "강원특별자치도"
    if not sido_dir.exists():
        pytest.skip(f"actual juso map data is not available: {sido_dir}")

    dataset = discover_sido_dataset(sido_dir)
    building_layer = dataset.layer("TL_SPBD_BULD")
    dbf_header = building_layer.read_dbf_header()
    field_names = {field.name for field in dbf_header.fields}

    assert field_names >= REQUIRED_BULD_FIELDS
    assert dbf_header.record_count > 0
    assert building_layer.read_shp_header().shape_type == 5
