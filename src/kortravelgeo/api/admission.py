"""API admission-control helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass

from kortravelgeo.settings import Settings

ADMISSION_GLOBAL_SCOPE = "address"

_SCOPE_SETTING_NAMES: dict[str, str] = {
    ADMISSION_GLOBAL_SCOPE: "KTG_API_MAX_CONCURRENCY",
    "geocode": "KTG_API_GEOCODE_MAX_CONCURRENCY",
    "reverse": "KTG_API_REVERSE_MAX_CONCURRENCY",
    "search": "KTG_API_SEARCH_MAX_CONCURRENCY",
    "zipcode": "KTG_API_ZIPCODE_MAX_CONCURRENCY",
    "pobox": "KTG_API_POBOX_MAX_CONCURRENCY",
    "regions": "KTG_API_REGIONS_MAX_CONCURRENCY",
}


@dataclass(frozen=True)
class AdmissionScopeSnapshot:
    scope: str
    limit: int
    in_use: int
    available: int
    utilization: float


class AdmissionController:
    """Process-local semaphores for public address API backpressure."""

    def __init__(self, limits: Mapping[str, int]) -> None:
        self._limits = dict(limits)
        self._semaphores = {
            scope: asyncio.Semaphore(limit) for scope, limit in self._limits.items()
        }
        self._in_use: dict[str, int] = dict.fromkeys(self._limits, 0)

    def scopes_for_path(self, path: str) -> tuple[str, ...]:
        if not _is_public_address_path(path):
            return ()

        scopes: list[str] = []
        endpoint_scope = _endpoint_scope_for_path(path)
        if endpoint_scope is not None and endpoint_scope in self._semaphores:
            scopes.append(endpoint_scope)
        if ADMISSION_GLOBAL_SCOPE in self._semaphores:
            scopes.append(ADMISSION_GLOBAL_SCOPE)
        return tuple(scopes)

    async def acquire(self, scope: str) -> None:
        await self._semaphores[scope].acquire()
        self._in_use[scope] += 1

    def release(self, scope: str) -> None:
        self._in_use[scope] -= 1
        self._semaphores[scope].release()

    def snapshots(self) -> tuple[AdmissionScopeSnapshot, ...]:
        snapshots: list[AdmissionScopeSnapshot] = []
        for scope, limit in self._limits.items():
            in_use = self._in_use[scope]
            available = max(0, limit - in_use)
            utilization = in_use / limit if limit > 0 else 1.0
            snapshots.append(
                AdmissionScopeSnapshot(
                    scope=scope,
                    limit=limit,
                    in_use=in_use,
                    available=available,
                    utilization=round(utilization, 4),
                )
            )
        return tuple(snapshots)


def build_admission_controller(settings: Settings) -> AdmissionController | None:
    limits: dict[str, int] = {}
    if settings.api_geocode_max_concurrency is not None:
        limits["geocode"] = settings.api_geocode_max_concurrency
    if settings.api_reverse_max_concurrency is not None:
        limits["reverse"] = settings.api_reverse_max_concurrency
    if settings.api_search_max_concurrency is not None:
        limits["search"] = settings.api_search_max_concurrency
    if settings.api_zipcode_max_concurrency is not None:
        limits["zipcode"] = settings.api_zipcode_max_concurrency
    if settings.api_pobox_max_concurrency is not None:
        limits["pobox"] = settings.api_pobox_max_concurrency
    if settings.api_regions_max_concurrency is not None:
        limits["regions"] = settings.api_regions_max_concurrency
    if settings.api_max_concurrency is not None:
        limits[ADMISSION_GLOBAL_SCOPE] = settings.api_max_concurrency
    return AdmissionController(limits) if limits else None


def admission_scope_setting_name(scope: str) -> str:
    return _SCOPE_SETTING_NAMES.get(scope, "KTG_API_MAX_CONCURRENCY")


def _is_public_address_path(path: str) -> bool:
    return path.startswith("/v1/address/") or path.startswith("/v2/")


def _endpoint_scope_for_path(path: str) -> str | None:
    if path in {"/v1/address/geocode", "/v2/geocode"}:
        return "geocode"
    if path in {"/v1/address/reverse", "/v2/reverse"}:
        return "reverse"
    if path in {"/v1/address/search", "/v2/search"}:
        return "search"
    if path == "/v1/address/zipcode":
        return "zipcode"
    if path == "/v1/address/pobox":
        return "pobox"
    if path == "/v2/regions/within-radius":
        return "regions"
    return None
