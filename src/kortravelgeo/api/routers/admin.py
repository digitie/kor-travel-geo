"""Admin endpoints for loading and consistency checks."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import re
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, TypedDict

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, ORJSONResponse, StreamingResponse

from kortravelgeo.api._jobs import JobQueue
from kortravelgeo.api.deps import get_client, get_job_queue
from kortravelgeo.api.security import (
    ROLE_DESTRUCTIVE_ADMIN,
    ROLE_REBUILD_OPERATOR,
    ROLE_SOURCE_FILE_MANAGER,
    ROLE_SOURCE_FILE_VIEWER,
    RequestContext,
    require_role,
)
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.core.normalize import parse_address
from kortravelgeo.core.source_categories import CATEGORY_CATALOG, serving_usage_for
from kortravelgeo.core.source_validation import GroupValidation
from kortravelgeo.dto.admin import (
    AuditEvent,
    BackupAllowedDirs,
    BackupArtifact,
    BackupCopyRequest,
    BackupCopyResult,
    BackupCreateRequest,
    BackupRetentionResult,
    BackupRetentionRunRequest,
    BackupVerifyRequest,
    BackupVerifyResult,
    BenchmarkArtifactRegisterRequest,
    CacheMetrics,
    ConsistencyBulkDecisionRequest,
    ConsistencyBulkDecisionResponse,
    ConsistencyCaseDefinition,
    ConsistencyCaseSample,
    ConsistencyCaseSummary,
    ConsistencyReport,
    ConsistencyReportSummary,
    ConsistencyRunRequest,
    ConsistencyRunValidationRequest,
    ConsistencyRunValidationResponse,
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
    PgStatStatementSnapshot,
    RestoreCreateRequest,
    RestoreDryRunResult,
    RestoreHotSwapExecuteRequest,
    RestoreHotSwapPlan,
    RestoreHotSwapPlanRequest,
    RestoreHotSwapResult,
    RestoreHotSwapRollbackRequest,
    RestoreHotSwapRollbackResult,
    RollbackPlan,
    RustfsConnectionCheck,
    RustfsImportPrefixRequest,
    RustfsStorageConfig,
    RustfsStorageConfigPatch,
    RustfsSyncLocalRequest,
    RustfsSyncLocalResult,
    ScheduledBackupRunResult,
    ScheduledBackupStatus,
    ServingRelease,
    TableStat,
    TableStatsSnapshot,
    UploadSetStatus,
    UploadSidoZipResponse,
)
from kortravelgeo.dto.source import (
    TERMINAL_UPLOAD_SESSION_STATES,
    EpostServerFetchRequest,
    EpostServerFetchResponse,
    GroupValidationResult,
    MultipartCompleteRequest,
    MultipartInitiateResponse,
    ReconcileResolveRequest,
    ReconcileResolveResponse,
    ReconcileRunRequest,
    RegisterRequest,
    RegisterResponse,
    RestoredFromBackupCreateRequest,
    RestoredFromBackupCreateResponse,
    RestoreSourceVerificationResult,
    ServingReleaseRollbackRequest,
    ServingReleaseRollbackResponse,
    SlotReplaceResponse,
    SourceBulkHardDeleteRequest,
    SourceBulkHardDeleteResponse,
    SourceCapacityUsage,
    SourceFileCategoryCatalog,
    SourceFileCategoryInfo,
    SourceGroupRelinkResponse,
    SourceGroupRestoreResponse,
    SourceGroupSoftDeleteRequest,
    SourceGroupSoftDeleteResponse,
    SourceJanitorRunResponse,
    SourceMatchSet,
    SourceMatchSetActivateResponse,
    SourceMatchSetCreateRequest,
    SourceMatchSetDetail,
    SourceMatchSetRetireResponse,
    SourceMatchSetValidateResponse,
    SourceRebuildDbRequest,
    SourceRebuildDbResponse,
    SourceReconcileItemPage,
    SourceReconcileRun,
    SourceUploadProgressEvent,
    UploadPartResponse,
    UploadSessionConflict,
    UploadSessionCreateRequest,
    UploadSessionStatus,
)
from kortravelgeo.exceptions import ForbiddenError, InvalidInputError, NotFoundError
from kortravelgeo.infra.backup import (
    BACKUP_ARTIFACT_TYPE,
    backup_download_url,
    resolve_existing_archive_path,
    validate_download_token,
)
from kortravelgeo.infra.backup_schedule import scheduled_backup_payload
from kortravelgeo.infra.concurrency import (
    AdvisoryLockKey,
    AdvisoryLockNamespace,
    ConcurrentExecutionError,
    cross_process_lock,
)
from kortravelgeo.infra.rustfs import (
    RustfsClient,
    RustfsUploadedPart,
    describe_rustfs_config,
    join_object_key,
    load_rustfs_config,
    require_enabled_rustfs,
    save_rustfs_config,
)
from kortravelgeo.infra.source_group_service import RegisterContext
from kortravelgeo.infra.source_rebuild_service import SourceRebuildService
from kortravelgeo.infra.source_upload_repo import should_fail_storage_state
from kortravelgeo.infra.uploads import (
    import_rustfs_prefix_as_upload_set,
    sync_local_to_rustfs,
)
from kortravelgeo.loaders.consistency_run_validation import (
    AUGMENT_CASE_CODES,
    is_augment_case,
)
from kortravelgeo.loaders.epost_server_fetch import (
    fetch_epost_source_file as run_epost_server_fetch,
)
from kortravelgeo.settings import Settings, get_settings

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


@router.get(
    "/source-file-categories",
    response_model=SourceFileCategoryCatalog,
    response_model_exclude_none=True,
)
async def source_file_categories() -> SourceFileCategoryCatalog:
    """Static catalog of source upload categories (T-200/T-201).

    Replaces the removed auto-detection upload-SET flow: the UI uses this to draw
    explicit per-category upload slots. ``role``/``default_role`` are UI defaults;
    the authoritative role lives on ``ops.source_match_set_items``.
    """
    return SourceFileCategoryCatalog(
        categories=tuple(
            SourceFileCategoryInfo(
                category=category.code,
                label=category.display_name,
                group_kind=category.group_kind,
                default_role=category.default_role,
                role=category.default_role,
                serving_usage=serving_usage_for(category.code),
                expected_member_kinds=category.expected_member_kinds,
                optional=category.optional,
            )
            for category in CATEGORY_CATALOG
        )
    )


# --- Source upload sessions (T-203a) --------------------------------------
# Lifecycle + storage-client slice of T-109. Mutating endpoints require
# source_file_manager; reads require source_file_viewer (doc "Admin 권한 모델").
# DEFERRED to T-203b/c: register, recompute_group_aggregates, archive structure
# validator, janitor, soft-delete/restore.

_SOURCE_MANAGER = Depends(require_role(ROLE_SOURCE_FILE_MANAGER))
_SOURCE_VIEWER = Depends(require_role(ROLE_SOURCE_FILE_VIEWER, ROLE_SOURCE_FILE_MANAGER))


@router.post(
    "/source-files/upload-sessions",
    response_model=UploadSessionStatus,
    response_model_exclude_none=True,
)
async def create_upload_session(
    req: UploadSessionCreateRequest,
    request: Request,
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> UploadSessionStatus | ORJSONResponse:
    """Create a session; ``409`` + resume payload when one already exists.

    ``user_yyyymm`` is server-mandatory (validated by the DTO). A non-terminal
    session for the same ``category+user_yyyymm`` returns ``409`` so the UI
    resumes it instead of creating a duplicate group + orphan object.
    """
    settings = get_settings()
    bucket: str | None = None
    prefix: str | None = None
    if req.storage_kind == "rustfs":
        config = require_enabled_rustfs(settings)
        bucket = config.bucket
        prefix = config.prefix
    result = await client.create_upload_session(
        req, bucket=bucket, prefix=prefix, created_by=ctx.actor
    )
    if result.conflict:
        existing = result.session
        conflict = UploadSessionConflict(
            message=(
                f"{existing.category}/{existing.user_yyyymm}에 진행 중인 "
                f"업로드 세션이 이미 있습니다"
            ),
            upload_session_id=existing.upload_session_id,
            state=existing.state,
            category=existing.category,
            user_yyyymm=existing.user_yyyymm,
            uploaded_file_count=existing.uploaded_file_count,
            expected_file_count=existing.expected_file_count,
            resumable_actions=("resume_upload", "cancel_session"),
            existing_session=existing,
        )
        await client.record_audit_event(
            action="source_upload.session_conflict",
            actor_type="ui",
            actor_id=ctx.actor,
            outcome="conflict",
            payload={"category": req.category, "user_yyyymm": req.user_yyyymm},
            resource_type="source_upload_session",
            resource_id=existing.upload_session_id,
            **_audit_request(request),
        )
        return ORJSONResponse(
            conflict.model_dump(mode="json", exclude_none=True),
            status_code=409,
        )
    await client.record_audit_event(
        action="source_upload.session_create",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome="created",
        payload={"category": req.category, "user_yyyymm": req.user_yyyymm},
        resource_type="source_upload_session",
        resource_id=result.session.upload_session_id,
        **_audit_request(request),
    )
    return result.session


@router.get(
    "/source-files/upload-sessions",
    response_model=list[UploadSessionStatus],
    response_model_exclude_none=True,
)
async def list_upload_sessions(
    state: str | None = Query(default=None),
    category: str | None = Query(default=None),
    user_yyyymm: str | None = Query(default=None, pattern=r"^\d{6}$"),
    created_by: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _ctx: RequestContext = _SOURCE_VIEWER,
    client: AsyncAddressClient = Depends(get_client),
) -> list[UploadSessionStatus]:
    """Resume entry point: filter resumable in-progress / recoverable sessions."""
    return await client.list_upload_sessions(
        state=state,
        category=category,
        user_yyyymm=user_yyyymm,
        created_by=created_by,
        limit=limit,
    )


@router.get(
    "/source-files/upload-sessions/{upload_session_id}",
    response_model=UploadSessionStatus,
    response_model_exclude_none=True,
)
async def get_upload_session(
    upload_session_id: str,
    _ctx: RequestContext = _SOURCE_VIEWER,
    client: AsyncAddressClient = Depends(get_client),
) -> UploadSessionStatus:
    return await client.get_upload_session(upload_session_id)


@router.post(
    "/source-files/epost-fetch",
    response_model=EpostServerFetchResponse,
    response_model_exclude_none=True,
)
async def fetch_epost_source(
    req: EpostServerFetchRequest,
    request: Request,
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
    queue: JobQueue = Depends(get_job_queue),
) -> EpostServerFetchResponse:
    """Manual epost server-fetch → RustFS register → postal load enqueue (T-207)."""
    result = await run_epost_server_fetch(
        engine=client._engine(),
        settings=get_settings(),
        req=req,
        actor=ctx.actor,
    )
    load_job_id: str | None = None
    if req.enqueue_load:
        load_job_id = await queue.enqueue(result.load_job_kind, result.load_payload)
    await client.record_audit_event(
        action="source.epost_server_fetch",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome="registered",
        payload={
            "category": req.category,
            "user_yyyymm": req.user_yyyymm,
            "load_job_kind": result.load_job_kind,
            "load_job_id": load_job_id,
            "warnings": list(result.warnings),
        },
        resource_type="source_upload_session",
        resource_id=result.upload_session.upload_session_id,
        job_id=load_job_id,
        **_audit_request(request),
    )
    return EpostServerFetchResponse(
        category=req.category,
        upload_session=result.upload_session,
        registration=result.register,
        load_job_id=load_job_id,
        load_job_kind=result.load_job_kind if req.enqueue_load else None,
        selected_filename=result.selected_filename,
        selected_path=str(result.selected_path),
        validation=result.load_payload["validation"],
        warnings=result.warnings,
    )


@router.post(
    "/source-files/upload-sessions/{upload_session_id}/files/{slot_id}/multipart",
    response_model=MultipartInitiateResponse,
    response_model_exclude_none=True,
)
async def initiate_multipart_upload(
    upload_session_id: str,
    slot_id: str,
    request: Request,
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> MultipartInitiateResponse:
    """Initiate a resumable multipart upload for one slot."""
    settings = get_settings()
    session = await client.get_upload_session(upload_session_id)
    _ensure_known_slot(session, slot_id)
    config = require_enabled_rustfs(settings)
    rustfs = RustfsClient(config)
    object_key = _slot_object_key(config.prefix, session, slot_id)
    upload_id = await rustfs.create_multipart_upload(
        object_key,
        metadata={
            "ktg-upload-session-id": session.upload_session_id,
            "ktg-source-file-group-id": session.source_file_group_id,
            "ktg-category": session.category,
            "ktg-upload-user-yyyymm": session.user_yyyymm,
            "ktg-part-key": slot_id,
        },
    )
    await client.record_upload_session_part(
        session.upload_session_id,
        part_key=slot_id,
        part_number=1,
        multipart_upload_id=upload_id,
        received_bytes=0,
    )
    await client.update_upload_session_state(session.upload_session_id, state="uploading")
    await client.record_audit_event(
        action="source_upload.multipart_initiate",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome="started",
        payload={"slot": slot_id, "multipart_upload_id": upload_id},
        resource_type="source_upload_session",
        resource_id=session.upload_session_id,
        **_audit_request(request),
    )
    return MultipartInitiateResponse(
        upload_session_id=session.upload_session_id,
        slot=slot_id,
        part_key=slot_id,
        multipart_upload_id=upload_id,
        object_key=object_key,
        part_size_bytes=session.part_size_bytes,
    )


@router.put(
    "/source-files/upload-sessions/{upload_session_id}/files/{slot_id}/multipart/{part_number}",
    response_model=UploadPartResponse,
    response_model_exclude_none=True,
)
async def upload_multipart_part(
    upload_session_id: str,
    slot_id: str,
    part_number: int,
    request: Request,
    multipart_upload_id: str = Query(min_length=1),
    _ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> UploadPartResponse:
    """Upload one part; records part etag/sha256/received_bytes for resume."""
    if part_number < 1:
        msg = "part_number must be >= 1"
        raise InvalidInputError(msg)
    settings = get_settings()
    session = await client.get_upload_session(upload_session_id)
    _ensure_known_slot(session, slot_id)
    body = await _read_upload_body(request, settings.api_max_upload_bytes)
    config = require_enabled_rustfs(settings)
    rustfs = RustfsClient(config)
    object_key = _slot_object_key(config.prefix, session, slot_id)
    part = await rustfs.upload_part(
        object_key,
        upload_id=multipart_upload_id,
        part_number=part_number,
        body=body,
    )
    part_sha256 = hashlib.sha256(body).hexdigest()
    recorded = await client.record_upload_session_part(
        session.upload_session_id,
        part_key=slot_id,
        part_number=part_number,
        multipart_upload_id=multipart_upload_id,
        part_etag=part.etag,
        part_sha256=part_sha256,
        received_bytes=len(body),
    )
    return UploadPartResponse(
        upload_session_id=session.upload_session_id,
        slot=slot_id,
        part_key=slot_id,
        part_number=part_number,
        received_bytes=recorded.received_bytes,
        part_etag=part.etag,
        part_sha256=part_sha256,
    )


@router.post(
    "/source-files/upload-sessions/{upload_session_id}/files/{slot_id}/multipart/complete",
    response_model=UploadSessionStatus,
    response_model_exclude_none=True,
)
async def complete_multipart_upload(
    upload_session_id: str,
    slot_id: str,
    req: MultipartCompleteRequest,
    request: Request,
    multipart_upload_id: str = Query(min_length=1),
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> UploadSessionStatus:
    """Complete the slot upload after verifying the multipart still exists.

    On resume the RustFS multipart upload must still hold every recorded part;
    if ``ListParts`` 404s or a recorded part is missing, the session transitions
    to ``failed_storage_state`` and the slot must be re-uploaded (doc 1294/1308).
    """
    settings = get_settings()
    session = await client.get_upload_session(upload_session_id)
    _ensure_known_slot(session, slot_id)
    config = require_enabled_rustfs(settings)
    rustfs = RustfsClient(config)
    object_key = _slot_object_key(config.prefix, session, slot_id)
    parts = await client.upload_session_slot_parts(
        session.upload_session_id, part_key=slot_id
    )
    recorded_numbers = frozenset(
        p.part_number for p in parts if p.part_etag is not None
    )
    try:
        listed = await rustfs.list_parts(object_key, upload_id=multipart_upload_id)
        listed_numbers: frozenset[int] | None = frozenset(p.part_number for p in listed)
    except NotFoundError:
        listed_numbers = None
    if should_fail_storage_state(
        recorded_part_numbers=recorded_numbers,
        listed_part_numbers=listed_numbers,
    ):
        failed = await client.update_upload_session_state(
            session.upload_session_id,
            state="failed_storage_state",
            error_message="RustFS multipart 상태가 기록과 일치하지 않습니다 (slot 재업로드 필요)",
        )
        await client.record_audit_event(
            action="source_upload.failed_storage_state",
            actor_type="ui",
            actor_id=ctx.actor,
            outcome="failed",
            payload={"slot": slot_id, "multipart_upload_id": multipart_upload_id},
            resource_type="source_upload_session",
            resource_id=session.upload_session_id,
            **_audit_request(request),
        )
        return failed
    complete_parts = tuple(
        RustfsUploadedPart(part_number=p.part_number, etag=p.part_etag)
        for p in sorted(parts, key=lambda x: x.part_number)
        if p.part_etag is not None
    )
    if req.part_etags:
        complete_parts = tuple(
            RustfsUploadedPart(part_number=number, etag=etag)
            for number, etag in sorted(req.part_etags)
        )
    await rustfs.complete_multipart_upload(
        object_key, upload_id=multipart_upload_id, parts=complete_parts
    )
    await client.record_upload_session_part(
        session.upload_session_id,
        part_key=slot_id,
        part_number=complete_parts[-1].part_number,
        multipart_upload_id=multipart_upload_id,
        part_etag=complete_parts[-1].etag,
        received_bytes=sum(p.received_bytes for p in parts),
        completed=True,
    )
    return await client.get_upload_session(session.upload_session_id)


@router.delete(
    "/source-files/upload-sessions/{upload_session_id}/files/{slot_id}/multipart",
    response_model=UploadSessionStatus,
    response_model_exclude_none=True,
)
async def abort_multipart_upload(
    upload_session_id: str,
    slot_id: str,
    multipart_upload_id: str = Query(min_length=1),
    _ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> UploadSessionStatus:
    """Abort the slot's multipart upload and clear its recorded parts."""
    settings = get_settings()
    session = await client.get_upload_session(upload_session_id)
    _ensure_known_slot(session, slot_id)
    config = require_enabled_rustfs(settings)
    rustfs = RustfsClient(config)
    object_key = _slot_object_key(config.prefix, session, slot_id)
    with suppress(InvalidInputError):
        await rustfs.abort_multipart_upload(object_key, upload_id=multipart_upload_id)
    return await client.replace_upload_session_slot(session.upload_session_id, part_key=slot_id)


@router.post(
    "/source-files/upload-sessions/{upload_session_id}/files/{slot_id}/replace",
    response_model=SlotReplaceResponse,
    response_model_exclude_none=True,
)
async def replace_upload_slot(
    upload_session_id: str,
    slot_id: str,
    request: Request,
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> SlotReplaceResponse:
    """Replace a completed slot before register: invalidate prior hash/validation.

    Clears the slot's recorded parts (so its etag/hash/structure results no
    longer apply) and reopens it for a fresh upload (doc line 1314).
    """
    session = await client.replace_upload_session_slot(upload_session_id, part_key=slot_id)
    await client.record_audit_event(
        action="source_upload.slot_replace",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome="invalidated",
        payload={"slot": slot_id},
        resource_type="source_upload_session",
        resource_id=session.upload_session_id,
        **_audit_request(request),
    )
    return SlotReplaceResponse(
        upload_session_id=session.upload_session_id,
        slot=slot_id,
        part_key=slot_id,
        invalidated=True,
        state=session.state,
    )


@router.get(
    "/source-files/upload-sessions/{upload_session_id}/events",
    response_model=None,
)
async def upload_session_events(
    upload_session_id: str,
    _ctx: RequestContext = _SOURCE_VIEWER,
    client: AsyncAddressClient = Depends(get_client),
) -> StreamingResponse:
    """SSE ``source_upload.progress`` stream (mirrors ``/jobs/{id}/events``).

    Emits a ``source_upload.progress`` event whenever the session payload
    changes and stops at a terminal state; clients fall back to polling
    ``GET .../upload-sessions/{id}`` if the stream drops.
    """

    async def event_stream() -> AsyncIterator[str]:
        last_payload: str | None = None
        while True:
            session = await client.get_upload_session(upload_session_id)
            event = _progress_event(session)
            payload = event.model_dump_json(exclude_none=True)
            if payload != last_payload:
                yield f"event: source_upload.progress\ndata: {payload}\n\n"
                last_payload = payload
            if session.state in _UPLOAD_TERMINAL_STATES:
                break
            await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Registry register + validate (T-203b) --------------------------------
# DEFERRED to T-203c: janitor (expires/registration_deadline), soft-delete/restore.


@router.post(
    "/source-files/upload-sessions/{upload_session_id}/register",
    response_model=RegisterResponse,
    response_model_exclude_none=True,
)
async def register_upload_session(
    upload_session_id: str,
    req: RegisterRequest,
    request: Request,
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> RegisterResponse:
    """Register a completed upload session into the source registry (doc ~1347).

    Head-verifies each completed slot object (size/etag), builds the structure
    decision from slot coverage, and creates the group + child files in one DB
    transaction. Storage-first: a DB failure leaves the objects in place and the
    same session can ``register`` again (``failed_register``).
    """
    session = await client.get_upload_session(upload_session_id)
    if req.confirm_user_yyyymm != session.user_yyyymm:
        msg = "confirm_user_yyyymm이 세션 user_yyyymm과 다릅니다 (기준년월 수정 아님)"
        raise InvalidInputError(msg)
    settings = get_settings()
    config = require_enabled_rustfs(settings) if session.storage_kind == "rustfs" else None
    rustfs = RustfsClient(config) if config is not None else None

    contexts: list[RegisterContext] = []
    completed_keys: list[str] = []
    for slot in session.file_slots:
        parts = await client.upload_session_slot_parts(
            session.upload_session_id, part_key=slot.part_key
        )
        completed = [p for p in parts if p.completed_at is not None]
        if not completed:
            if slot.required:
                msg = f"필수 slot 미완료: {slot.part_key}"
                raise InvalidInputError(msg)
            continue
        object_key = _slot_object_key(config.prefix if config else "", session, slot.slot)
        sha256 = next((p.part_sha256 for p in completed if p.part_sha256), None)
        size_bytes = sum(p.received_bytes for p in completed)
        object_etag = next((p.part_etag for p in completed if p.part_etag), None)
        if rustfs is not None:
            head = await rustfs.head_object(object_key)
            object_etag = head.etag or object_etag
            if head.size:
                size_bytes = head.size
            if sha256 is None:
                # No streamed hash recorded → compute once from the object body.
                sha256 = head.metadata.get("ktg-sha256") or await rustfs.compute_sha256(object_key)
        if sha256 is None:
            msg = f"slot {slot.part_key}의 SHA-256을 확인할 수 없습니다"
            raise InvalidInputError(msg)
        completed_keys.append(slot.part_key)
        contexts.append(
            RegisterContext(
                part_key=slot.part_key,
                part_kind=slot.part_kind,
                part_label=slot.part_label,
                original_filename=f"{slot.part_label or slot.part_key}",
                sha256=sha256,
                size_bytes=size_bytes,
                object_key=object_key,
                object_etag=object_etag,
                compression_format="zip",
            )
        )

    structure_validation = _coverage_structure_validation(
        category=session.category,
        group_kind=session.group_kind,
        present_part_keys=tuple(completed_keys),
    )
    try:
        response = await client.register_source_group(
            session_id=session.upload_session_id,
            contexts=tuple(contexts),
            structure_validation=structure_validation,
            storage_kind=session.storage_kind,
            bucket=config.bucket if config else None,
            actor=ctx.actor,
            yyyymm_mismatch_ack=req.yyyymm_mismatch_ack,
            display_name=req.display_name,
        )
    except Exception:
        await client.update_upload_session_state(
            session.upload_session_id,
            state="failed_register",
            error_message="registry 등록 실패 (재시도 가능)",
        )
        raise
    return response


@router.post(
    "/source-file-groups/{source_file_group_id}/validate",
    response_model=GroupValidationResult,
    response_model_exclude_none=True,
)
async def validate_source_file_group(
    source_file_group_id: str,
    request: Request,
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> GroupValidationResult:
    """Re-run the archive structure validator over a registered group (doc ~1318).

    Materializing archive internals needs GDAL/zip and is gated for live use; the
    pure decision logic and the recompute it drives are exercised in unit tests.
    """
    result = await client.revalidate_source_file_group(
        source_file_group_id, actor=ctx.actor
    )
    await client.record_audit_event(
        action="source.group_validate",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome=result.validation_state,
        payload={"category": result.category},
        resource_type="source_file_group",
        resource_id=source_file_group_id,
        **_audit_request(request),
    )
    return result


# --- Soft-delete / restore + janitor (T-203c) -----------------------------
# soft-delete/restore require source_file_manager; the group + its children are
# soft-deleted (RustFS objects preserved). restore is the canonical recovery path.


@router.post(
    "/source-file-groups/{source_file_group_id}/soft-delete",
    response_model=SourceGroupSoftDeleteResponse,
    response_model_exclude_none=True,
)
async def soft_delete_source_file_group(
    source_file_group_id: str,
    req: SourceGroupSoftDeleteRequest,
    request: Request,
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> SourceGroupSoftDeleteResponse:
    """Soft-delete a group + its children (doc line ~1441).

    Sets ``state='soft_deleted'`` / ``deleted_at=now()``; RustFS objects are kept.
    A group an ACTIVE match set still references is blocked (409) — retire the
    match set first. ``recompute_group_aggregates`` re-propagates to referencing
    match sets (``validated`` → ``invalid`` etc.).
    """
    result = await client.soft_delete_source_file_group(
        source_file_group_id, actor=ctx.actor, reason=req.reason
    )
    await client.record_audit_event(
        action="source.soft_delete",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome=result.state,
        payload={"affected_file_count": result.affected_file_count},
        resource_type="source_file_group",
        resource_id=source_file_group_id,
        **_audit_request(request),
    )
    return result


@router.post(
    "/source-file-groups/{source_file_group_id}/restore",
    response_model=SourceGroupRestoreResponse,
    response_model_exclude_none=True,
)
async def restore_source_file_group(
    source_file_group_id: str,
    request: Request,
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> SourceGroupRestoreResponse:
    """Restore a soft-deleted group via RustFS head + hash (doc line ~1442).

    Verifies each soft-deleted child's RustFS object, transitions
    ``soft_deleted`` → ``validating``/``available`` (present + consistent),
    ``missing`` (absent), or ``quarantined`` (hash/size mismatch), clears
    ``deleted_at``, and recomputes (re-propagating to referencing match sets).
    """
    result = await client.restore_source_file_group(source_file_group_id, actor=ctx.actor)
    await client.record_audit_event(
        action="source.restore",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome=result.state,
        payload={"category": result.category},
        resource_type="source_file_group",
        resource_id=source_file_group_id,
        **_audit_request(request),
    )
    return result


@router.post(
    "/source-file-groups/{source_file_group_id}/relink",
    response_model=SourceGroupRelinkResponse,
    response_model_exclude_none=True,
)
async def relink_restored_source_file_group(
    source_file_group_id: str,
    request: Request,
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> SourceGroupRelinkResponse:
    """Relink a ``restored_from_backup`` stub group's RustFS objects (T-208, doc steps 7-9).

    Reattaches each ``missing`` stub child by head-verifying + streaming-rehashing
    its RustFS object against the MANIFEST sha256/size (the trust boundary): a
    consistent object → ``validating`` (then ``available`` once all are
    consistent), absent → ``missing``, mismatch → ``quarantined``. The group
    recomputes ``group_sha256`` and, when every referenced group is ``available``,
    the match set precomputes its canonical ``source_set_hash`` and transitions
    ``restored_from_backup → revalidatable`` (M-A option 2). Requires
    ``source_file_manager``; direct active promotion is forbidden (separate
    ``activate`` after ``validate``).
    """
    result = await client.relink_restored_source_group(
        source_file_group_id, actor=ctx.actor
    )
    await client.record_audit_event(
        action="source.restored_from_backup_relink",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome=result.state,
        payload={
            "category": result.category,
            "affected_match_set_ids": list(result.affected_match_set_ids),
        },
        resource_type="source_file_group",
        resource_id=source_file_group_id,
        **_audit_request(request),
    )
    return result


@router.post(
    "/source-files/janitor/run",
    response_model=SourceJanitorRunResponse,
    response_model_exclude_none=True,
)
async def run_source_upload_janitor(
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> SourceJanitorRunResponse:
    """Run one upload-session janitor pass on demand (doc lines ~519-525).

    Aborts unfinished multipart uploads past ``expires_at`` (RustFS objects that
    finished storing are never auto-deleted) and transitions stored-but-
    unregistered sessions past the registration deadline to
    ``registration_expired``. Skips if the ``SOURCE_JANITOR`` lock is held.
    """
    return await client.run_source_upload_janitor()


# --- RustFS reconciliation (T-204) ----------------------------------------
# DB/RustFS consistency scan + resolve (doc lines ~638-726, ~1449-1479). run +
# non-destructive resolve = source_file_manager; reads = source_file_viewer;
# destructive resolves (delete_object / retry_delete_object) additionally require
# destructive_admin (doc lines ~1446-1447, ~1154).

_DESTRUCTIVE_ADMIN = Depends(require_role(ROLE_DESTRUCTIVE_ADMIN))
_DESTRUCTIVE_RESOLVE_ACTIONS = frozenset({"delete_object", "retry_delete_object"})


@router.post(
    "/source-files/reconcile",
    response_model=SourceReconcileRun,
    response_model_exclude_none=True,
)
async def run_source_reconcile(
    req: ReconcileRunRequest,
    request: Request,
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> SourceReconcileRun:
    """Run one RustFS ⟷ DB reconciliation pass (doc lines ~638-726).

    Lists RustFS objects under the prefix, classifies each against
    ``ops.source_files`` (quick skips rehash for unchanged objects, force-deeping
    past the rolling-deep window; deep rehashes every body), and records an issue
    item per discrepancy. En-masse loss propagates referenced groups to
    ``missing`` (active match sets → ``integrity_alert``, ``validated`` → ``invalid``).
    """
    result = await client.run_source_reconcile(
        prefix=req.prefix, mode=req.mode, actor=ctx.actor
    )
    await client.record_audit_event(
        action="source.reconcile_run",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome=result.state,
        payload={"prefix": result.prefix, "mode": result.mode,
                 "mismatch_count": result.mismatch_count},
        resource_type="source_storage_reconcile",
        resource_id=result.source_storage_reconcile_run_id,
        **_audit_request(request),
    )
    return result


@router.get(
    "/source-files/reconcile",
    response_model=list[SourceReconcileRun],
    response_model_exclude_none=True,
)
async def list_source_reconcile_runs(
    _ctx: RequestContext = _SOURCE_VIEWER,
    client: AsyncAddressClient = Depends(get_client),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[SourceReconcileRun]:
    """List recent reconciliation runs (newest first)."""
    return list(await client.list_source_reconcile_runs(limit=limit))


@router.get(
    "/source-files/reconcile/{source_storage_reconcile_run_id}",
    response_model=SourceReconcileRun,
    response_model_exclude_none=True,
)
async def get_source_reconcile_run(
    source_storage_reconcile_run_id: str,
    _ctx: RequestContext = _SOURCE_VIEWER,
    client: AsyncAddressClient = Depends(get_client),
) -> SourceReconcileRun:
    """Get one reconciliation run by id."""
    return await client.get_source_reconcile_run(source_storage_reconcile_run_id)


@router.get(
    "/source-files/reconcile/{source_storage_reconcile_run_id}/items",
    response_model=SourceReconcileItemPage,
    response_model_exclude_none=True,
)
async def list_source_reconcile_items(
    source_storage_reconcile_run_id: str,
    _ctx: RequestContext = _SOURCE_VIEWER,
    client: AsyncAddressClient = Depends(get_client),
    issue_type: str | None = Query(default=None),
    state: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
) -> SourceReconcileItemPage:
    """List a run's issue items (filter by issue_type / state)."""
    items = await client.list_source_reconcile_items(
        source_storage_reconcile_run_id,
        issue_type=issue_type,
        state=state,
        limit=limit,
    )
    return SourceReconcileItemPage(items=items)


@router.post(
    "/source-files/reconcile/items/{source_storage_reconcile_item_id}/resolve",
    response_model=ReconcileResolveResponse,
    response_model_exclude_none=True,
)
async def resolve_source_reconcile_item(
    source_storage_reconcile_item_id: str,
    req: ReconcileResolveRequest,
    request: Request,
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> ReconcileResolveResponse:
    """Resolve one reconciliation item (doc lines ~1458-1479).

    Most resolves require ``source_file_manager``; destructive resolves
    (``delete_object`` / ``retry_delete_object``) additionally require the
    ``destructive_admin`` role. A read-after-write recheck rejects stale items and
    the active-정본 deletion guard refuses deleting an object an active match set
    references.
    """
    if req.action in _DESTRUCTIVE_RESOLVE_ACTIONS and not ctx.has_any_role(
        frozenset({ROLE_DESTRUCTIVE_ADMIN})
    ):
        raise ForbiddenError(
            "destructive resolve requires the destructive_admin role",
            hint=f"requires role: {ROLE_DESTRUCTIVE_ADMIN}",
        )
    result = await client.resolve_source_reconcile_item(
        source_storage_reconcile_item_id,
        action=req.action,
        actor=ctx.actor,
        category=req.category,
        user_yyyymm=req.user_yyyymm,
        registration_deadline_at=req.registration_deadline_at,
        typed_confirmation=req.typed_confirmation,
    )
    await client.record_audit_event(
        action="source.reconcile_resolve",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome=result.outcome,
        payload={"issue_type": result.issue_type, "action": req.action},
        resource_type="source_storage_reconcile_item",
        resource_id=source_storage_reconcile_item_id,
        **_audit_request(request),
    )
    return result


@router.get(
    "/source-files/capacity",
    response_model=SourceCapacityUsage,
    response_model_exclude_none=True,
)
async def source_files_capacity(
    _ctx: RequestContext = _SOURCE_VIEWER,
    client: AsyncAddressClient = Depends(get_client),
) -> SourceCapacityUsage:
    """Per-category storage capacity usage (doc line ~2107).

    Computation + surfacing. Includes the T-212 (ADR-052) retention
    recommendation (over-threshold + reclaimable / eligible-for-cleanup signal);
    the policy never auto-deletes registered archives.
    """
    return await client.source_storage_capacity()


@router.post(
    "/source-files/bulk-hard-delete",
    response_model=SourceBulkHardDeleteResponse,
    response_model_exclude_none=True,
)
async def bulk_hard_delete_source_files(
    req: SourceBulkHardDeleteRequest,
    request: Request,
    ctx: RequestContext = _DESTRUCTIVE_ADMIN,
    client: AsyncAddressClient = Depends(get_client),
) -> SourceBulkHardDeleteResponse:
    """Manually bulk hard-delete eligible source objects (T-212, ADR-052).

    The ONLY admin-driven hard-delete path — registered archives are NEVER
    auto-deleted. Requires ``destructive_admin`` and a ``typed_confirmation`` of
    ``HARD-DELETE-SOURCES``. Only ``soft_deleted``/``quarantined`` files and
    unregistered stored objects (``object_missing_db``/``registration_expired``)
    are eligible; the reused T-204 active-정본 guard makes an object an active
    match set references never eligible. A completed ``db_backup`` manifest/export
    must exist OR ``manifest_ack=true`` must be passed (pre-delete safety gate).
    Each deletion is audited; the owning group is recomputed so referencing match
    sets follow.
    """
    result = await client.bulk_hard_delete_source_objects(
        object_keys=req.object_keys,
        typed_confirmation=req.typed_confirmation,
        manifest_ack=req.manifest_ack,
        actor=ctx.actor,
        reason=req.reason,
    )
    await client.record_audit_event(
        action="source.hard_delete",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome="bulk_hard_delete",
        payload={
            "requested": result.requested_count,
            "hard_deleted": result.hard_deleted_count,
            "delete_failed": result.delete_failed_count,
            "skipped": result.skipped_count,
            "manifest_ack": req.manifest_ack,
        },
        resource_type="source_storage",
        resource_id="bulk-hard-delete",
        **_audit_request(request),
    )
    return result


# --- Source match sets (T-205a) -------------------------------------------
# CRUD + validate/activate/retire over ops.source_match_sets. create/validate/
# retire require source_file_manager; activate requires rebuild_operator (doc
# "Admin 권한 모델" role table); reads require source_file_viewer. T-205b adds
# rebuild-db (rebuild_operator) bridging to the full_load_batch loader DAG with
# the source_rebuild_db lock + integrity gate + consistency-ERROR/forced_promotion
# gate (dataset_snapshots.source_match_set_id FK), and the rollback match-set swap
# (destructive_admin) below the rollback-plan endpoint.

_REBUILD_OPERATOR = Depends(require_role(ROLE_REBUILD_OPERATOR))


@router.get(
    "/source-match-sets",
    response_model=list[SourceMatchSet],
    response_model_exclude_none=True,
)
async def list_source_match_sets(
    state: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _ctx: RequestContext = _SOURCE_VIEWER,
    client: AsyncAddressClient = Depends(get_client),
) -> list[SourceMatchSet]:
    """List source match sets (doc "ops.source_match_sets")."""
    return list(await client.list_source_match_sets(state=state, limit=limit))


@router.get(
    "/source-match-sets/{source_match_set_id}",
    response_model=SourceMatchSetDetail,
    response_model_exclude_none=True,
)
async def get_source_match_set(
    source_match_set_id: str,
    _ctx: RequestContext = _SOURCE_VIEWER,
    client: AsyncAddressClient = Depends(get_client),
) -> SourceMatchSetDetail:
    """Get one source match set + its items."""
    return await client.get_source_match_set(source_match_set_id)


@router.post(
    "/source-match-sets",
    response_model=SourceMatchSetDetail,
    response_model_exclude_none=True,
)
async def create_source_match_set(
    req: SourceMatchSetCreateRequest,
    request: Request,
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> SourceMatchSetDetail:
    """Create a ``draft`` match set + its items (doc lines ~820-857).

    Item role/omitted/UNIQUE-category invariants are enforced before insert; the
    canonical ``source_set_hash`` stays NULL for a draft (computed at validate).
    """
    result = await client.create_source_match_set(req, actor=ctx.actor)
    await client.record_audit_event(
        action="source_match_set.create",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome=result.match_set.state,
        payload={"name": req.name, "profile": req.profile,
                 "item_count": len(req.items)},
        resource_type="source_match_set",
        resource_id=result.match_set.source_match_set_id,
        **_audit_request(request),
    )
    return result


@router.post(
    "/source-match-sets/restored-from-backup",
    response_model=RestoredFromBackupCreateResponse,
    response_model_exclude_none=True,
)
async def create_restored_from_backup_match_set(
    req: RestoredFromBackupCreateRequest,
    request: Request,
    ctx: RequestContext = _DESTRUCTIVE_ADMIN,
    client: AsyncAddressClient = Depends(get_client),
) -> RestoredFromBackupCreateResponse:
    """Reconstruct a ``restored_from_backup`` match set from a backup manifest (T-208).

    Reads the ``db_backup`` artifact's manifest ``source_match_set`` block and
    creates stub groups/files (``missing``/``unknown``, the manifest
    ``group_sha256`` preserved as UNTRUSTED metadata) + items + a match set at
    ``state='restored_from_backup'`` in one transaction (doc steps 1-6). Rebuild
    stays disabled until every referenced group is relinked to ``available``.
    Restore-from-backup is sensitive → requires ``destructive_admin``.
    """
    result = await client.create_restored_from_backup(
        req.artifact_id, actor=ctx.actor
    )
    await client.record_audit_event(
        action="source.restored_from_backup_create",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome=result.state,
        payload={
            "artifact_id": req.artifact_id,
            "created_group_count": len(result.created_group_ids),
            "created_file_count": result.created_file_count,
        },
        resource_type="source_match_set",
        resource_id=result.source_match_set_id,
        **_audit_request(request),
    )
    return result


@router.post(
    "/source-match-sets/{source_match_set_id}/validate",
    response_model=SourceMatchSetValidateResponse,
    response_model_exclude_none=True,
)
async def validate_source_match_set(
    source_match_set_id: str,
    request: Request,
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> SourceMatchSetValidateResponse:
    """Run the match set ``validate`` state-split (doc lines ~806/813-815).

    ``draft``→``validated`` (compute fresh hash), ``revalidatable``→``validated``
    (re-check pre-computed hash), ``active``+``integrity_alert``→ validate-in-place
    (clear alert, stay active). ``retired``/``invalid``/``restored_from_backup`` are
    rejected (must recover to ``revalidatable`` first).
    """
    result = await client.validate_source_match_set(
        source_match_set_id, actor=ctx.actor
    )
    await client.record_audit_event(
        action="source_match_set.validate",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome=f"{result.action}:{'ok' if result.ok else 'fail'}",
        payload={"action": result.action, "ok": result.ok,
                 "reasons": list(result.reasons)},
        resource_type="source_match_set",
        resource_id=source_match_set_id,
        **_audit_request(request),
    )
    return result


@router.post(
    "/source-match-sets/{source_match_set_id}/activate",
    response_model=SourceMatchSetActivateResponse,
    response_model_exclude_none=True,
)
async def activate_source_match_set(
    source_match_set_id: str,
    request: Request,
    ctx: RequestContext = _REBUILD_OPERATOR,
    client: AsyncAddressClient = Depends(get_client),
) -> SourceMatchSetActivateResponse:
    """Atomic-swap activate a ``validated`` match set (doc line ~807).

    Under the ``SOURCE_MATCH_ACTIVATE`` advisory lock in ONE transaction: re-check
    the canonical hash (stale-hash guard), retire the current active, then set the
    target ``active`` — no externally-observable active gap. Requires
    ``rebuild_operator``.
    """
    result = await client.activate_source_match_set(
        source_match_set_id, actor=ctx.actor
    )
    await client.record_audit_event(
        action="source_match_set.activate",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome=result.state,
        payload={"retired_match_set_id": result.retired_match_set_id},
        resource_type="source_match_set",
        resource_id=source_match_set_id,
        **_audit_request(request),
    )
    return result


@router.post(
    "/source-match-sets/{source_match_set_id}/retire",
    response_model=SourceMatchSetRetireResponse,
    response_model_exclude_none=True,
)
async def retire_source_match_set(
    source_match_set_id: str,
    request: Request,
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> SourceMatchSetRetireResponse:
    """Retire a source match set (doc line ~808)."""
    result = await client.retire_source_match_set(
        source_match_set_id, actor=ctx.actor
    )
    await client.record_audit_event(
        action="source_match_set.retire",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome=result.state,
        payload={"was_active": result.was_active},
        resource_type="source_match_set",
        resource_id=source_match_set_id,
        **_audit_request(request),
    )
    return result


def _rebuild_typed_confirmation(source_match_set_id: str) -> str:
    return f"REBUILD-PROMOTE {source_match_set_id}"


@router.post(
    "/source-match-sets/{source_match_set_id}/rebuild-db",
    response_model=SourceRebuildDbResponse,
    response_model_exclude_none=True,
)
async def rebuild_source_match_set_db(
    source_match_set_id: str,
    req: SourceRebuildDbRequest,
    request: Request,
    ctx: RequestContext = _REBUILD_OPERATOR,
    client: AsyncAddressClient = Depends(get_client),
    queue: JobQueue = Depends(get_job_queue),
) -> SourceRebuildDbResponse:
    """Rebuild the serving DB from a match set (doc "DB 재구성", ~1532-1562).

    Bridges to the EXISTING ``full_load_batch`` loader DAG: assembles the batch
    payload from the match set's build groups and enqueues it under the
    ``source_rebuild_db`` global advisory lock (409 if another rebuild is
    enqueuing/running). Before any child loader is enqueued the pre-load
    source-archive integrity gate re-verifies each group's RustFS objects'
    ``sha256``/``size``/presence + ``group_sha256`` against the registry; a
    mismatch quarantines the failing groups, propagates (active →
    ``integrity_alert``, non-active ``validated`` → ``invalid``), and fails
    without creating any child job.

    ``force_promotion`` (the ERROR-bypass) additionally requires the
    ``destructive_admin`` role and a ``typed_confirmation`` of
    ``REBUILD-PROMOTE {id}``. It bypasses ONLY the later consistency ERROR
    promotion block — never the integrity gate above, an unavailable group, or a
    match set ``integrity_alert`` (doc ~1559, ADR-049 #13).
    """
    if req.force_promotion:
        if not ctx.has_any_role(frozenset({ROLE_DESTRUCTIVE_ADMIN})):
            raise ForbiddenError(
                "force_promotion requires the destructive_admin role",
                hint=f"requires role: {ROLE_DESTRUCTIVE_ADMIN}",
            )
        if req.typed_confirmation != _rebuild_typed_confirmation(source_match_set_id):
            raise InvalidInputError(
                "force_promotion requires typed_confirmation "
                f"'{_rebuild_typed_confirmation(source_match_set_id)}'"
            )

    # The source_rebuild_db lock serializes the prepare+enqueue critical section
    # vs other rebuilds (409 on conflict); the integrity gate + stale-job sweep
    # run inside it. The actual COPY/MV steps are serialized by the JobQueue.
    async with cross_process_lock(client._engine(), SourceRebuildService.rebuild_lock_key()):
        response, batch_payload = await client.prepare_source_match_set_rebuild(
            source_match_set_id,
            actor=ctx.actor,
            force_promotion=req.force_promotion,
            typed_confirmation=req.typed_confirmation,
            reason=req.reason,
        )
        if batch_payload is None:
            await client.record_audit_event(
                action="source.rebuild_db",
                actor_type="ui",
                actor_id=ctx.actor,
                outcome="integrity_gate_failed",
                payload={"failed_group_ids": list(response.failed_group_ids)},
                resource_type="source_match_set",
                resource_id=source_match_set_id,
                **_audit_request(request),
            )
            return response
        job_id = await queue.enqueue_batch(batch_payload)
        await client.record_rebuild_enqueued(
            source_match_set_id,
            actor=ctx.actor,
            job_id=job_id,
            load_batch_id=job_id,
            forced_promotion=req.force_promotion,
            reason=req.reason,
        )
    return response.model_copy(update={"job_id": job_id, "load_batch_id": job_id})


@router.post(
    "/source-match-sets/{source_match_set_id}/run-validation",
    response_model=ConsistencyRunValidationResponse,
    response_model_exclude_none=True,
)
async def run_source_match_set_validation(
    source_match_set_id: str,
    req: ConsistencyRunValidationRequest,
    request: Request,
    ctx: RequestContext = _SOURCE_MANAGER,
    client: AsyncAddressClient = Depends(get_client),
) -> ConsistencyRunValidationResponse:
    """Run the registry C11~C17 validation cases against an existing DB (T-206).

    Does NOT rebuild the serving DB or create a snapshot/release (doc
    ~1564-1578). For each registry case's inputs: an input absent from the match
    set is ``skipped``; a present input whose RustFS archive fails the 사용 직전
    무결성 게이트 is ``failed`` (``source_integrity_mismatch``) and its group is
    quarantined + propagated (active → ``integrity_alert``, non-active
    ``validated`` → ``invalid``); a ``validator_version`` change reverts a prior
    ``passed`` group to ``not_started`` and marks referencing match sets needing
    re-validation. Requires the ``source_file_manager`` role.

    Only the C11~C17 registry cases are run-validatable. This endpoint performs
    the source-archive presence/integrity gate and returns whether each case is
    runnable; it does not execute the heavy prototype metric validators inline.
    The prototype metric binding remains a drift guard for the later validator
    execution path. A request for any non-augment case is rejected.
    """
    if req.cases is not None:
        invalid = tuple(c for c in req.cases if not is_augment_case(c))
        if invalid:
            raise InvalidInputError(
                "run-validation only supports the augment cases "
                f"{', '.join(AUGMENT_CASE_CODES)}; got unsupported: "
                f"{', '.join(invalid)}"
            )
    result = await client.run_consistency_validation(
        source_match_set_id,
        actor=ctx.actor,
        cases=req.cases,
    )
    await client.record_audit_event(
        action="consistency.run_validation",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome="failed" if result.failed_count else "succeeded",
        payload={
            "cases": list(req.cases) if req.cases else None,
            "skipped": result.skipped_count,
            "failed": result.failed_count,
            "runnable": result.runnable_count,
            "revalidated": list(result.revalidated_case_codes),
        },
        resource_type="source_match_set",
        resource_id=source_match_set_id,
        **_audit_request(request),
    )
    return result


@router.get(
    "/storage/rustfs/config",
    response_model=RustfsStorageConfig,
    response_model_exclude_none=True,
)
async def rustfs_storage_config() -> RustfsStorageConfig:
    return describe_rustfs_config(load_rustfs_config(get_settings()))


@router.patch(
    "/storage/rustfs/config",
    response_model=RustfsStorageConfig,
    response_model_exclude_none=True,
)
async def patch_rustfs_storage_config(req: RustfsStorageConfigPatch) -> RustfsStorageConfig:
    return save_rustfs_config(get_settings(), req)


@router.post(
    "/storage/rustfs/check",
    response_model=RustfsConnectionCheck,
    response_model_exclude_none=True,
)
async def check_rustfs_storage() -> RustfsConnectionCheck:
    settings = get_settings()
    config = require_enabled_rustfs(settings)
    return await RustfsClient(config).check()


@router.post(
    "/storage/rustfs/import-prefix",
    response_model=UploadSetStatus,
    response_model_exclude_none=True,
)
async def import_rustfs_prefix(req: RustfsImportPrefixRequest) -> UploadSetStatus:
    settings = get_settings()
    config = require_enabled_rustfs(settings)
    client = RustfsClient(config)
    return await import_rustfs_prefix_as_upload_set(
        settings.loader_data_dir,
        req,
        rustfs_client=client,
        rustfs_config=config,
    )


@router.post(
    "/storage/rustfs/sync-local",
    response_model=RustfsSyncLocalResult,
    response_model_exclude_none=True,
)
async def sync_local_to_rustfs_storage(req: RustfsSyncLocalRequest) -> RustfsSyncLocalResult:
    settings = get_settings()
    config = require_enabled_rustfs(settings)
    client = RustfsClient(config)
    await client.ensure_bucket()
    return await sync_local_to_rustfs(
        settings.loader_data_dir,
        req,
        rustfs_client=client,
        rustfs_config=config,
        allowed_roots=settings.rustfs_local_import_roots,
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


@router.get(
    "/backups/allowed-dirs",
    response_model=BackupAllowedDirs,
    response_model_exclude_none=True,
)
async def backup_allowed_dirs() -> BackupAllowedDirs:
    settings = get_settings()
    dirs = tuple(str(path) for path in settings.backup_allowed_dirs)
    return BackupAllowedDirs(dirs=dirs, default_dir=dirs[0] if dirs else None)


@router.get("/backups", response_model=list[BackupArtifact], response_model_exclude_none=True)
async def list_backups(
    limit: int = Query(default=50, ge=1, le=500),
    state: str | None = None,
    expiring_within_days: int | None = Query(default=None, ge=0),
    client: AsyncAddressClient = Depends(get_client),
) -> list[BackupArtifact]:
    settings = get_settings()
    # T-240 follow-up (Codex review): push the expiry cutoff into the query so LIMIT
    # applies to the already-filtered set. A Python filter after LIMIT would miss
    # soon-expiring backups that sit beyond the newest N.
    expires_before = (
        datetime.now(UTC) + timedelta(days=expiring_within_days)
        if expiring_within_days is not None
        else None
    )
    artifacts = await client.list_artifacts(
        limit=limit,
        artifact_type=BACKUP_ARTIFACT_TYPE,
        state=state,
        expires_before=expires_before,
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


@router.post(
    "/backups/{artifact_id}/copy",
    response_model=BackupCopyResult,
    response_model_exclude_none=True,
)
async def copy_backup(
    artifact_id: str,
    req: BackupCopyRequest,
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
) -> BackupCopyResult:
    """Copy a stored backup to another allowlisted directory (T-236).

    Streams the archive to ``target_dir`` (under ``backup_copy_targets`` / backup roots),
    re-hashes the copy and verifies it matches the source (mismatch → removed + error).
    A 3-2-1 guard so a single disk failure doesn't lose the backup. Filesystem only.
    """
    result = await client.copy_backup(artifact_id, target_dir=req.target_dir)
    await client.record_audit_event(
        action="db_backup.copy",
        outcome="succeeded",
        payload={"destination": result.destination_path, "verified": result.verified},
        resource_type="artifact",
        resource_id=artifact_id,
        **_audit_request(request),
    )
    return result


@router.post(
    "/backups/{artifact_id}/verify",
    response_model=BackupVerifyResult,
    response_model_exclude_none=True,
)
async def verify_backup(
    artifact_id: str,
    req: BackupVerifyRequest,
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
) -> BackupVerifyResult:
    """Non-destructively verify a stored backup (T-231).

    ``quick`` recomputes the archive sha256; ``deep`` also extracts and checks the
    internal ``checksums.sha256`` and ``manifest.json``. Corruption is reported as
    ``ok=False`` with ``errors`` rather than an exception, so an operator can probe
    bit rot without attempting a restore.
    """
    result = await client.verify_backup(artifact_id, mode=req.mode)
    await client.record_audit_event(
        action="db_backup.verify",
        outcome="succeeded" if result.ok else "failed",
        payload={"mode": req.mode, "ok": result.ok, "errors": list(result.errors)},
        resource_type="artifact",
        resource_id=artifact_id,
        **_audit_request(request),
    )
    return result


@router.post(
    "/backups/janitor/run",
    response_model=BackupRetentionResult,
    response_model_exclude_none=True,
)
async def run_backup_retention_janitor(
    req: BackupRetentionRunRequest,
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
) -> BackupRetentionResult:
    """Expire backups whose TTL passed, keeping ``pinned`` and the newest N (T-230).

    Archives are regenerable, so this removes the ``.tar.zst`` file and marks the
    artifact ``expired``. Idempotent and serialized by the ``BACKUP_JANITOR``
    advisory lock (concurrent calls return ``skipped_locked``). ``dry_run`` reports
    targets without touching files.
    """
    result = await client.run_backup_retention_janitor(
        dry_run=req.dry_run,
        keep_min_count=req.keep_min_count,
    )
    await client.record_audit_event(
        action="db_backup.retention_janitor",
        outcome="succeeded",
        payload={
            "dry_run": result.dry_run,
            "expired_count": result.expired_count,
            "failed_count": result.failed_count,
            "skipped_locked": result.skipped_locked,
        },
        resource_type="artifact",
        **_audit_request(request),
    )
    return result


@router.get(
    "/backups/scheduled/status",
    response_model=ScheduledBackupStatus,
    response_model_exclude_none=True,
)
async def scheduled_backup_status(
    client: AsyncAddressClient = Depends(get_client),
) -> ScheduledBackupStatus:
    """Report whether a scheduled backup is due now, last run, and next due (T-239).

    Read-only — does not enqueue anything. ``enabled`` reflects
    ``KTG_BACKUP_SCHEDULE_ENABLED``; ``next_due_at`` is ``last_scheduled_at + interval``.
    """
    return await client.scheduled_backup_status()


@router.post(
    "/backups/scheduled/run-due",
    response_model=ScheduledBackupRunResult,
    response_model_exclude_none=True,
)
async def run_due_scheduled_backup(
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
    queue: JobQueue = Depends(get_job_queue),
) -> ScheduledBackupRunResult:
    """Idempotent scheduled-backup trigger for an external cron (T-239).

    Enqueues exactly one ``retention_class='scheduled'`` backup, and only if scheduling
    is enabled and ``interval_hours`` has elapsed since the last scheduled run (no-op
    otherwise). The decide+enqueue critical section runs under the ``BACKUP_SCHEDULE``
    advisory lock so concurrent triggers cannot double-enqueue; a concurrent caller that
    cannot take the lock returns ``skipped_locked=True`` (still HTTP 200 for the cron).
    """
    key = AdvisoryLockKey.global_key(AdvisoryLockNamespace.BACKUP_SCHEDULE)
    try:
        async with cross_process_lock(client._engine(), key):
            status = await client.scheduled_backup_status()
            if not status.due:
                return ScheduledBackupRunResult(enqueued=False, status=status)
            payload = scheduled_backup_payload(get_settings())
            job_id = await queue.enqueue("db_backup", payload)
            await client.record_audit_event(
                action="db_backup.scheduled_run_due",
                outcome="started",
                payload={"job_id": job_id, "reason": status.reason},
                resource_type="load_job",
                resource_id=job_id,
                job_id=job_id,
                **_audit_request(request),
            )
            return ScheduledBackupRunResult(enqueued=True, job_id=job_id, status=status)
    except ConcurrentExecutionError:
        status = await client.scheduled_backup_status()
        return ScheduledBackupRunResult(enqueued=False, skipped_locked=True, status=status)


@router.post(
    "/restores/dry-run",
    response_model=RestoreDryRunResult,
    response_model_exclude_none=True,
)
async def restore_dry_run(
    req: RestoreCreateRequest,
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
) -> RestoreDryRunResult:
    """Preflight a restore without running pg_restore (T-232).

    Checks archive sha256 + internal checksums + manifest, target restorability, and
    version compatibility, returning ``can_restore`` + ``blockers`` + ``warnings``.
    Non-mutating — safe to run before a long restore.
    """
    result = await client.restore_dry_run(req)
    await client.record_audit_event(
        action="db_restore.dry_run",
        outcome="succeeded" if result.can_restore else "blocked",
        payload={
            "mode": req.mode,
            "can_restore": result.can_restore,
            "blockers": list(result.blockers),
        },
        resource_type="load_job",
        **_audit_request(request),
    )
    return result


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


@router.post(
    "/restores/hot-swap",
    response_model=RestoreHotSwapResult,
    response_model_exclude_none=True,
)
async def restore_hot_swap_execute(
    req: RestoreHotSwapExecuteRequest,
    request: Request,
    ctx: RequestContext = _DESTRUCTIVE_ADMIN,
    client: AsyncAddressClient = Depends(get_client),
) -> RestoreHotSwapResult:
    """Execute the ADR-036 rename hot-swap (T-241; ADR-036/T-058 plan → execution).

    Renames `current↔restore` in two `ALTER DATABASE RENAME` steps under the `HOT_SWAP`
    advisory lock, only with an active `restore` maintenance window + exact typed
    confirmation, then refreshes the engine pool, runs a post-swap smoke test, and
    **auto-rolls-back on smoke failure**. A concurrent second hot-swap fails fast (409).
    Records started/succeeded/failed/rolled_back audits + an active `serving_releases`
    row with `previous_release_id` lineage. Live serving DB swap → requires
    `destructive_admin`. Integration-tested in T-246.
    """
    return await client.execute_restore_hot_swap(
        req, actor=ctx.actor, audit_meta=_audit_request(request)
    )


@router.post(
    "/restores/hot-swap-rollback",
    response_model=RestoreHotSwapRollbackResult,
    response_model_exclude_none=True,
)
async def restore_hot_swap_rollback(
    req: RestoreHotSwapRollbackRequest,
    request: Request,
    ctx: RequestContext = _DESTRUCTIVE_ADMIN,
    client: AsyncAddressClient = Depends(get_client),
) -> RestoreHotSwapRollbackResult:
    """Manually roll back a completed hot-swap to the previous serving DB (T-264).

    Brings `previous_alias` back as the current DB (renaming the restored DB to
    `restore_database`) under the `HOT_SWAP` advisory lock, only with an active `restore`
    maintenance window + exact `rollback_confirmation`. **Rejected once `previous_alias`
    retention has dropped it.** Records a `rollback` serving release with
    previous/rollback_target lineage. Live serving DB swap → requires `destructive_admin`.
    Integration-tested in T-246.
    """
    return await client.execute_hot_swap_rollback(
        req, actor=ctx.actor, audit_meta=_audit_request(request)
    )


@router.post(
    "/restores/hot-swap-source-verify",
    response_model=RestoreSourceVerificationResult,
    response_model_exclude_none=True,
)
async def restore_hot_swap_source_verify(
    request: Request,
    ctx: RequestContext = _DESTRUCTIVE_ADMIN,
    client: AsyncAddressClient = Depends(get_client),
) -> RestoreSourceVerificationResult:
    """Run the ADR-036 rename hot-swap source verification (T-208, doc ~1896-1902).

    The second restore entrypoint in the source-verification matrix: invoked right
    after the operator completes the ALTER DATABASE rename + smoke test. Resolves
    the (now swapped-in) active snapshot's ``source_match_set_id`` and runs ONE
    source quick reconcile against RustFS object availability. If source objects
    are missing, serving stays up but a "재구성 불가" warning is surfaced. A legacy
    snapshot (no FK) only flags the legacy estimate. (The pg_restore manifest
    entrypoint runs the same verification automatically at restore finalize.)
    Restore is sensitive → requires ``destructive_admin``.
    """
    result = await client.verify_restore_source_hot_swap(actor=ctx.actor)
    await client.record_audit_event(
        action="source.restore_source_verify",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome=(
            "reconstruct_unavailable" if result.reconstruct_unavailable else "verified"
        ),
        payload={
            "entrypoint": result.entrypoint,
            "active_source_match_set_id": result.active_source_match_set_id,
            "mismatch_count": result.mismatch_count,
            "reconstruct_unavailable": result.reconstruct_unavailable,
        },
        resource_type="database",
        resource_id=result.active_source_match_set_id or "current",
        **_audit_request(request),
    )
    return result


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
    "/ops/releases/{serving_release_id}/rollback-plan",
    response_model=RollbackPlan,
    response_model_exclude_none=True,
)
async def rollback_plan(
    serving_release_id: str,
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
) -> RollbackPlan:
    plan = await client.rollback_plan(serving_release_id)
    await client.record_audit_event(
        action="serving_release.rollback_plan",
        outcome="succeeded",
        payload={"serving_release_id": serving_release_id},
        resource_type="serving_release",
        resource_id=serving_release_id,
        **_audit_request(request),
    )
    return plan


@router.post(
    "/ops/releases/{serving_release_id}/rollback",
    response_model=ServingReleaseRollbackResponse,
    response_model_exclude_none=True,
)
async def rollback_serving_release(
    serving_release_id: str,
    req: ServingReleaseRollbackRequest,
    request: Request,
    ctx: RequestContext = _DESTRUCTIVE_ADMIN,
    client: AsyncAddressClient = Depends(get_client),
) -> ServingReleaseRollbackResponse:
    """Roll a serving release back, swapping the source match set (doc #18, ~818).

    Requires ``destructive_admin`` + a ``typed_confirmation`` of
    ``ROLLBACK {serving_release_id}`` (the rollback-plan token). When the target snapshot
    carries a ``source_match_set_id`` the match set is swapped atomically under
    the match-activate lock (current active → ``retired``, target → ``active``),
    with the target's ``integrity_alert`` recomputed from a pre-rollback source
    quick reconcile. Legacy snapshots (no FK) stay ``알수없음/추정`` — no
    auto-promotion (ADR-049 #18).
    """
    if req.typed_confirmation != f"ROLLBACK {serving_release_id}":
        raise InvalidInputError(
            f"rollback requires typed_confirmation 'ROLLBACK {serving_release_id}'"
        )
    result = await client.rollback_serving_release(
        serving_release_id, actor=ctx.actor, reason=req.reason
    )
    await client.record_audit_event(
        action="serving_release.rollback",
        actor_type="ui",
        actor_id=ctx.actor,
        outcome=result.mode,
        payload={
            "mode": result.mode,
            "activated_match_set_id": result.activated_match_set_id,
            "retired_match_set_id": result.retired_match_set_id,
            "target_integrity_alert": result.target_integrity_alert,
        },
        resource_type="serving_release",
        resource_id=serving_release_id,
        **_audit_request(request),
    )
    return result


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


@router.post(
    "/ops/benchmark-artifacts",
    response_model=OpsArtifact,
    response_model_exclude_none=True,
    status_code=201,
)
async def register_benchmark_artifact(
    req: BenchmarkArtifactRegisterRequest,
    client: AsyncAddressClient = Depends(get_client),
) -> OpsArtifact:
    """T-265 (precursor to T-222): register a perf benchmark run (T-138/T-141/T-146) as a
    ``benchmark`` ops artifact so the Admin UI can surface latest-vs-baseline p95/p99
    read-only. List them via ``GET /ops/artifacts?artifact_type=benchmark``."""
    return await client.register_benchmark_artifact(req)


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
    "/ops/maintenance-windows/{maintenance_window_id}/end",
    response_model=MaintenanceWindow,
    response_model_exclude_none=True,
)
async def end_ops_maintenance_window(
    maintenance_window_id: str,
    req: MaintenanceWindowEnd,
    client: AsyncAddressClient = Depends(get_client),
) -> MaintenanceWindow:
    return await client.end_maintenance_window(maintenance_window_id, req)


@router.get(
    "/ops/table-stats",
    response_model=list[TableStatsSnapshot],
    response_model_exclude_none=True,
)
async def list_ops_table_stats(
    limit: int = Query(default=200, ge=1, le=1000),
    dataset_snapshot_id: str | None = None,
    client: AsyncAddressClient = Depends(get_client),
) -> list[TableStatsSnapshot]:
    return await client.list_table_stats_snapshots(
        limit=limit, dataset_snapshot_id=dataset_snapshot_id
    )


@router.post(
    "/ops/table-stats/capture",
    response_model=list[TableStatsSnapshot],
    response_model_exclude_none=True,
)
async def capture_ops_table_stats(
    dataset_snapshot_id: str | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    client: AsyncAddressClient = Depends(get_client),
) -> list[TableStatsSnapshot]:
    return await client.capture_table_stats_snapshots(
        dataset_snapshot_id=dataset_snapshot_id, limit=limit
    )


@router.get(
    "/ops/pg-stat-statements",
    response_model=list[PgStatStatementSnapshot],
    response_model_exclude_none=True,
)
async def list_ops_pg_stat_statements(
    limit: int = Query(default=20, ge=1, le=100),
    latest_only: bool = True,
    client: AsyncAddressClient = Depends(get_client),
) -> list[PgStatStatementSnapshot]:
    return await client.list_pg_stat_statement_snapshots(
        limit=limit,
        latest_only=latest_only,
    )


@router.post(
    "/ops/pg-stat-statements/capture",
    response_model=list[PgStatStatementSnapshot],
    response_model_exclude_none=True,
)
async def capture_ops_pg_stat_statements(
    limit: int = Query(default=20, ge=1, le=100),
    client: AsyncAddressClient = Depends(get_client),
) -> list[PgStatStatementSnapshot]:
    return await client.capture_pg_stat_statement_snapshots(limit=limit)


def backup_catalog_summary(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """Manifest-derived catalog fields for the backup list (T-240). Pure; defensive."""
    data = manifest or {}
    source_set = data.get("source_set")
    yyyymm = source_set.get("yyyymm_by_kind") if isinstance(source_set, dict) else None
    mixed = source_set.get("mixed_yyyymm") if isinstance(source_set, dict) else None
    inventory = data.get("source_inventory_verification")
    inventory_ok: bool | None = None
    if isinstance(inventory, dict) and not inventory.get("skipped"):
        ok = inventory.get("ok")
        inventory_ok = ok if isinstance(ok, bool) else None
    return {
        "source_set_yyyymm": yyyymm if isinstance(yyyymm, dict) else None,
        "source_set_mixed": mixed if isinstance(mixed, bool) else None,
        "source_inventory_ok": inventory_ok,
    }


def _backup_artifact_response(artifact: OpsArtifact, *, settings: Settings) -> BackupArtifact:
    download_url = None
    if artifact.state == "available" and artifact.sha256:
        download_url = backup_download_url(artifact, settings)
    return BackupArtifact(
        **artifact.model_dump(),
        download_url=download_url,
        **backup_catalog_summary(artifact.manifest),
    )


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


def _audit_request(request: Request) -> _AuditRequest:
    return {
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "request_id": request.headers.get("x-request-id"),
        "trace_id": request.headers.get("traceparent"),
    }


# --- Source upload-session helpers (T-203a) -------------------------------

#: Terminal session states for the SSE loop (mirrors jobs events' done set).
# SSE stream-end states reuse the canonical terminal set (single source of truth).
# Crucially this EXCLUDES ``failed_register`` (retryable in the same session — see
# register_upload_session) and the non-session state ``quarantined``, so the live
# stream does not end on a state the client treats as still in-progress (#176 review).
_UPLOAD_TERMINAL_STATES = TERMINAL_UPLOAD_SESSION_STATES


def _ensure_known_slot(session: UploadSessionStatus, slot_id: str) -> None:
    if slot_id not in {slot.slot for slot in session.file_slots}:
        msg = f"unknown upload slot '{slot_id}' for category {session.category}"
        raise NotFoundError(msg)


def _slot_object_key(prefix: str, session: UploadSessionStatus, slot_id: str) -> str:
    """Session-scoped staging key for a slot upload.

    Follows the t109 RustFS layout prefix (``source-files/<category>/<yyyymm>/
    <group_id>/...``). ``register`` (T-203b) assigns the final ``source_file_id``
    segment; the live upload keys by ``upload_session_id`` so a session can be
    aborted/replaced without touching a registered object.
    """
    return join_object_key(
        prefix,
        "source-files",
        session.category,
        session.user_yyyymm,
        session.source_file_group_id,
        session.upload_session_id,
        _safe_path_token(slot_id),
        "archive",
    )


async def _read_upload_body(request: Request, max_bytes: int) -> bytes:
    buffer = bytearray()
    async for chunk in request.stream():
        if not chunk:
            continue
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            msg = f"upload part exceeds {max_bytes} bytes limit"
            raise InvalidInputError(msg)
    return bytes(buffer)


def _coverage_structure_validation(
    *,
    category: str,
    group_kind: str,
    present_part_keys: tuple[str, ...],
) -> GroupValidation:
    """Coverage-level structure decision used at register time (T-203b).

    Register works storage-first and does not materialize archive internals, so
    it decides on slot *coverage* (which expected parts arrived). The dedicated
    ``POST /source-file-groups/{id}/validate`` re-runs the full member-level
    validator over materialized archives. Both share the pure decision logic in
    ``core.source_validation``.
    """
    from kortravelgeo.core.source_validation import validate_group_coverage

    return validate_group_coverage(
        category=category,
        group_kind=group_kind,
        present_part_keys=present_part_keys,
    )


def _progress_event(session: UploadSessionStatus) -> SourceUploadProgressEvent:
    total = session.expected_file_count or 1
    progress = min(session.uploaded_file_count / total, 1.0)
    received = sum(slot.received_bytes for slot in session.file_slots)
    return SourceUploadProgressEvent(
        upload_session_id=session.upload_session_id,
        state=session.state,
        stage=f"upload:{session.category}",
        progress=progress,
        uploaded_bytes=received,
        total_bytes=received,
        message=session.error_message,
    )
