"""Admin endpoints for loading and consistency checks."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from kraddr.geo.api._jobs import JobQueue
from kraddr.geo.api.deps import get_client, get_job_queue
from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.core.normalize import parse_address
from kraddr.geo.dto.admin import (
    CacheMetrics,
    ConsistencyReport,
    ConsistencyReportSummary,
    ConsistencyRunRequest,
    ExplainRequest,
    ExplainResponse,
    LoadJobStatus,
    LoadSubmitRequest,
    NormalizeRequest,
    NormalizeResponse,
    TableStat,
    UploadSidoZipResponse,
)
from kraddr.geo.settings import get_settings

router = APIRouter(tags=["admin"])


@router.post("/normalize", response_model=NormalizeResponse)
async def normalize(req: NormalizeRequest) -> NormalizeResponse:
    parts = parse_address(req.address)
    tokens = tuple(token for token in (parts.si, parts.sgg, parts.emd, parts.road) if token)
    return NormalizeResponse(original=req.address, normalized=parts.normalized, tokens=tokens)


@router.get("/tables", response_model=list[TableStat], response_model_exclude_none=True)
async def table_stats(
    limit: int = Query(default=200, ge=1, le=500),
    client: AsyncAddressClient = Depends(get_client),
) -> list[TableStat]:
    return await client.table_stats(limit=limit)


@router.post("/explain", response_model=ExplainResponse)
async def explain(
    req: ExplainRequest,
    client: AsyncAddressClient = Depends(get_client),
) -> ExplainResponse:
    return await client.explain(req.sql, analyze=req.analyze, buffers=req.buffers)


@router.get("/cache/metrics", response_model=CacheMetrics)
async def cache_metrics(
    client: AsyncAddressClient = Depends(get_client),
) -> CacheMetrics:
    return await client.cache_metrics()


@router.get("/logs", response_model=list[str])
async def recent_logs(
    limit: int = Query(default=200, ge=1, le=500),
    client: AsyncAddressClient = Depends(get_client),
) -> list[str]:
    return await client.recent_logs(limit=limit)


@router.post(
    "/upload/sido-zip",
    response_model=UploadSidoZipResponse,
    response_model_exclude_none=True,
)
async def upload_sido_zip(
    request: Request,
    filename: str = Query(min_length=1),
    sido: str | None = Query(default=None, min_length=1),
) -> UploadSidoZipResponse:
    settings = get_settings()
    safe_name = _safe_filename(filename)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    upload_id = f"{timestamp}_{sido or Path(safe_name).stem}"
    upload_dir = settings.loader_data_dir / "uploads" / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / safe_name
    digest = hashlib.sha256()
    size = 0
    with dest.open("wb") as fh:
        async for chunk in request.stream():
            if not chunk:
                continue
            size += len(chunk)
            digest.update(chunk)
            fh.write(chunk)
    return UploadSidoZipResponse(
        upload_id=upload_id,
        filename=safe_name,
        path=str(dest),
        size_bytes=size,
        sha256=digest.hexdigest(),
    )


@router.post("/maintenance/refresh-mv", response_model=LoadJobStatus)
async def refresh_mv(
    strategy: Literal["concurrent", "swap"] = "concurrent",
    client: AsyncAddressClient = Depends(get_client),
    queue: JobQueue = Depends(get_job_queue),
) -> LoadJobStatus:
    job_id = await queue.enqueue("mv_refresh", {"strategy": strategy})
    return await client.load_status(job_id)


@router.post("/loads", response_model=LoadJobStatus, response_model_exclude_none=True)
async def submit_load(
    req: LoadSubmitRequest,
    client: AsyncAddressClient = Depends(get_client),
    queue: JobQueue = Depends(get_job_queue),
) -> LoadJobStatus:
    if req.kind == "full_load_batch":
        job_id = await queue.enqueue_batch(req.payload)
    else:
        job_id = await queue.enqueue(req.kind, req.payload)
    return await client.load_status(job_id)


@router.get("/jobs", response_model=list[LoadJobStatus], response_model_exclude_none=True)
async def list_jobs(
    kind: str | None = None,
    state: str | None = None,
    limit: int = 50,
    client: AsyncAddressClient = Depends(get_client),
) -> list[LoadJobStatus]:
    return await list_loads(kind=kind, state=state, limit=limit, client=client)


@router.get("/jobs/{job_id}", response_model=LoadJobStatus, response_model_exclude_none=True)
async def job_status(
    job_id: str,
    client: AsyncAddressClient = Depends(get_client),
) -> LoadJobStatus:
    return await load_status(job_id, client=client)


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=LoadJobStatus,
    response_model_exclude_none=True,
)
async def cancel_job(
    job_id: str,
    client: AsyncAddressClient = Depends(get_client),
    queue: JobQueue = Depends(get_job_queue),
) -> LoadJobStatus:
    return await cancel_load(job_id, client=client, queue=queue)


@router.get("/loads", response_model=list[LoadJobStatus], response_model_exclude_none=True)
async def list_loads(
    kind: str | None = None,
    state: str | None = None,
    limit: int = 50,
    client: AsyncAddressClient = Depends(get_client),
) -> list[LoadJobStatus]:
    return await client.list_load_jobs(kind=kind, state=state, limit=limit)


@router.get("/loads/{job_id}", response_model=LoadJobStatus, response_model_exclude_none=True)
async def load_status(
    job_id: str,
    client: AsyncAddressClient = Depends(get_client),
) -> LoadJobStatus:
    return await client.load_status(job_id)


@router.post(
    "/loads/{job_id}/cancel",
    response_model=LoadJobStatus,
    response_model_exclude_none=True,
)
async def cancel_load(
    job_id: str,
    client: AsyncAddressClient = Depends(get_client),
    queue: JobQueue = Depends(get_job_queue),
) -> LoadJobStatus:
    await queue.cancel(job_id)
    return await client.load_status(job_id)


@router.post("/consistency/run", response_model=LoadJobStatus, response_model_exclude_none=True)
async def run_consistency(
    req: ConsistencyRunRequest,
    client: AsyncAddressClient = Depends(get_client),
    queue: JobQueue = Depends(get_job_queue),
) -> LoadJobStatus:
    job_id = await queue.enqueue(
        "consistency_check",
        {
            "scope": req.scope,
            "sido": req.sido,
            "recent_days": req.recent_days,
            "cases": req.cases,
        },
    )
    return await client.load_status(job_id)


@router.get(
    "/consistency",
    response_model=list[ConsistencyReportSummary],
    response_model_exclude_none=True,
)
async def list_consistency(
    limit: int = 20,
    severity_at_least: Literal["INFO", "WARN", "ERROR"] | None = None,
    client: AsyncAddressClient = Depends(get_client),
) -> list[ConsistencyReportSummary]:
    return await client.list_consistency_reports(
        limit=limit,
        severity_at_least=severity_at_least,
    )


@router.get(
    "/consistency/{report_id}",
    response_model=ConsistencyReport,
    response_model_exclude_none=True,
)
async def consistency_report(
    report_id: str,
    client: AsyncAddressClient = Depends(get_client),
) -> ConsistencyReport:
    return await client.consistency_report(report_id)


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.replace("\\", "_")
    if not name or name in {".", ".."}:
        return "upload.bin"
    return name
