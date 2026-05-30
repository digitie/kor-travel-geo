"""Repository protocols and transport-neutral row objects for core logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from kraddr.geo.dto.common import AddressType, Point, ZipSource
from kraddr.geo.dto.region import RegionHint
from kraddr.geo.dto.v2 import BBoxV2, GeometryV2, V2GeometryKind

from .normalize import AddrParts


@dataclass(frozen=True, slots=True)
class AddressLookup:
    bd_mgt_sn: str
    text: str
    address_type: AddressType
    point: Point | None
    si_nm: str | None = None
    sgg_nm: str | None = None
    emd_nm: str | None = None
    li_nm: str | None = None
    road_nm: str | None = None
    detail: str | None = None
    rncode_full: str | None = None
    bjd_cd: str | None = None
    adm_cd: str | None = None
    adm_nm: str | None = None
    zip_no: str | None = None
    buld_nm: str | None = None
    pt_source: Literal["entrance", "centroid"] | None = None
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class ReverseLookup(AddressLookup):
    distance_m: float | None = None


@dataclass(frozen=True, slots=True)
class SppnAreaLookup:
    sig_cd: str
    makarea_id: str
    makarea_nm: str | None = None
    ntfc_yn: str | None = None
    ntfc_de: str | None = None
    mvm_res_cd: str | None = None
    source_file: str | None = None
    source_yyyymm: str | None = None
    area_m2: float | None = None
    point: Point | None = None


@dataclass(frozen=True, slots=True)
class SearchLookup:
    type: Literal["address", "place", "district", "road"]
    title: str
    address: str | None = None
    lookup: AddressLookup | None = None
    score: float | None = None


@dataclass(frozen=True, slots=True)
class GeometryLookup:
    kind: V2GeometryKind
    geometry: GeometryV2
    bbox: BBoxV2 | None = None
    point: Point | None = None
    title: str | None = None
    sig_cd: str | None = None
    bjd_cd: str | None = None
    sido: str | None = None
    sigungu: str | None = None
    eup_myeon_dong: str | None = None
    li: str | None = None
    road_name: str | None = None
    rncode_full: str | None = None
    bd_mgt_sn: str | None = None
    score: float | None = None


@dataclass(frozen=True, slots=True)
class ZipLookup:
    zip_no: str
    source: ZipSource
    address: str | None = None
    bd_mgt_sn: str | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class PoboxLookup:
    zip_no: str
    pobox_kind: Literal["PO", "PG"]
    pobox_name: str | None = None
    pobox_no_mn: int | None = None
    pobox_no_sl: int | None = None
    si_nm: str | None = None
    sgg_nm: str | None = None
    emd_nm: str | None = None
    bjd_cd: str | None = None


@dataclass(frozen=True, slots=True)
class LoadJobRow:
    job_id: str
    kind: str
    state: Literal["queued", "running", "done", "failed", "cancelled"]
    load_batch_id: str | None = None
    parent_job_id: str | None = None
    progress: float = 0.0
    current_stage: str | None = None
    source_yyyymm: str | None = None
    source_set: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    error_message: str | None = None
    log_tail: tuple[str, ...] = ()
    payload_summary: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ConsistencyCaseRow:
    code: str
    name: str
    severity: Literal["OK", "INFO", "WARN", "ERROR"]
    count: int
    ratio: float | None = None
    threshold: str | None = None
    metric: dict[str, float] | None = None
    sample: tuple[dict[str, Any], ...] = ()
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ConsistencyReportRow:
    report_id: str
    scope: str
    severity_max: Literal["OK", "INFO", "WARN", "ERROR"]
    source_set: dict[str, Any]
    started_at: datetime
    finished_at: datetime | None = None
    cases: tuple[ConsistencyCaseRow, ...] = ()
    generated_by: Literal["cli", "api", "cron"] = "api"


@runtime_checkable
class GeocodeRepo(Protocol):
    async def lookup_by_road(
        self,
        parts: AddrParts,
        *,
        region_hint: RegionHint | None = None,
    ) -> AddressLookup | None: ...

    async def lookup_by_jibun(
        self,
        parts: AddrParts,
        *,
        region_hint: RegionHint | None = None,
    ) -> AddressLookup | None: ...

    async def fuzzy_roads(
        self,
        parts: AddrParts,
        *,
        limit: int = 5,
        region_hint: RegionHint | None = None,
    ) -> list[AddressLookup]: ...

    async def lookup_sppn_area(self, point_5179: Point) -> SppnAreaLookup | None: ...


@runtime_checkable
class ReverseRepo(Protocol):
    async def nearest(
        self,
        point: Point,
        *,
        crs: str,
        address_type: Literal["both", "road", "parcel"],
        radius_m: int,
        limit: int = 5,
        region_hint: RegionHint | None = None,
    ) -> list[ReverseLookup]: ...

    async def sppn_areas(
        self,
        point: Point,
        *,
        crs: str,
        limit: int = 5,
    ) -> list[SppnAreaLookup]: ...


@runtime_checkable
class SearchRepo(Protocol):
    async def search(
        self,
        query: str,
        *,
        search_type: Literal["address", "place", "district", "road"],
        page: int,
        size: int,
        region_hint: RegionHint | None = None,
    ) -> tuple[list[SearchLookup], int]: ...


@runtime_checkable
class ZipRepo(Protocol):
    async def lookup_zipcode_by_address(
        self,
        parts: AddrParts,
        *,
        include_bulk: bool,
    ) -> list[ZipLookup]: ...

    async def lookup_zipcode_by_point(
        self,
        point: Point,
        *,
        include_bulk: bool,
    ) -> list[ZipLookup]: ...

    async def lookup_zipcode_by_bd_mgt_sn(
        self,
        bd_mgt_sn: str,
        *,
        include_bulk: bool,
    ) -> list[ZipLookup]: ...


@runtime_checkable
class PoboxRepo(Protocol):
    async def lookup_poboxes(
        self,
        *,
        query: str | None,
        si_nm: str | None,
        sgg_nm: str | None,
        kind: Literal["PO", "PG", "ALL"],
        page: int,
        size: int,
    ) -> tuple[list[PoboxLookup], int]: ...


@runtime_checkable
class AdminRepo(Protocol):
    async def get_load_job(self, job_id: str) -> LoadJobRow | None: ...

    async def list_load_jobs(
        self,
        *,
        kind: str | None = None,
        state: str | None = None,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[LoadJobRow]: ...

    async def insert_load_job(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        job_id: str | None = None,
        load_batch_id: str | None = None,
        parent_job_id: str | None = None,
    ) -> LoadJobRow: ...

    async def cancel_load_job(self, job_id: str) -> LoadJobRow | None: ...

    async def consistency_report(self, report_id: str) -> ConsistencyReportRow | None: ...

    async def list_consistency_reports(
        self,
        *,
        limit: int = 20,
        severity_at_least: Literal["INFO", "WARN", "ERROR"] | None = None,
    ) -> list[ConsistencyReportRow]: ...


@dataclass(slots=True)
class FakeGeocodeRepo:
    """Small fake useful for core tests and examples."""

    road_result: AddressLookup | None = None
    jibun_result: AddressLookup | None = None
    fuzzy_result: list[AddressLookup] = field(default_factory=list)

    last_region_hint: RegionHint | None = None

    async def lookup_by_road(
        self,
        parts: AddrParts,
        *,
        region_hint: RegionHint | None = None,
    ) -> AddressLookup | None:
        self.last_region_hint = region_hint
        return self.road_result

    async def lookup_by_jibun(
        self,
        parts: AddrParts,
        *,
        region_hint: RegionHint | None = None,
    ) -> AddressLookup | None:
        self.last_region_hint = region_hint
        return self.jibun_result

    async def fuzzy_roads(
        self,
        parts: AddrParts,
        *,
        limit: int = 5,
        region_hint: RegionHint | None = None,
    ) -> list[AddressLookup]:
        self.last_region_hint = region_hint
        return self.fuzzy_result[:limit]

    async def lookup_sppn_area(self, point_5179: Point) -> SppnAreaLookup | None:
        _ = point_5179
        return None
