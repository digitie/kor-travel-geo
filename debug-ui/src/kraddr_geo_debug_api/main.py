"""Address search and geocoding API."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .database import geocode, health, list_addresses, lookup_postal_code, reverse_geocode
from .ingest import (
    DatasetKind,
    create_load_job,
    get_load_job,
    list_load_jobs,
    run_load_job,
)

app = FastAPI(title="kraddr.geo address API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3010",
        "http://127.0.0.1:3010",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def run() -> None:
    """Run the debug API with uvicorn for local inspection."""

    import uvicorn

    uvicorn.run(
        "kraddr_geo_debug_api.main:app",
        host="127.0.0.1",
        port=3011,
        reload=False,
    )


@app.get("/health")
def get_health() -> dict[str, object]:
    return health()


@app.get("/addresses")
def get_addresses(
    query: str = "",
    scope: str = Query("all", pattern="^(all|road|jibun|code)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> dict[str, object]:
    return list_addresses(query=query, scope=scope, page=page, page_size=page_size)


@app.get("/geocode")
async def get_geocode(
    query: str = "",
    road_name_code: str | None = Query(None, alias="rnMgtSn"),
    legal_dong_code: str | None = Query(None, alias="admCd"),
    underground_yn: str | None = Query(None, alias="udrtYn"),
    building_main_no: str | None = Query(None, alias="buldMnnm"),
    building_sub_no: str | None = Query(None, alias="buldSlno"),
    crs: str = "EPSG:4326",
    limit: int = Query(10, ge=1, le=100),
) -> dict[str, object]:
    return await geocode(
        query=query,
        road_name_code=road_name_code,
        legal_dong_code=legal_dong_code,
        underground_yn=underground_yn,
        building_main_no=building_main_no,
        building_sub_no=building_sub_no,
        crs=crs,
        limit=limit,
    )


@app.get("/reverse-geocode")
async def get_reverse_geocode(
    x: float,
    y: float,
    crs: str = "EPSG:4326",
    max_distance_m: float = Query(50.0, ge=0),
) -> dict[str, object]:
    return await reverse_geocode(x=x, y=y, crs=crs, max_distance_m=max_distance_m)


@app.get("/postal-codes/{zipcode}")
def get_postal_code(
    zipcode: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, object]:
    return lookup_postal_code(zipcode, limit=limit, offset=offset)


@app.post("/load-jobs")
async def create_dataset_load_job(
    background_tasks: BackgroundTasks,
    dataset: Annotated[DatasetKind, Form()] = "auto",
    replace: Annotated[bool, Form()] = False,
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> dict[str, object]:
    if not files:
        raise HTTPException(status_code=400, detail="업로드된 파일이 없습니다.")
    saved_files = []
    with tempfile.TemporaryDirectory(prefix="kraddr-geo-upload-") as tmp:
        tmp_path = Path(tmp)
        for index, upload in enumerate(files, 1):
            filename = upload.filename or f"upload-{index}"
            target = tmp_path / str(index)
            with target.open("wb") as handle:
                while chunk := await upload.read(1024 * 1024):
                    handle.write(chunk)
            saved_files.append((filename, target))
        snapshot = create_load_job(files=saved_files, dataset=dataset, replace=replace)
    background_tasks.add_task(run_load_job, str(snapshot["id"]))
    return snapshot


@app.get("/load-jobs")
def get_dataset_load_jobs(limit: int = Query(20, ge=1, le=100)) -> dict[str, object]:
    return list_load_jobs(limit=limit)


@app.get("/load-jobs/{job_id}")
def get_dataset_load_job(job_id: str) -> dict[str, object]:
    try:
        return get_load_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="적재 작업을 찾을 수 없습니다.") from exc
