"""Raw SQL admin repository for load jobs and consistency reports."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.core.protocols import ConsistencyReportRow, LoadJobRow
from kraddr.geo.dto.admin import CacheMetrics, TableStat
from kraddr.geo.exceptions import InvalidInputError

from ._rows import map_consistency_report, map_load_job

_JOB_SELECT = """
SELECT job_id, kind, state, load_batch_id, parent_job_id,
       progress, current_stage, source_yyyymm, source_set,
       started_at, finished_at, heartbeat_at, error_message, log_tail, payload_summary
  FROM load_jobs
"""


class AdminRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def get_load_job(self, job_id: str) -> LoadJobRow | None:
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    text(_JOB_SELECT + " WHERE job_id = :job_id"),
                    {"job_id": job_id},
                )
            ).mappings().first()
        return map_load_job(dict(row)) if row else None

    async def list_load_jobs(
        self,
        *,
        kind: str | None = None,
        state: str | None = None,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[LoadJobRow]:
        clauses = []
        params: dict[str, Any] = {"limit": limit}
        if kind is not None:
            clauses.append("kind = :kind")
            params["kind"] = kind
        if state is not None:
            clauses.append("state = :state")
            params["state"] = state
        if since is not None:
            clauses.append("created_at >= :since")
            params["since"] = since
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = text(_JOB_SELECT + where + " ORDER BY created_at DESC LIMIT :limit")
        async with self.engine.connect() as conn:
            rows = (await conn.execute(sql, params)).mappings().all()
        return [map_load_job(dict(row)) for row in rows]

    async def table_stats(self, *, limit: int = 200) -> list[TableStat]:
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
SELECT relname AS table_name,
       GREATEST(n_live_tup, 0)::bigint AS row_count,
       pg_total_relation_size(relid)::bigint AS size_bytes,
       NULLIF(
         GREATEST(
           COALESCE(last_vacuum, '-infinity'::timestamptz),
           COALESCE(last_autovacuum, '-infinity'::timestamptz),
           COALESCE(last_analyze, '-infinity'::timestamptz),
           COALESCE(last_autoanalyze, '-infinity'::timestamptz)
         ),
         '-infinity'::timestamptz
       )::text AS updated_at
  FROM pg_stat_user_tables
 WHERE schemaname = 'public'
 ORDER BY relname
 LIMIT :limit
"""
                    ),
                    {"limit": limit},
                )
            ).mappings().all()
        return [
            TableStat(
                table_name=str(row["table_name"]),
                row_count=int(row["row_count"] or 0),
                size_bytes=int(row["size_bytes"]) if row["size_bytes"] is not None else None,
                updated_at=str(row["updated_at"]) if row["updated_at"] is not None else None,
            )
            for row in rows
        ]

    async def explain(
        self,
        sql: str,
        *,
        analyze: bool = False,
        buffers: bool = False,
    ) -> object:
        query = _validated_explain_sql(sql)
        options = ["FORMAT JSON"]
        if analyze:
            options.append("ANALYZE")
        if buffers:
            options.append("BUFFERS")
        async with self.engine.connect() as conn:
            plan = await conn.scalar(text(f"EXPLAIN ({', '.join(options)}) {query}"))
        return plan

    async def cache_metrics(self, *, enabled: bool) -> CacheMetrics:
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        """
SELECT count(*)::bigint AS entries,
       COALESCE(sum(hit_count), 0)::bigint AS hits,
       count(*) FILTER (WHERE expires_at <= now())::bigint AS expired
  FROM geo_cache
"""
                    )
                )
            ).mappings().one()
        return CacheMetrics(
            enabled=enabled,
            entries=int(row["entries"] or 0),
            hits=int(row["hits"] or 0),
            expired=int(row["expired"] or 0),
        )

    async def load_job_metric_counts(self) -> list[tuple[str, str, int]]:
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
SELECT kind, state, count(*)::bigint AS count
  FROM load_jobs
 GROUP BY kind, state
 ORDER BY kind, state
"""
                    )
                )
            ).mappings().all()
        return [(str(row["kind"]), str(row["state"]), int(row["count"])) for row in rows]

    async def recent_log_lines(self, *, limit: int = 200) -> list[str]:
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
SELECT job_id, kind, state, log_tail
  FROM load_jobs
 WHERE jsonb_array_length(log_tail) > 0
 ORDER BY COALESCE(heartbeat_at, finished_at, started_at, created_at) DESC
 LIMIT :limit
"""
                    ),
                    {"limit": limit},
                )
            ).mappings().all()
        lines: list[str] = []
        for row in rows:
            tail = row["log_tail"]
            if not isinstance(tail, list):
                continue
            prefix = f"{row['job_id']} {row['kind']} {row['state']}"
            lines.extend(f"{prefix} | {line}" for line in tail if isinstance(line, str))
        return lines[-limit:]

    async def insert_load_job(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        job_id: str | None = None,
        load_batch_id: str | None = None,
        parent_job_id: str | None = None,
        state: str = "queued",
        progress: float = 0.0,
        current_stage: str | None = None,
    ) -> LoadJobRow:
        resolved_job_id = job_id or f"job_{uuid4().hex}"
        payload_summary = _summarize_payload(payload)
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    _json_text(
                        """
INSERT INTO load_jobs
  (job_id, kind, payload, state, load_batch_id, parent_job_id,
   progress, current_stage, payload_summary)
VALUES
  (:job_id, :kind, :payload, :state, :load_batch_id, :parent_job_id,
   :progress, :current_stage, :payload_summary)
RETURNING job_id, kind, state, load_batch_id, parent_job_id,
          progress, current_stage, source_yyyymm, source_set,
          started_at, finished_at, heartbeat_at, error_message, log_tail, payload_summary
""",
                        "payload",
                        "payload_summary",
                    ),
                    {
                        "job_id": resolved_job_id,
                        "kind": kind,
                        "payload": payload,
                        "state": state,
                        "load_batch_id": load_batch_id,
                        "parent_job_id": parent_job_id,
                        "progress": progress,
                        "current_stage": current_stage,
                        "payload_summary": payload_summary,
                    },
                )
            ).mappings().one()
        return map_load_job(dict(row))

    async def insert_load_batch(
        self,
        *,
        payload: dict[str, Any],
        children: Sequence[tuple[str, dict[str, Any]]],
        job_id: str | None = None,
    ) -> LoadJobRow:
        """Create a batch root row and first-stage child jobs in one transaction."""

        root_job_id = job_id or f"batch_{uuid4().hex}"
        root_summary = _summarize_payload(payload)
        async with self.engine.begin() as conn:
            root = (
                await conn.execute(
                    _json_text(
                        """
INSERT INTO load_jobs
  (job_id, kind, payload, state, load_batch_id, progress, current_stage,
   payload_summary, started_at, heartbeat_at)
VALUES
  (:job_id, 'full_load_batch', :payload, 'running', :load_batch_id, 0.0,
   'source_loads', :payload_summary, now(), now())
RETURNING job_id, kind, state, load_batch_id, parent_job_id,
          progress, current_stage, source_yyyymm, source_set,
          started_at, finished_at, heartbeat_at, error_message, log_tail, payload_summary
""",
                        "payload",
                        "payload_summary",
                    ),
                    {
                        "job_id": root_job_id,
                        "payload": payload,
                        "load_batch_id": root_job_id,
                        "payload_summary": root_summary,
                    },
                )
            ).mappings().one()
            for kind, child_payload in children:
                await conn.execute(
                    _json_text(
                        """
INSERT INTO load_jobs
  (job_id, kind, payload, state, load_batch_id, parent_job_id, payload_summary)
VALUES
  (:job_id, :kind, :payload, 'queued', :load_batch_id, :parent_job_id,
   :payload_summary)
""",
                        "payload",
                        "payload_summary",
                    ),
                    {
                        "job_id": f"job_{uuid4().hex}",
                        "kind": kind,
                        "payload": child_payload,
                        "load_batch_id": root_job_id,
                        "parent_job_id": root_job_id,
                        "payload_summary": _summarize_payload(child_payload),
                    },
                )
        return map_load_job(dict(root))

    async def cancel_load_job(self, job_id: str) -> LoadJobRow | None:
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        _JOB_SELECT
                        + """
 WHERE job_id = :job_id
   AND state IN ('queued','running')
 FOR UPDATE
"""
                    ),
                    {"job_id": job_id},
                )
            ).mappings().first()
            if row is None:
                return None
            updated = (
                await conn.execute(
                    text(
                        """
UPDATE load_jobs
   SET state = 'cancelled',
       finished_at = now(),
       heartbeat_at = now()
WHERE job_id = :job_id
RETURNING job_id, kind, state, load_batch_id, parent_job_id,
          progress, current_stage, source_yyyymm, source_set,
          started_at, finished_at, heartbeat_at, error_message, log_tail, payload_summary
"""
                    ),
                    {"job_id": job_id},
                )
            ).mappings().one()
        return map_load_job(dict(updated))

    async def consistency_report(self, report_id: str) -> ConsistencyReportRow | None:
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        """
SELECT report_id, scope, severity_max, source_set, started_at, finished_at,
       cases, generated_by
  FROM load_consistency_reports
 WHERE report_id = :report_id
"""
                    ),
                    {"report_id": report_id},
                )
            ).mappings().first()
        return map_consistency_report(dict(row)) if row else None

    async def list_consistency_reports(
        self,
        *,
        limit: int = 20,
        severity_at_least: Literal["INFO", "WARN", "ERROR"] | None = None,
    ) -> list[ConsistencyReportRow]:
        severity_rank = {"INFO": 1, "WARN": 2, "ERROR": 3}
        min_rank = severity_rank.get(severity_at_least or "INFO", 0)
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
SELECT report_id, scope, severity_max, source_set, started_at, finished_at,
       cases, generated_by
  FROM load_consistency_reports
 ORDER BY started_at DESC
 LIMIT :limit
"""
                    ),
                    {"limit": limit},
                )
            ).mappings().all()
        reports = [map_consistency_report(dict(row)) for row in rows]
        if severity_at_least is None:
            return reports
        return [
            report
            for report in reports
            if severity_rank.get(report.severity_max, 0) >= min_rank
        ]


def _summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted_keys = {"api_key", "token", "secret", "password"}
    summary: dict[str, Any] = {}
    for key, value in payload.items():
        lower_key = key.lower()
        if any(secret in lower_key for secret in redacted_keys):
            summary[key] = "***"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            summary[key] = value
        else:
            summary[key] = type(value).__name__
    return summary


def _json_text(sql: str, *json_params: str) -> Any:
    return text(sql).bindparams(*(bindparam(name, type_=JSONB) for name in json_params))


def _validated_explain_sql(sql: str) -> str:
    query = sql.strip()
    lowered = query.lower()
    if not lowered.startswith(("select", "with")):
        msg = "EXPLAIN only accepts SELECT or WITH queries"
        raise InvalidInputError(msg)
    if ";" in query:
        msg = "EXPLAIN query must not contain semicolons"
        raise InvalidInputError(msg)
    return query
