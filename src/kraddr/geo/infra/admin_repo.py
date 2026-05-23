"""Raw SQL admin repository for load jobs and consistency reports."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.core.protocols import ConsistencyReportRow, LoadJobRow

from ._rows import map_consistency_report, map_load_job

_JOB_SELECT = """
SELECT job_id, kind, state, progress, current_stage, source_yyyymm, source_set,
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

    async def insert_load_job(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        job_id: str | None = None,
    ) -> LoadJobRow:
        resolved_job_id = job_id or f"job_{uuid4().hex}"
        payload_summary = _summarize_payload(payload)
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        """
INSERT INTO load_jobs (job_id, kind, payload, state, payload_summary)
VALUES (:job_id, :kind, :payload, 'queued', :payload_summary)
RETURNING job_id, kind, state, progress, current_stage, source_yyyymm, source_set,
          started_at, finished_at, heartbeat_at, error_message, log_tail, payload_summary
"""
                    ),
                    {
                        "job_id": resolved_job_id,
                        "kind": kind,
                        "payload": payload,
                        "payload_summary": payload_summary,
                    },
                )
            ).mappings().one()
        return map_load_job(dict(row))

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
RETURNING job_id, kind, state, progress, current_stage, source_yyyymm, source_set,
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
