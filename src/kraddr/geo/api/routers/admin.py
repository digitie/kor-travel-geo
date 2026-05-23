"""Admin endpoints for loading and consistency checks."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends

from kraddr.geo.api.deps import get_client
from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.core.normalize import parse_address
from kraddr.geo.dto.admin import (
    ConsistencyReport,
    ConsistencyReportSummary,
    ConsistencyRunRequest,
    LoadJobStatus,
    LoadSubmitRequest,
    NormalizeRequest,
    NormalizeResponse,
)

router = APIRouter(tags=["admin"])


@router.post("/normalize", response_model=NormalizeResponse)
async def normalize(req: NormalizeRequest) -> NormalizeResponse:
    parts = parse_address(req.address)
    tokens = tuple(token for token in (parts.si, parts.sgg, parts.emd, parts.road) if token)
    return NormalizeResponse(original=req.address, normalized=parts.normalized, tokens=tokens)


@router.post("/loads", response_model=LoadJobStatus, response_model_exclude_none=True)
async def submit_load(
    req: LoadSubmitRequest,
    client: AsyncAddressClient = Depends(get_client),
) -> LoadJobStatus:
    return await client.submit_load(req.kind, req.payload)


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
) -> LoadJobStatus:
    return await client.cancel_load(job_id)


@router.post("/consistency/run", response_model=LoadJobStatus, response_model_exclude_none=True)
async def run_consistency(
    req: ConsistencyRunRequest,
    client: AsyncAddressClient = Depends(get_client),
) -> LoadJobStatus:
    return await client.run_consistency_check(
        scope=req.scope,
        sido=req.sido,
        recent_days=req.recent_days,
        cases=req.cases,
    )


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
