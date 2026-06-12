import pytest
from pydantic import ValidationError

from kortravelgeo.dto.admin import (
    BackupCreateRequest,
    CacheMetrics,
    ExplainRequest,
    LoadJobStatus,
    RestoreCreateRequest,
    UploadSidoZipResponse,
)
from kortravelgeo.dto.common import Point, ServiceMeta
from kortravelgeo.dto.pobox import PoboxInput, PoboxResponse, PoboxResultItem
from kortravelgeo.dto.search import BBox, SearchInput
from kortravelgeo.dto.zipcode import ZipcodeInput, ZipcodeResponse, ZipcodeResultItem


def test_search_input_page_and_bbox_validation() -> None:
    item = SearchInput(query="테헤란로", bbox=BBox(min_x=126, min_y=37, max_x=128, max_y=38))

    assert item.page == 1
    assert item.size == 10
    assert item.crs == "EPSG:4326"

    with pytest.raises(ValidationError):
        BBox(min_x=128, min_y=37, max_x=126, max_y=38)


def test_zipcode_input_requires_exactly_one_lookup_key() -> None:
    assert ZipcodeInput(address="서울특별시 강남구 테헤란로 152").address is not None
    assert ZipcodeInput(point=Point(x=127.0286, y=37.5003)).point is not None
    assert ZipcodeInput(bd_mgt_sn="1168010100108250000000001").bd_mgt_sn is not None

    with pytest.raises(ValidationError):
        ZipcodeInput()

    with pytest.raises(ValidationError):
        ZipcodeInput(address="서울", point=Point(x=127.0286, y=37.5003))


def test_zipcode_response_serializes_zip_source() -> None:
    response = ZipcodeResponse(
        service=ServiceMeta(name="kor-travel-geo", operation="zipcode"),
        status="OK",
        input=ZipcodeInput(address="서울특별시 강남구 테헤란로 152"),
        result=(ZipcodeResultItem(zip_no="06236", source="building_bsi_zon_no"),),
    )

    assert response.model_dump(mode="json")["result"][0]["source"] == "building_bsi_zon_no"


def test_pobox_defaults_and_response() -> None:
    response = PoboxResponse(
        service=ServiceMeta(name="kor-travel-geo", operation="pobox"),
        status="OK",
        input=PoboxInput(query="서울", kind="ALL"),
        result=(PoboxResultItem(zip_no="03000", pobox_kind="PO", pobox_name="서울사서함"),),
        total=1,
    )

    assert response.input.kind == "ALL"
    assert response.result[0].pobox_kind == "PO"


def test_admin_debug_dtos_are_bounded() -> None:
    assert ExplainRequest(sql="SELECT 1").analyze is False
    assert LoadJobStatus(job_id="job-1", kind="sido_load", state="queued").progress == 0.0
    nested_source_set = {
        "load_batch_id": "batch-1",
        "yyyymm_by_kind": {"juso": "202603", "locsum": "202604"},
    }
    status = LoadJobStatus(
        job_id="job-2",
        kind="full_load_batch",
        state="running",
        source_set=nested_source_set,
    )
    assert status.source_set == nested_source_set
    assert CacheMetrics(enabled=True, entries=0, hits=0, expired=0).enabled is True
    assert BackupCreateRequest().format == "directory_tar_zstd"
    assert BackupCreateRequest(jobs=8, compression_level=5).profile == "serving-ready"
    assert RestoreCreateRequest(target_database="kor_travel_geo_restore").mode == "new_database"
    assert (
        UploadSidoZipResponse(
            upload_id="u1",
            filename="seoul.zip",
            path="data/uploads/u1/seoul.zip",
            size_bytes=1,
            sha256="a" * 64,
        ).filename
        == "seoul.zip"
    )

    with pytest.raises(ValidationError):
        LoadJobStatus(job_id="job-1", kind="sido_load", state="running", progress=1.5)

    with pytest.raises(ValidationError):
        UploadSidoZipResponse(
            upload_id="u1",
            filename="seoul.zip",
            path="data/uploads/u1/seoul.zip",
            size_bytes=1,
            sha256="short",
        )
