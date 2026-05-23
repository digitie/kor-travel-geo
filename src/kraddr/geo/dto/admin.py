"""Admin and debugging DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .common import FrozenModel

LoadJobState = Literal["queued", "running", "done", "failed", "cancelled"]
LoadJobKind = Literal[
    "full_load_batch",
    "juso_text_load",
    "locsum_load",
    "navi_load",
    "shp_polygons_load",
    "shp_polygons_delta",
    "pobox_load",
    "bulk_load",
    "mv_refresh",
    "consistency_check",
]
ConsistencySeverity = Literal["OK", "INFO", "WARN", "ERROR"]


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
    kind: LoadJobKind | str
    state: LoadJobState
    load_batch_id: str | None = None
    parent_job_id: str | None = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    current_stage: str | None = None
    source_yyyymm: str | None = None
    source_set: dict[str, str] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    error_message: str | None = None
    log_tail: tuple[str, ...] = ()
    payload_summary: dict[str, Any] | None = None


class CacheMetrics(FrozenModel):
    enabled: bool
    entries: int = Field(ge=0)
    hits: int = Field(ge=0)
    expired: int = Field(ge=0)


class LoadSubmitRequest(FrozenModel):
    kind: LoadJobKind | str
    payload: dict[str, Any] = Field(default_factory=dict)


class ConsistencyRunRequest(FrozenModel):
    scope: Literal["full", "sido", "recent"] = "full"
    sido: str | None = None
    recent_days: int = Field(default=7, ge=1, le=365)
    cases: tuple[str, ...] | None = None


class ConsistencyCase(FrozenModel):
    code: str
    name: str
    severity: ConsistencySeverity
    count: int = Field(ge=0)
    ratio: float | None = Field(default=None, ge=0.0)
    threshold: str | None = None
    metric: dict[str, float] | None = None
    sample: tuple[dict[str, Any], ...] = ()
    note: str | None = None


class ConsistencyReportSummary(FrozenModel):
    report_id: str
    scope: str
    severity_max: ConsistencySeverity
    source_set: dict[str, str]
    started_at: datetime
    finished_at: datetime | None = None
    generated_by: Literal["cli", "api", "cron"] = "api"


class ConsistencyReport(ConsistencyReportSummary):
    cases: tuple[ConsistencyCase, ...] = ()
