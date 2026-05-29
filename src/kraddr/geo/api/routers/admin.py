"""Admin endpoints for loading and consistency checks."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import re
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from kraddr.geo.api._jobs import JobQueue
from kraddr.geo.api.deps import get_client, get_job_queue
from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.core.normalize import parse_address
from kraddr.geo.dto.admin import (
    AuditEvent,
    BackupArtifact,
    BackupCreateRequest,
    CacheMetrics,
    ConsistencyBulkDecisionRequest,
    ConsistencyBulkDecisionResponse,
    ConsistencyCaseDefinition,
    ConsistencyCaseSample,
    ConsistencyCaseSummary,
    ConsistencyReport,
    ConsistencyReportSummary,
    ConsistencyRunRequest,
    ConsistencySampleDecisionRequest,
    ConsistencySamplePage,
    ConsistencySampleRecheckResponse,
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
    RestoreCreateRequest,
    RestoreHotSwapPlan,
    RestoreHotSwapPlanRequest,
    RollbackPlan,
    ServingRelease,
    SourceSetDiscovery,
    SourceSetDiscoveryRequest,
    SourceSetPlan,
    SourceSetPlanRequest,
    TableStat,
    TableStatsSnapshot,
    UploadFileStatus,
    UploadSetCreateRequest,
    UploadSetStatus,
    UploadSidoZipResponse,
)
from kraddr.geo.exceptions import InvalidInputError
from kraddr.geo.infra.backup import (
    BACKUP_ARTIFACT_TYPE,
    backup_download_url,
    resolve_existing_archive_path,
    validate_download_token,
)
from kraddr.geo.infra.source_set import (
    build_full_load_source_set_plan,
    discover_load_sources,
)
from kraddr.geo.infra.uploads import (
    cancel_upload_set,
    create_upload_set,
    get_upload_set,
    store_upload_file,
    upload_set_root,
)
from kraddr.geo.settings import Settings, get_settings

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


@router.post(
    "/uploads",
    response_model=UploadSetStatus,
    response_model_exclude_none=True,
)
async def create_upload_session(req: UploadSetCreateRequest) -> UploadSetStatus:
    return await create_upload_set(get_settings().loader_data_dir, req)


@router.get(
    "/uploads/{upload_set_id}",
    response_model=UploadSetStatus,
    response_model_exclude_none=True,
)
async def upload_session_status(upload_set_id: str) -> UploadSetStatus:
    return await get_upload_set(get_settings().loader_data_dir, upload_set_id)


@router.put(
    "/uploads/{upload_set_id}/files",
    response_model=UploadFileStatus,
    response_model_exclude_none=True,
)
async def put_upload_file(
    upload_set_id: str,
    request: Request,
    filename: str = Query(min_length=1),
    relative_path: str | None = None,
) -> UploadFileStatus:
    settings = get_settings()
    return await store_upload_file(
        settings.loader_data_dir,
        upload_set_id,
        filename=filename,
        relative_path=relative_path,
        chunks=request.stream(),
        max_bytes=settings.api_max_upload_bytes,
    )


@router.post(
    "/uploads/{upload_set_id}/cancel",
    response_model=UploadSetStatus,
    response_model_exclude_none=True,
)
async def cancel_upload_session(upload_set_id: str) -> UploadSetStatus:
    return await cancel_upload_set(get_settings().loader_data_dir, upload_set_id)


@router.post(
    "/load-sources/discover",
    response_model=SourceSetDiscovery,
    response_model_exclude_none=True,
)
async def discover_load_source_set(req: SourceSetDiscoveryRequest) -> SourceSetDiscovery:
    root_path = _source_root_from_request(req.root_path, req.upload_set_id)
    assert root_path is not None
    return discover_load_sources(root_path, include_optional=req.include_optional)


@router.post(
    "/load-sources/plan",
    response_model=SourceSetPlan,
    response_model_exclude_none=True,
)
async def plan_load_source_set(req: SourceSetPlanRequest) -> SourceSetPlan:
    root_path = _source_root_from_request(req.root_path, req.upload_set_id, required=False)
    return build_full_load_source_set_plan(
        root_path=root_path,
        versions=req.versions,
        explicit_paths=req.explicit_paths,
        include_optional=req.include_optional,
        allow_mixed_yyyymm=req.allow_mixed_yyyymm,
        confirmation_token=req.confirmation_token,
        acknowledged_by=req.acknowledged_by,
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


@router.post("/backups", response_model=LoadJobStatus, response_model_exclude_none=True)
async def submit_backup(
    req: BackupCreateRequest,
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
    queue: JobQueue = Depends(get_job_queue),
) -> LoadJobStatus:
    payload = req.model_dump(exclude_none=True)
    job_id = await queue.enqueue("db_backup", payload)
    status = await client.load_status(job_id)
    await client.record_audit_event(
        action="db_backup.submit",
        outcome="started",
        payload=payload,
        resource_type="load_job",
        resource_id=job_id,
        job_id=job_id,
        **_audit_request(request),
    )
    return status


@router.get("/backups", response_model=list[BackupArtifact], response_model_exclude_none=True)
async def list_backups(
    limit: int = Query(default=50, ge=1, le=500),
    state: str | None = None,
    client: AsyncAddressClient = Depends(get_client),
) -> list[BackupArtifact]:
    settings = get_settings()
    artifacts = await client.list_artifacts(
        limit=limit,
        artifact_type=BACKUP_ARTIFACT_TYPE,
        state=state,
    )
    return [_backup_artifact_response(artifact, settings=settings) for artifact in artifacts]


@router.get(
    "/backups/{artifact_id}",
    response_model=BackupArtifact,
    response_model_exclude_none=True,
)
async def get_backup(
    artifact_id: str,
    client: AsyncAddressClient = Depends(get_client),
) -> BackupArtifact:
    artifact = await client.get_artifact(artifact_id)
    if artifact.artifact_type != BACKUP_ARTIFACT_TYPE:
        msg = f"artifact is not a db_backup: {artifact_id}"
        raise InvalidInputError(msg)
    return _backup_artifact_response(artifact, settings=get_settings())


@router.get("/backups/{artifact_id}/download", response_model=None)
async def download_backup(
    artifact_id: str,
    token: str = Query(min_length=64, max_length=64),
    client: AsyncAddressClient = Depends(get_client),
) -> FileResponse:
    settings = get_settings()
    artifact = await client.get_artifact(artifact_id)
    if artifact.artifact_type != BACKUP_ARTIFACT_TYPE or artifact.state != "available":
        msg = f"backup artifact is not available: {artifact_id}"
        raise InvalidInputError(msg)
    validate_download_token(artifact, settings, token)
    if not artifact.storage_uri:
        msg = f"backup artifact has no storage_uri: {artifact_id}"
        raise InvalidInputError(msg)
    archive_path = resolve_existing_archive_path(artifact.storage_uri, settings)
    return FileResponse(
        archive_path,
        media_type=artifact.media_type or "application/octet-stream",
        filename=artifact.display_name or archive_path.name,
    )


@router.post(
    "/backups/{artifact_id}/delete",
    response_model=BackupArtifact,
    response_model_exclude_none=True,
)
async def delete_backup(
    artifact_id: str,
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
) -> BackupArtifact:
    settings = get_settings()
    artifact = await client.get_artifact(artifact_id)
    if artifact.artifact_type != BACKUP_ARTIFACT_TYPE:
        msg = f"artifact is not a db_backup: {artifact_id}"
        raise InvalidInputError(msg)
    if artifact.storage_uri:
        with suppress(FileNotFoundError):
            resolve_existing_archive_path(artifact.storage_uri, settings).unlink()
    deleted = await client.delete_artifact(artifact_id)
    await client.record_audit_event(
        action="db_backup.delete",
        outcome="succeeded",
        payload={"artifact_id": artifact_id},
        resource_type="artifact",
        resource_id=artifact_id,
        **_audit_request(request),
    )
    return _backup_artifact_response(deleted, settings=settings)


@router.post("/restores", response_model=LoadJobStatus, response_model_exclude_none=True)
async def submit_restore(
    req: RestoreCreateRequest,
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
    queue: JobQueue = Depends(get_job_queue),
) -> LoadJobStatus:
    payload = req.model_dump(exclude_none=True)
    job_id = await queue.enqueue("db_restore", payload)
    status = await client.load_status(job_id)
    await client.record_audit_event(
        action="db_restore.submit",
        outcome="started",
        payload=payload,
        resource_type="load_job",
        resource_id=job_id,
        job_id=job_id,
        **_audit_request(request),
    )
    return status


@router.post(
    "/restores/hot-swap-plan",
    response_model=RestoreHotSwapPlan,
    response_model_exclude_none=True,
)
async def restore_hot_swap_plan(
    req: RestoreHotSwapPlanRequest,
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
) -> RestoreHotSwapPlan:
    plan = await client.restore_hot_swap_plan(req)
    await client.record_audit_event(
        action="serving_release.hot_swap_plan",
        outcome="succeeded" if plan.can_execute else "denied",
        payload={
            "current_database": plan.current_database,
            "restore_database": plan.restore_database,
            "previous_alias": plan.previous_alias,
            "blockers": plan.blockers,
        },
        resource_type="database",
        resource_id=plan.restore_database,
        **_audit_request(request),
    )
    return plan


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


@router.get("/jobs/{job_id}/events", response_model=None)
async def job_events(
    job_id: str,
    client: AsyncAddressClient = Depends(get_client),
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        last_payload: str | None = None
        while True:
            status = await client.load_status(job_id)
            payload = status.model_dump_json()
            if payload != last_payload:
                yield f"event: status\ndata: {payload}\n\n"
                last_payload = payload
            if status.state in {"done", "failed", "cancelled"}:
                break
            await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
    "/consistency/case-definitions",
    response_model=list[ConsistencyCaseDefinition],
    response_model_exclude_none=True,
)
async def consistency_case_definitions(
    client: AsyncAddressClient = Depends(get_client),
) -> tuple[ConsistencyCaseDefinition, ...]:
    return await client.consistency_case_definitions()


@router.get(
    "/consistency/{report_id}/cases/{case_code}/samples",
    response_model=ConsistencySamplePage,
    response_model_exclude_none=True,
)
async def list_consistency_case_samples(
    report_id: str,
    case_code: str,
    severity: Literal["OK", "INFO", "WARN", "ERROR"] | None = None,
    decision: Literal["unreviewed", "approved", "rejected", "deferred"] | None = None,
    sig_cd: str | None = Query(default=None, min_length=2, max_length=5),
    bjd_cd: str | None = Query(default=None, min_length=8, max_length=10),
    bd_mgt_sn: str | None = Query(default=None, min_length=1, max_length=25),
    reason_code: str | None = Query(default=None, min_length=1, max_length=80),
    source_kind: str | None = Query(default=None, min_length=1, max_length=80),
    source_yyyymm: str | None = Query(default=None, pattern=r"^\d{6}$"),
    min_distance_m: float | None = Query(default=None, ge=0),
    max_distance_m: float | None = Query(default=None, ge=0),
    order_by: str = Query(default="sample_rank", max_length=40),
    desc: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    output_format: Literal["json", "csv"] = Query(default="json", alias="format"),
    client: AsyncAddressClient = Depends(get_client),
) -> ConsistencySamplePage | StreamingResponse:
    result = await client.list_consistency_case_samples(
        report_id=report_id,
        case_code=case_code,
        severity=severity,
        decision=decision,
        sig_cd=sig_cd,
        bjd_cd=bjd_cd,
        bd_mgt_sn=bd_mgt_sn,
        reason_code=reason_code,
        source_kind=source_kind,
        source_yyyymm=source_yyyymm,
        min_distance_m=min_distance_m,
        max_distance_m=max_distance_m,
        order_by=order_by,
        desc=desc,
        page=page,
        page_size=page_size,
    )
    if output_format == "csv":
        return _samples_csv_response(result)
    return result


@router.get(
    "/consistency/{report_id}/cases/{case_code}/summary",
    response_model=ConsistencyCaseSummary,
    response_model_exclude_none=True,
)
async def consistency_case_summary(
    report_id: str,
    case_code: str,
    client: AsyncAddressClient = Depends(get_client),
) -> ConsistencyCaseSummary:
    return await client.consistency_case_summary(report_id=report_id, case_code=case_code)


@router.patch(
    "/consistency/{report_id}/cases/{case_code}/samples/{sample_id}/decision",
    response_model=ConsistencyCaseSample,
    response_model_exclude_none=True,
)
async def update_consistency_sample_decision(
    report_id: str,
    case_code: str,
    sample_id: str,
    req: ConsistencySampleDecisionRequest,
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
) -> ConsistencyCaseSample:
    return await client.update_consistency_sample_decision(
        report_id=report_id,
        case_code=case_code,
        sample_id=sample_id,
        req=req,
        actor_type="ui",
        **_audit_request(request),
    )


@router.post(
    "/consistency/{report_id}/cases/{case_code}/samples/bulk-decision",
    response_model=ConsistencyBulkDecisionResponse,
    response_model_exclude_none=True,
)
async def bulk_update_consistency_sample_decisions(
    report_id: str,
    case_code: str,
    req: ConsistencyBulkDecisionRequest,
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
) -> ConsistencyBulkDecisionResponse:
    return await client.bulk_update_consistency_sample_decisions(
        report_id=report_id,
        case_code=case_code,
        req=req,
        actor_type="ui",
        **_audit_request(request),
    )


@router.post(
    "/consistency/{report_id}/cases/{case_code}/samples/{sample_id}/recheck",
    response_model=ConsistencySampleRecheckResponse,
    response_model_exclude_none=True,
)
async def recheck_consistency_sample(
    report_id: str,
    case_code: str,
    sample_id: str,
    client: AsyncAddressClient = Depends(get_client),
) -> ConsistencySampleRecheckResponse:
    return await client.recheck_consistency_sample(
        report_id=report_id,
        case_code=case_code,
        sample_id=sample_id,
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


def _backup_artifact_response(artifact: OpsArtifact, *, settings: Settings) -> BackupArtifact:
    download_url = None
    if artifact.state == "available" and artifact.sha256:
        download_url = backup_download_url(artifact, settings)
    return BackupArtifact(**artifact.model_dump(), download_url=download_url)


def _samples_csv_response(page: ConsistencySamplePage) -> StreamingResponse:
    buffer = io.StringIO()
    buffer.write("\ufeff")
    fieldnames = (
        "sample_id",
        "report_id",
        "case_code",
        "severity",
        "sample_rank",
        "decision_state",
        "reason_code",
        "reviewed_by",
        "reviewed_at",
        "bd_mgt_sn",
        "rncode_full",
        "sig_cd",
        "bjd_cd",
        "distance_m",
        "source_kind",
        "source_yyyymm",
        "lon",
        "lat",
        "has_polygon",
        "has_line",
        "note",
        "case_metric",
        "source_snapshot",
    )
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for sample in page.items:
        writer.writerow(_sample_csv_row(sample))
    filename = f"{page.report_id}_{page.case_code}_samples.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={_safe_filename(filename)}"},
    )


def _sample_csv_row(sample: ConsistencyCaseSample) -> dict[str, object]:
    return {
        "sample_id": sample.sample_id,
        "report_id": sample.report_id,
        "case_code": sample.case_code,
        "severity": sample.severity,
        "sample_rank": sample.sample_rank,
        "decision_state": sample.decision_state,
        "reason_code": sample.reason_code or "",
        "reviewed_by": sample.reviewed_by or "",
        "reviewed_at": sample.reviewed_at.isoformat() if sample.reviewed_at else "",
        "bd_mgt_sn": sample.bd_mgt_sn or "",
        "rncode_full": sample.rncode_full or "",
        "sig_cd": sample.sig_cd or "",
        "bjd_cd": sample.bjd_cd or "",
        "distance_m": sample.distance_m if sample.distance_m is not None else "",
        "source_kind": sample.source_kind or "",
        "source_yyyymm": sample.source_yyyymm or "",
        "lon": sample.point.x if sample.point else "",
        "lat": sample.point.y if sample.point else "",
        "has_polygon": sample.has_polygon,
        "has_line": sample.has_line,
        "note": sample.note or "",
        "case_metric": sample.case_metric,
        "source_snapshot": sample.source_snapshot,
    }


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


def _source_root_from_request(
    root_path: str | None,
    upload_set_id: str | None,
    *,
    required: bool = True,
) -> Path | None:
    if upload_set_id:
        return upload_set_root(get_settings().loader_data_dir, upload_set_id)
    if root_path:
        return Path(root_path)
    if required:
        msg = "root_path or upload_set_id is required"
        raise InvalidInputError(msg)
    return None


def _audit_request(request: Request) -> _AuditRequest:
    return {
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "request_id": request.headers.get("x-request-id"),
        "trace_id": request.headers.get("traceparent"),
    }
