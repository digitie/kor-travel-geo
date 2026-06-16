"""Runtime cache/buffer warm helpers for cold-start and serving swaps."""

from __future__ import annotations

import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

RuntimeWarmMode = Literal["plan", "execute"]
RuntimeWarmStepMode = Literal["automatic", "optional"]
RuntimeWarmExecutionStatus = Literal["planned", "skipped", "succeeded", "warning", "failed"]

RUNTIME_WARM_REPORT_SCHEMA_VERSION = 1
DEFAULT_RUNTIME_WARM_QUERY_LIMIT = 32
DEFAULT_RUNTIME_WARM_STATEMENT_TIMEOUT_MS = 30_000
DEFAULT_RUNTIME_WARM_PREWARM_RELATIONS: tuple[str, ...] = (
    "mv_geocode_target",
    "mv_geocode_text_search",
    "region_radius_parts",
)

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


@dataclass(frozen=True, slots=True)
class RuntimeWarmStep:
    step_id: str
    mode: RuntimeWarmStepMode
    required: bool
    command: str
    reason: str
    lock_impact: str
    notes: str


@dataclass(frozen=True, slots=True)
class RuntimeWarmExecution:
    step_id: str
    status: RuntimeWarmExecutionStatus
    seconds: float | None = None
    row_count: int | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeWarmRelation:
    relation_name: str
    regclass: str | None


@dataclass(frozen=True, slots=True)
class RuntimeWarmAvailability:
    pg_prewarm_schema: str | None
    relations: tuple[RuntimeWarmRelation, ...]


@dataclass(frozen=True, slots=True)
class RuntimeWarmQueryProfile:
    step_id: str
    statement: Any
    required_relations: tuple[str, ...]
    local_similarity_threshold: float | None = None


@dataclass(frozen=True, slots=True)
class RuntimeWarmReport:
    schema_version: int
    task_id: str
    mode: RuntimeWarmMode
    started_at: str
    finished_at: str
    settings: Mapping[str, Any]
    steps: tuple[RuntimeWarmStep, ...]
    executions: tuple[RuntimeWarmExecution, ...]
    availability: RuntimeWarmAvailability | None


_GEOCODE_EXACT_WARM_SQL = text(
    """
WITH samples AS MATERIALIZED (
  SELECT rncode_full, buld_mnnm, buld_slno, buld_se_cd
    FROM mv_geocode_target
   WHERE rncode_full IS NOT NULL
     AND buld_mnnm IS NOT NULL
   ORDER BY bd_mgt_sn
   LIMIT :sample_limit
)
SELECT warmed.bd_mgt_sn
  FROM samples s
  JOIN LATERAL (
    SELECT t.bd_mgt_sn
      FROM mv_geocode_target t
     WHERE t.rncode_full = s.rncode_full
       AND t.buld_mnnm IS NOT DISTINCT FROM s.buld_mnnm
       AND t.buld_slno IS NOT DISTINCT FROM s.buld_slno
       AND t.buld_se_cd IS NOT DISTINCT FROM s.buld_se_cd
     ORDER BY t.bd_mgt_sn
     LIMIT 1
  ) warmed ON true
 LIMIT :sample_limit
"""
)

_SEARCH_TEXT_WARM_SQL = text(
    """
WITH samples AS MATERIALIZED (
  SELECT rn_nrm
    FROM mv_geocode_text_search
   WHERE rn_nrm IS NOT NULL
     AND rn_nrm <> ''
   ORDER BY bd_mgt_sn
   LIMIT :sample_limit
),
queries AS MATERIALIZED (
  SELECT left(rn_nrm, LEAST(6, char_length(rn_nrm))) AS query_nrm
    FROM samples
   WHERE char_length(rn_nrm) >= 2
)
SELECT warmed.bd_mgt_sn
  FROM queries q
  JOIN LATERAL (
    SELECT ts.bd_mgt_sn
      FROM mv_geocode_text_search ts
     WHERE ts.rn_nrm ILIKE '%' || q.query_nrm || '%'
        OR ts.rn_nrm % q.query_nrm
     ORDER BY ts.bd_mgt_sn
     LIMIT 3
  ) warmed ON true
 LIMIT :sample_limit
"""
)

_REVERSE_NEAREST_WARM_SQL = text(
    """
WITH samples AS MATERIALIZED (
  SELECT pt_4326
    FROM mv_geocode_target
   WHERE pt_4326 IS NOT NULL
     AND pt_5179 IS NOT NULL
   ORDER BY bd_mgt_sn
   LIMIT :sample_limit
)
SELECT warmed.bd_mgt_sn
  FROM samples s
  JOIN LATERAL (
    SELECT t.bd_mgt_sn
      FROM mv_geocode_target t
     WHERE t.pt_5179 IS NOT NULL
     ORDER BY t.pt_5179 <-> ST_Transform(s.pt_4326, 5179)
     LIMIT 1
  ) warmed ON true
 LIMIT :sample_limit
"""
)

_REGION_RADIUS_WARM_SQL = text(
    """
WITH samples AS MATERIALIZED (
  SELECT pt_4326
    FROM mv_geocode_target
   WHERE pt_4326 IS NOT NULL
     AND pt_5179 IS NOT NULL
   ORDER BY bd_mgt_sn
   LIMIT :sample_limit
)
SELECT warmed.code
  FROM samples s
  JOIN LATERAL (
    SELECT r.code
      FROM region_radius_parts r
     WHERE ST_DWithin(r.geom, ST_Transform(s.pt_4326, 5179), 250)
     ORDER BY ST_Area(r.geom), r.level, r.code
     LIMIT 3
  ) warmed ON true
 LIMIT :sample_limit
"""
)

_QUERY_PROFILES: tuple[RuntimeWarmQueryProfile, ...] = (
    RuntimeWarmQueryProfile(
        step_id="query.geocode_exact",
        statement=_GEOCODE_EXACT_WARM_SQL,
        required_relations=("mv_geocode_target",),
    ),
    RuntimeWarmQueryProfile(
        step_id="query.search_text",
        statement=_SEARCH_TEXT_WARM_SQL,
        required_relations=("mv_geocode_text_search",),
        local_similarity_threshold=0.42,
    ),
    RuntimeWarmQueryProfile(
        step_id="query.reverse_nearest",
        statement=_REVERSE_NEAREST_WARM_SQL,
        required_relations=("mv_geocode_target",),
    ),
    RuntimeWarmQueryProfile(
        step_id="query.region_radius",
        statement=_REGION_RADIUS_WARM_SQL,
        required_relations=("mv_geocode_target", "region_radius_parts"),
    ),
)


def build_runtime_warm_plan(
    *,
    prewarm_enabled: bool = False,
    prewarm_relations: Sequence[str] = DEFAULT_RUNTIME_WARM_PREWARM_RELATIONS,
) -> tuple[RuntimeWarmStep, ...]:
    relations = ", ".join(dict.fromkeys(prewarm_relations)) or "(none)"
    return (
        RuntimeWarmStep(
            step_id="catalog.available",
            mode="automatic",
            required=True,
            command="collect_runtime_warm_availability()",
            reason="확장과 serving relation 존재 여부를 확인해 startup warm 실패를 격리한다.",
            lock_impact="read-only catalog query",
            notes="relation이 없으면 해당 query warm만 skipped로 기록한다.",
        ),
        RuntimeWarmStep(
            step_id="buffer.pg_prewarm",
            mode="optional",
            required=prewarm_enabled,
            command=f"pg_prewarm({relations})",
            reason="재기동이나 hot-swap 직후 shared buffer cold spike를 줄인다.",
            lock_impact="읽기 IO와 shared buffer pressure; 명시 옵션에서만 실행한다.",
            notes="pg_prewarm extension이 없으면 warning 없이 skipped로 남긴다.",
        ),
        RuntimeWarmStep(
            step_id="query.geocode_exact",
            mode="automatic",
            required=True,
            command="warm indexed road-address exact lookup probes",
            reason="v1/v2 geocode exact path의 btree index와 MV heap page를 데운다.",
            lock_impact="read-only limited SELECT",
            notes="sample_limit으로 bounded execution을 유지한다.",
        ),
        RuntimeWarmStep(
            step_id="query.search_text",
            mode="automatic",
            required=True,
            command="warm text-search probes with transaction-local pg_trgm threshold",
            reason="search/address fuzzy path의 text-search MV와 trgm index를 데운다.",
            lock_impact="read-only limited SELECT",
            notes="pg_trgm.similarity_threshold는 SET LOCAL equivalent만 사용한다.",
        ),
        RuntimeWarmStep(
            step_id="query.reverse_nearest",
            mode="automatic",
            required=True,
            command="warm nearest reverse KNN probes",
            reason="reverse nearest path의 point GiST index와 대표 heap page를 데운다.",
            lock_impact="read-only limited SELECT",
            notes="좌표 순서는 내부 geometry에서만 사용하고 외부 입력은 받지 않는다.",
        ),
        RuntimeWarmStep(
            step_id="query.region_radius",
            mode="automatic",
            required=True,
            command="warm region_radius_parts spatial probes",
            reason="reverse/region radius path의 subdivided polygon index를 데운다.",
            lock_impact="read-only limited SELECT",
            notes="region_radius_parts가 없으면 skipped로 기록한다.",
        ),
    )


async def collect_runtime_warm_availability(
    engine: AsyncEngine,
    *,
    relation_names: Sequence[str],
) -> RuntimeWarmAvailability:
    relation_tuple = tuple(dict.fromkeys(relation_names))
    async with engine.connect() as conn:
        pg_prewarm_schema = await conn.scalar(
            text(
                """
SELECT n.nspname
  FROM pg_extension e
  JOIN pg_namespace n ON n.oid = e.extnamespace
 WHERE e.extname = 'pg_prewarm'
"""
            )
        )
        relations: list[RuntimeWarmRelation] = []
        for relation_name in relation_tuple:
            regclass = await conn.scalar(
                text("SELECT to_regclass(:relation_name)::text"),
                {"relation_name": relation_name},
            )
            relations.append(
                RuntimeWarmRelation(
                    relation_name=relation_name,
                    regclass=str(regclass) if regclass is not None else None,
                )
            )
    return RuntimeWarmAvailability(
        pg_prewarm_schema=str(pg_prewarm_schema) if pg_prewarm_schema is not None else None,
        relations=tuple(relations),
    )


async def run_runtime_warm(
    engine: AsyncEngine,
    *,
    mode: RuntimeWarmMode = "execute",
    prewarm_enabled: bool = False,
    prewarm_relations: Sequence[str] = DEFAULT_RUNTIME_WARM_PREWARM_RELATIONS,
    query_limit: int = DEFAULT_RUNTIME_WARM_QUERY_LIMIT,
    statement_timeout_ms: int = DEFAULT_RUNTIME_WARM_STATEMENT_TIMEOUT_MS,
) -> RuntimeWarmReport:
    started_at = _utc_now()
    relation_names = _runtime_warm_relation_names(prewarm_relations)
    steps = build_runtime_warm_plan(
        prewarm_enabled=prewarm_enabled,
        prewarm_relations=prewarm_relations,
    )
    if mode == "plan":
        plan_executions = tuple(
            RuntimeWarmExecution(
                step_id=step.step_id,
                status="planned" if step.required else "skipped",
                detail="plan mode" if step.required else "optional disabled",
            )
            for step in steps
        )
        return _runtime_warm_report(
            mode=mode,
            started_at=started_at,
            settings=_runtime_warm_settings(
                prewarm_enabled=prewarm_enabled,
                prewarm_relations=prewarm_relations,
                query_limit=query_limit,
                statement_timeout_ms=statement_timeout_ms,
            ),
            steps=steps,
            executions=plan_executions,
            availability=None,
        )

    availability = await collect_runtime_warm_availability(
        engine,
        relation_names=relation_names,
    )
    available = {
        relation.relation_name
        for relation in availability.relations
        if relation.regclass is not None
    }
    executions: list[RuntimeWarmExecution] = [
        RuntimeWarmExecution(
            step_id="catalog.available",
            status="succeeded",
            row_count=len(availability.relations),
            detail=f"pg_prewarm={'yes' if availability.pg_prewarm_schema else 'no'}",
        )
    ]
    executions.append(
        await _execute_prewarm(
            engine,
            availability=availability,
            prewarm_enabled=prewarm_enabled,
            prewarm_relations=prewarm_relations,
            statement_timeout_ms=statement_timeout_ms,
        )
    )
    for profile in _QUERY_PROFILES:
        executions.append(
            await _execute_query_profile(
                engine,
                profile=profile,
                available_relations=available,
                query_limit=query_limit,
                statement_timeout_ms=statement_timeout_ms,
            )
        )
    return _runtime_warm_report(
        mode=mode,
        started_at=started_at,
        settings=_runtime_warm_settings(
            prewarm_enabled=prewarm_enabled,
            prewarm_relations=prewarm_relations,
            query_limit=query_limit,
            statement_timeout_ms=statement_timeout_ms,
        ),
        steps=steps,
        executions=tuple(executions),
        availability=availability,
    )


def runtime_warm_report_to_dict(report: RuntimeWarmReport) -> dict[str, Any]:
    return asdict(report)


def runtime_warm_report_metrics(report: RuntimeWarmReport) -> dict[str, int | float]:
    error_count = sum(1 for execution in report.executions if execution.status == "failed")
    warning_count = sum(1 for execution in report.executions if execution.status == "warning")
    return {
        "samples": sum(execution.row_count or 0 for execution in report.executions),
        "error_count": error_count,
        "warning_count": warning_count,
        "error_rate": 0.0 if not report.executions else error_count / len(report.executions),
        "max_ms": round(
            max((execution.seconds or 0.0 for execution in report.executions), default=0.0)
            * 1000,
            3,
        ),
    }


def _runtime_warm_relation_names(prewarm_relations: Sequence[str]) -> tuple[str, ...]:
    names: list[str] = list(prewarm_relations)
    for profile in _QUERY_PROFILES:
        names.extend(profile.required_relations)
    return tuple(dict.fromkeys(name for name in names if name))


def _runtime_warm_settings(
    *,
    prewarm_enabled: bool,
    prewarm_relations: Sequence[str],
    query_limit: int,
    statement_timeout_ms: int,
) -> Mapping[str, Any]:
    return {
        "prewarm_enabled": prewarm_enabled,
        "prewarm_relations": tuple(dict.fromkeys(prewarm_relations)),
        "query_limit": query_limit,
        "statement_timeout_ms": statement_timeout_ms,
    }


def _runtime_warm_report(
    *,
    mode: RuntimeWarmMode,
    started_at: str,
    settings: Mapping[str, Any],
    steps: tuple[RuntimeWarmStep, ...],
    executions: tuple[RuntimeWarmExecution, ...],
    availability: RuntimeWarmAvailability | None,
) -> RuntimeWarmReport:
    return RuntimeWarmReport(
        schema_version=RUNTIME_WARM_REPORT_SCHEMA_VERSION,
        task_id="T-162",
        mode=mode,
        started_at=started_at,
        finished_at=_utc_now(),
        settings=settings,
        steps=steps,
        executions=executions,
        availability=availability,
    )


async def _execute_prewarm(
    engine: AsyncEngine,
    *,
    availability: RuntimeWarmAvailability,
    prewarm_enabled: bool,
    prewarm_relations: Sequence[str],
    statement_timeout_ms: int,
) -> RuntimeWarmExecution:
    if not prewarm_enabled:
        return RuntimeWarmExecution(
            step_id="buffer.pg_prewarm",
            status="skipped",
            detail="disabled by setting",
        )
    if availability.pg_prewarm_schema is None:
        return RuntimeWarmExecution(
            step_id="buffer.pg_prewarm",
            status="skipped",
            detail="pg_prewarm extension is not installed",
        )
    relation_regclass = {
        relation.relation_name: relation.regclass for relation in availability.relations
    }
    present = tuple(
        dict.fromkeys(
            relation_name
            for relation_name in prewarm_relations
            if relation_regclass.get(relation_name) is not None
        )
    )
    if not present:
        return RuntimeWarmExecution(
            step_id="buffer.pg_prewarm",
            status="skipped",
            detail="no configured prewarm relation exists",
        )
    started = time.perf_counter()
    try:
        block_count = 0
        async with engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('statement_timeout', :timeout_ms, true)"),
                {"timeout_ms": str(statement_timeout_ms)},
            )
            function_name = f"{_quote_identifier(availability.pg_prewarm_schema)}.pg_prewarm"
            for relation_name in present:
                warmed = await conn.scalar(
                    text(
                        "SELECT "
                        f"{function_name}(to_regclass(:relation_name), 'buffer')::bigint"
                    ),
                    {"relation_name": relation_name},
                )
                if warmed is not None:
                    block_count += int(warmed)
    except Exception as exc:
        return RuntimeWarmExecution(
            step_id="buffer.pg_prewarm",
            status="warning",
            seconds=round(time.perf_counter() - started, 6),
            detail=_format_exception(exc),
        )
    return RuntimeWarmExecution(
        step_id="buffer.pg_prewarm",
        status="succeeded",
        seconds=round(time.perf_counter() - started, 6),
        row_count=block_count,
        detail=f"relations={len(present)}",
    )


async def _execute_query_profile(
    engine: AsyncEngine,
    *,
    profile: RuntimeWarmQueryProfile,
    available_relations: set[str],
    query_limit: int,
    statement_timeout_ms: int,
) -> RuntimeWarmExecution:
    missing = tuple(
        relation
        for relation in profile.required_relations
        if relation not in available_relations
    )
    if missing:
        return RuntimeWarmExecution(
            step_id=profile.step_id,
            status="skipped",
            detail=f"missing relation: {', '.join(missing)}",
        )
    started = time.perf_counter()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('statement_timeout', :timeout_ms, true)"),
                {"timeout_ms": str(statement_timeout_ms)},
            )
            if profile.local_similarity_threshold is not None:
                await conn.execute(
                    text("SELECT set_config('pg_trgm.similarity_threshold', :value, true)"),
                    {"value": f"{profile.local_similarity_threshold:.2f}"},
                )
            result = await conn.execute(
                profile.statement,
                {"sample_limit": query_limit},
            )
            row_count = len(result.all())
    except Exception as exc:
        return RuntimeWarmExecution(
            step_id=profile.step_id,
            status="failed",
            seconds=round(time.perf_counter() - started, 6),
            detail=_format_exception(exc),
        )
    return RuntimeWarmExecution(
        step_id=profile.step_id,
        status="succeeded",
        seconds=round(time.perf_counter() - started, 6),
        row_count=row_count,
    )


def _quote_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        msg = f"invalid PostgreSQL identifier: {value!r}"
        raise ValueError(msg)
    return '"' + value.replace('"', '""') + '"'


def _format_exception(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
