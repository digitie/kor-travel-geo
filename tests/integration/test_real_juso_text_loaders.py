from __future__ import annotations

from pathlib import Path

import pytest

from kortravelgeo.loaders.shp.polygons_loader import POLYGON_LAYER_NAMES, build_shp_load_plan
from kortravelgeo.loaders.text.daily_juso_loader import (
    discover_daily_juso_sources,
    is_no_data_source,
    iter_daily_juso_rows,
)
from kortravelgeo.loaders.text.juso_hangul_loader import (
    discover_juso_hangul_files,
    iter_juso_rows,
)
from kortravelgeo.loaders.text.locsum_loader import discover_locsum_files, iter_locsum_rows
from kortravelgeo.loaders.text.navi_loader import (
    discover_navi_build_files,
    discover_navi_entrance_files,
    iter_navi_build_rows,
    iter_navi_entrance_rows,
)

DATA_ROOT = Path("data/juso")
ALT_DATA_ROOTS = (
    Path("/mnt/f/dev/kor-travel-geo/data/juso"),
    Path("/home/digitie/kor-travel-geo-data/juso"),
)


def _require(path: Path) -> Path:
    if not path.exists():
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
    return path


def test_actual_juso_hangul_file_loads_rows_and_pnu_mapping() -> None:
    root = _require(DATA_ROOT / "202603_도로명주소 한글_전체분")
    sources = {source.name: source for source in discover_juso_hangul_files(root)}

    seoul = sources["rnaddrkor_seoul.txt"]
    rows = list(iter_juso_rows(seoul, source_yyyymm="202603", limit=25))

    assert len(rows) == 25
    first = rows[0]
    assert first.bd_mgt_sn == "11110101310001200009400000"
    assert first.bjd_cd == "1111010100"
    assert first.rncode_full == "111103100012"
    assert first.rn == "자하문로"
    assert first.buld_mnnm == 94
    assert first.zip_no == "03047"
    assert first.pnu == "1111010100101440003"
    assert all(row.source_file == "rnaddrkor_seoul.txt" for row in rows)


def test_actual_daily_juso_zip_loads_mst_rows_and_skips_no_data_members() -> None:
    archive = _require(DATA_ROOT / "daily" / "20260401_dailyjusukrdata.zip")
    sources = discover_daily_juso_sources(archive)

    rows = list(iter_daily_juso_rows(sources.mst[0], source_yyyymm=None))

    assert len(rows) == 422
    assert len(sources.lnbr) == 1
    assert rows[0].mvmn_de == "20260402"
    assert rows[0].juso.source_yyyymm == "202604"
    assert {row.mvm_res_cd for row in rows} == {"31", "34", "63"}
    assert sum(1 for row in rows if row.mvm_res_cd == "31") == 185
    assert sum(1 for row in rows if row.mvm_res_cd == "34") == 57
    assert sum(1 for row in rows if row.mvm_res_cd == "63") == 180

    no_data_archive = _require(DATA_ROOT / "daily" / "20260404_dailyjusukrdata.zip")
    no_data_sources = discover_daily_juso_sources(no_data_archive)
    assert is_no_data_source(no_data_sources.mst[0])
    assert is_no_data_source(no_data_sources.lnbr[0])
    assert list(iter_daily_juso_rows(no_data_sources.mst[0], source_yyyymm=None)) == []


def test_actual_locsum_zip_member_loads_entrance_coordinates_without_bd_mgt_sn() -> None:
    archive = _require(DATA_ROOT / "202604_위치정보요약DB_전체분.zip")
    sources = {source.name: source for source in discover_locsum_files(archive)}

    seoul = sources["entrc_seoul.txt"]
    rows = list(iter_locsum_rows(seoul, source_yyyymm="202604", limit=10))

    assert len(rows) == 10
    first = rows[0]
    assert first.sig_cd == "11110"
    assert first.ent_man_no == 760
    assert first.bjd_cd == "1111010100"
    assert first.rncode_full == "111103100012"
    assert first.buld_mnnm == 94
    assert first.ent_se_cd == "0"
    assert first.x_5179 == pytest.approx(953241.683263)
    assert first.y_5179 == pytest.approx(1954023.466812)


def test_actual_navi_files_load_building_centroid_and_entrance_rows() -> None:
    root = _require(DATA_ROOT / "202604_내비게이션용DB_전체분")
    build_sources = {source.name: source for source in discover_navi_build_files(root)}
    entrance_sources = {source.name: source for source in discover_navi_entrance_files(root)}

    build = next(
        iter_navi_build_rows(build_sources["match_build_seoul.txt"], source_yyyymm="202604")
    )
    build_with_sigungu_name = next(
        row
        for row in iter_navi_build_rows(
            build_sources["match_build_seoul.txt"], source_yyyymm="202604"
        )
        if row.sigungu_buld_nm
    )
    entrance = next(
        iter_navi_entrance_rows(entrance_sources["match_rs_entrc.txt"], source_yyyymm="202604")
    )

    assert build.bd_mgt_sn == "1111010100101440003031291"
    assert build.rn_cd == "3100012"
    assert build.buld_mnnm == 94
    assert build.centroid_x == pytest.approx(953243.01328)
    assert build.centroid_y == pytest.approx(1954025.806161)
    assert build.entrance_x == pytest.approx(953241.683263)
    assert build.entrance_y == pytest.approx(1954023.466812)
    assert build_with_sigungu_name.sigungu_buld_nm == "에이동"
    assert entrance.sig_cd == "11110"
    assert entrance.entry_no == 1331
    assert entrance.kind == "navi"
    assert entrance.x_5179 == pytest.approx(953135.056899)


def test_actual_shp_dataset_builds_polygon_only_load_plan() -> None:
    root = _require(DATA_ROOT / "도로명주소 전자지도" / "강원특별자치도")

    plans = build_shp_load_plan(root)

    assert tuple(plan.source_layer for plan in plans) == POLYGON_LAYER_NAMES
    assert {plan.target_table for plan in plans} >= {
        "tl_scco_ctprvn",
        "tl_kodis_bas",
        "tl_spbd_buld_polygon",
        "tl_sprd_rw",
    }
    assert all(plan.shp_path.is_file() and plan.dbf_path.is_file() for plan in plans)
    building = next(plan for plan in plans if plan.source_layer == "TL_SPBD_BULD")
    assert "BD_MGT_SN AS bd_mgt_sn" in (building.sql_statement or "")
