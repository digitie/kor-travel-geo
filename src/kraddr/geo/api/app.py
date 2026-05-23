"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from kraddr.geo.api import _jobs
from kraddr.geo.api.responses import register_exception_handlers
from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.version import __version__

from .routers import admin, geocode, healthz, pobox, reverse, search, zipcode


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    client = AsyncAddressClient()
    await client.__aenter__()
    app.state.client = client
    assert client.engine is not None
    queue = _jobs.JobQueue(client.engine)
    app.state.job_queue = queue
    await queue.recover_startup()
    try:
        yield
    finally:
        await client.__aexit__(None, None, None)


def create_app() -> FastAPI:
    app = FastAPI(
        title="kraddr-geo",
        version=__version__,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/v1/docs",
        openapi_url="/v1/openapi.json",
    )
    register_exception_handlers(app)
    app.include_router(healthz.router, prefix="/v1")
    app.include_router(geocode.router, prefix="/v1")
    app.include_router(reverse.router, prefix="/v1")
    app.include_router(search.router, prefix="/v1")
    app.include_router(zipcode.router, prefix="/v1")
    app.include_router(pobox.router, prefix="/v1")
    app.include_router(admin.router, prefix="/v1/admin")
    return app


app = create_app()

