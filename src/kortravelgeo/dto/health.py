"""Health/readiness DTOs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .common import FrozenModel

ComponentStatus = Literal["ok", "degraded", "saturated", "unavailable", "skipped", "unknown"]
ReadinessStatus = Literal["ok", "degraded", "unavailable"]


class ReadinessComponent(FrozenModel):
    status: ComponentStatus
    detail: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float | None = None
    error_type: str | None = None


class ReadinessResponse(FrozenModel):
    status: ReadinessStatus
    ready: bool
    degraded: bool
    components: dict[str, ReadinessComponent]
