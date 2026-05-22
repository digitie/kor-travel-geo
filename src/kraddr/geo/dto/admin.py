"""Admin and debugging DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import FrozenModel

LoadJobState = Literal["queued", "running", "done", "failed", "cancelled"]


class TableStat(FrozenModel):
    table_name: str
    row_count: int = Field(ge=0)
    size_bytes: int | None = Field(default=None, ge=0)
    updated_at: str | None = None


class NormalizeRequest(FrozenModel):
    address: str = Field(min_length=1, max_length=200)


class NormalizeResponse(FrozenModel):
    original: str
    normalized: str
    tokens: tuple[str, ...] = ()


class ExplainRequest(FrozenModel):
    sql: str = Field(min_length=1)
    analyze: bool = False
    buffers: bool = False


class ExplainResponse(FrozenModel):
    plan: object


class LoadJobStatus(FrozenModel):
    job_id: str
    kind: str
    state: LoadJobState
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    current_stage: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    error: str | None = None
    log_tail: tuple[str, ...] = ()


class CacheMetrics(FrozenModel):
    enabled: bool
    entries: int = Field(ge=0)
    hits: int = Field(ge=0)
    expired: int = Field(ge=0)
