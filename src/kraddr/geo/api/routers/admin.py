"""Admin endpoints for loading and consistency checks."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict

from fastapi import APIRouter, Depends, Query, Request

from kraddr.geo.api._jobs import JobQueue
from kraddr.geo.api.deps import get_client, get_job_queue
from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.core.normalize import parse_address
from kraddr.geo.dto.admin import (
    AuditEvent,
    CacheMetrics,
    ConsistencyReport,
    ConsistencyReportSummary,
    ConsistencyRunRequest,
    DatasetSnapshot,
    ExplainRequest,
    ExplainResponse,
    LoadJobStatus,
    LoadSubmitRequest,
    MaintenanceWindow,
    MaintenanceWindowCreate,
    MaintenanceWindowEnd,
    NormalizeRequest,
    NormalizeResponse,
    OpsArtifact,
    RollbackPlan,
    ServingRelease,
    TableStat,
    TableStatsSnapshot,
    UploadSidoZipResponse,
)
from kraddr.geo.exceptions import InvalidInputError
from kraddr.geo.settings import get_settings

router = APIRouter(tags=["admin"])
_SAFE_TOKEN_RE = re.compile(r"[^0-9A-Za-z가-힣._-]+")


class _AuditRequest(TypedDict):
    client_ip: str | None
    user_agent: str | None
    request_id: str | None
    trace_id: str | None


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
    upload_id = f"{timestamp}_{_safe_path_token(sido or Path(safe_name).stem)}"
    upload_dir = _safe_upload_dir(settings.loader_data_dir, upload_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = (upload_dir / safe_name).resolve()
    if not _is_relative_to(dest, upload_dir):
        msg = "upload filename escapes upload directory"
        raise InvalidInputError(msg)
    digest = hashlib.sha256()
    size = 0
    with dest.open("wb") as fh:
        async for chunk in request.stream():
            if not chunk:
                continue
            size += len(chunk)
            if size > settings.api_max_upload_bytes:
                dest.unlink(missing_ok=True)
                msg = f"upload exceeds {settings.api_max_upload_bytes} bytes limit"
                raise InvalidInputError(msg)
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
    request: Request,
    strategy: Literal["concurrent", "swap"] = "concurrent",
    client: AsyncAddressClient = Depends(get_client),
    queue: JobQueue = Depends(get_job_queue),
) -> LoadJobStatus:
    job_id = await queue.enqueue("mv_refresh", {"strategy": strategy})
    status = await client.load_status(job_id)
    await client.record_audit_event(
        action="mv_refresh.submit",
        outcome="started",
        payload={"strategy": strategy},
        resource_type="load_job",
        resource_id=job_id,
        job_id=job_id,
        **_audit_request(request),
    )
    return status


@router.post("/loads", response_model=LoadJobStatus, response_model_exclude_none=True)
async def submit_load(
    req: LoadSubmitRequest,
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
    queue: JobQueue = Depends(get_job_queue),
) -> LoadJobStatus:
    if req.kind == "full_load_batch":
        job_id = await queue.enqueue_batch(req.payload)
    else:
        job_id = await queue.enqueue(req.kind, req.payload)
    status = await client.load_status(job_id)
    await client.record_audit_event(
        action="load.submit",
        outcome="started",
        payload={"kind": req.kind, "payload": req.payload},
        resource_type="load_job",
        resource_id=job_id,
        job_id=job_id,
        **_audit_request(request),
    )
    return status


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
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
    queue: JobQueue = Depends(get_job_queue),
) -> LoadJobStatus:
    return await cancel_load(job_id, request=request, client=client, queue=queue)


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
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
    queue: JobQueue = Depends(get_job_queue),
) -> LoadJobStatus:
    await queue.cancel(job_id)
    status = await client.load_status(job_id)
    await client.record_audit_event(
        action="load.cancel",
        outcome="cancelled",
        payload={"job_id": job_id},
        resource_type="load_job",
        resource_id=job_id,
        job_id=job_id,
        **_audit_request(request),
    )
    return status


@router.post("/consistency/run", response_model=LoadJobStatus, response_model_exclude_none=True)
async def run_consistency(
    req: ConsistencyRunRequest,
    request: Request,
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
    status = await client.load_status(job_id)
    await client.record_audit_event(
        action="consistency_check.submit",
        outcome="started",
        payload=req.model_dump(),
        resource_type="load_job",
        resource_id=job_id,
        job_id=job_id,
        **_audit_request(request),
    )
    return status


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


@router.get(
    "/ops/audit-events",
    response_model=list[AuditEvent],
    response_model_exclude_none=True,
)
async def list_ops_audit_events(
    limit: int = Query(default=50, ge=1, le=500),
    action: str | None = None,
    outcome: str | None = None,
    client: AsyncAddressClient = Depends(get_client),
) -> list[AuditEvent]:
    return await client.list_audit_events(limit=limit, action=action, outcome=outcome)


@router.get(
    "/ops/snapshots",
    response_model=list[DatasetSnapshot],
    response_model_exclude_none=True,
)
async def list_ops_snapshots(
    limit: int = Query(default=20, ge=1, le=200),
    state: str | None = None,
    client: AsyncAddressClient = Depends(get_client),
) -> list[DatasetSnapshot]:
    return await client.list_dataset_snapshots(limit=limit, state=state)


@router.get(
    "/ops/releases",
    response_model=list[ServingRelease],
    response_model_exclude_none=True,
)
async def list_ops_releases(
    limit: int = Query(default=20, ge=1, le=200),
    state: str | None = None,
    client: AsyncAddressClient = Depends(get_client),
) -> list[ServingRelease]:
    return await client.list_serving_releases(limit=limit, state=state)


@router.post(
    "/ops/releases/{release_id}/rollback-plan",
    response_model=RollbackPlan,
    response_model_exclude_none=True,
)
async def rollback_plan(
    release_id: str,
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
) -> RollbackPlan:
    plan = await client.rollback_plan(release_id)
    await client.record_audit_event(
        action="serving_release.rollback_plan",
        outcome="succeeded",
        payload={"release_id": release_id},
        resource_type="serving_release",
        resource_id=release_id,
        **_audit_request(request),
    )
    return plan


@router.get(
    "/ops/artifacts",
    response_model=list[OpsArtifact],
    response_model_exclude_none=True,
)
async def list_ops_artifacts(
    limit: int = Query(default=50, ge=1, le=500),
    artifact_type: str | None = None,
    state: str | None = None,
    client: AsyncAddressClient = Depends(get_client),
) -> list[OpsArtifact]:
    return await client.list_artifacts(limit=limit, artifact_type=artifact_type, state=state)


@router.get(
    "/ops/maintenance-windows",
    response_model=list[MaintenanceWindow],
    response_model_exclude_none=True,
)
async def list_ops_maintenance_windows(
    limit: int = Query(default=50, ge=1, le=500),
    state: str | None = None,
    client: AsyncAddressClient = Depends(get_client),
) -> list[MaintenanceWindow]:
    return await client.list_maintenance_windows(limit=limit, state=state)


@router.post(
    "/ops/maintenance-windows",
    response_model=MaintenanceWindow,
    response_model_exclude_none=True,
)
async def create_ops_maintenance_window(
    req: MaintenanceWindowCreate,
    client: AsyncAddressClient = Depends(get_client),
) -> MaintenanceWindow:
    return await client.create_maintenance_window(req)


@router.post(
    "/ops/maintenance-windows/{window_id}/end",
    response_model=MaintenanceWindow,
    response_model_exclude_none=True,
)
async def end_ops_maintenance_window(
    window_id: str,
    req: MaintenanceWindowEnd,
    client: AsyncAddressClient = Depends(get_client),
) -> MaintenanceWindow:
    return await client.end_maintenance_window(window_id, req)


@router.get(
    "/ops/table-stats",
    response_model=list[TableStatsSnapshot],
    response_model_exclude_none=True,
)
async def list_ops_table_stats(
    limit: int = Query(default=200, ge=1, le=1000),
    snapshot_id: str | None = None,
    client: AsyncAddressClient = Depends(get_client),
) -> list[TableStatsSnapshot]:
    return await client.list_table_stats_snapshots(limit=limit, snapshot_id=snapshot_id)


@router.post(
    "/ops/table-stats/capture",
    response_model=list[TableStatsSnapshot],
    response_model_exclude_none=True,
)
async def capture_ops_table_stats(
    snapshot_id: str | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    client: AsyncAddressClient = Depends(get_client),
) -> list[TableStatsSnapshot]:
    return await client.capture_table_stats_snapshots(snapshot_id=snapshot_id, limit=limit)


def _safe_filename(filename: str) -> str:
    name = _safe_path_token(filename)
    if not name or name in {".", ".."}:
        return "upload.bin"
    return name


def _safe_path_token(value: str) -> str:
    name = Path(value).name.replace("\\", "_").replace("/", "_")
    name = name.replace("..", "_")
    name = _SAFE_TOKEN_RE.sub("_", name).strip("._")
    return name or "upload"


def _safe_upload_dir(loader_data_dir: Path, upload_id: str) -> Path:
    base = (loader_data_dir / "uploads").resolve()
    resolved = (base / upload_id).resolve()
    if not _is_relative_to(resolved, base):
        msg = "upload path escapes base directory"
        raise InvalidInputError(msg)
    return resolved


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def _audit_request(request: Request) -> _AuditRequest:
    return {
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "request_id": request.headers.get("x-request-id"),
        "trace_id": request.headers.get("traceparent"),
    }
