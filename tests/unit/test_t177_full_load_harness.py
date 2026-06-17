from __future__ import annotations

import json
import zipfile
from typing import TYPE_CHECKING

import pytest

from kortravelgeo.core.source_layers import MASTER_LAYER_NAMES, POLYGON_LAYER_NAMES
from tests.integration._t177_full_load_harness import (
    _T177F_LINK_EVIDENCE_SQL,
    ENV_DATA_ROOT,
    ENV_DSN,
    ENV_ENABLED,
    ENV_RUN_ID,
    ENV_SAMPLE_LIMIT,
    T177PreflightError,
    T177SkipError,
    assert_no_existing_rows_without_confirmation,
    build_discovery_plan,
    expected_confirmation,
    looks_like_t177_scratch_database,
    required_source_path,
    runtime_from_env,
    sample_limit_from_env,
    source_yyyymm,
    t177c_text_delta_source_paths,
    t177d_shp_geometry_source,
    t177e_supplemental_source_paths,
    validate_t177_confirmation,
    write_json_artifact,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_runtime_from_env_skips_when_not_opted_in(tmp_path: Path) -> None:
    with pytest.raises(T177SkipError):
        runtime_from_env({}, cwd=tmp_path)


def test_runtime_from_env_resolves_data_root_and_artifact_dir(tmp_path: Path) -> None:
    data_root = tmp_path / "juso"
    data_root.mkdir()

    runtime = runtime_from_env(
        {
            ENV_ENABLED: "1",
            ENV_DSN: "postgresql+psycopg://addr:addr@localhost:5432/kor_travel_geo_t177",
            ENV_DATA_ROOT: str(data_root),
            ENV_RUN_ID: "unit-run",
        },
        cwd=tmp_path,
    )

    assert runtime.data_root == data_root
    assert runtime.artifact_dir == tmp_path / "artifacts" / "t177" / "unit-run"
    assert runtime.run_id == "unit-run"


def test_database_name_and_confirmation_guard() -> None:
    assert looks_like_t177_scratch_database("kor_travel_geo_t177")
    assert looks_like_t177_scratch_database("kor_travel_geo_scratch")
    assert looks_like_t177_scratch_database("address_test")
    assert not looks_like_t177_scratch_database("kor_travel_geo")

    validate_t177_confirmation(
        "kor_travel_geo_t177",
        expected_confirmation("kor_travel_geo_t177"),
    )
    with pytest.raises(T177PreflightError):
        validate_t177_confirmation("kor_travel_geo", "RUN-T177-E2E kor_travel_geo")
    with pytest.raises(T177PreflightError):
        validate_t177_confirmation("kor_travel_geo_t177", None)
    with pytest.raises(T177PreflightError):
        validate_t177_confirmation("kor_travel_geo_t177", "RUN-T177-E2E other_db")


def test_existing_row_guard_requires_destructive_confirmation() -> None:
    counts = {"public.tl_juso_text": 2, "public.load_manifest": 0}

    with pytest.raises(T177PreflightError):
        assert_no_existing_rows_without_confirmation(counts, destructive_confirmed=False)
    with pytest.raises(T177PreflightError):
        assert_no_existing_rows_without_confirmation(counts, destructive_confirmed=True)
    assert_no_existing_rows_without_confirmation(
        counts,
        destructive_confirmed=True,
        allow_nonempty=True,
    )


def test_sample_limit_from_env() -> None:
    assert sample_limit_from_env({}) == 2
    assert sample_limit_from_env({ENV_SAMPLE_LIMIT: "7"}) == 7

    with pytest.raises(T177PreflightError):
        sample_limit_from_env({ENV_SAMPLE_LIMIT: "0"})
    with pytest.raises(T177PreflightError):
        sample_limit_from_env({ENV_SAMPLE_LIMIT: "many"})


def test_t177f_link_evidence_query_materializes_locsum_keys() -> None:
    normalized_sql = " ".join(_T177F_LINK_EVIDENCE_SQL.split())

    assert "locsum_bd AS MATERIALIZED" in normalized_sql
    assert "SELECT DISTINCT bd_mgt_sn" in normalized_sql
    assert "JOIN locsum_bd USING (bd_mgt_sn)" in normalized_sql
    assert "WHERE EXISTS" not in normalized_sql


def test_discovery_plan_and_artifact_shape(tmp_path: Path) -> None:
    data_root = tmp_path / "juso"
    _seed_minimal_t177_sources(data_root)

    plan = build_discovery_plan(data_root)
    sources = plan["sources"]

    assert plan["data_root"] == str(data_root)
    assert sources["juso_hangul"]["source_count"] == 1
    assert sources["jibun_rnaddrkor"]["source_count"] == 1
    assert sources["daily_juso"]["source_count"] == 2
    assert sources["daily_lnbr"]["source_count"] == 1
    assert sources["locsum"]["source_count"] == 1
    assert sources["navi"]["source_count"] == 2
    assert sources["roadaddr_entrance"]["source_count"] == 1
    assert sources["sppn_makarea"]["source_count"] == 1
    assert sources["electronic_map"]["source_count"] == len(POLYGON_LAYER_NAMES)
    assert source_yyyymm(plan, "juso_hangul") == "202605"
    assert source_yyyymm(plan, "electronic_map") == "202604"
    assert required_source_path(plan, "juso_hangul") == data_root / "202605_도로명주소 한글_전체분"

    source_paths = t177c_text_delta_source_paths(plan)
    assert source_paths.juso_hangul == data_root / "202605_도로명주소 한글_전체분"
    assert source_paths.jibun_rnaddrkor == data_root / "202605_도로명주소 한글_전체분"
    assert source_paths.daily_juso == data_root / "daily" / "20260401_dailyjusukrdata.zip"
    assert source_paths.daily_lnbr == data_root / "daily" / "20260401_dailyjusukrdata.zip"
    assert source_paths.locsum == data_root / "202604_위치정보요약DB_전체분.zip"
    assert source_paths.navi == data_root / "202604_내비게이션용DB_전체분"

    shp_source = t177d_shp_geometry_source(plan)
    assert shp_source.electronic_map_root == data_root / "도로명주소 전자지도" / "202604"
    assert shp_source.sido_path == data_root / "도로명주소 전자지도" / "202604" / "세종특별자치시"
    assert shp_source.sido_name == "세종특별자치시"
    assert shp_source.sig_code == "36110"
    assert shp_source.archive_path is None
    assert shp_source.materialized is False

    supplemental_paths = t177e_supplemental_source_paths(plan)
    assert supplemental_paths.roadaddr_entrance == (
        data_root
        / "도로명주소 출입구 정보"
        / "202604"
        / "sejong.zip"
    )
    assert supplemental_paths.roadaddr_entrance_plan_yyyymm == "202604"
    assert supplemental_paths.sppn_makarea == (
        data_root
        / "구역의도형"
        / "202603"
        / "구역의도형_전체분_세종특별자치시.zip"
    )
    assert supplemental_paths.sppn_makarea_source_yyyymm == "202603"

    artifact = write_json_artifact(tmp_path / "artifacts", "plan.json", plan)
    saved = json.loads(artifact.read_text(encoding="utf-8"))
    assert saved["sources"]["daily_juso"]["sample_names"] == [
        "AlterD.JUSUKR.20260402.TH_SGCO_RNADR_MST.TXT",
        "AlterD.JUSUKR.20260402.TH_SGCO_RNADR_LNBR.TXT",
    ]


def test_t177d_shp_geometry_source_materializes_zip_source(tmp_path: Path) -> None:
    data_root = tmp_path / "juso"
    electronic_root = data_root / "도로명주소 전자지도" / "202604"
    electronic_root.mkdir(parents=True)
    archive = electronic_root / "세종특별자치시.zip"
    _write_electronic_map_zip(archive, sig_code="36000")

    plan = build_discovery_plan(data_root)
    sources = plan["sources"]
    assert sources["electronic_map"]["source_count"] == len(POLYGON_LAYER_NAMES)

    materialize_dir = tmp_path / "work"
    shp_source = t177d_shp_geometry_source(plan, materialize_dir=materialize_dir)

    assert shp_source.electronic_map_root == electronic_root
    assert shp_source.archive_path == archive
    assert shp_source.sido_path == materialize_dir / "세종특별자치시"
    assert shp_source.sido_name == "세종특별자치시"
    assert shp_source.sig_code == "36000"
    assert shp_source.materialized is True
    assert (shp_source.sido_path / "36000" / "TL_SPBD_BULD.shp").is_file()


def _seed_minimal_t177_sources(data_root: Path) -> None:
    juso_dir = data_root / "202605_도로명주소 한글_전체분"
    juso_dir.mkdir(parents=True)
    (juso_dir / "rnaddrkor_seoul.txt").write_text("", encoding="utf-8")
    (juso_dir / "jibun_rnaddrkor_seoul.txt").write_text("", encoding="utf-8")

    daily_dir = data_root / "daily"
    daily_dir.mkdir()
    _write_zip(
        daily_dir / "20260401_dailyjusukrdata.zip",
        {
            "AlterD.JUSUKR.20260402.TH_SGCO_RNADR_MST.TXT": "",
            "AlterD.JUSUKR.20260402.TH_SGCO_RNADR_LNBR.TXT": "",
        },
    )

    _write_zip(data_root / "202604_위치정보요약DB_전체분.zip", {"entrc_sejong.txt": ""})

    navi_dir = data_root / "202604_내비게이션용DB_전체분"
    navi_dir.mkdir()
    (navi_dir / "match_build_seoul.txt").write_text("", encoding="utf-8")
    (navi_dir / "match_rs_entrc.txt").write_text("", encoding="utf-8")

    roadaddr_dir = data_root / "도로명주소 출입구 정보" / "202604"
    roadaddr_dir.mkdir(parents=True)
    _write_zip(roadaddr_dir / "sejong.zip", {"RNENTDATA_2605_36110.txt": ""})

    zone_dir = data_root / "구역의도형" / "202603"
    zone_dir.mkdir(parents=True)
    _write_zip(zone_dir / "구역의도형_전체분_세종특별자치시.zip", {"TL_SPPN_MAKAREA.shp": ""})

    _seed_minimal_electronic_map(
        data_root / "도로명주소 전자지도" / "202604" / "세종특별자치시" / "36110"
    )


def _seed_minimal_electronic_map(sig_dir: Path) -> None:
    sig_dir.mkdir(parents=True)
    for layer_name in MASTER_LAYER_NAMES:
        for suffix in (".shp", ".shx", ".dbf"):
            (sig_dir / f"{layer_name}{suffix}").write_bytes(b"")


def _write_electronic_map_zip(path: Path, *, sig_code: str) -> None:
    members = {
        f"{sig_code}/{layer_name}{suffix}": ""
        for layer_name in MASTER_LAYER_NAMES
        for suffix in (".shp", ".shx", ".dbf")
    }
    _write_zip(path, members)


def _write_zip(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
