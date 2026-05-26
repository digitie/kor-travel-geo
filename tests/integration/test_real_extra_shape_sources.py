from __future__ import annotations

import struct
import zipfile
from dataclasses import dataclass
from os import getenv
from pathlib import Path

import pytest

from kraddr.geo.loaders.building_shape_bundle import compare_building_shape_bundle

DATA_ROOT = Path("data/juso")
ALT_DATA_ROOTS = (
    Path("/mnt/f/dev/python-kraddr-geo/data/juso"),
    Path("/home/digitie/kraddr-geo-data/juso"),
)

SHAPE_TYPES = {
    1: "Point",
    3: "PolyLine",
    5: "Polygon",
}


def test_actual_detail_dong_zip_contains_address_dong_polygon_and_entrance_point() -> None:
    archive = _require(
        DATA_ROOT / "건물군 내 상세주소 동 도형" / "건물군내동도형_전체분_세종특별자치시.zip"
    )
    layers = _zip_layers(archive)

    assert layers["TL_SGCO_RNADR_DONG"].shape_type == "Polygon"
    assert layers["TL_SGCO_RNADR_DONG"].rows == 40478
    assert {"ADR_MNG_NO", "BD_MGT_SN", "EQB_MAN_SN"} <= set(
        layers["TL_SGCO_RNADR_DONG"].fields
    )
    assert layers["TL_SPBD_ENTRC_DONG"].shape_type == "Point"
    assert layers["TL_SPBD_ENTRC_DONG"].rows == 4098
    assert {"SIG_CD", "ENT_MAN_NO", "ENTRC_DC"} <= set(layers["TL_SPBD_ENTRC_DONG"].fields)


def test_actual_zone_zip_overlaps_electronic_map_and_adds_two_layers() -> None:
    archive = _require(DATA_ROOT / "구역의 도형" / "구역의도형_전체분_세종특별자치시.zip")
    layers = _zip_layers(archive)

    assert {"TL_SCCO_CTPRVN", "TL_SCCO_SIG", "TL_SCCO_EMD", "TL_SCCO_LI", "TL_KODIS_BAS"} <= set(
        layers
    )
    assert layers["TL_SCCO_EMD"].rows == 33
    assert layers["TL_SCCO_LI"].rows == 117
    assert layers["TL_KODIS_BAS"].rows == 155
    assert layers["TL_SCCO_GEMD"].shape_type == "Polygon"
    assert layers["TL_SCCO_GEMD"].rows == 24
    assert layers["TL_SPPN_MAKAREA"].shape_type == "Polygon"
    assert layers["TL_SPPN_MAKAREA"].rows == 146


def test_actual_building_shape_zip_is_address_bundle_not_electronic_map_duplicate() -> None:
    archive = _require(
        DATA_ROOT / "도로명주소 건물 도형" / "건물도형_전체분_세종특별자치시.zip"
    )
    layers = _zip_layers(archive)

    assert layers["TL_SGCO_RNADR_MST"].shape_type == "Polygon"
    assert layers["TL_SGCO_RNADR_MST"].rows == 27792
    assert {"ADR_MNG_NO", "SIG_CD", "RN_CD", "BUL_MAN_NO"} <= set(
        layers["TL_SGCO_RNADR_MST"].fields
    )
    assert layers["TL_SPBD_ENTRC"].shape_type == "Point"
    assert layers["TL_SPBD_ENTRC"].rows == 28111
    assert layers["TL_SPOT_CNTC"].shape_type == "PolyLine"
    assert layers["TL_SPOT_CNTC"].rows == 27776


def test_actual_building_shape_bundle_sejong_key_overlap_is_not_simple_duplicate() -> None:
    comparison = compare_building_shape_bundle(
        _require(DATA_ROOT / "도로명주소 건물 도형" / "건물도형_전체분_세종특별자치시.zip"),
        _require(DATA_ROOT / "도로명주소 전자지도" / "세종특별자치시"),
    )

    assert comparison.bundle_address_layer.row_count == 27792
    assert comparison.electronic_building_layer.row_count == 55819
    assert comparison.address_key_overlap.intersection_count == 15339
    assert comparison.address_key_overlap.left_only_count == 12453
    assert comparison.address_key_overlap.right_only_count == 40480
    assert comparison.entrance_key_overlap.intersection_count == 27766
    assert comparison.entrance_key_overlap.left_only_count == 345
    assert comparison.entrance_key_overlap.right_only_count == 21
    assert comparison.connection_entrance_ref_overlap.intersection_count == 27774
    assert comparison.connection_entrance_ref_overlap.left_only_count == 2


@pytest.mark.skipif(
    getenv("KRADDR_GEO_SLOW_REAL_DATA") != "1",
    reason="set KRADDR_GEO_SLOW_REAL_DATA=1 to scan the large Gyeongnam DBFs",
)
def test_actual_building_shape_bundle_gyeongnam_key_overlap_slow() -> None:
    comparison = compare_building_shape_bundle(
        _require(DATA_ROOT / "도로명주소 건물 도형" / "건물도형_전체분_경상남도.zip"),
        _require(DATA_ROOT / "도로명주소 전자지도" / "경상남도"),
    )

    assert comparison.bundle_address_layer.row_count == 656230
    assert comparison.electronic_building_layer.row_count == 1269029
    assert comparison.address_key_overlap.intersection_count == 345290
    assert comparison.address_key_overlap.left_only_count == 310940
    assert comparison.address_key_overlap.right_only_count == 923739
    assert comparison.entrance_key_overlap.intersection_count == 656114
    assert comparison.entrance_key_overlap.left_only_count == 5302
    assert comparison.entrance_key_overlap.right_only_count == 19
    assert comparison.connection_entrance_ref_overlap.intersection_count == 652660
    assert comparison.connection_entrance_ref_overlap.left_only_count == 0


def test_actual_road_address_entrance_zip_is_direct_text_with_bd_mgt_sn_and_5179_point() -> None:
    archive = _require(
        DATA_ROOT / "도로명주소 출입구 정보" / "도로명주소출입구_전체분_세종특별자치시.zip"
    )
    with zipfile.ZipFile(archive) as zip_file:
        member = zip_file.namelist()[0]
        rows = zip_file.read(member).decode("cp949").splitlines()[:3]

    first = rows[0].split("|")

    assert member == "RNENTDATA_2605_36110.txt"
    assert [len(row.split("|")) for row in rows] == [19, 19, 19]
    assert first[0] == "36110101200000200181100000"
    assert first[6] == "361102000002"
    assert first[14] == "32169"
    assert first[15] == "RM"
    assert first[16] == "01"
    assert float(first[17]) == pytest.approx(983296.172464)
    assert float(first[18]) == pytest.approx(1833330.968984)


@dataclass(frozen=True, slots=True)
class LayerInfo:
    name: str
    shape_type: str
    rows: int
    fields: tuple[str, ...]


def _require(path: Path) -> Path:
    if path.exists():
        return path
    try:
        relative = path.relative_to(DATA_ROOT)
    except ValueError:
        relative = None
    if relative is not None:
        for root in ALT_DATA_ROOTS:
            candidate = root / relative
            if candidate.exists():
                return candidate
    pytest.skip(f"actual juso data not available: {path}")


def _zip_layers(archive: Path) -> dict[str, LayerInfo]:
    layers: dict[str, LayerInfo] = {}
    with zipfile.ZipFile(archive) as zip_file:
        names = zip_file.namelist()
        for shp_name in names:
            if not shp_name.lower().endswith(".shp"):
                continue
            layer_name = _layer_name(shp_name)
            dbf_name = next(
                name
                for name in names
                if name.lower().endswith(".dbf") and Path(name).stem == Path(shp_name).stem
            )
            shape_type = SHAPE_TYPES[struct.unpack("<i", zip_file.read(shp_name)[:100][32:36])[0]]
            rows, fields = _dbf_header(zip_file.read(dbf_name))
            layers[layer_name] = LayerInfo(layer_name, shape_type, rows, fields)
    return layers


def _layer_name(path: str) -> str:
    stem = Path(path).stem
    for part in stem.split("."):
        if part.startswith("TL_"):
            return part
    return stem


def _dbf_header(data: bytes) -> tuple[int, tuple[str, ...]]:
    rows = struct.unpack("<I", data[4:8])[0]
    header_len = struct.unpack("<H", data[8:10])[0]
    fields: list[str] = []
    pos = 32
    while pos < header_len - 1 and data[pos] != 0x0D:
        raw = data[pos : pos + 32]
        fields.append(raw[:11].split(b"\x00", 1)[0].decode("ascii"))
        pos += 32
    return rows, tuple(fields)
