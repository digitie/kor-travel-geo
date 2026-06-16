"""Async library client entry point."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Literal, Self

from sqlalchemy.ext.asyncio import AsyncEngine

from .core.consistency_definitions import CASE_DEFINITIONS
from .core.geocoder import geocode as core_geocode
from .core.poboxer import pobox as core_pobox
from .core.reverse_geocoder import reverse_geocode as core_reverse_geocode
from .core.searcher import search as core_search
from .core.source_categories import CATEGORY_CATALOG, serving_usage_for
from .core.source_validation import GroupValidation
from .core.v2 import (
    geocode_v2_from_geometry_lookups,
    geocode_v2_from_search,
    geocode_v2_from_v1,
    merge_geocode_v2_responses,
    reverse_v2_from_v1,
    search_v2_from_v1,
    with_candidate_geometry,
)
from .core.zipcoder import zipcode as core_zipcode
from .dto.admin import (
    BENCHMARK_ARTIFACT_TYPE,
    AuditEvent,
    BackupCopyResult,
    BackupRetentionResult,
    BackupVerifyResult,
    BenchmarkArtifactRegisterRequest,
    CacheMetrics,
    ConsistencyBulkDecisionRequest,
    ConsistencyBulkDecisionResponse,
    ConsistencyCase,
    ConsistencyCaseDefinition,
    ConsistencyCaseSample,
    ConsistencyCaseSummary,
    ConsistencyReport,
    ConsistencyReportSummary,
    ConsistencyRunValidationResponse,
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
    PgStatStatementSnapshot,
    RestoreCreateRequest,
    RestoreDrillResult,
    RestoreDryRunResult,
    RestoreHotSwapExecuteRequest,
    RestoreHotSwapPlan,
    RestoreHotSwapPlanRequest,
    RestoreHotSwapResult,
    RestoreHotSwapRollbackRequest,
    RestoreHotSwapRollbackResult,
    RollbackPlan,
    ScheduledBackupStatus,
    ServingRelease,
    TableStat,
    TableStatsSnapshot,
)
from .dto.geocode import FallbackMode, GeocodeInput, GeocodeResponse
from .dto.pobox import PoboxInput, PoboxKind, PoboxResponse
from .dto.region import RegionHint
from .dto.reverse import ReverseInput, ReverseResponse, ReverseType
from .dto.search import SearchResponse, SearchType
from .dto.source import (
    GroupValidationResult,
    ReconcileResolveResponse,
    RegisterResponse,
    RestoredFromBackupCreateResponse,
    RestoreSourceVerificationResult,
    ServingReleaseRollbackResponse,
    SourceBulkHardDeleteResponse,
    SourceCapacityUsage,
    SourceFileCategoryInfo,
    SourceGroupRelinkResponse,
    SourceGroupRestoreResponse,
    SourceGroupSoftDeleteResponse,
    SourceJanitorRunResponse,
    SourceMatchSet,
    SourceMatchSetActivateResponse,
    SourceMatchSetCreateRequest,
    SourceMatchSetDetail,
    SourceMatchSetRetireResponse,
    SourceMatchSetValidateResponse,
    SourceRebuildDbResponse,
    SourceReconcileItem,
    SourceReconcileRun,
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
from .infra.cache import GeoCacheRepository, make_cache_key
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


def _geocode_cache_payload(response: GeocodeResponse) -> dict[str, Any]:
    payload = response.model_dump(mode="json")
    payload["input"]["type"] = response.input.type
    return payload


def _reverse_cache_payload(response: ReverseResponse) -> dict[str, Any]:
    payload = response.model_dump(mode="json")
    payload["input"]["type"] = response.input.type
    payload["result"] = [
        {**item_payload, "type": item.type}
        for item_payload, item in zip(payload["result"], response.result, strict=True)
    ]
    return payload


def _cached_geocode_response(response: GeocodeResponse) -> GeocodeResponse:
    if response.x_extension is None:
        return response
    return response.model_copy(
        update={"x_extension": response.x_extension.model_copy(update={"source": "cache"})}
    )


def _cached_reverse_response(response: ReverseResponse) -> ReverseResponse:
    return response.model_copy(
        update={
            "result": tuple(
                item.model_copy(update={"source": "cache"}) for item in response.result
            )
        }
    )


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
            converted = await self._with_geocode_geometries(converted)
            if self._should_collect_geocode_supplements(inp, response, address):
                supplemental = await self._geocode_supplemental_road_candidates(inp, address)
                if supplemental.status == "OK":
                    return merge_geocode_v2_responses(inp, converted, supplemental)
            return converted
        fallback_response = await self._geocode_road_or_region_candidates(inp, address)
        return fallback_response if fallback_response.status == "OK" else converted

    @staticmethod
    def _should_collect_geocode_supplements(
        inp: GeocodeV2Input,
        response: GeocodeResponse,
        address: str,
    ) -> bool:
        if inp.limit <= 1:
            return False
        if inp.jibun_address and not (inp.road_address or inp.query):
            return False
        if response.x_extension and response.x_extension.national_point_number:
            return False
        source = response.x_extension.source if response.x_extension else "local"
        if source not in {"local", "cache"}:
            return False
        refined_text = response.refined.text if response.refined else None
        return refined_text is None or address.strip() != refined_text.strip()

    async def _geocode_supplemental_road_candidates(
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
        return geocode_v2_from_geometry_lookups(inp, road_rows)

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
        cache_key = self._geocode_cache_key(inp, sig_cd=sig_cd, bjd_cd=bjd_cd)
        if self._use_result_cache(fallback=fallback):
            cached = await GeoCacheRepository(self._engine()).get_json(cache_key)
            if cached is not None:
                return _cached_geocode_response(GeocodeResponse.model_validate(cached))
        response = await core_geocode(
            GeocodeRepository(self._engine()),
            inp,
            region_hint=region_hint,
        )
        if self._use_result_cache(fallback=fallback):
            await self._store_geocode_cache(cache_key, response)
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
        simple: bool = False,
        radius_m: int | None = None,
        sig_cd: str | None = None,
        bjd_cd: str | None = None,
    ) -> ReverseResponse:
        from .dto.common import Point

        inp = ReverseInput(
            point=Point(x=x, y=y),
            crs=crs,
            type=type,
            zipcode=zipcode,
            simple=simple,
            radius_m=radius_m or self.settings.api_default_radius_m,
        )
        region_hint = self._region_hint(sig_cd, bjd_cd)
        cache_key = self._reverse_cache_key(inp, sig_cd=sig_cd, bjd_cd=bjd_cd)
        if self._use_result_cache(fallback="local_only"):
            cached = await GeoCacheRepository(self._engine()).get_json(cache_key)
            if cached is not None:
                return _cached_reverse_response(ReverseResponse.model_validate(cached))
        response = await core_reverse_geocode(
            ReverseRepository(self._engine()),
            inp,
            region_hint=region_hint,
        )
        if self._use_result_cache(fallback="local_only"):
            await self._store_reverse_cache(cache_key, response)
        return response

    def _use_result_cache(
        self,
        *,
        fallback: FallbackMode,
    ) -> bool:
        return self.settings.cache_enabled and fallback != "api"

    @staticmethod
    def _geocode_cache_key(
        inp: GeocodeInput,
        *,
        sig_cd: str | None,
        bjd_cd: str | None,
    ) -> str:
        return make_cache_key(
            "geocode",
            {
                "address": inp.address,
                "type": inp.type,
                "crs": inp.crs,
                "refine": inp.refine,
                "simple": inp.simple,
                "fallback": inp.fallback,
                "sig_cd": sig_cd,
                "bjd_cd": bjd_cd,
            },
        )

    @staticmethod
    def _reverse_cache_key(
        inp: ReverseInput,
        *,
        sig_cd: str | None,
        bjd_cd: str | None,
    ) -> str:
        return make_cache_key(
            "reverse",
            {
                "x": inp.point.x,
                "y": inp.point.y,
                "crs": inp.crs,
                "type": inp.type,
                "zipcode": inp.zipcode,
                "simple": inp.simple,
                "radius_m": inp.radius_m,
                "sig_cd": sig_cd,
                "bjd_cd": bjd_cd,
            },
        )

    async def _store_geocode_cache(self, cache_key: str, response: GeocodeResponse) -> None:
        if response.status != "OK":
            return
        if response.x_extension is not None and response.x_extension.source != "local":
            return
        await GeoCacheRepository(self._engine()).set_json(
            cache_key=cache_key,
            service="geocode",
            payload=_geocode_cache_payload(response),
            ttl_days=self.settings.cache_ttl_days,
        )

    async def _store_reverse_cache(self, cache_key: str, response: ReverseResponse) -> None:
        if response.status != "OK":
            return
        if any(item.source != "local" for item in response.result):
            return
        await GeoCacheRepository(self._engine()).set_json(
            cache_key=cache_key,
            service="reverse",
            payload=_reverse_cache_payload(response),
            ttl_days=self.settings.cache_ttl_days,
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

    async def run_backup_retention_janitor(
        self,
        *,
        dry_run: bool = False,
        keep_min_count: int | None = None,
        actor_id: str = "system:backup_janitor",
    ) -> BackupRetentionResult:
        """Run one backup retention janitor pass (T-230).

        Expires backup archives whose ``expires_at`` has passed, except ``pinned``
        ones and the newest ``keep_min_count`` (``backup_retention_keep_min`` default).
        Runs under the ``BACKUP_JANITOR`` advisory lock; skips if another holds it.
        """
        from .infra.backup_janitor import run_backup_retention_janitor

        return await run_backup_retention_janitor(
            self._engine(),
            self.settings,
            dry_run=dry_run,
            keep_min_count=keep_min_count,
            actor_id=actor_id,
        )

    async def verify_backup(
        self, artifact_id: str, *, mode: str = "quick"
    ) -> BackupVerifyResult:
        """Non-destructively verify a stored backup's integrity (T-231).

        ``quick`` = archive sha256 vs recorded; ``deep`` also extracts and checks the
        internal ``checksums.sha256`` and ``manifest.json``. Corruption is returned as
        ``ok=False`` (not raised).
        """
        from .exceptions import InvalidInputError
        from .infra.backup import BACKUP_ARTIFACT_TYPE, verify_backup_artifact

        artifact = await self.get_artifact(artifact_id)
        if artifact.artifact_type != BACKUP_ARTIFACT_TYPE:
            msg = f"artifact is not a db_backup: {artifact_id}"
            raise InvalidInputError(msg)
        return await verify_backup_artifact(artifact, self.settings, mode=mode)

    async def copy_backup(self, artifact_id: str, *, target_dir: str) -> BackupCopyResult:
        """Copy a stored backup to another allowlisted dir with sha256 re-check (T-236)."""
        from .exceptions import InvalidInputError
        from .infra.backup import BACKUP_ARTIFACT_TYPE, copy_backup_artifact

        artifact = await self.get_artifact(artifact_id)
        if artifact.artifact_type != BACKUP_ARTIFACT_TYPE:
            msg = f"artifact is not a db_backup: {artifact_id}"
            raise InvalidInputError(msg)
        return await copy_backup_artifact(artifact, self.settings, target_dir=target_dir)

    async def restore_dry_run(self, req: RestoreCreateRequest) -> RestoreDryRunResult:
        """Preflight a restore without running pg_restore (T-232).

        Returns ``can_restore`` + ``blockers`` + ``warnings`` after checking archive
        integrity, target restorability, and version compatibility. Non-mutating.
        """
        from .infra.backup import run_restore_dry_run

        return await run_restore_dry_run(self._engine(), self.settings, req)

    async def run_restore_drill(
        self,
        *,
        timestamp: str,
        artifact_id: str | None = None,
        archive_path: str | None = None,
        base_database: str | None = None,
        jobs: int | None = None,
    ) -> RestoreDrillResult:
        """Restore a backup into a throwaway DB, reconcile+smoke, then drop it (T-242).

        Proves restorability without touching the serving DB; returns a PASS/FAIL result.
        ``timestamp`` names the throwaway DB deterministically.
        """
        from .infra.restore_drill import run_restore_drill

        return await run_restore_drill(
            self._engine(),
            self.settings,
            timestamp=timestamp,
            artifact_id=artifact_id,
            archive_path=archive_path,
            base_database=base_database,
            jobs=jobs,
        )

    async def scheduled_backup_status(
        self, *, now: datetime | None = None
    ) -> ScheduledBackupStatus:
        """Compute the current scheduled-backup due-check status (T-239, read-only).

        Reports whether a scheduled backup is due at ``now`` given the last scheduled
        run and whether one is in progress. Does not enqueue anything.
        """
        from .infra.backup_schedule import resolve_scheduled_backup_status

        return await resolve_scheduled_backup_status(self._engine(), self.settings, now=now)

    # --- RustFS reconciliation (T-204) ------------------------------------

    async def run_source_reconcile(
        self,
        *,
        prefix: str | None = None,
        mode: str = "quick",
        actor: str | None,
    ) -> SourceReconcileRun:
        """Run one RustFS ⟷ DB reconciliation pass (T-204, doc lines ~638-726).

        Scans the configured RustFS source prefix against ``ops.source_files``,
        emitting a ``source_storage_reconcile_items`` row for each issue_type.
        """
        from .infra.rustfs import RustfsClient, require_enabled_rustfs
        from .infra.source_reconcile import get_reconcile_run, run_source_reconcile

        config = require_enabled_rustfs(self.settings)
        rustfs = RustfsClient(config)
        scan_prefix = prefix or config.prefix
        result = await run_source_reconcile(
            self._engine(),
            rustfs=rustfs,
            prefix=scan_prefix,
            mode=mode,
            actor=actor,
            rolling_deep_days=self.settings.source_reconcile_rolling_deep_days,
            object_limit=self.settings.source_reconcile_object_limit,
        )
        return await get_reconcile_run(
            self._engine(), result.source_storage_reconcile_run_id
        )

    async def get_source_reconcile_run(self, run_id: str) -> SourceReconcileRun:
        from .infra.source_reconcile import get_reconcile_run

        return await get_reconcile_run(self._engine(), run_id)

    async def list_source_reconcile_runs(
        self, *, limit: int = 50
    ) -> tuple[SourceReconcileRun, ...]:
        from .infra.source_reconcile import list_reconcile_runs

        return await list_reconcile_runs(self._engine(), limit=limit)

    async def list_source_reconcile_items(
        self,
        run_id: str,
        *,
        issue_type: str | None = None,
        state: str | None = None,
        limit: int = 500,
    ) -> tuple[SourceReconcileItem, ...]:
        from .infra.source_reconcile import list_reconcile_items

        return await list_reconcile_items(
            self._engine(),
            run_id,
            issue_type=issue_type,
            state=state,
            limit=limit,
        )

    async def resolve_source_reconcile_item(
        self,
        item_id: str,
        *,
        action: str,
        actor: str | None,
        category: str | None = None,
        user_yyyymm: str | None = None,
        registration_deadline_at: datetime | None = None,
        typed_confirmation: str | None = None,
    ) -> ReconcileResolveResponse:
        """Resolve one reconciliation item (T-204, doc lines ~1458-1479).

        Runs the read-after-write recheck + active-정본 deletion guard, then the
        action; audits and may re-propagate via ``recompute_group_aggregates``.
        """
        from .infra.rustfs import RustfsClient, load_rustfs_config
        from .infra.source_reconcile import resolve_reconcile_item

        config = load_rustfs_config(self.settings)
        rustfs = (
            RustfsClient(config)
            if config.enabled and config.credentials_configured
            else None
        )
        return await resolve_reconcile_item(
            self._engine(),
            item_id,
            action=action,  # type: ignore[arg-type]
            actor=actor,
            rustfs=rustfs,
            category=category,
            user_yyyymm=user_yyyymm,
            registration_deadline_at=registration_deadline_at,
            typed_confirmation=typed_confirmation,
        )

    async def source_storage_capacity(self) -> SourceCapacityUsage:
        """Per-category storage capacity usage (T-204, doc line ~2107).

        Includes the T-212 (ADR-052) retention recommendation: an advisory
        cleanup signal (over-threshold + reclaimable soft_deleted/quarantined/
        unregistered bytes + eligible object count). Never auto-deletes.
        """
        from .infra.source_reconcile import compute_source_capacity

        return await compute_source_capacity(
            self._engine(),
            capacity_limit_bytes=self.settings.source_storage_capacity_limit_bytes,
        )

    async def bulk_hard_delete_source_objects(
        self,
        *,
        object_keys: tuple[str, ...],
        typed_confirmation: str,
        manifest_ack: bool = False,
        actor: str | None,
        reason: str | None = None,
    ) -> SourceBulkHardDeleteResponse:
        """Manually bulk hard-delete eligible source objects (T-212, ADR-052).

        ``destructive_admin`` + typed confirmation. NEVER deletes an active-정본
        (the T-204 active-match-set guard is reused) or a live registered archive;
        only ``soft_deleted``/``quarantined`` files and unregistered stored objects
        are eligible. A completed ``db_backup`` manifest/export must exist OR
        ``manifest_ack=true`` must be passed (pre-delete safety gate).
        """
        from .infra.rustfs import RustfsClient, load_rustfs_config
        from .infra.source_reconcile import bulk_hard_delete_sources

        config = load_rustfs_config(self.settings)
        rustfs = (
            RustfsClient(config)
            if config.enabled and config.credentials_configured
            else None
        )
        return await bulk_hard_delete_sources(
            self._engine(),
            object_keys=object_keys,
            typed_confirmation=typed_confirmation,
            manifest_ack=manifest_ack,
            actor=actor,
            reason=reason,
            rustfs=rustfs,
        )

    async def source_upload_session_state_counts(self) -> dict[str, int]:
        """Upload sessions by lifecycle state for the /metrics feed (T-211)."""
        return await SourceUploadSessionRepository(self._engine()).state_counts()

    # --- Source match sets (T-205a) ---------------------------------------

    async def list_source_match_sets(
        self, *, state: str | None = None, limit: int = 100
    ) -> tuple[SourceMatchSet, ...]:
        """List source match sets (T-205a)."""
        from .infra.source_match_set_service import SourceMatchSetRepository

        return await SourceMatchSetRepository(self._engine()).list_match_sets(
            state=state, limit=limit
        )

    async def get_source_match_set(
        self, source_match_set_id: str
    ) -> SourceMatchSetDetail:
        """Get one source match set + its items (T-205a)."""
        from .infra.source_match_set_service import SourceMatchSetRepository

        return await SourceMatchSetRepository(self._engine()).get_match_set(
            source_match_set_id
        )

    async def create_source_match_set(
        self, req: SourceMatchSetCreateRequest, *, actor: str | None
    ) -> SourceMatchSetDetail:
        """Create a ``draft`` source match set + its items (T-205a)."""
        from .infra.source_match_set_service import SourceMatchSetRepository

        return await SourceMatchSetRepository(self._engine()).create_match_set(
            req, actor=actor
        )

    async def validate_source_match_set(
        self, source_match_set_id: str, *, actor: str | None
    ) -> SourceMatchSetValidateResponse:
        """Run the match set ``validate`` state-split (T-205a, doc ~806/813-815)."""
        from .infra.source_match_set_service import SourceMatchSetRepository

        return await SourceMatchSetRepository(self._engine()).validate_match_set(
            source_match_set_id, actor=actor
        )

    async def activate_source_match_set(
        self, source_match_set_id: str, *, actor: str | None
    ) -> SourceMatchSetActivateResponse:
        """Atomic-swap activate a ``validated`` match set (T-205a, doc ~807)."""
        from .infra.source_match_set_service import SourceMatchSetRepository

        return await SourceMatchSetRepository(self._engine()).activate_match_set(
            source_match_set_id, actor=actor
        )

    async def retire_source_match_set(
        self, source_match_set_id: str, *, actor: str | None
    ) -> SourceMatchSetRetireResponse:
        """Retire a source match set (T-205a, doc ~808)."""
        from .infra.source_match_set_service import SourceMatchSetRepository

        return await SourceMatchSetRepository(self._engine()).retire_match_set(
            source_match_set_id, actor=actor
        )

    async def prepare_source_match_set_rebuild(
        self,
        source_match_set_id: str,
        *,
        actor: str | None,
        force_promotion: bool,
        typed_confirmation: str | None,
        reason: str | None,
    ) -> tuple[SourceRebuildDbResponse, dict[str, Any] | None]:
        """Run the rebuild-db precondition + pre-load integrity gate (T-205b).

        Returns ``(response, batch_payload)``. When ``batch_payload`` is not
        ``None`` the caller (endpoint) must enqueue it as a ``full_load_batch``
        under the ``source_rebuild_db`` advisory lock; the existing loader DAG
        then runs consistency → mv_refresh → snapshot(FK)/release. When the
        integrity gate fails ``batch_payload`` is ``None``, the failing groups
        have been quarantined + propagated, and ``response.enqueued=False``.

        ``force_promotion`` only arms the consistency-ERROR bypass (recorded on
        the batch root for the mv_refresh stage); it never bypasses the integrity
        gate run here (doc ~1559, ADR-049 #13).
        """
        from .infra.rustfs import RustfsClient, require_enabled_rustfs
        from .infra.source_rebuild_service import SourceRebuildService

        service = SourceRebuildService(self._engine())
        plan, stale = await service.prepare_rebuild(source_match_set_id)

        config = require_enabled_rustfs(self.settings)
        rustfs = RustfsClient(config)
        checks = await self._rebuild_integrity_checks(rustfs, plan)
        gate = service.integrity_gate(checks)
        if not gate.ok:
            affected = await service.quarantine_failed_groups(
                source_match_set_id,
                gate.failed_group_ids,
                actor=actor,
                reason="; ".join(gate.reasons),
            )
            return (
                SourceRebuildDbResponse(
                    source_match_set_id=source_match_set_id,
                    enqueued=False,
                    forced_promotion=False,
                    integrity_gate_ok=False,
                    failed_group_ids=gate.failed_group_ids,
                    stale_jobs_closed=stale.stale_job_ids,
                    affected_match_set_ids=affected,
                    message="pre-load integrity gate failed; groups quarantined",
                ),
                None,
            )

        batch_payload = dict(plan.batch_payload)
        if force_promotion:
            batch_payload["forced_promotion"] = True
            batch_payload["forced_promotion_actor"] = actor
            batch_payload["forced_promotion_reason"] = reason
        response = SourceRebuildDbResponse(
            source_match_set_id=source_match_set_id,
            enqueued=True,
            forced_promotion=force_promotion,
            integrity_gate_ok=True,
            stale_jobs_closed=stale.stale_job_ids,
            message="rebuild integrity gate passed; full_load_batch ready",
        )
        return response, batch_payload

    async def _rebuild_integrity_checks(
        self, rustfs: Any, plan: Any
    ) -> tuple[Any, ...]:
        """Materialize + re-verify each build group's archives (doc ~1544).

        Streams each child object's SHA-256 (head + ``compute_sha256``) and
        compares against the registry ``ops.source_files`` row + the group's
        ``group_sha256``. Returns the per-group :class:`GroupArchiveCheck` facts
        the pure gate decides on.
        """
        from sqlalchemy import text

        from .core.source_match_propagation import (
            ChildFileFacts,
            compute_group_sha256,
        )
        from .core.source_rebuild import GroupArchiveCheck

        checks: list[GroupArchiveCheck] = []
        engine = self._engine()
        for ref in plan.groups:
            async with engine.connect() as conn:
                rows = (
                    await conn.execute(
                        text(
                            """
SELECT source_file_id, part_kind, part_key, state, sha256, size_bytes, object_key
  FROM ops.source_files
 WHERE source_file_group_id = :gid
   AND state NOT IN ('hard_deleted','soft_deleted')
 ORDER BY part_key
"""
                        ),
                        {"gid": ref.source_file_group_id},
                    )
                ).mappings().all()
                group_state = await conn.scalar(
                    text(
                        "SELECT state FROM ops.source_file_groups "
                        "WHERE source_file_group_id = :gid"
                    ),
                    {"gid": ref.source_file_group_id},
                )

            all_present = True
            sha256_ok = True
            size_ok = True
            observed: list[ChildFileFacts] = []
            for row in rows:
                object_key = row["object_key"]
                if not object_key:
                    all_present = False
                    continue
                try:
                    head = await rustfs.head_object(object_key)
                except Exception:
                    all_present = False
                    continue
                observed_size = head.size or 0
                if observed_size != int(row["size_bytes"]):
                    size_ok = False
                observed_sha = head.metadata.get("ktg-sha256")
                if observed_sha is None:
                    observed_sha = await rustfs.compute_sha256(object_key)
                if observed_sha != row["sha256"]:
                    sha256_ok = False
                observed.append(
                    ChildFileFacts(
                        part_kind=str(row["part_kind"]),
                        part_key=str(row["part_key"]),
                        state=str(row["state"]),
                        sha256=str(observed_sha),
                        size_bytes=int(observed_size),
                    )
                )
            recomputed_group_sha = compute_group_sha256(tuple(observed))
            group_sha_ok = (
                ref.group_sha256 is None
                or recomputed_group_sha == ref.group_sha256
            )
            checks.append(
                GroupArchiveCheck(
                    source_file_group_id=ref.source_file_group_id,
                    category=ref.category,
                    group_state=str(group_state) if group_state else "missing",
                    all_objects_present=all_present and bool(rows),
                    sha256_ok=sha256_ok,
                    size_ok=size_ok,
                    group_sha256_ok=group_sha_ok,
                )
            )
        return tuple(checks)

    async def record_rebuild_enqueued(
        self,
        source_match_set_id: str,
        *,
        actor: str | None,
        job_id: str | None,
        load_batch_id: str | None,
        forced_promotion: bool,
        reason: str | None,
    ) -> None:
        """Audit a successfully-enqueued rebuild + forced_promotion (T-205b)."""
        from .infra.source_rebuild_service import SourceRebuildService

        await SourceRebuildService(self._engine()).record_rebuild_audit(
            source_match_set_id,
            actor=actor,
            outcome="enqueued",
            job_id=job_id,
            load_batch_id=load_batch_id,
            forced_promotion=forced_promotion,
            reason=reason,
        )

    async def rollback_serving_release(
        self,
        serving_release_id: str,
        *,
        actor: str | None,
        reason: str | None,
    ) -> ServingReleaseRollbackResponse:
        """Atomic source-match-set swap on serving rollback (T-205b, doc #18).

        Resolves the target snapshot's ``source_match_set_id``; when present,
        retires the current active match set and restores the target to
        ``active`` under the match-activate lock in one transaction, recomputing
        the target's ``integrity_alert`` from a pre-rollback source quick
        reconcile. Legacy snapshots (no FK) make no match-set change.
        """
        from .infra.source_rebuild_service import SourceRebuildService

        decision, integrity_alert = await SourceRebuildService(
            self._engine()
        ).rollback_swap(serving_release_id, actor=actor, reason=reason)
        return ServingReleaseRollbackResponse(
            serving_release_id=serving_release_id,
            mode=decision.mode,
            activated_match_set_id=decision.activate_match_set_id,
            retired_match_set_id=decision.retire_match_set_id,
            target_integrity_alert=integrity_alert,
            message="; ".join(decision.reasons) or None,
        )

    # --- restored_from_backup + relink (T-208) ----------------------------

    async def create_restored_from_backup(
        self, artifact_id: str, *, actor: str | None
    ) -> RestoredFromBackupCreateResponse:
        """Reconstruct a ``restored_from_backup`` match set from a backup manifest.

        Reads the ``db_backup`` artifact's manifest ``source_match_set`` block and
        creates stub groups/files (``missing``/``unknown``) + items + the match set
        at ``state='restored_from_backup'`` in one transaction (T-208, doc steps
        1-6). Rebuild stays disabled until relink completes.
        """
        from .exceptions import InvalidInputError
        from .infra.backup import BACKUP_ARTIFACT_TYPE
        from .infra.source_restore_service import (
            create_restored_from_backup,
            parse_manifest_source_match_set,
        )

        artifact = await self.get_artifact(artifact_id)
        if artifact.artifact_type != BACKUP_ARTIFACT_TYPE:
            raise InvalidInputError(f"artifact is not a db_backup: {artifact_id}")
        block_json = artifact.manifest.get("source_match_set")
        if not isinstance(block_json, dict):
            raise InvalidInputError(
                "backup manifest has no source_match_set block to reconstruct from"
            )
        block = parse_manifest_source_match_set(block_json)
        return await create_restored_from_backup(
            self._engine(), block, actor=actor
        )

    async def relink_restored_source_group(
        self, source_file_group_id: str, *, actor: str | None
    ) -> SourceGroupRelinkResponse:
        """Relink a ``restored_from_backup`` stub group's RustFS objects (T-208).

        Head-verifies + streaming-rehashes each stub child against the manifest
        sha256/size (the trust boundary) and feeds the observations to the pure
        relink transition; ``recompute_group_aggregates`` then recomputes
        ``group_sha256`` and drives ``restored_from_backup → revalidatable`` once
        every referenced group is ``available`` (M-A option 2, doc steps 7-9).
        """
        from .exceptions import NotFoundError
        from .infra.rustfs import RustfsClient, require_enabled_rustfs
        from .infra.source_restore_service import (
            RelinkChildVerification,
            relink_restored_group,
        )
        from .infra.source_upload_repo import source_group_children

        children = await source_group_children(self._engine(), source_file_group_id)
        if not children:
            raise NotFoundError(f"source file group not found: {source_file_group_id}")
        config = require_enabled_rustfs(self.settings)
        rustfs = RustfsClient(config)
        verifications: list[RelinkChildVerification] = []
        for child in children:
            if not child.object_key:
                verifications.append(
                    RelinkChildVerification(
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
                    RelinkChildVerification(
                        source_file_id=child.source_file_id,
                        part_key=child.part_key,
                        object_present=False,
                    )
                )
                continue
            # Always streaming-rehash on relink: the manifest hash is the trust
            # boundary and the ETag is never assumed equal to the SHA-256.
            observed_sha256 = await rustfs.compute_sha256(child.object_key)
            verifications.append(
                RelinkChildVerification(
                    source_file_id=child.source_file_id,
                    part_key=child.part_key,
                    object_present=True,
                    observed_sha256=observed_sha256,
                    observed_size=head.size or None,
                )
            )
        return await relink_restored_group(
            self._engine(),
            source_file_group_id,
            verifications=tuple(verifications),
            actor=actor,
        )

    async def verify_restore_source_hot_swap(
        self, *, actor: str | None
    ) -> RestoreSourceVerificationResult:
        """Run the ADR-036 rename hot-swap source verification (T-208, doc ~1901).

        Invoked after the operator completes the rename/smoke: resolves the (now
        swapped-in) active snapshot's ``source_match_set_id`` and runs ONE source
        quick reconcile against RustFS, surfacing a "재구성 불가" warning if source
        objects are missing. Legacy snapshots (no FK) only flag the estimate.
        """
        from .infra.rustfs import RustfsClient, load_rustfs_config
        from .infra.source_restore_service import verify_restore_source

        config = load_rustfs_config(self.settings)
        rustfs = (
            RustfsClient(config)
            if config.enabled and config.credentials_configured
            else None
        )
        return await verify_restore_source(
            self._engine(),
            entrypoint="rename_hot_swap",
            rustfs=rustfs,
            actor=actor,
            rolling_deep_days=self.settings.source_reconcile_rolling_deep_days,
            object_limit=self.settings.source_reconcile_object_limit,
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

    async def rollback_plan(self, serving_release_id: str) -> RollbackPlan:
        plan = await AdminRepository(self._engine()).rollback_plan(serving_release_id)
        if plan is None:
            from .exceptions import NotFoundError

            raise NotFoundError(f"serving release not found: {serving_release_id}")
        return plan

    async def list_artifacts(
        self,
        *,
        limit: int = 50,
        artifact_type: str | None = None,
        state: str | None = None,
        expires_before: datetime | None = None,
    ) -> list[OpsArtifact]:
        return await AdminRepository(self._engine()).list_artifacts(
            limit=limit,
            artifact_type=artifact_type,
            state=state,
            expires_before=expires_before,
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

    async def register_benchmark_artifact(
        self, request: BenchmarkArtifactRegisterRequest
    ) -> OpsArtifact:
        """T-265: persist a perf benchmark run's headline metrics as a ``benchmark`` ops
        artifact (T-138/T-141/T-146) so the Admin UI (T-222) can surface it read-only. The
        benchmark sub-type/workload/phase and metrics live in the artifact manifest; heavy
        run data stays as the file referenced by ``storage_uri``."""
        from uuid import uuid4

        manifest: dict[str, Any] = {
            "run_id": request.run_id,
            "kind": request.kind,
            "profile": request.profile,
            "workload": request.workload,
            "phase": request.phase,
            "metrics": request.metrics.model_dump(exclude_none=True),
            "baseline_artifact_id": request.baseline_artifact_id,
            "captured_at": request.captured_at.isoformat() if request.captured_at else None,
            "notes": request.notes,
        }
        return await AdminRepository(self._engine()).insert_artifact(
            artifact_id=uuid4().hex,
            artifact_type=BENCHMARK_ARTIFACT_TYPE,
            state="available",
            storage_kind="local_file" if request.storage_uri else "none",
            storage_uri=request.storage_uri,
            display_name=request.display_name,
            media_type="application/json",
            size_bytes=request.size_bytes,
            sha256=request.sha256,
            manifest=manifest,
        )

    async def restore_hot_swap_plan(
        self,
        req: RestoreHotSwapPlanRequest,
    ) -> RestoreHotSwapPlan:
        return await inspect_restore_hot_swap_plan(self.settings, req)

    async def execute_restore_hot_swap(
        self,
        req: RestoreHotSwapExecuteRequest,
        *,
        actor: str | None = None,
        audit_meta: Mapping[str, Any] | None = None,
    ) -> RestoreHotSwapResult:
        """Execute the ADR-036 rename hot-swap with auto-rollback (T-241).

        Requires an active ``restore`` maintenance window + exact typed confirmation, runs
        under the ``HOT_SWAP`` advisory lock (concurrent second call fails fast), and
        auto-rolls-back if the post-swap smoke test fails. Disposes/refreshes this client's
        engine pool as part of the swap.
        """
        from .infra.hotswap import execute_restore_hot_swap

        return await execute_restore_hot_swap(
            self._engine(), self.settings, req, actor=actor, audit_meta=audit_meta
        )

    async def execute_hot_swap_rollback(
        self,
        req: RestoreHotSwapRollbackRequest,
        *,
        actor: str | None = None,
        audit_meta: Mapping[str, Any] | None = None,
    ) -> RestoreHotSwapRollbackResult:
        """Manually roll back a completed hot-swap to the previous serving DB (T-264).

        Requires an active ``restore`` maintenance window + exact rollback confirmation, rejects
        once ``previous_alias`` retention has dropped it, runs under the ``HOT_SWAP`` lock
        (concurrent call fails fast), and disposes/refreshes this client's engine pool.
        """
        from .infra.hotswap import execute_hot_swap_rollback

        return await execute_hot_swap_rollback(
            self._engine(), self.settings, req, actor=actor, audit_meta=audit_meta
        )

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
            resource_id=window.maintenance_window_id,
        )
        return window

    async def end_maintenance_window(
        self,
        maintenance_window_id: str,
        req: MaintenanceWindowEnd,
    ) -> MaintenanceWindow:
        window = await AdminRepository(self._engine()).end_maintenance_window(
            maintenance_window_id=maintenance_window_id,
            confirmation=req.confirmation,
            closed_by_job_id=req.closed_by_job_id,
        )
        if window is None:
            from .exceptions import NotFoundError

            raise NotFoundError(
                f"active maintenance window not found: {maintenance_window_id}"
            )
        await self.record_audit_event(
            action="maintenance_window.end",
            outcome="succeeded",
            payload=req.model_dump(exclude={"confirmation"}),
            resource_type="maintenance_window",
            resource_id=window.maintenance_window_id,
        )
        return window

    async def list_table_stats_snapshots(
        self,
        *,
        limit: int = 200,
        dataset_snapshot_id: str | None = None,
    ) -> list[TableStatsSnapshot]:
        return await AdminRepository(self._engine()).list_table_stats_snapshots(
            limit=limit,
            dataset_snapshot_id=dataset_snapshot_id,
        )

    async def capture_table_stats_snapshots(
        self,
        *,
        dataset_snapshot_id: str | None = None,
        limit: int = 500,
        skip_if_locked: bool = False,
    ) -> list[TableStatsSnapshot]:
        return await AdminRepository(self._engine()).capture_table_stats_snapshots(
            dataset_snapshot_id=dataset_snapshot_id,
            limit=limit,
            skip_if_locked=skip_if_locked,
        )

    async def list_pg_stat_statement_snapshots(
        self,
        *,
        limit: int = 20,
        latest_only: bool = True,
    ) -> list[PgStatStatementSnapshot]:
        return await AdminRepository(self._engine()).list_pg_stat_statement_snapshots(
            limit=limit,
            latest_only=latest_only,
        )

    async def capture_pg_stat_statement_snapshots(
        self,
        *,
        limit: int = 20,
        skip_if_locked: bool = False,
    ) -> list[PgStatStatementSnapshot]:
        return await AdminRepository(self._engine()).capture_pg_stat_statement_snapshots(
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
                serving_usage=serving_usage_for(category.code),
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
        """Return the C1~C17 registry rows (T-206).

        Reads ``ops.consistency_case_definitions`` so the response is the full
        dynamic registry the UI case tab (T-209) renders. Falls back to the
        in-code C1~C10 ``CASE_DEFINITIONS`` only when the registry is empty (not
        yet seeded), so a fresh/un-migrated DB still serves the core cases.
        """
        from .infra.consistency_registry_service import ConsistencyRegistryService

        rows = await ConsistencyRegistryService(self._engine()).list_case_definitions()
        return rows or CASE_DEFINITIONS

    async def seed_consistency_registry(self) -> int:
        """Idempotently upsert the C1~C17 consistency case registry seed (T-206)."""
        from .infra.consistency_registry_service import ConsistencyRegistryService

        return await ConsistencyRegistryService(self._engine()).seed_registry()

    async def run_consistency_validation(
        self,
        source_match_set_id: str,
        *,
        actor: str | None,
        cases: tuple[str, ...] | None = None,
    ) -> ConsistencyRunValidationResponse:
        """Run registry C11~C17 validation against an existing DB (T-206, doc ~1564).

        No rebuild/snapshot/release. Each present input's archive is re-verified
        with the 사용 직전 무결성 게이트 (RustFS, when configured); an absent input
        is ``skipped``, a corrupt/mismatched archive is ``failed`` + the group is
        quarantined; a ``validator_version`` change reverts a prior ``passed`` to
        ``not_started`` and marks referencing match sets needing re-validation.
        """
        from .infra.consistency_run_validation_service import (
            ConsistencyRunValidationService,
        )

        service = ConsistencyRunValidationService(self._engine())
        verifier = await self._build_run_validation_verifier()
        return await service.run_validation(
            source_match_set_id,
            actor=actor,
            cases=cases,
            integrity_verifier=verifier,
        )

    async def _build_run_validation_verifier(self) -> Any | None:
        """An ``(group_id, category) -> GroupArchiveCheck`` RustFS verifier or None.

        Reuses the same per-group RustFS re-verification the rebuild integrity
        gate uses. Returns ``None`` when RustFS is not enabled, in which case
        present inputs are treated as integrity-ok (the absent→skipped and
        runnable decision paths still run).
        """
        try:
            from .infra.rustfs import RustfsClient, require_enabled_rustfs

            config = require_enabled_rustfs(self.settings)
        except Exception:
            return None
        rustfs = RustfsClient(config)

        async def verify(group_id: str, category: str) -> Any:
            return await self._group_archive_check(rustfs, group_id, category)

        return verify

    async def _group_archive_check(
        self, rustfs: Any, group_id: str, category: str
    ) -> Any:
        """Re-verify one group's RustFS archive → ``GroupArchiveCheck`` (doc ~1544)."""
        from sqlalchemy import text

        from .core.source_match_propagation import ChildFileFacts, compute_group_sha256
        from .core.source_rebuild import GroupArchiveCheck

        engine = self._engine()
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
SELECT part_kind, part_key, state, sha256, size_bytes, object_key
  FROM ops.source_files
 WHERE source_file_group_id = :gid
   AND state NOT IN ('hard_deleted','soft_deleted')
 ORDER BY part_key
"""
                    ),
                    {"gid": group_id},
                )
            ).mappings().all()
            group_state = await conn.scalar(
                text(
                    "SELECT state FROM ops.source_file_groups "
                    "WHERE source_file_group_id = :gid"
                ),
                {"gid": group_id},
            )
            registry_group_sha = await conn.scalar(
                text(
                    "SELECT group_sha256 FROM ops.source_file_groups "
                    "WHERE source_file_group_id = :gid"
                ),
                {"gid": group_id},
            )

        all_present = True
        sha256_ok = True
        size_ok = True
        observed: list[ChildFileFacts] = []
        for row in rows:
            object_key = row["object_key"]
            if not object_key:
                all_present = False
                continue
            try:
                head = await rustfs.head_object(object_key)
            except Exception:
                all_present = False
                continue
            observed_size = head.size or 0
            if observed_size != int(row["size_bytes"]):
                size_ok = False
            observed_sha = head.metadata.get("ktg-sha256")
            if observed_sha is None:
                observed_sha = await rustfs.compute_sha256(object_key)
            if observed_sha != row["sha256"]:
                sha256_ok = False
            observed.append(
                ChildFileFacts(
                    part_kind=str(row["part_kind"]),
                    part_key=str(row["part_key"]),
                    state=str(row["state"]),
                    sha256=str(observed_sha),
                    size_bytes=int(observed_size),
                )
            )
        recomputed_group_sha = compute_group_sha256(tuple(observed))
        group_sha_ok = registry_group_sha is None or recomputed_group_sha == registry_group_sha
        return GroupArchiveCheck(
            source_file_group_id=group_id,
            category=category,
            group_state=str(group_state) if group_state else "missing",
            all_objects_present=all_present and bool(rows),
            sha256_ok=sha256_ok,
            size_ok=size_ok,
            group_sha256_ok=group_sha_ok,
        )

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
