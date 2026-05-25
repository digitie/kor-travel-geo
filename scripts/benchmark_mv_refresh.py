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
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kraddr.geo.infra.engine import make_async_engine
from kraddr.geo.infra.sql import iter_sql_statements
from kraddr.geo.loaders.postload import (
    _rename_mv_next_indexes,
    build_mv_next_sql,
    normalize_mv_index_names,
)
from kraddr.geo.settings import get_settings

Strategy = Literal["concurrent", "swap"]
PhaseRunner = Callable[[AsyncEngine], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class RelationStats:
    row_count: int | None
    total_bytes: int | None
    heap_bytes: int | None
    index_bytes: int | None
    database_bytes: int
    temp_files: int
    temp_bytes: int
    indexes: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class BenchmarkPhase:
    name: str
    seconds: float


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    strategy: Strategy
    started_at: str
    finished_at: str
    total_seconds: float
    before: RelationStats
    after: RelationStats
    phases: tuple[BenchmarkPhase, ...]


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
    return parser


async def run_benchmark(engine: AsyncEngine, strategy: Strategy) -> BenchmarkResult:
    before = await collect_relation_stats(engine)
    started = datetime.now(UTC)
    start_clock = time.perf_counter()
    if strategy == "concurrent":
        phases = await _run_phases(
            engine,
            (
                ("refresh_concurrently", _refresh_concurrently),
                ("analyze", _analyze_mv),
            ),
        )
    else:
        phases = (
            *await _run_phases(engine, (("normalize_index_names", normalize_mv_index_names),)),
            *await _rebuild_mv_next_phases(engine),
            *await _shadow_swap_phases(engine),
        )
    total_seconds = time.perf_counter() - start_clock
    finished = datetime.now(UTC)
    after = await collect_relation_stats(engine)
    return BenchmarkResult(
        strategy=strategy,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        total_seconds=total_seconds,
        before=before,
        after=after,
        phases=phases,
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
        await conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geocode_target"))


async def _analyze_mv(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("ANALYZE mv_geocode_target"))


async def _rebuild_mv_next_phases(engine: AsyncEngine) -> tuple[BenchmarkPhase, ...]:
    results: list[BenchmarkPhase] = []
    async with engine.begin() as conn:
        for sql in iter_sql_statements(build_mv_next_sql()):
            name = _statement_phase_name(sql)
            start = time.perf_counter()
            await conn.execute(text(sql))
            results.append(BenchmarkPhase(name=name, seconds=time.perf_counter() - start))
    return tuple(results)


async def _shadow_swap_phases(engine: AsyncEngine) -> tuple[BenchmarkPhase, ...]:
    results: list[BenchmarkPhase] = []
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL lock_timeout = '2s'"))
        current_mv = await conn.scalar(text("SELECT to_regclass('mv_geocode_target')"))
        if current_mv is not None:
            await _timed_execute(
                conn,
                results,
                "swap.drop_old_pre",
                "DROP MATERIALIZED VIEW IF EXISTS mv_geocode_target_old",
            )
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
        if current_mv is not None:
            await _timed_execute(
                conn,
                results,
                "swap.drop_old_post",
                "DROP MATERIALIZED VIEW mv_geocode_target_old",
            )
        start = time.perf_counter()
        await _rename_mv_next_indexes(conn)
        results.append(
            BenchmarkPhase(name="swap.rename_indexes", seconds=time.perf_counter() - start)
        )
    async with engine.begin() as conn:
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
    if upper.startswith("SET "):
        return "rebuild.set_search_path"
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
    except Exception:  # pragma: no cover - missing MV only in manual preflight
        return None
    return int(value) if value is not None else None


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
   AND t.relname = 'mv_geocode_target'
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
        result = await run_benchmark(engine, args.strategy)
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
