"""Async library client entry point."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal, Self

from sqlalchemy.ext.asyncio import AsyncEngine

from .core.consistency_definitions import CASE_DEFINITIONS
from .core.geocoder import geocode as core_geocode
from .core.poboxer import pobox as core_pobox
from .core.reverse_geocoder import reverse_geocode as core_reverse_geocode
from .core.searcher import search as core_search
from .core.v2 import (
    geocode_v2_from_search,
    geocode_v2_from_v1,
    reverse_v2_from_v1,
    search_v2_from_v1,
)
from .core.zipcoder import zipcode as core_zipcode
from .dto.admin import (
    AuditEvent,
    CacheMetrics,
    ConsistencyBulkDecisionRequest,
    ConsistencyBulkDecisionResponse,
    ConsistencyCase,
    ConsistencyCaseDefinition,
    ConsistencyCaseSample,
    ConsistencyCaseSummary,
    ConsistencyReport,
    ConsistencyReportSummary,
    ConsistencySampleDecisionRequest,
    ConsistencySamplePage,
    ConsistencySampleRecheckResponse,
    DatasetSnapshot,
    ExplainRequest,
    ExplainResponse,
    LoadJobStatus,
    MaintenanceWindow,
    MaintenanceWindowCreate,
    MaintenanceWindowEnd,
    OpsArtifact,
    RestoreHotSwapPlan,
    RestoreHotSwapPlanRequest,
    RollbackPlan,
    ServingRelease,
    SourceSetDiscovery,
    SourceSetPlan,
    TableStat,
    TableStatsSnapshot,
)
from .dto.geocode import FallbackMode, GeocodeInput, GeocodeResponse
from .dto.pobox import PoboxInput, PoboxKind, PoboxResponse
from .dto.region import RegionHint
from .dto.reverse import ReverseResponse, ReverseType
from .dto.search import SearchResponse, SearchType
from .dto.v2 import (
    BBoxV2,
    GeocodeV2Input,
    GeocodeV2Response,
    ReverseV2Input,
    ReverseV2Response,
    SearchV2Input,
    SearchV2Response,
)
from .dto.zipcode import ZipcodeResponse
from .infra.admin_repo import AdminRepository
from .infra.batch import batch_children
from .infra.engine import make_async_engine
from .infra.external_api import ExternalGeocodeClient
from .infra.geocode_repo import GeocodeRepository
from .infra.hotswap import inspect_restore_hot_swap_plan
from .infra.pobox_repo import PoboxRepository
from .infra.reverse_repo import ReverseRepository
from .infra.search_repo import SearchRepository
from .infra.source_set import (
    build_full_load_source_set_plan,
    discover_load_sources,
)
from .infra.uploads import UploadSetCleanupResult, cleanup_upload_sets
from .infra.zip_repo import ZipRepository
from .settings import Settings, get_settings


class AsyncAddressClient:
    """Async-only client facade for address geocoding operations."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        pg_dsn: str | None = None,
        engine: AsyncEngine | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if pg_dsn is not None:
            self.settings = self.settings.model_copy(update={"pg_dsn": pg_dsn})
        self.engine: AsyncEngine | None = engine
        self._owns_engine = engine is None
        self.closed = True

    async def __aenter__(self) -> Self:
        if self.engine is None:
            self.engine = make_async_engine(self.settings)
        self.closed = False
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self.engine is not None and self._owns_engine:
            await self.engine.dispose()
        self.closed = True

    def _engine(self) -> AsyncEngine:
        if self.engine is None:
            self.engine = make_async_engine(self.settings)
        return self.engine

    @staticmethod
    def _region_hint(sig_cd: str | None, bjd_cd: str | None) -> RegionHint | None:
        if sig_cd is None and bjd_cd is None:
            return None
        return RegionHint(sig_cd=sig_cd, bjd_cd=bjd_cd)

    async def geocode(
        self,
        address: str,
        *,
        type: Literal["road", "parcel"] = "road",
        crs: str = "EPSG:4326",
        refine: bool = True,
        simple: bool = False,
        fallback: FallbackMode = "local_only",
        sig_cd: str | None = None,
        bjd_cd: str | None = None,
    ) -> GeocodeResponse:
        inp = GeocodeInput(
            address=address,
            type=type,
            crs=crs,
            refine=refine,
            simple=simple,
            fallback=fallback,
        )
        region_hint = self._region_hint(sig_cd, bjd_cd)
        response = await core_geocode(
            GeocodeRepository(self._engine()),
            inp,
            region_hint=region_hint,
        )
        if fallback != "api" or response.status != "NOT_FOUND" or region_hint is not None:
            return response
        external = await ExternalGeocodeClient(self.settings).geocode(inp)
        return external or response

    async def geocode_many(
        self,
        addresses: Iterable[str],
        *,
        concurrency: int = 8,
        type: Literal["road", "parcel"] = "road",
    ) -> tuple[GeocodeResponse, ...]:
        semaphore = asyncio.Semaphore(concurrency)

        async def one(address: str) -> GeocodeResponse:
            async with semaphore:
                return await self.geocode(address, type=type)

        return tuple(await asyncio.gather(*(one(address) for address in addresses)))

    async def geocode_v2(
        self,
        *,
        query: str | None = None,
        road_address: str | None = None,
        jibun_address: str | None = None,
        keyword: str | None = None,
        sig_cd: str | None = None,
        bjd_cd: str | None = None,
        bbox: BBoxV2 | None = None,
        limit: int = 10,
        fallback: Literal["none", "api"] = "none",
    ) -> GeocodeV2Response:
        inp = GeocodeV2Input(
            query=query,
            road_address=road_address,
            jibun_address=jibun_address,
            keyword=keyword,
            sig_cd=sig_cd,
            bjd_cd=bjd_cd,
            bbox=bbox,
            limit=limit,
            fallback=fallback,
        )
        if keyword and not any((query, road_address, jibun_address)):
            search_response = await self.search_v2(
                query=keyword,
                type="place",
                size=limit,
                sig_cd=sig_cd,
                bjd_cd=bjd_cd,
                bbox=bbox,
            )
            return geocode_v2_from_search(inp, search_response)

        address = road_address or jibun_address or query or keyword
        assert address is not None
        response = await self.geocode(
            address,
            type="parcel" if jibun_address and not road_address else "road",
            fallback="api" if fallback == "api" else "local_only",
            sig_cd=sig_cd,
            bjd_cd=bjd_cd,
        )
        return geocode_v2_from_v1(inp, response)

    async def reverse_geocode(
        self,
        x: float,
        y: float,
        *,
        crs: str = "EPSG:4326",
        type: ReverseType = "both",
        zipcode: bool = True,
        radius_m: int | None = None,
        sig_cd: str | None = None,
        bjd_cd: str | None = None,
    ) -> ReverseResponse:
        from .dto.common import Point
        from .dto.reverse import ReverseInput

        inp = ReverseInput(
            point=Point(x=x, y=y),
            crs=crs,
            type=type,
            zipcode=zipcode,
            radius_m=radius_m or self.settings.api_default_radius_m,
        )
        return await core_reverse_geocode(
            ReverseRepository(self._engine()),
            inp,
            region_hint=self._region_hint(sig_cd, bjd_cd),
        )

    async def reverse_v2(
        self,
        lon: float,
        lat: float,
        *,
        crs: str = "EPSG:4326",
        include_region: bool = True,
        include_zipcode: bool = True,
        radius_m: int | None = None,
        sig_cd: str | None = None,
        bjd_cd: str | None = None,
    ) -> ReverseV2Response:
        inp = ReverseV2Input(
            lon=lon,
            lat=lat,
            crs=crs,
            include_region=include_region,
            include_zipcode=include_zipcode,
            radius_m=radius_m or self.settings.api_default_radius_m,
            sig_cd=sig_cd,
            bjd_cd=bjd_cd,
        )
        response = await self.reverse_geocode(
            lon,
            lat,
            crs=crs,
            zipcode=include_zipcode,
            radius_m=inp.radius_m,
            sig_cd=sig_cd,
            bjd_cd=bjd_cd,
        )
        return reverse_v2_from_v1(inp, response)

    async def search(
        self,
        query: str,
        *,
        type: SearchType = "address",
        page: int = 1,
        size: int = 10,
        crs: str = "EPSG:4326",
        sig_cd: str | None = None,
        bjd_cd: str | None = None,
    ) -> SearchResponse:
        from .dto.search import SearchInput

        inp = SearchInput(query=query, type=type, page=page, size=size, crs=crs)
        return await core_search(
            SearchRepository(self._engine()),
            inp,
            region_hint=self._region_hint(sig_cd, bjd_cd),
        )

    async def search_v2(
        self,
        *,
        query: str,
        type: Literal["address", "place", "district", "road", "category"] = "address",
        category_group_code: str | None = None,
        page: int = 1,
        size: int = 10,
        sig_cd: str | None = None,
        bjd_cd: str | None = None,
        bbox: BBoxV2 | None = None,
    ) -> SearchV2Response:
        inp = SearchV2Input(
            query=query,
            type=type,
            category_group_code=category_group_code,
            page=page,
            size=size,
            sig_cd=sig_cd,
            bjd_cd=bjd_cd,
            bbox=bbox,
        )
        response = await self.search(
            query,
            type="place" if type == "category" else type,
            page=page,
            size=size,
            sig_cd=sig_cd,
            bjd_cd=bjd_cd,
        )
        return search_v2_from_v1(inp, response)

    async def zipcode(
        self,
        *,
        address: str | None = None,
        point: tuple[float, float] | None = None,
        bd_mgt_sn: str | None = None,
        include_bulk: bool = True,
    ) -> ZipcodeResponse:
        from .dto.common import Point
        from .dto.zipcode import ZipcodeInput

        inp = ZipcodeInput(
            address=address,
            point=Point(x=point[0], y=point[1]) if point else None,
            bd_mgt_sn=bd_mgt_sn,
            include_bulk=include_bulk,
        )
        return await core_zipcode(ZipRepository(self._engine()), inp)

    async def pobox(
        self,
        *,
        query: str | None = None,
        si_nm: str | None = None,
        sgg_nm: str | None = None,
        kind: PoboxKind = "ALL",
        page: int = 1,
        size: int = 10,
    ) -> PoboxResponse:
        inp = PoboxInput(query=query, si_nm=si_nm, sgg_nm=sgg_nm, kind=kind, page=page, size=size)
        return await core_pobox(PoboxRepository(self._engine()), inp)

    async def load_status(self, job_id: str) -> LoadJobStatus:
        row = await AdminRepository(self._engine()).get_load_job(job_id)
        if row is None:
            from .exceptions import NotFoundError

            raise NotFoundError(f"load job not found: {job_id}")
        return _load_job_status(row)

    async def list_load_jobs(
        self,
        *,
        kind: str | None = None,
        state: str | None = None,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[LoadJobStatus]:
        rows = await AdminRepository(self._engine()).list_load_jobs(
            kind=kind,
            state=state,
            limit=limit,
            since=since,
        )
        return [_load_job_status(row) for row in rows]

    async def table_stats(self, *, limit: int = 200) -> list[TableStat]:
        return await AdminRepository(self._engine()).table_stats(limit=limit)

    async def explain(
        self,
        sql: str,
        *,
        analyze: bool = False,
        buffers: bool = False,
    ) -> ExplainResponse:
        req = ExplainRequest(sql=sql, analyze=analyze, buffers=buffers)
        plan = await AdminRepository(self._engine()).explain(
            req.sql,
            analyze=req.analyze,
            buffers=req.buffers,
            timeout_ms=self.settings.api_explain_timeout_ms,
        )
        return ExplainResponse(plan=plan)

    async def cache_metrics(self) -> CacheMetrics:
        return await AdminRepository(self._engine()).cache_metrics(
            enabled=self.settings.cache_enabled,
        )

    async def recent_logs(self, *, limit: int = 200) -> list[str]:
        return await AdminRepository(self._engine()).recent_log_lines(limit=limit)

    async def load_job_metric_counts(self) -> list[tuple[str, str, int]]:
        return await AdminRepository(self._engine()).load_job_metric_counts()

    async def record_audit_event(
        self,
        *,
        action: str,
        actor_type: str = "api",
        outcome: str = "started",
        payload: dict[str, Any] | None = None,
        actor_id: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        job_id: str | None = None,
        error_code: str | None = None,
    ) -> AuditEvent:
        return await AdminRepository(self._engine()).record_audit_event(
            action=action,
            actor_type=actor_type,
            outcome=outcome,
            payload=payload,
            actor_id=actor_id,
            client_ip=client_ip,
            user_agent=user_agent,
            request_id=request_id,
            trace_id=trace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            job_id=job_id,
            error_code=error_code,
        )

    async def list_audit_events(
        self,
        *,
        limit: int = 50,
        action: str | None = None,
        outcome: str | None = None,
    ) -> list[AuditEvent]:
        return await AdminRepository(self._engine()).list_audit_events(
            limit=limit,
            action=action,
            outcome=outcome,
        )

    async def list_dataset_snapshots(
        self,
        *,
        limit: int = 20,
        state: str | None = None,
    ) -> list[DatasetSnapshot]:
        return await AdminRepository(self._engine()).list_dataset_snapshots(
            limit=limit,
            state=state,
        )

    async def list_serving_releases(
        self,
        *,
        limit: int = 20,
        state: str | None = None,
    ) -> list[ServingRelease]:
        return await AdminRepository(self._engine()).list_serving_releases(
            limit=limit,
            state=state,
        )

    async def rollback_plan(self, release_id: str) -> RollbackPlan:
        plan = await AdminRepository(self._engine()).rollback_plan(release_id)
        if plan is None:
            from .exceptions import NotFoundError

            raise NotFoundError(f"serving release not found: {release_id}")
        return plan

    async def list_artifacts(
        self,
        *,
        limit: int = 50,
        artifact_type: str | None = None,
        state: str | None = None,
    ) -> list[OpsArtifact]:
        return await AdminRepository(self._engine()).list_artifacts(
            limit=limit,
            artifact_type=artifact_type,
            state=state,
        )

    async def get_artifact(self, artifact_id: str) -> OpsArtifact:
        artifact = await AdminRepository(self._engine()).get_artifact(artifact_id)
        if artifact is None:
            from .exceptions import NotFoundError

            raise NotFoundError(f"artifact not found: {artifact_id}")
        return artifact

    async def delete_artifact(self, artifact_id: str) -> OpsArtifact:
        artifact = await AdminRepository(self._engine()).mark_artifact_deleted(artifact_id)
        if artifact is None:
            from .exceptions import NotFoundError

            raise NotFoundError(f"artifact not found: {artifact_id}")
        return artifact

    async def restore_hot_swap_plan(
        self,
        req: RestoreHotSwapPlanRequest,
    ) -> RestoreHotSwapPlan:
        return await inspect_restore_hot_swap_plan(self.settings, req)

    async def list_maintenance_windows(
        self,
        *,
        limit: int = 50,
        state: str | None = None,
    ) -> list[MaintenanceWindow]:
        return await AdminRepository(self._engine()).list_maintenance_windows(
            limit=limit,
            state=state,
        )

    async def create_maintenance_window(
        self,
        req: MaintenanceWindowCreate,
    ) -> MaintenanceWindow:
        window = await AdminRepository(self._engine()).create_maintenance_window(req)
        await self.record_audit_event(
            action="maintenance_window.create",
            outcome="started",
            payload=req.model_dump(exclude={"confirmation"}),
            resource_type="maintenance_window",
            resource_id=window.window_id,
        )
        return window

    async def end_maintenance_window(
        self,
        window_id: str,
        req: MaintenanceWindowEnd,
    ) -> MaintenanceWindow:
        window = await AdminRepository(self._engine()).end_maintenance_window(
            window_id=window_id,
            confirmation=req.confirmation,
            closed_by_job_id=req.closed_by_job_id,
        )
        if window is None:
            from .exceptions import NotFoundError

            raise NotFoundError(f"active maintenance window not found: {window_id}")
        await self.record_audit_event(
            action="maintenance_window.end",
            outcome="succeeded",
            payload=req.model_dump(exclude={"confirmation"}),
            resource_type="maintenance_window",
            resource_id=window.window_id,
        )
        return window

    async def list_table_stats_snapshots(
        self,
        *,
        limit: int = 200,
        snapshot_id: str | None = None,
    ) -> list[TableStatsSnapshot]:
        return await AdminRepository(self._engine()).list_table_stats_snapshots(
            limit=limit,
            snapshot_id=snapshot_id,
        )

    async def capture_table_stats_snapshots(
        self,
        *,
        snapshot_id: str | None = None,
        limit: int = 500,
        skip_if_locked: bool = False,
    ) -> list[TableStatsSnapshot]:
        return await AdminRepository(self._engine()).capture_table_stats_snapshots(
            snapshot_id=snapshot_id,
            limit=limit,
            skip_if_locked=skip_if_locked,
        )

    async def cleanup_upload_sets(
        self,
        *,
        ttl_days: int | None = None,
        active_grace_minutes: int | None = None,
        dry_run: bool = False,
    ) -> UploadSetCleanupResult:
        repo = AdminRepository(self._engine())
        active_refs = await repo.active_upload_set_ids()
        return cleanup_upload_sets(
            self.settings.loader_data_dir,
            ttl_days=ttl_days or self.settings.upload_set_ttl_days,
            active_grace_minutes=(
                active_grace_minutes or self.settings.upload_set_active_grace_minutes
            ),
            active_upload_set_ids=active_refs,
            dry_run=dry_run,
        )

    async def discover_load_sources(
        self,
        root_path: str,
        *,
        include_optional: bool = True,
    ) -> SourceSetDiscovery:
        from pathlib import Path

        return discover_load_sources(Path(root_path), include_optional=include_optional)

    async def build_full_load_source_set_plan(
        self,
        *,
        root_path: str | None = None,
        versions: dict[str, str] | None = None,
        explicit_paths: dict[str, str] | None = None,
        include_optional: bool = True,
        allow_mixed_yyyymm: bool = False,
        confirmation_token: str | None = None,
        acknowledged_by: str = "api",
    ) -> SourceSetPlan:
        from pathlib import Path

        return build_full_load_source_set_plan(
            root_path=Path(root_path) if root_path else None,
            versions=versions,
            explicit_paths=explicit_paths,
            include_optional=include_optional,
            allow_mixed_yyyymm=allow_mixed_yyyymm,
            confirmation_token=confirmation_token,
            acknowledged_by=acknowledged_by,
        )

    async def submit_full_load_source_set(self, plan: SourceSetPlan) -> LoadJobStatus:
        return await self.submit_load("full_load_batch", plan.batch_payload)

    async def submit_load(self, kind: str, payload: dict[str, Any]) -> LoadJobStatus:
        repo = AdminRepository(self._engine())
        if kind == "full_load_batch":
            row = await repo.insert_load_batch(
                payload=payload,
                children=batch_children(payload),
            )
        else:
            row = await repo.insert_load_job(kind=kind, payload=payload)
        return _load_job_status(row)

    async def cancel_load(self, job_id: str) -> LoadJobStatus:
        row = await AdminRepository(self._engine()).cancel_load_job(job_id)
        if row is None:
            from .exceptions import NotFoundError

            raise NotFoundError(f"cancellable load job not found: {job_id}")
        return _load_job_status(row)

    async def run_consistency_check(
        self,
        *,
        scope: Literal["full", "sido", "recent"] = "full",
        sido: str | None = None,
        recent_days: int = 7,
        cases: tuple[str, ...] | None = None,
    ) -> LoadJobStatus:
        return await self.submit_load(
            "consistency_check",
            {"scope": scope, "sido": sido, "recent_days": recent_days, "cases": cases},
        )

    async def consistency_report(self, report_id: str) -> ConsistencyReport:
        row = await AdminRepository(self._engine()).consistency_report(report_id)
        if row is None:
            from .exceptions import NotFoundError

            raise NotFoundError(f"consistency report not found: {report_id}")
        return _consistency_report(row)

    async def list_consistency_reports(
        self,
        *,
        limit: int = 20,
        severity_at_least: Literal["INFO", "WARN", "ERROR"] | None = None,
    ) -> list[ConsistencyReportSummary]:
        rows = await AdminRepository(self._engine()).list_consistency_reports(
            limit=limit,
            severity_at_least=severity_at_least,
        )
        return [
            ConsistencyReportSummary(
                report_id=row.report_id,
                scope=row.scope,
                severity_max=row.severity_max,
                source_set=row.source_set,
                started_at=row.started_at,
                finished_at=row.finished_at,
                generated_by=row.generated_by,
            )
            for row in rows
        ]

    async def consistency_case_definitions(self) -> tuple[ConsistencyCaseDefinition, ...]:
        return CASE_DEFINITIONS

    async def list_consistency_case_samples(
        self,
        *,
        report_id: str,
        case_code: str,
        severity: str | None = None,
        decision: str | None = None,
        sig_cd: str | None = None,
        bjd_cd: str | None = None,
        bd_mgt_sn: str | None = None,
        reason_code: str | None = None,
        source_kind: str | None = None,
        source_yyyymm: str | None = None,
        min_distance_m: float | None = None,
        max_distance_m: float | None = None,
        order_by: str = "sample_rank",
        desc: bool = False,
        page: int = 1,
        page_size: int = 100,
    ) -> ConsistencySamplePage:
        repo = AdminRepository(self._engine())
        page_result = await repo.list_consistency_case_samples(
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
        if page_result.total == 0:
            report_exists = await repo.consistency_report(report_id)
            if report_exists is None:
                from .exceptions import NotFoundError

                raise NotFoundError(f"consistency report not found: {report_id}")
        return page_result

    async def consistency_case_summary(
        self,
        *,
        report_id: str,
        case_code: str,
    ) -> ConsistencyCaseSummary:
        if await AdminRepository(self._engine()).consistency_report(report_id) is None:
            from .exceptions import NotFoundError

            raise NotFoundError(f"consistency report not found: {report_id}")
        return await AdminRepository(self._engine()).consistency_case_summary(
            report_id=report_id,
            case_code=case_code,
        )

    async def update_consistency_sample_decision(
        self,
        *,
        report_id: str,
        case_code: str,
        sample_id: str,
        req: ConsistencySampleDecisionRequest,
        actor_type: str = "api",
        client_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> ConsistencyCaseSample:
        row = await AdminRepository(self._engine()).update_consistency_sample_decision(
            report_id=report_id,
            case_code=case_code,
            sample_id=sample_id,
            req=req,
            actor_type=actor_type,
            client_ip=client_ip,
            user_agent=user_agent,
            request_id=request_id,
            trace_id=trace_id,
        )
        if row is None:
            from .exceptions import NotFoundError

            raise NotFoundError(f"consistency sample not found: {sample_id}")
        return row

    async def bulk_update_consistency_sample_decisions(
        self,
        *,
        report_id: str,
        case_code: str,
        req: ConsistencyBulkDecisionRequest,
        actor_type: str = "api",
        client_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> ConsistencyBulkDecisionResponse:
        return await AdminRepository(self._engine()).bulk_update_consistency_sample_decisions(
            report_id=report_id,
            case_code=case_code,
            req=req,
            actor_type=actor_type,
            client_ip=client_ip,
            user_agent=user_agent,
            request_id=request_id,
            trace_id=trace_id,
        )

    async def recheck_consistency_sample(
        self,
        *,
        report_id: str,
        case_code: str,
        sample_id: str,
    ) -> ConsistencySampleRecheckResponse:
        row = await AdminRepository(self._engine()).recheck_consistency_sample(
            report_id=report_id,
            case_code=case_code,
            sample_id=sample_id,
        )
        if row is None:
            from .exceptions import NotFoundError

            raise NotFoundError(f"consistency sample not found: {sample_id}")
        return row


def open_client(
    settings: Settings | None = None,
    *,
    pg_dsn: str | None = None,
) -> AsyncAddressClient:
    return AsyncAddressClient(settings, pg_dsn=pg_dsn)


def _load_job_status(row: Any) -> LoadJobStatus:
    return LoadJobStatus(
        job_id=row.job_id,
        kind=row.kind,
        state=row.state,
        load_batch_id=row.load_batch_id,
        parent_job_id=row.parent_job_id,
        progress=row.progress,
        current_stage=row.current_stage,
        source_yyyymm=row.source_yyyymm,
        source_set=row.source_set,
        started_at=row.started_at,
        finished_at=row.finished_at,
        heartbeat_at=row.heartbeat_at,
        error_message=row.error_message,
        log_tail=row.log_tail,
        payload_summary=row.payload_summary,
    )


def _consistency_report(row: Any) -> ConsistencyReport:
    return ConsistencyReport(
        report_id=row.report_id,
        scope=row.scope,
        severity_max=row.severity_max,
        source_set=row.source_set,
        started_at=row.started_at,
        finished_at=row.finished_at,
        generated_by=row.generated_by,
        cases=tuple(
            ConsistencyCase(
                code=case.code,
                name=case.name,
                severity=case.severity,
                count=case.count,
                ratio=case.ratio,
                threshold=case.threshold,
                metric=case.metric,
                sample=case.sample,
                note=case.note,
            )
            for case in row.cases
        ),
    )
