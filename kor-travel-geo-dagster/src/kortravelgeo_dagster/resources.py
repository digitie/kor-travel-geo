"""Dagster resource factory (geo).

Production deployments use this module's default resources as-is, or replace them
in a test/special deployment via ``Definitions(..., resources={...})``.

Resources share the *configuration* (``Settings``, env prefix ``KTG_*``) and the
main-lib *constructors*, NOT live resource objects (dagster-boundary §3). Missing
credentials fail at run init with a key-specific message rather than at import, so
the code location always loads.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Awaitable, Iterator
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urljoin, urlparse

import httpx
from dagster import InitResourceContext, resource
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.rustfs import RustfsClient, load_rustfs_config
from kortravelgeo.settings import Settings

__all__ = [
    "ACTOR_HEADER",
    "ADMIN_PROXY_SECRET_HEADER",
    "DESTRUCTIVE_ADMIN_ROLE",
    "ROLES_HEADER",
    "SYSTEM_ACTOR",
    "DagsterAdminApiClient",
    "admin_api_resource",
    "client_resource",
    "rustfs_resource",
    "settings_resource",
]

ACTOR_HEADER = "x-ktg-actor"
ROLES_HEADER = "x-ktg-roles"
ADMIN_PROXY_SECRET_HEADER = "x-ktg-admin-proxy-secret"
SYSTEM_ACTOR = "system:dagster"
DESTRUCTIVE_ADMIN_ROLE = "destructive_admin"


@dataclass(frozen=True, slots=True)
class DagsterAdminApiClient:
    """Small authenticated client for Dagster -> geo admin API onramp calls."""

    base_url: str
    timeout_seconds: float
    admin_proxy_secret: str | None = None
    actor: str = SYSTEM_ACTOR
    roles: tuple[str, ...] = (DESTRUCTIVE_ADMIN_ROLE,)

    @classmethod
    def from_settings(cls, settings: Settings) -> DagsterAdminApiClient:
        secret = settings.admin_proxy_secret
        return cls(
            base_url=_normalize_http_base_url(settings.dagster_admin_api_url),
            timeout_seconds=settings.dagster_request_timeout_seconds,
            admin_proxy_secret=secret.get_secret_value() if secret is not None else None,
        )

    async def run_due_scheduled_backup(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        """Call ``POST /v1/admin/backups/scheduled/run-due`` and return its JSON body."""

        async def _post(client: httpx.AsyncClient) -> dict[str, Any]:
            response = await client.post(
                self.url_for("/v1/admin/backups/scheduled/run-due"),
                headers=self.headers(),
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                msg = "scheduled backup run-due response must be a JSON object"
                raise RuntimeError(msg)
            return cast("dict[str, Any]", payload)

        if http_client is not None:
            return await _post(http_client)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            return await _post(client)

    def url_for(self, path: str) -> str:
        return urljoin(f"{self.base_url}/", path.lstrip("/"))

    def headers(self) -> dict[str, str]:
        headers = {
            ACTOR_HEADER: self.actor,
            ROLES_HEADER: ",".join(self.roles),
        }
        if self.admin_proxy_secret:
            headers[ADMIN_PROXY_SECRET_HEADER] = self.admin_proxy_secret
        return headers


def _normalize_http_base_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        msg = "KTG_DAGSTER_ADMIN_API_URL must be an absolute http(s) URL"
        raise ValueError(msg)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        msg = "KTG_DAGSTER_ADMIN_API_URL must not include userinfo, query, or fragment"
        raise ValueError(msg)
    return value.rstrip("/")


async def _await_resource_teardown(awaitable: Awaitable[object]) -> None:
    await awaitable


def _run_async_resource_teardown(awaitable: Awaitable[object]) -> None:
    """Run an async cleanup from a Dagster sync-generator resource teardown.

    If there is no running loop, run it directly; otherwise run it on a short-lived
    worker thread so we never call ``asyncio.run`` inside an active event loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_await_resource_teardown(awaitable))
        return

    raised: list[BaseException] = []

    def _runner() -> None:
        try:
            asyncio.run(_await_resource_teardown(awaitable))
        except BaseException as exc:  # pragma: no cover - exercised via re-raise below
            raised.append(exc)

    thread = threading.Thread(
        target=_runner,
        name="kor-travel-geo-dagster-resource-teardown",
    )
    thread.start()
    thread.join()
    if raised:
        raise raised[0]


def _dispose_async_engine(engine: Any) -> None:
    """Dispose a SQLAlchemy ``AsyncEngine`` from a sync-generator teardown.

    An ``AsyncEngine`` exposes ``sync_engine.dispose(close=False)`` which tears down
    the pool without needing an event loop; prefer it. Fall back to awaiting the
    async ``dispose()`` on a dedicated loop when that path is unavailable. (Same
    helper the kor-travel-map Dagster resources use.)
    """
    sync_engine = getattr(engine, "sync_engine", None)
    sync_dispose = getattr(sync_engine, "dispose", None)
    if sync_dispose is not None:
        sync_dispose(close=False)
        return

    dispose_result = engine.dispose()
    if inspect.isawaitable(dispose_result):
        _run_async_resource_teardown(cast("Awaitable[object]", dispose_result))


def _maintenance_engine_settings(settings: Settings) -> Settings:
    """Return ``settings`` with the serving ``statement_timeout`` disabled.

    A Dagster orchestration engine runs long MAINTENANCE work — ``mv_refresh``,
    backup, restore, full-load — never online serving, so it must NOT carry the
    short serving ``statement_timeout`` (default 5s) that ``make_async_engine`` bakes
    into every connection via ``-c statement_timeout=...`` (``infra/engine.py``
    ``_connect_options``). We set ``pg_statement_timeout_ms=0`` (PostgreSQL "disabled")
    so no maintenance statement inherits the serving cap. This is belt-and-suspenders
    with each leaf's own ``SET LOCAL statement_timeout = 0``: the concurrent
    ``refresh_mv`` path (``loaders/postload.py``) has follow-up statements
    (``GeoCacheRepository.clear`` and region-radius refresh on fresh connections) that
    do not all reset the timeout, and future backup/restore/full-load ops must be
    protected too (ADR-066 §7 — the Dagster runtime is a maintenance engine).

    ``model_copy`` does not re-validate, so the ``ge=1`` field bound is intentionally
    bypassed here — ``0`` is a valid PostgreSQL sentinel meaning "no timeout".
    """
    return settings.model_copy(update={"pg_statement_timeout_ms": 0})


@resource(description="AsyncAddressClient bound to the kor-travel-geo app DB (KTG_PG_DSN).")
def client_resource(_context: InitResourceContext) -> Iterator[AsyncAddressClient]:
    """Default Dagster ``client`` resource.

    Builds a **maintenance** async engine (serving ``statement_timeout`` disabled — see
    :func:`_maintenance_engine_settings`) from ``Settings()`` and yields an
    ``AsyncAddressClient`` bound to it. Because the client is given an explicit engine,
    it does NOT own the engine (its ``close()`` will not dispose it) — so the engine is
    disposed here on teardown.
    """
    settings = Settings()
    engine = make_async_engine(_maintenance_engine_settings(settings))
    try:
        yield AsyncAddressClient(settings, engine=engine)
    finally:
        _dispose_async_engine(engine)


@resource(
    description=(
        "RustFS (S3-compatible) client for backup archive/artifact storage "
        "(KTG_RUSTFS_*). Fails at run init when disabled or missing credentials."
    )
)
def rustfs_resource(_context: InitResourceContext) -> RustfsClient:
    """Default Dagster ``rustfs`` resource.

    Loads the effective RustFS config from ``KTG_RUSTFS_*``. When RustFS is disabled
    or the access/secret keys are missing, raises a key-specific ``RuntimeError`` so
    the code location import still succeeds and only the *run* fails (mirrors map's
    missing-credential behaviour).
    """
    settings = Settings()
    config = load_rustfs_config(settings)
    if not config.enabled:
        raise RuntimeError(
            "Dagster resource 'rustfs' is not configured: RustFS storage is disabled. "
            "Set KTG_RUSTFS_ENABLED=true together with KTG_RUSTFS_ACCESS_KEY and "
            "KTG_RUSTFS_SECRET_KEY to enable it."
        )
    if not config.credentials_configured:
        raise RuntimeError(
            "Dagster resource 'rustfs' is not configured: RustFS access key / secret "
            "key are missing. Set KTG_RUSTFS_ACCESS_KEY and KTG_RUSTFS_SECRET_KEY."
        )
    return RustfsClient(config)


@resource(description="kor-travel-geo Settings loaded from KTG_* environment variables.")
def settings_resource(_context: InitResourceContext) -> Settings:
    """Default Dagster ``settings`` resource — the source for value/settings resources."""
    return Settings()


@resource(
    description=(
        "Authenticated geo admin API client for Dagster onramp calls "
        "(KTG_DAGSTER_ADMIN_API_URL + optional KTG_ADMIN_PROXY_SECRET)."
    )
)
def admin_api_resource(_context: InitResourceContext) -> DagsterAdminApiClient:
    """Default Dagster ``admin_api`` resource for API-backed orchestration onramps."""
    return DagsterAdminApiClient.from_settings(Settings())
