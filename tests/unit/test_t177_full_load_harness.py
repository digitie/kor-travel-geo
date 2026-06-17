from __future__ import annotations

import json
import zipfile
from typing import TYPE_CHECKING

import pytest

from tests.integration._t177_full_load_harness import (
    ENV_DATA_ROOT,
    ENV_DSN,
    ENV_ENABLED,
    ENV_RUN_ID,
    T177PreflightError,
    T177SkipError,
    assert_no_existing_rows_without_confirmation,
    build_discovery_plan,
    expected_confirmation,
    looks_like_t177_scratch_database,
    runtime_from_env,
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
    assert sources["electronic_map"]["exists"] is False

    artifact = write_json_artifact(tmp_path / "artifacts", "plan.json", plan)
    saved = json.loads(artifact.read_text(encoding="utf-8"))
    assert saved["sources"]["daily_juso"]["sample_names"] == [
        "AlterD.JUSUKR.20260402.TH_SGCO_RNADR_MST.TXT",
        "AlterD.JUSUKR.20260402.TH_SGCO_RNADR_LNBR.TXT",
    ]


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

    zone_dir = data_root / "구역의 도형"
    zone_dir.mkdir()
    _write_zip(zone_dir / "구역의도형_전체분_세종특별자치시.zip", {"TL_SPPN_MAKAREA.shp": ""})


def _write_zip(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
