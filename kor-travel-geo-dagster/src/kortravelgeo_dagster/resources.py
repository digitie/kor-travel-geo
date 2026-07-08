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
from typing import Any, cast

from dagster import InitResourceContext, resource
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.rustfs import RustfsClient, load_rustfs_config
from kortravelgeo.settings import Settings

__all__ = [
    "client_resource",
    "rustfs_resource",
    "settings_resource",
]


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
