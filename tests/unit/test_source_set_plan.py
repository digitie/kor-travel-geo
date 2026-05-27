from __future__ import annotations

from pathlib import Path

import pytest

from kraddr.geo.dto.admin import UploadSetCreateRequest
from kraddr.geo.exceptions import InvalidInputError
from kraddr.geo.infra.source_set import (
    build_full_load_source_set_plan,
    confirmation_token_for,
    discover_load_sources,
    infer_yyyymm,
)
from kraddr.geo.infra.uploads import (
    cancel_upload_set,
    create_upload_set,
    get_upload_set,
    store_upload_file,
)


def test_source_set_discovery_matches_required_sources_and_mixed_months(tmp_path: Path) -> None:
    _touch(tmp_path / "202603_도로명주소 한글_전체분" / "rnaddrkor_seoul.txt")
    _touch(tmp_path / "202604_위치정보요약DB_전체분.zip")
    _touch(tmp_path / "202604_내비게이션용DB_전체분" / "navi.txt")
    _touch(tmp_path / "202604_도로명주소 전자지도" / "TL_SPBD_BULD.shp")
    _touch(tmp_path / "도로명주소 출입구 정보" / "RNENTDATA_2605_11.txt")

    discovery = discover_load_sources(tmp_path)

    assert discovery.missing_required == ()
    assert discovery.mixed_yyyymm is True
    assert discovery.recommended["juso"].inferred_yyyymm == "202603"
    assert discovery.recommended["parcel_link"].path == discovery.recommended["juso"].path
    assert discovery.recommended["locsum"].inferred_yyyymm == "202604"
    assert discovery.recommended["roadaddr_entrance"].inferred_yyyymm == "202605"
    assert infer_yyyymm(Path("RNENTDATA_2605_11.txt")) == "202605"


def test_infer_yyyymm_prefers_nearest_file_or_directory_name() -> None:
    path = Path(
        "/tmp/uploads/upload_20260527T000000Z_deadbeef/files/"
        "서울/202603_도로명주소 한글_전체분.zip"
    )

    assert infer_yyyymm(path) == "202603"


def test_source_set_plan_requires_explicit_mixed_confirmation(tmp_path: Path) -> None:
    _touch(tmp_path / "202603_도로명주소 한글_전체분" / "rnaddrkor_seoul.txt")
    _touch(tmp_path / "202604_위치정보요약DB_전체분.zip")
    _touch(tmp_path / "202604_내비게이션용DB_전체분" / "navi.txt")
    _touch(tmp_path / "202604_도로명주소 전자지도" / "TL_SPBD_BULD.shp")

    versions = {"parcel_link": "202603", "shp": "202604"}
    with pytest.raises(InvalidInputError):
        build_full_load_source_set_plan(root_path=tmp_path, versions=versions)

    token = confirmation_token_for(
        {
            "juso": "202603",
            "parcel_link": "202603",
            "locsum": "202604",
            "navi": "202604",
            "shp": "202604",
        }
    )
    plan = build_full_load_source_set_plan(
        root_path=tmp_path,
        versions=versions,
        allow_mixed_yyyymm=True,
        confirmation_token=token,
        acknowledged_by="cli",
    )

    assert plan.mixed_yyyymm is True
    assert plan.mixed_yyyymm_acknowledged is True
    assert plan.acknowledged_by == "cli"
    assert plan.confirmation_token_hash is not None
    assert plan.batch_payload["source_set"]["yyyymm_by_kind"]["juso"] == "202603"
    assert [child["kind"] for child in plan.batch_payload["children"]] == [
        "juso_text_load",
        "juso_parcel_link_load",
        "locsum_load",
        "navi_load",
        "shp_polygons_load",
    ]


def test_source_set_plan_builds_single_month_batch_without_confirmation(
    tmp_path: Path,
) -> None:
    _touch(tmp_path / "202604_도로명주소 한글_전체분" / "rnaddrkor_seoul.txt")
    _touch(tmp_path / "202604_위치정보요약DB_전체분.zip")
    _touch(tmp_path / "202604_내비게이션용DB_전체분" / "navi.txt")
    _touch(tmp_path / "202604_도로명주소 전자지도" / "TL_SPBD_BULD.shp")
    _touch(tmp_path / "202604_도로명주소 출입구 정보" / "RNENTDATA_2404_11.txt")
    _touch(tmp_path / "202604_구역의 도형" / "36110" / "TL_SPPN_MAKAREA.shp")

    plan = build_full_load_source_set_plan(root_path=tmp_path)

    assert plan.mixed_yyyymm is False
    assert plan.expected_confirmation_token is None
    assert plan.confirmation_token_hash is None
    children_by_kind = {
        child["kind"]: child["payload"]
        for child in plan.batch_payload["children"]
    }
    assert children_by_kind["juso_text_load"]["source_yyyymm"] == "202604"
    assert children_by_kind["roadaddr_entrance_load"]["source_yyyymm"] == "202604"
    assert children_by_kind["shp_polygons_load"]["mode"] == "full"
    assert children_by_kind["sppn_makarea_load"]["mode"] == "full"
    assert children_by_kind["sppn_makarea_load"]["source_yyyymm"] == "202604"
    assert "source_set" in children_by_kind["locsum_load"]


def test_source_set_discovery_can_exclude_optional_sources(tmp_path: Path) -> None:
    _touch(tmp_path / "202604_도로명주소 한글_전체분" / "rnaddrkor_seoul.txt")
    _touch(tmp_path / "202604_위치정보요약DB_전체분.zip")
    _touch(tmp_path / "202604_내비게이션용DB_전체분" / "navi.txt")
    _touch(tmp_path / "202604_도로명주소 전자지도" / "TL_SPBD_BULD.shp")
    _touch(tmp_path / "202604_도로명주소 출입구 정보" / "RNENTDATA_2404_11.txt")
    _touch(tmp_path / "202604_구역의 도형" / "36110" / "TL_SPPN_MAKAREA.shp")

    discovery = discover_load_sources(tmp_path, include_optional=False)

    assert "roadaddr_entrance" not in discovery.recommended
    assert "sppn_makarea" not in discovery.recommended
    assert discovery.missing_required == ()


@pytest.mark.asyncio
async def test_upload_set_stores_files_safely_and_can_be_cancelled(tmp_path: Path) -> None:
    upload_set = await create_upload_set(tmp_path, UploadSetCreateRequest())
    file_status = await store_upload_file(
        tmp_path,
        upload_set.upload_set_id,
        filename="202603_도로명주소 한글_전체분.zip",
        relative_path="../서울/202603_도로명주소 한글_전체분.zip",
        chunks=_chunks(b"hello"),
        max_bytes=100,
    )

    assert file_status.state == "uploaded"
    assert file_status.size_bytes == 5
    assert file_status.uploaded_bytes == 5
    assert file_status.source_kind == "juso"
    assert file_status.inferred_yyyymm == "202603"
    assert ".." not in file_status.relative_path

    loaded = await get_upload_set(tmp_path, upload_set.upload_set_id)
    assert loaded.state == "uploaded"
    assert loaded.total_bytes == 5
    assert loaded.files[0].sha256 == file_status.sha256

    cancelled = await cancel_upload_set(tmp_path, upload_set.upload_set_id)
    assert cancelled.state == "cancelled"


@pytest.mark.asyncio
async def test_upload_set_marks_failed_file_when_size_limit_is_exceeded(
    tmp_path: Path,
) -> None:
    upload_set = await create_upload_set(tmp_path, UploadSetCreateRequest())

    with pytest.raises(InvalidInputError, match="upload exceeds"):
        await store_upload_file(
            tmp_path,
            upload_set.upload_set_id,
            filename="navi.txt",
            relative_path="202604_내비게이션용DB_전체분/navi.txt",
            chunks=_chunks(b"abcdef"),
            max_bytes=3,
        )

    loaded = await get_upload_set(tmp_path, upload_set.upload_set_id)
    assert loaded.state == "failed"
    assert loaded.files[0].state == "failed"
    assert loaded.files[0].uploaded_bytes == 6


async def _chunks(payload: bytes):
    yield payload


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
