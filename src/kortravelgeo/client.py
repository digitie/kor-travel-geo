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
from .core.source_categories import CATEGORY_CATALOG
from .core.source_validation import GroupValidation
from .core.v2 import (
    geocode_v2_from_geometry_lookups,
    geocode_v2_from_search,
    geocode_v2_from_v1,
    reverse_v2_from_v1,
    search_v2_from_v1,
    with_candidate_geometry,
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
    TableStat,
    TableStatsSnapshot,
)
from .dto.geocode import FallbackMode, GeocodeInput, GeocodeResponse
from .dto.pobox import PoboxInput, PoboxKind, PoboxResponse
from .dto.region import RegionHint
from .dto.reverse import ReverseResponse, ReverseType
from .dto.search import SearchResponse, SearchType
from .dto.source import (
    GroupValidationResult,
    RegisterResponse,
    SourceFileCategoryInfo,
    SourceGroupRestoreResponse,
    SourceGroupSoftDeleteResponse,
    SourceJanitorRunResponse,
    UploadSessionCreateRequest,
    UploadSessionPartStatus,
    UploadSessionStatus,
)
from .dto.v2 import (
    BBoxV2,
    GeocodeV2Input,
    GeocodeV2Response,
    RegionsWithinRadiusInput,
    RegionsWithinRadiusResponse,
    RegionWithinRadiusItem,
    RegionWithinRadiusLevel,
    ReverseV2Input,
    ReverseV2Response,
    SearchV2Input,
    SearchV2Response,
)
from .dto.zipcode import ZipcodeResponse
from .exceptions import InvalidAddressError
from .infra.admin_repo import AdminRepository
from .infra.batch import batch_children
from .infra.engine import make_async_engine
from .infra.external_api import ExternalGeocodeClient
from .infra.geocode_repo import GeocodeRepository
from .infra.geometry_repo import GeometryRepository
from .infra.hotswap import inspect_restore_hot_swap_plan
from .infra.pobox_repo import PoboxRepository
from .infra.reverse_repo import ReverseRepository
from .infra.search_repo import SearchRepository
from .infra.source_group_service import (
    RegisterContext,
    SourceGroupRegistrar,
)
from .infra.source_upload_repo import (
    SessionCreateResult,
    SourceUploadSessionRepository,
)
from .infra.zip_repo import ZipRepository
from .settings import Settings, get_settings


def _metadata_str(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


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
        query: str | None = None,
        *,
        road_address: str | None = None,
        jibun_address: str | None = None,
        keyword: str | None = None,
        sig_cd: str | None = None,
        bjd_cd: str | None = None,
        bbox: BBoxV2 | None = None,
        limit: int = 10,
        fallback: Literal["none", "api"] = "none",
        include_geometry: bool = False,
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
            include_geometry=include_geometry,
        )
        if keyword and not any((query, road_address, jibun_address)):
            search_response = await self.search(
                query=keyword,
                type="place",
                size=limit,
                sig_cd=sig_cd,
                bjd_cd=bjd_cd,
                bbox=bbox,
            )
            return await self._with_geocode_geometries(
                geocode_v2_from_search(inp, search_response)
            )

        address = road_address or jibun_address or query or keyword
        assert address is not None
        try:
            response = await self._geocode_v1(
                address,
                type="parcel" if jibun_address and not road_address else "road",
                fallback="api" if fallback == "api" else "local_only",
                sig_cd=sig_cd,
                bjd_cd=bjd_cd,
            )
        except InvalidAddressError:
            return await self._geocode_road_or_region_candidates(inp, address)
        converted = geocode_v2_from_v1(inp, response)
        if response.status == "OK":
            return await self._with_geocode_geometries(converted)
        fallback_response = await self._geocode_road_or_region_candidates(inp, address)
        return fallback_response if fallback_response.status == "OK" else converted

    async def _geocode_road_or_region_candidates(
        self,
        inp: GeocodeV2Input,
        address: str,
    ) -> GeocodeV2Response:
        geometry_repo = GeometryRepository(self._engine())
        road_rows = await geometry_repo.road_geometries(
            address,
            limit=inp.limit,
            region_hint=inp.region_hint,
        )
        if road_rows:
            return geocode_v2_from_geometry_lookups(inp, road_rows)
        search_response = await self.search(
            query=address,
            type="district",
            size=inp.limit,
            sig_cd=inp.sig_cd,
            bjd_cd=inp.bjd_cd,
            bbox=inp.bbox,
        )
        return await self._with_geocode_geometries(geocode_v2_from_search(inp, search_response))

    async def _with_geocode_geometries(
        self,
        response: GeocodeV2Response,
    ) -> GeocodeV2Response:
        if not response.input.include_geometry or not response.candidates:
            return response
        geometry_repo = GeometryRepository(self._engine())
        enriched = []
        for candidate in response.candidates:
            if candidate.source != "local":
                enriched.append(candidate)
                continue
            if candidate.match_kind == "region" and candidate.region is not None:
                geometry = await geometry_repo.region_geometry(
                    sig_cd=candidate.region.sig_cd,
                    bjd_cd=candidate.region.bjd_cd,
                )
            elif candidate.match_kind in {"road", "parcel"}:
                geometry = await geometry_repo.building_geometry(
                    bd_mgt_sn=_metadata_str(candidate.metadata.get("bd_mgt_sn")),
                    rncode_full=_metadata_str(
                        candidate.metadata.get("rncode_full")
                        or (candidate.address.road_name_code if candidate.address else None)
                    ),
                    bjd_cd=_metadata_str(
                        candidate.metadata.get("bjd_cd")
                        or (candidate.region.bjd_cd if candidate.region else None)
                    ),
                    detail=_metadata_str(candidate.metadata.get("detail")),
                )
            else:
                geometry = None
            enriched.append(
                with_candidate_geometry(
                    candidate,
                    geometry,
                    include_geometry=response.input.include_geometry,
                )
            )
        return response.model_copy(update={"candidates": tuple(enriched)})

    async def _geocode_v1(
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
        queries: Iterable[str],
        *,
        concurrency: int = 8,
    ) -> tuple[GeocodeV2Response, ...]:
        semaphore = asyncio.Semaphore(concurrency)

        async def one(query: str) -> GeocodeV2Response:
            async with semaphore:
                return await self.geocode(query=query)

        return tuple(await asyncio.gather(*(one(query) for query in queries)))

    async def _reverse_geocode_v1(
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

    async def reverse(
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
        response = await self._reverse_geocode_v1(
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
        response = await self._search_v1(
            query,
            type="place" if type == "category" else type,
            page=page,
            size=size,
            sig_cd=sig_cd,
            bjd_cd=bjd_cd,
        )
        return search_v2_from_v1(inp, response)

    async def regions_within_radius(
        self,
        *,
        lon: float,
        lat: float,
        radius_km: float = 3.0,
        levels: tuple[RegionWithinRadiusLevel, ...] = ("sigungu", "emd"),
    ) -> RegionsWithinRadiusResponse:
        inp = RegionsWithinRadiusInput(
            lon=lon,
            lat=lat,
            radius_km=radius_km,
            levels=levels,
        )
        regions = await GeometryRepository(self._engine()).regions_within_radius(
            lon=inp.lon,
            lat=inp.lat,
            radius_km=inp.radius_km,
            levels=inp.levels,
        )
        empty: tuple[RegionWithinRadiusItem, ...] = ()
        return RegionsWithinRadiusResponse(
            center=inp.center,
            radius_km=inp.radius_km,
            sido=regions.get("sido", empty),
            sigungu=regions.get("sigungu", empty),
            emd=regions.get("emd", empty),
        )

    async def _search_v1(
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

    # --- Source upload sessions (T-203a) ----------------------------------

    async def create_upload_session(
        self,
        req: UploadSessionCreateRequest,
        *,
        bucket: str | None = None,
        prefix: str | None = None,
        created_by: str | None = None,
    ) -> SessionCreateResult:
        """Create a session, or return the existing non-terminal one (conflict).

        The caller (admin router) maps ``result.conflict`` to a ``409`` body.
        """
        return await SourceUploadSessionRepository(self._engine()).create_session(
            req,
            bucket=bucket,
            prefix=prefix,
            created_by=created_by,
        )

    async def get_upload_session(self, session_id: str) -> UploadSessionStatus:
        session = await SourceUploadSessionRepository(self._engine()).get_session(session_id)
        if session is None:
            from .exceptions import NotFoundError

            raise NotFoundError(f"upload session not found: {session_id}")
        return session

    async def list_upload_sessions(
        self,
        *,
        state: str | None = None,
        category: str | None = None,
        user_yyyymm: str | None = None,
        created_by: str | None = None,
        limit: int = 50,
    ) -> list[UploadSessionStatus]:
        return await SourceUploadSessionRepository(self._engine()).list_sessions(
            state=state,
            category=category,
            user_yyyymm=user_yyyymm,
            created_by=created_by,
            limit=limit,
        )

    async def update_upload_session_state(
        self,
        session_id: str,
        *,
        state: str,
        error_message: str | None = None,
    ) -> UploadSessionStatus:
        session = await SourceUploadSessionRepository(self._engine()).update_state(
            session_id, state=state, error_message=error_message
        )
        if session is None:
            from .exceptions import NotFoundError

            raise NotFoundError(f"upload session not found: {session_id}")
        return session

    async def replace_upload_session_slot(
        self,
        session_id: str,
        *,
        part_key: str,
    ) -> UploadSessionStatus:
        await SourceUploadSessionRepository(self._engine()).replace_slot(
            session_id, part_key=part_key
        )
        return await self.get_upload_session(session_id)

    async def record_upload_session_part(
        self,
        session_id: str,
        *,
        part_key: str,
        part_number: int,
        multipart_upload_id: str | None = None,
        part_etag: str | None = None,
        part_sha256: str | None = None,
        received_bytes: int = 0,
        completed: bool = False,
    ) -> UploadSessionPartStatus:
        return await SourceUploadSessionRepository(self._engine()).record_part(
            session_id,
            part_key=part_key,
            part_number=part_number,
            multipart_upload_id=multipart_upload_id,
            part_etag=part_etag,
            part_sha256=part_sha256,
            received_bytes=received_bytes,
            completed=completed,
        )

    async def upload_session_slot_parts(
        self,
        session_id: str,
        *,
        part_key: str,
    ) -> tuple[UploadSessionPartStatus, ...]:
        return await SourceUploadSessionRepository(self._engine()).slot_parts(
            session_id, part_key=part_key
        )

    async def register_source_group(
        self,
        *,
        session_id: str,
        contexts: tuple[RegisterContext, ...],
        structure_validation: GroupValidation,
        storage_kind: str,
        bucket: str | None,
        actor: str | None,
        yyyymm_mismatch_ack: bool,
        display_name: str | None = None,
    ) -> RegisterResponse:
        """Register a completed upload session into the source registry (T-203b)."""
        return await SourceGroupRegistrar(self._engine()).register(
            session_id=session_id,
            contexts=contexts,
            structure_validation=structure_validation,
            storage_kind=storage_kind,
            bucket=bucket,
            actor=actor,
            yyyymm_mismatch_ack=yyyymm_mismatch_ack,
            display_name=display_name,
        )

    async def revalidate_source_file_group(
        self,
        source_file_group_id: str,
        *,
        actor: str | None,
    ) -> GroupValidationResult:
        """Re-run the archive structure validator over a registered group.

        Materializes each child archive from RustFS to a temp dir, scans member
        manifests (GDAL-free zip/dir listing), decides pass/warning/failed, then
        persists the decision + recompute in one transaction.
        """
        import tempfile
        from pathlib import Path

        from .exceptions import NotFoundError
        from .infra.rustfs import RustfsClient, require_enabled_rustfs
        from .infra.source_group_service import revalidate_group
        from .infra.source_member_scan import scan_group_manifest
        from .infra.source_upload_repo import source_group_children

        children = await source_group_children(self._engine(), source_file_group_id)
        if not children:
            raise NotFoundError(f"source file group not found: {source_file_group_id}")
        category = children[0].category
        group_kind = children[0].group_kind
        config = require_enabled_rustfs(self.settings)
        rustfs = RustfsClient(config)
        decision: GroupValidation
        with tempfile.TemporaryDirectory(prefix="ktg-revalidate-") as tmp:
            parts: dict[str, Path] = {}
            for child in children:
                if not child.object_key:
                    continue
                dest = Path(tmp) / child.part_key / child.original_filename
                await rustfs.download_file(child.object_key, dest)
                parts[child.part_key] = dest
            from .core.source_validation import validate_group_manifest

            manifest = scan_group_manifest(
                category=category, group_kind=group_kind, parts=parts
            )
            decision = validate_group_manifest(manifest)
        return await revalidate_group(
            self._engine(), source_file_group_id, decision=decision, actor=actor
        )

    async def soft_delete_source_file_group(
        self,
        source_file_group_id: str,
        *,
        actor: str | None,
        reason: str | None = None,
    ) -> SourceGroupSoftDeleteResponse:
        """Soft-delete a group + its children (T-203c, doc line ~1441)."""
        from .infra.source_group_service import soft_delete_group

        return await soft_delete_group(
            self._engine(), source_file_group_id, actor=actor, reason=reason
        )

    async def restore_source_file_group(
        self,
        source_file_group_id: str,
        *,
        actor: str | None,
    ) -> SourceGroupRestoreResponse:
        """Restore a soft-deleted group via RustFS head + hash (T-203c, doc ~1442).

        Head-verifies each soft-deleted child's RustFS object (size/etag, then a
        full SHA-256 when needed) and feeds the observations to the pure restore
        transition decision in ``infra.source_group_service.restore_group``.
        """
        from .exceptions import NotFoundError
        from .infra.rustfs import RustfsClient, require_enabled_rustfs
        from .infra.source_group_service import (
            RestoreChildVerification,
            restore_group,
        )
        from .infra.source_upload_repo import source_group_children

        children = await source_group_children(self._engine(), source_file_group_id)
        if not children:
            raise NotFoundError(f"source file group not found: {source_file_group_id}")
        config = require_enabled_rustfs(self.settings)
        rustfs = RustfsClient(config)
        verifications: list[RestoreChildVerification] = []
        for child in children:
            if not child.object_key:
                verifications.append(
                    RestoreChildVerification(
                        source_file_id=child.source_file_id,
                        part_key=child.part_key,
                        object_present=False,
                    )
                )
                continue
            try:
                head = await rustfs.head_object(child.object_key)
            except Exception:  # absent / unreadable object → missing transition
                verifications.append(
                    RestoreChildVerification(
                        source_file_id=child.source_file_id,
                        part_key=child.part_key,
                        object_present=False,
                    )
                )
                continue
            observed_sha256 = head.metadata.get("ktg-sha256")
            if observed_sha256 is None:
                observed_sha256 = await rustfs.compute_sha256(child.object_key)
            verifications.append(
                RestoreChildVerification(
                    source_file_id=child.source_file_id,
                    part_key=child.part_key,
                    object_present=True,
                    observed_sha256=observed_sha256,
                    observed_size=head.size or None,
                )
            )
        return await restore_group(
            self._engine(),
            source_file_group_id,
            verifications=tuple(verifications),
            actor=actor,
        )

    async def run_source_upload_janitor(self) -> SourceJanitorRunResponse:
        """Run one upload-session janitor pass (T-203c, doc lines ~519-525).

        Aborts unfinished multipart uploads past ``expires_at`` and marks those
        sessions expired/cancelled; transitions stored-but-unregistered objects
        past the registration deadline to ``registration_expired``. Runs under the
        ``SOURCE_JANITOR`` advisory lock and skips the pass if another holds it.
        """
        from .infra.rustfs import RustfsClient, load_rustfs_config
        from .infra.source_janitor import run_source_upload_janitor

        config = load_rustfs_config(self.settings)
        rustfs = (
            RustfsClient(config)
            if config.enabled and config.credentials_configured
            else None
        )
        summary = await run_source_upload_janitor(
            self._engine(),
            rustfs=rustfs,
            ttl_days=self.settings.source_upload_session_ttl_days,
            deadline_days=self.settings.source_registration_deadline_days,
            session_limit=self.settings.source_janitor_session_limit,
        )
        return SourceJanitorRunResponse(**summary.as_payload())

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

    def list_source_file_categories(self) -> tuple[SourceFileCategoryInfo, ...]:
        """Return the static upload-category catalog (T-201).

        Synchronous in spirit (static data) but kept ``async`` is unnecessary;
        callers can use the value directly. Mirrors the
        ``GET /v1/admin/source-file-categories`` endpoint payload.
        """
        return tuple(
            SourceFileCategoryInfo(
                category=category.code,
                label=category.display_name,
                group_kind=category.group_kind,
                default_role=category.default_role,
                role=category.default_role,
                expected_member_kinds=category.expected_member_kinds,
                optional=category.optional,
            )
            for category in CATEGORY_CATALOG
        )

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
