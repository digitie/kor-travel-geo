"""FastAPI dependency helpers."""

from __future__ import annotations

from typing import cast

from fastapi import Request

from kortravelgeo.api._jobs import JobQueue
from kortravelgeo.client import AsyncAddressClient


def get_client(request: Request) -> AsyncAddressClient:
    return cast("AsyncAddressClient", request.app.state.client)


def get_job_queue(request: Request) -> JobQueue:
    return cast("JobQueue", request.app.state.job_queue)
