"""Dagster materialized-view refresh job (T-290a wiring proof).

Minimal ``@op`` + ``@job`` that refreshes the geo serving materialized views
(``mv_geocode_target`` / ``mv_geocode_text_search``). Dagster owns only the
orchestration; the actual refresh logic is the main-lib leaf
``kortravelgeo.loaders.postload.refresh_mv`` called as-is (no domain-logic
reimplementation — dagster-boundary §4).

IMPORTANT (dagster-boundary §10): this module must NOT use
``from __future__ import annotations`` — Dagster validates the ``@op`` function's
``context`` type at runtime, which requires real (non-stringized) annotations.
"""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from dagster import Bool, Failure, Field, OpExecutionContext, String, job, op
from kortravelgeo.loaders.postload import refresh_mv

if TYPE_CHECKING:
    from kortravelgeo.client import AsyncAddressClient

__all__ = [
    "MV_REFRESH_JOBS",
    "MV_REFRESH_JOB_TAGS",
    "mv_refresh_job",
    "refresh_geocode_mv_op",
]

MV_REFRESH_JOB_TAGS: Final[dict[str, str]] = {
    "kor_travel_geo.job_scope": "maintenance",
    "kor_travel_geo.job_kind": "mv_refresh",
}
"""Common tags for the mv_refresh Dagster job."""

_MV_REFRESH_CONFIG_SCHEMA: Final[dict[str, object]] = {
    "strategy": Field(
        String,
        default_value="concurrent",
        description=(
            "MV refresh strategy. 'concurrent' runs REFRESH MATERIALIZED VIEW "
            "[CONCURRENTLY]; 'swap' rebuilds shadow MVs then renames them into place "
            "(ADR-007/ADR-017)."
        ),
    ),
    "concurrently": Field(
        Bool,
        default_value=True,
        description=(
            "Whether the 'concurrent' strategy uses CONCURRENTLY. Ignored by the "
            "'swap' strategy."
        ),
    ),
}


@op(
    name="refresh_geocode_mv",
    description=(
        "Refresh the geo serving MVs (mv_geocode_target / mv_geocode_text_search) by "
        "calling the main-lib leaf refresh_mv with the client resource's engine."
    ),
    required_resource_keys={"client"},
    config_schema=_MV_REFRESH_CONFIG_SCHEMA,
)
async def refresh_geocode_mv_op(context: OpExecutionContext) -> dict[str, object]:
    """Run the geo MV-refresh leaf (``refresh_mv``) as a Dagster op.

    Passes the ``client`` resource's (``AsyncAddressClient``) engine straight to
    ``refresh_mv`` and records reference/summary metadata. MV refresh is idempotent,
    but the 'swap' strategy performs DROP/RENAME, so this wiring-proof op does NOT
    attach a RetryPolicy (conservative — ADR-066 §4).
    """
    client = cast("AsyncAddressClient", _resource_object(context, "client"))
    config = cast("Mapping[str, object]", context.op_config)
    strategy = _mv_strategy(config.get("strategy"))
    concurrently = _bool_config(config.get("concurrently"), default=True)

    await refresh_mv(client._engine(), concurrently=concurrently, strategy=strategy)

    metadata: dict[str, object] = {
        "strategy": strategy,
        "concurrently": concurrently,
        "materialized_views": ["mv_geocode_target", "mv_geocode_text_search"],
    }
    context.add_output_metadata(metadata)
    return metadata


@job(
    name="mv_refresh",
    tags=MV_REFRESH_JOB_TAGS,
    description="Refresh the geo serving materialized views (T-290a wiring proof).",
)
def mv_refresh_job() -> None:
    """Operator-facing mv_refresh job (note: op name != job name)."""
    refresh_geocode_mv_op()


MV_REFRESH_JOBS: Final = [mv_refresh_job]
"""Job list aggregated by ``definitions.py``."""


def _resource_object(context: OpExecutionContext, name: str) -> object:
    resources = cast("Any", context.resources)
    if not hasattr(resources, name):
        raise AttributeError(f"Dagster resource missing: {name}")
    return getattr(resources, name)


def _mv_strategy(value: object) -> Literal["concurrent", "swap"]:
    if value is None or value == "concurrent":
        return "concurrent"
    if value == "swap":
        return "swap"
    raise Failure(
        description=f"mv_refresh strategy must be 'concurrent' or 'swap': {value!r}"
    )


def _bool_config(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    raise TypeError("boolean config value expected")
