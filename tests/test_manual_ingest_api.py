from __future__ import annotations

import io
import sys
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "backend"))

from kraddr_geo_api import database, ingest  # noqa: E402
from kraddr_geo_api.main import app  # noqa: E402

from kraddr.geo.reverse import NAVIGATION_BUILDING_COLUMNS  # noqa: E402
from kraddr.geo.spatialite import (  # noqa: E402
    LOCATION_SUMMARY_ENTRANCE_COLUMNS,
    NAVIGATION_ROAD_SECTION_ENTRANCE_COLUMNS,
)


@pytest.fixture(autouse=True)
def isolated_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KRADDR_GEO_SPATIALITE_PATH", str(tmp_path / "manual.sqlite"))
    monkeypatch.setattr(ingest, "UPLOAD_ROOT", tmp_path / "uploads")
    database.store.cache_clear()
    ingest.reset_jobs_for_tests()
    yield
    database.store.cache_clear()
    ingest.reset_jobs_for_tests()


def test_manual_location_summary_zip_upload_loads_points_and_progress() -> None:
    client = TestClient(app)

    response = client.post(
        "/load-jobs",
        data={"dataset": "auto", "replace": "true"},
        files={
            "files": (
                "entrc_fixture.zip",
                _zip_bytes("entrc_seoul.txt", _location_summary_line()),
                "application/zip",
            )
        },
    )

    assert response.status_code == 200
    job = _wait_for_job(client, response.json()["id"])
    assert job["status"] == "succeeded"
    assert job["progress_percent"] == 100.0
    assert job["total_files"] == 1
    assert job["processed_files"] == 1
    assert job["loaded"] == 1
    assert job["skipped"] == 0

    health = client.get("/health").json()
    assert health["address_point_count"] == 1
    assert client.get("/load-jobs").json()["items"][0]["id"] == job["id"]


def test_manual_multi_txt_upload_loads_navigation_and_road_section_records() -> None:
    client = TestClient(app)

    response = client.post(
        "/load-jobs",
        data={"dataset": "auto", "replace": "true"},
        files=[
            (
                "files",
                ("match_build_seoul.txt", _navigation_line().encode("utf-8"), "text/plain"),
            ),
            (
                "files",
                (
                    "match_rs_entrc.txt",
                    _road_section_line().encode("utf-8"),
                    "text/plain",
                ),
            ),
        ],
    )

    assert response.status_code == 200
    job = _wait_for_job(client, response.json()["id"])
    assert job["status"] == "succeeded"
    assert job["total_files"] == 2
    assert job["processed_files"] == 2
    assert job["loaded"] == 3
    assert job["skipped"] == 0

    sources = {
        row["source_dataset"]: row["row_count"]
        for row in client.get("/health").json()["sources"]
    }
    assert sources == {
        "navigation_building": 2,
        "navigation_road_section_entrance": 1,
    }


def test_manual_shp_sidecars_are_grouped_and_loaded(tmp_path: Path) -> None:
    geopandas = pytest.importorskip("geopandas")
    from shapely.geometry import Polygon

    shp_dir = tmp_path / "shape"
    shp_dir.mkdir()
    shp_path = shp_dir / "TL_SCCO_SIG.shp"
    frame = geopandas.GeoDataFrame(
        [{"SIG_CD": "11110", "SIG_KOR_NM": "종로구", "geometry": Polygon(_square())}],
        crs="EPSG:5179",
    )
    frame.to_file(shp_path, encoding="utf-8")

    upload_files = []
    for path in sorted(shp_dir.iterdir()):
        upload_files.append(
            (
                "files",
                (
                    f"sig/{path.name}",
                    path.read_bytes(),
                    "application/octet-stream",
                ),
            )
        )

    client = TestClient(app)
    response = client.post(
        "/load-jobs",
        data={"dataset": "boundary_shapes", "replace": "true"},
        files=upload_files,
    )

    assert response.status_code == 200
    job = _wait_for_job(client, response.json()["id"])
    assert job["status"] == "succeeded"
    assert job["total_files"] == 1
    assert job["loaded"] == 1
    assert client.get("/health").json()["boundary_count"] == 1


def test_manual_unknown_upload_fails_with_visible_job_error() -> None:
    client = TestClient(app)
    response = client.post(
        "/load-jobs",
        data={"dataset": "auto", "replace": "false"},
        files={"files": ("notes.bin", b"not a supported dataset", "application/octet-stream")},
    )

    assert response.status_code == 200
    job = _wait_for_job(client, response.json()["id"])
    assert job["status"] == "failed"
    assert job["errors"]
    assert "적재할 수 있는" in job["message"]


def _wait_for_job(client: TestClient, job_id: str) -> dict[str, object]:
    for _ in range(60):
        response = client.get(f"/load-jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] not in {"pending", "running"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"load job did not finish: {job_id}")


def _zip_bytes(name: str, line: str, *, encoding: str = "cp949") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, (line + "\n").encode(encoding))
    return buffer.getvalue()


def _location_summary_line(**overrides: str) -> str:
    values = {
        "sigungu_code": "11110",
        "entrance_serial_no": "1",
        "legal_dong_code": "1111010100",
        "sido_name": "Seoul",
        "sigungu_name": "Jongno-gu",
        "eup_myeon_dong_name": "Cheongun-dong",
        "road_name_code": "111103100012",
        "road_name": "Jahamun-ro",
        "underground_yn": "0",
        "building_main_no": "96",
        "building_sub_no": "0",
        "building_name": "Pyeongan",
        "postal_code": "03047",
        "building_use": "residence",
        "apartment_kind_code": "0",
        "detail_building_name": "main",
        "entrance_x": "953243.0",
        "entrance_y": "1954023.0",
    }
    values.update(overrides)
    return "|".join(values[column] for column in LOCATION_SUMMARY_ENTRANCE_COLUMNS)


def _navigation_line(**overrides: str) -> str:
    values = {
        "jurisdiction_emd_code": "1111010100",
        "sido_name": "Seoul",
        "sigungu_name": "Jongno-gu",
        "eup_myeon_dong_name": "Cheongun-dong",
        "road_name_code": "111103100012",
        "road_name": "Jahamun-ro",
        "underground_yn": "0",
        "building_main_no": "96",
        "building_sub_no": "0",
        "postal_code": "03047",
        "building_management_number": "1111010100101080014031432",
        "sigungu_building_name": "Pyeongan",
        "building_use": "residence",
        "administrative_dong_code": "1111051500",
        "administrative_dong_name": "Cheongunhyoja-dong",
        "ground_floor_count": "4",
        "underground_floor_count": "0",
        "apartment_kind_code": "2",
        "building_count": "1",
        "detail_building_name": "",
        "building_name_history": "",
        "detail_building_name_history": "",
        "residential_yn": "1",
        "building_center_x": "953247.0",
        "building_center_y": "1954041.0",
        "entrance_x": "953243.2",
        "entrance_y": "1954034.2",
        "sido_name_en": "Seoul",
        "sigungu_name_en": "Jongno-gu",
        "eup_myeon_dong_name_en": "Cheongun-dong",
        "road_name_en": "Jahamun-ro",
        "eup_myeon_dong_type": "1",
        "change_reason_code": "31",
    }
    values.update(overrides)
    return "|".join(values[column] for column in NAVIGATION_BUILDING_COLUMNS)


def _road_section_line(**overrides: str) -> str:
    values = {
        "sigungu_code": "11110",
        "entrance_serial_no": "1",
        "road_name_code": "111103100012",
        "underground_yn": "0",
        "building_main_no": "96",
        "building_sub_no": "0",
        "legal_dong_code": "1111010100",
        "entrance_type_code": "1",
        "x": "953243.3",
        "y": "1954034.3",
        "reserved": "",
    }
    values.update(overrides)
    return "|".join(values[column] for column in NAVIGATION_ROAD_SECTION_ENTRANCE_COLUMNS)


def _square() -> list[tuple[float, float]]:
    return [
        (953200.0, 1954000.0),
        (953300.0, 1954000.0),
        (953300.0, 1954100.0),
        (953200.0, 1954100.0),
        (953200.0, 1954000.0),
    ]
