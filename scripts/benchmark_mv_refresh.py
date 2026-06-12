"""Benchmark ``mv_geocode_target`` refresh strategies.

이 스크립트는 운영 CLI가 아니라 PR/운영 점검용 계측 도구다. 출력 JSON은
문서에 붙여 넣거나 artifacts 디렉터리에 보관할 수 있게 안정적인 필드명을
사용한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.sql import iter_sql_statements
from kortravelgeo.loaders.postload import (
    build_mv_next_sql,
    build_text_search_mv_next_sql,
    normalize_mv_index_names,
    rename_mv_next_indexes_for_conn,
)
from kortravelgeo.settings import get_settings

Strategy = Literal["concurrent", "swap"]
PhaseRunner = Callable[[AsyncEngine], Awaitable[None]]
BENCHMARK_SCHEMA_VERSION = 3


@dataclass(frozen=True, slots=True)
class RelationStats:
    row_count: int | None
    total_bytes: int | None
    heap_bytes: int | None
    index_bytes: int | None
    text_search_row_count: int | None
    text_search_total_bytes: int | None
    text_search_heap_bytes: int | None
    text_search_index_bytes: int | None
    database_bytes: int
    temp_files: int
    temp_bytes: int
    indexes: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class BenchmarkPhase:
    name: str
    seconds: float


@dataclass(frozen=True, slots=True)
class BenchmarkMetadata:
    trial_index: int
    cache_warm_hint: str
    notes: tuple[str, ...]
    concurrent_sessions_before: int
    concurrent_sessions_after: int
    wait_events_before: tuple[tuple[str, int], ...]
    wait_events_after: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    strategy: Strategy
    started_at: str
    finished_at: str
    total_seconds: float
    before: RelationStats
    after: RelationStats
    phases: tuple[BenchmarkPhase, ...]
    metadata: BenchmarkMetadata
    schema_version: int = BENCHMARK_SCHEMA_VERSION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark mv_geocode_target refresh strategies.",
    )
    parser.add_argument(
        "--strategy",
        choices=("concurrent", "swap"),
        required=True,
        help="Refresh strategy to execute.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path. Parent directories are created.",
    )
    parser.add_argument(
        "--trial-index",
        type=int,
        default=1,
        help="1-based trial number recorded in JSON metadata.",
    )
    parser.add_argument(
        "--cache-warm-hint",
        default="unknown",
        help="Free-form cache state hint, e.g. cold, warm, repeated-same-db.",
    )
    parser.add_argument(
        "--note",
        action="append",
        help="Additional metadata note. May be passed multiple times.",
    )
    return parser


async def run_benchmark(
    engine: AsyncEngine,
    strategy: Strategy,
    *,
    trial_index: int = 1,
    cache_warm_hint: str = "unknown",
    notes: Sequence[str] = (),
) -> BenchmarkResult:
    before = await collect_relation_stats(engine)
    concurrent_before = await _concurrent_session_count(engine)
    wait_events_before = await _wait_event_snapshot(engine)
    started = datetime.now(UTC)
    start_clock = time.perf_counter()
    if strategy == "concurrent":
        phases = await _run_phases(
            engine,
            (
                ("refresh_concurrently", _refresh_concurrently),
                ("refresh_text_search_concurrently", _refresh_text_search_concurrently),
                ("analyze", _analyze_mv),
            ),
        )
    else:
        phases = (
            *await _run_phases(engine, (("normalize_index_names", normalize_mv_index_names),)),
            *await _rebuild_mv_next_phases(engine),
            *await _rebuild_text_search_mv_next_phases(engine),
            *await _shadow_swap_phases(engine),
        )
    total_seconds = time.perf_counter() - start_clock
    finished = datetime.now(UTC)
    after = await collect_relation_stats(engine)
    concurrent_after = await _concurrent_session_count(engine)
    wait_events_after = await _wait_event_snapshot(engine)
    return BenchmarkResult(
        strategy=strategy,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        total_seconds=total_seconds,
        before=before,
        after=after,
        phases=phases,
        metadata=BenchmarkMetadata(
            trial_index=trial_index,
            cache_warm_hint=cache_warm_hint,
            notes=tuple(notes),
            concurrent_sessions_before=concurrent_before,
            concurrent_sessions_after=concurrent_after,
            wait_events_before=wait_events_before,
            wait_events_after=wait_events_after,
        ),
    )


async def collect_relation_stats(engine: AsyncEngine) -> RelationStats:
    async with engine.connect() as conn:
        return RelationStats(
            row_count=await _optional_int(conn, "SELECT count(*) FROM mv_geocode_target"),
            total_bytes=await _optional_int(
                conn,
                "SELECT pg_total_relation_size('mv_geocode_target')",
            ),
            heap_bytes=await _optional_int(
                conn,
                "SELECT pg_relation_size('mv_geocode_target')",
            ),
            index_bytes=await _optional_int(
                conn,
                """
SELECT pg_indexes_size('mv_geocode_target')
""",
            ),
            text_search_row_count=await _optional_int(
                conn,
                "SELECT count(*) FROM mv_geocode_text_search",
            ),
            text_search_total_bytes=await _optional_int(
                conn,
                "SELECT pg_total_relation_size('mv_geocode_text_search')",
            ),
            text_search_heap_bytes=await _optional_int(
                conn,
                "SELECT pg_relation_size('mv_geocode_text_search')",
            ),
            text_search_index_bytes=await _optional_int(
                conn,
                "SELECT pg_indexes_size('mv_geocode_text_search')",
            ),
            database_bytes=int(
                await conn.scalar(text("SELECT pg_database_size(current_database())")) or 0
            ),
            temp_files=int(
                await conn.scalar(
                    text(
                        """
SELECT temp_files
  FROM pg_stat_database
 WHERE datname = current_database()
"""
                    )
                )
                or 0
            ),
            temp_bytes=int(
                await conn.scalar(
                    text(
                        """
SELECT temp_bytes
  FROM pg_stat_database
 WHERE datname = current_database()
"""
                    )
                )
                or 0
            ),
            indexes=await _mv_index_sizes(conn),
        )


async def _run_phases(
    engine: AsyncEngine,
    phases: Sequence[tuple[str, PhaseRunner]],
) -> tuple[BenchmarkPhase, ...]:
    results: list[BenchmarkPhase] = []
    for name, runner in phases:
        start = time.perf_counter()
        await runner(engine)
        results.append(BenchmarkPhase(name=name, seconds=time.perf_counter() - start))
    return tuple(results)


async def _refresh_concurrently(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL statement_timeout = 0"))
        await conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geocode_target"))


async def _refresh_text_search_concurrently(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL statement_timeout = 0"))
        await conn.execute(
            text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geocode_text_search")
        )


async def _analyze_mv(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL lock_timeout = '2s'"))
        await conn.execute(text("ANALYZE mv_geocode_target"))
        await conn.execute(text("ANALYZE mv_geocode_text_search"))


async def _rebuild_mv_next_phases(engine: AsyncEngine) -> tuple[BenchmarkPhase, ...]:
    results: list[BenchmarkPhase] = []
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL statement_timeout = 0"))
        for sql in iter_sql_statements(build_mv_next_sql()):
            name = _statement_phase_name(sql)
            start = time.perf_counter()
            await conn.execute(text(sql))
            results.append(BenchmarkPhase(name=name, seconds=time.perf_counter() - start))
    return tuple(results)


async def _rebuild_text_search_mv_next_phases(engine: AsyncEngine) -> tuple[BenchmarkPhase, ...]:
    results: list[BenchmarkPhase] = []
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL statement_timeout = 0"))
        for sql in iter_sql_statements(build_text_search_mv_next_sql()):
            name = _statement_phase_name(sql).replace("rebuild.", "rebuild_text_search.", 1)
            start = time.perf_counter()
            await conn.execute(text(sql))
            results.append(BenchmarkPhase(name=name, seconds=time.perf_counter() - start))
    return tuple(results)


async def _shadow_swap_phases(engine: AsyncEngine) -> tuple[BenchmarkPhase, ...]:
    results: list[BenchmarkPhase] = []
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL lock_timeout = '2s'"))
        current_mv = await conn.scalar(text("SELECT to_regclass('mv_geocode_target')"))
        current_text_search_mv = await conn.scalar(
            text("SELECT to_regclass('mv_geocode_text_search')")
        )
        await _timed_execute(
            conn,
            results,
            "swap.drop_text_search_old_pre",
            "DROP MATERIALIZED VIEW IF EXISTS mv_geocode_text_search_old",
        )
        if current_mv is not None:
            await _timed_execute(
                conn,
                results,
                "swap.drop_old_pre",
                "DROP MATERIALIZED VIEW IF EXISTS mv_geocode_target_old",
            )
        if current_text_search_mv is not None:
            await _timed_execute(
                conn,
                results,
                "swap.rename_text_search_live_to_old",
                "ALTER MATERIALIZED VIEW mv_geocode_text_search "
                "RENAME TO mv_geocode_text_search_old",
            )
        if current_mv is not None:
            await _timed_execute(
                conn,
                results,
                "swap.rename_live_to_old",
                "ALTER MATERIALIZED VIEW mv_geocode_target RENAME TO mv_geocode_target_old",
            )
        await _timed_execute(
            conn,
            results,
            "swap.rename_next_to_live",
            "ALTER MATERIALIZED VIEW mv_geocode_target_next RENAME TO mv_geocode_target",
        )
        await _timed_execute(
            conn,
            results,
            "swap.rename_text_search_next_to_live",
            "ALTER MATERIALIZED VIEW mv_geocode_text_search_next "
            "RENAME TO mv_geocode_text_search",
        )
        if current_text_search_mv is not None:
            await _timed_execute(
                conn,
                results,
                "swap.drop_text_search_old_post",
                "DROP MATERIALIZED VIEW mv_geocode_text_search_old",
            )
        if current_mv is not None:
            await _timed_execute(
                conn,
                results,
                "swap.drop_old_post",
                "DROP MATERIALIZED VIEW mv_geocode_target_old",
            )
        start = time.perf_counter()
        await rename_mv_next_indexes_for_conn(conn)
        results.append(
            BenchmarkPhase(name="swap.rename_indexes", seconds=time.perf_counter() - start)
        )
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL lock_timeout = '2s'"))
        await _timed_execute(conn, results, "swap.analyze_live", "ANALYZE mv_geocode_target")
    return tuple(results)


async def _timed_execute(
    conn: AsyncConnection,
    results: list[BenchmarkPhase],
    name: str,
    sql: str,
) -> None:
    start = time.perf_counter()
    await conn.execute(text(sql))
    results.append(BenchmarkPhase(name=name, seconds=time.perf_counter() - start))


def _statement_phase_name(sql: str) -> str:
    normalized = " ".join(sql.split())
    upper = normalized.upper()
    if upper.startswith("SET SEARCH_PATH") or upper.startswith("SET LOCAL SEARCH_PATH"):
        return "rebuild.set_search_path"
    if upper.startswith("SET MAINTENANCE_WORK_MEM") or upper.startswith(
        "SET LOCAL MAINTENANCE_WORK_MEM"
    ):
        return "rebuild.set_maintenance_work_mem"
    if upper.startswith("SET "):
        return "rebuild.set"
    if upper.startswith("DROP MATERIALIZED VIEW"):
        return "rebuild.drop_next"
    if upper.startswith("CREATE MATERIALIZED VIEW"):
        return "rebuild.create_next"
    if upper.startswith("CREATE UNIQUE INDEX"):
        return "rebuild.index." + _created_index_name(normalized)
    if upper.startswith("CREATE INDEX"):
        return "rebuild.index." + _created_index_name(normalized)
    if upper.startswith("ANALYZE"):
        return "rebuild.analyze_next"
    return "rebuild.statement"


def _created_index_name(normalized_sql: str) -> str:
    parts = normalized_sql.split()
    try:
        return parts[parts.index("INDEX") + 1]
    except (ValueError, IndexError):  # pragma: no cover - defensive fallback
        return "unknown"


async def _optional_int(conn: AsyncConnection, sql: str) -> int | None:
    try:
        value = await conn.scalar(text(sql))
    except ProgrammingError:  # pragma: no cover - missing MV only in manual preflight
        await conn.rollback()
        return None
    return int(value) if value is not None else None


async def _concurrent_session_count(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return int(
            await conn.scalar(
                text(
                    """
SELECT count(*)
  FROM pg_stat_activity
 WHERE datname = current_database()
   AND pid <> pg_backend_pid()
   AND state <> 'idle'
"""
                )
            )
            or 0
        )


async def _wait_event_snapshot(engine: AsyncEngine) -> tuple[tuple[str, int], ...]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
SELECT COALESCE(wait_event_type, '') || ':' || wait_event AS wait_event,
       count(*)::int AS sessions
  FROM pg_stat_activity
 WHERE datname = current_database()
   AND wait_event IS NOT NULL
 GROUP BY wait_event_type, wait_event
 ORDER BY wait_event
"""
            )
        )
        return tuple((str(row[0]), int(row[1])) for row in result)


async def _mv_index_sizes(conn: AsyncConnection) -> tuple[tuple[str, int], ...]:
    result = await conn.execute(
        text(
            """
SELECT i.relname AS index_name,
       pg_total_relation_size(i.oid)::bigint AS bytes
  FROM pg_class i
  JOIN pg_index ix ON ix.indexrelid = i.oid
  JOIN pg_class t ON t.oid = ix.indrelid
  JOIN pg_namespace n ON n.oid = i.relnamespace
 WHERE n.nspname = current_schema()
   AND t.relname IN ('mv_geocode_target', 'mv_geocode_text_search')
 ORDER BY i.relname
"""
        )
    )
    return tuple((str(row[0]), int(row[1])) for row in result)


def result_to_json(result: BenchmarkResult) -> str:
    return json.dumps(asdict(result), ensure_ascii=False, indent=2)


async def _async_main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    engine = make_async_engine(get_settings())
    try:
        result = await run_benchmark(
            engine,
            args.strategy,
            trial_index=args.trial_index,
            cache_warm_hint=args.cache_warm_hint,
            notes=args.note or (),
        )
    finally:
        await engine.dispose()
    payload = result_to_json(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
