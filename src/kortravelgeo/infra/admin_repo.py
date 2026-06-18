"""Raw SQL admin repository for load jobs and consistency reports."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.core.protocols import ConsistencyReportRow, LoadJobRow
from kortravelgeo.core.redaction import (
    canonical_payload_hash,
    hash_confirmation,
    hash_identifier,
    redact_audit_payload,
)
from kortravelgeo.dto.admin import (
    AuditEvent,
    CacheMetrics,
    ConsistencyBulkDecisionRequest,
    ConsistencyBulkDecisionResponse,
    ConsistencyCase,
    ConsistencyCaseSample,
    ConsistencyCaseSummary,
    ConsistencyReport,
    ConsistencySampleDecisionRequest,
    ConsistencySamplePage,
    ConsistencySamplePoint,
    ConsistencySampleRecheckResponse,
    DatasetSnapshot,
    MaintenanceWindow,
    MaintenanceWindowCreate,
    OpsArtifact,
    PgStatStatementSnapshot,
    RollbackPlan,
    ServingRelease,
    TableStat,
    TableStatsSnapshot,
)
from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra.metrics import sql_fingerprint, sql_operation
from kortravelgeo.infra.uploads import extract_upload_set_ids
from kortravelgeo.version import __version__

from ._rows import map_consistency_report, map_load_job

_JOB_SELECT = """
SELECT job_id, kind, state, load_batch_id, parent_job_id,
       progress, current_stage, source_yyyymm, source_set,
       started_at, finished_at, heartbeat_at, error_message, log_tail, payload_summary
  FROM load_jobs
"""

_AUDIT_SELECT = """
SELECT audit_event_id, occurred_at, actor_type, actor_id, client_ip_hash,
       user_agent_hash, request_id, trace_id, action, resource_type,
       resource_id, job_id, outcome, error_code, payload_redacted,
       payload_hash
  FROM ops.audit_events
"""

_SNAPSHOT_SELECT = """
SELECT dataset_snapshot_id, state, parent_dataset_snapshot_id, source_set, source_set_hash,
       git_commit, alembic_revision, postgres_version, postgis_version,
       row_counts, table_stats_artifact_id, consistency_report_id,
       performance_artifact_id, backup_artifact_id, created_by_job_id,
       created_at, validated_at
  FROM ops.dataset_snapshots
"""

_RELEASE_SELECT = """
SELECT serving_release_id, dataset_snapshot_id, state, release_kind, previous_serving_release_id,
       rollback_target_serving_release_id, mv_name, mv_hash, consistency_gate,
       performance_gate, activated_by_job_id, activated_at, notes, created_at
  FROM ops.serving_releases
"""

_ARTIFACT_SELECT = """
SELECT artifact_id, artifact_type, state, storage_kind, storage_uri,
       display_name, media_type, compression, size_bytes, sha256,
       retention_class, expires_at, job_id, dataset_snapshot_id, serving_release_id,
       manifest, callback_url, callback_state, created_at, finished_at
  FROM ops.artifacts
"""

_MAINTENANCE_SELECT = """
SELECT maintenance_window_id, kind, state, starts_at, ends_at, actual_started_at,
       actual_ended_at, reason, requested_by, approved_by, blocks,
       created_by_job_id, closed_by_job_id, created_at
  FROM ops.maintenance_windows
"""

_TABLE_STATS_SNAPSHOT_SELECT = """
SELECT table_stats_snapshot_id, dataset_snapshot_id, captured_at, schema_name, object_name,
       object_kind, estimated_rows, exact_rows, total_bytes, table_bytes,
       index_bytes, toast_bytes, dead_tuples, last_vacuum, last_analyze, stats
  FROM ops.table_stats_snapshots
"""

_PG_STAT_STATEMENTS_SNAPSHOT_SELECT = """
SELECT pg_stat_snapshot_id, captured_at, rank, queryid, query_fingerprint, operation,
       calls, total_exec_time_ms, mean_exec_time_ms, max_exec_time_ms, rows_returned,
       shared_blks_hit, shared_blks_read, temp_blks_read, temp_blks_written,
       query_preview, stats
  FROM ops.pg_stat_statements_snapshots
"""

_ROW_COUNT_OBJECTS = (
    "tl_juso_text",
    "tl_juso_parcel_link",
    "tl_locsum_entrc",
    "tl_roadaddr_entrc",
    "tl_navi_buld_centroid",
    "tl_navi_entrc",
    "tl_spbd_buld_polygon",
    "tl_spbd_eqb",
    "mv_geocode_target",
    "mv_geocode_text_search",
)

_OPS_TABLE_STATS_ADVISORY_LOCK = 0x4B47_00A0
_OPS_PG_STAT_STATEMENTS_ADVISORY_LOCK = 0x4B47_00A1
TABLE_STATS_CAPTURE_LOCKED_MESSAGE = "table stats capture is already running"
PG_STAT_STATEMENTS_CAPTURE_LOCKED_MESSAGE = "pg_stat_statements capture is already running"
_SQL_LITERAL_RE = re.compile(
    r"\$([A-Za-z_][A-Za-z_0-9]*)\$.*?\$\1\$|\$\$.*?\$\$|"
    r"[eE]?'(?:''|[^'])*'|\b\d+(?:\.\d+)?\b",
    re.DOTALL,
)
_SQL_SPACE_RE = re.compile(r"\s+")

_CONSISTENCY_SAMPLE_SELECT = """
SELECT sample_id::text AS sample_id, report_id, case_code, severity, sample_rank,
       bd_mgt_sn, rncode_full, sig_cd, bjd_cd, distance_m, source_yyyymm,
       source_kind, case_metric, source_snapshot,
       CASE WHEN point_4326 IS NULL THEN NULL ELSE ST_X(point_4326) END AS lon,
       CASE WHEN point_4326 IS NULL THEN NULL ELSE ST_Y(point_4326) END AS lat,
       bbox_4326, has_polygon, has_line, decision_state, reason_code, note,
       reviewed_by, reviewed_at, created_at
  FROM ops.consistency_case_samples
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

    async def active_upload_set_ids(self) -> set[str]:
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
SELECT payload
  FROM load_jobs
 WHERE state IN ('queued','running')
   AND payload::text LIKE '%upload_%'
"""
                    )
                )
            ).mappings().all()
        refs: set[str] = set()
        for row in rows:
            refs.update(extract_upload_set_ids(row["payload"]))
        return refs

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
        timeout_ms: int = 3_000,
    ) -> object:
        query = _validated_explain_sql(sql)
        options = ["FORMAT JSON"]
        if analyze:
            options.append("ANALYZE")
        if buffers:
            options.append("BUFFERS")
        async with self.engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {"timeout": f"{timeout_ms}ms"},
            )
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

    async def record_audit_event(
        self,
        *,
        action: str,
        actor_type: str,
        outcome: str,
        payload: dict[str, Any] | None = None,
        actor_id: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        job_id: str | None = None,
        error_code: str | None = None,
    ) -> AuditEvent:
        payload_redacted, payload_hash = redact_audit_payload(payload)
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    _json_text(
                        """
INSERT INTO ops.audit_events
  (audit_event_id, actor_type, actor_id, client_ip_hash, user_agent_hash,
   request_id, trace_id, action, resource_type, resource_id, job_id,
   outcome, error_code, payload_redacted, payload_hash)
VALUES
  (:audit_event_id, :actor_type, :actor_id, :client_ip_hash, :user_agent_hash,
   :request_id, :trace_id, :action, :resource_type, :resource_id, :job_id,
   :outcome, :error_code, :payload_redacted, :payload_hash)
RETURNING audit_event_id, occurred_at, actor_type, actor_id, client_ip_hash,
          user_agent_hash, request_id, trace_id, action, resource_type,
          resource_id, job_id, outcome, error_code, payload_redacted,
          payload_hash
""",
                        "payload_redacted",
                    ),
                    {
                        "audit_event_id": str(uuid4()),
                        "actor_type": actor_type,
                        "actor_id": actor_id,
                        "client_ip_hash": hash_identifier(client_ip) if client_ip else None,
                        "user_agent_hash": hash_identifier(user_agent) if user_agent else None,
                        "request_id": request_id,
                        "trace_id": trace_id,
                        "action": action,
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "job_id": job_id,
                        "outcome": outcome,
                        "error_code": error_code,
                        "payload_redacted": payload_redacted,
                        "payload_hash": payload_hash,
                    },
                )
            ).mappings().one()
        return _audit_event(dict(row))

    async def list_audit_events(
        self,
        *,
        limit: int = 50,
        action: str | None = None,
        outcome: str | None = None,
    ) -> list[AuditEvent]:
        clauses = []
        params: dict[str, Any] = {"limit": limit}
        if action is not None:
            clauses.append("action = :action")
            params["action"] = action
        if outcome is not None:
            clauses.append("outcome = :outcome")
            params["outcome"] = outcome
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(_AUDIT_SELECT + where + " ORDER BY occurred_at DESC LIMIT :limit"),
                    params,
                )
            ).mappings().all()
        return [_audit_event(dict(row)) for row in rows]

    async def list_dataset_snapshots(
        self,
        *,
        limit: int = 20,
        state: str | None = None,
    ) -> list[DatasetSnapshot]:
        where = " WHERE state = :state" if state is not None else ""
        params: dict[str, Any] = {"limit": limit}
        if state is not None:
            params["state"] = state
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(_SNAPSHOT_SELECT + where + " ORDER BY created_at DESC LIMIT :limit"),
                    params,
                )
            ).mappings().all()
        return [_dataset_snapshot(dict(row)) for row in rows]

    async def list_serving_releases(
        self,
        *,
        limit: int = 20,
        state: str | None = None,
    ) -> list[ServingRelease]:
        where = " WHERE state = :state" if state is not None else ""
        params: dict[str, Any] = {"limit": limit}
        if state is not None:
            params["state"] = state
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(_RELEASE_SELECT + where + " ORDER BY created_at DESC LIMIT :limit"),
                    params,
                )
            ).mappings().all()
        return [_serving_release(dict(row)) for row in rows]

    async def record_mv_refresh_release(
        self,
        *,
        job_id: str | None = None,
        load_batch_id: str | None = None,
        strategy: str | None = None,
        notes: str | None = None,
        source_match_set_id: str | None = None,
        forced_promotion: bool = False,
        forced_promotion_metadata: Mapping[str, Any] | None = None,
    ) -> tuple[DatasetSnapshot, ServingRelease]:
        """Record the dataset state exposed by a successful MV refresh.

        When ``source_match_set_id`` is provided (rebuild-db path, T-205b) it is
        written as the 정본 ``ops.dataset_snapshots.source_match_set_id`` FK and
        any ``forced_promotion`` provenance is recorded as read-only snapshot
        metadata (doc step 10, ~1551 / line ~1559)."""

        async with self.engine.begin() as conn:
            await conn.execute(text("SET LOCAL statement_timeout = 0"))
            report = (
                await _latest_consistency_gate_for_batch(conn, load_batch_id)
                if load_batch_id
                else None
            )
            batch_source_set = (
                await _load_batch_source_set(conn, load_batch_id) if load_batch_id else {}
            )
            source_set = batch_source_set or _json_dict(report.get("source_set") if report else {})
            if not source_set:
                source_set = await _infer_current_source_set(conn)
            if load_batch_id:
                source_set = dict(source_set)
                source_set.setdefault("load_batch_id", load_batch_id)

            consistency_gate = (
                {
                    "report_id": str(report["report_id"]),
                    "severity_max": str(report["severity_max"]),
                    "load_batch_id": load_batch_id,
                }
                if report is not None
                else {}
            )
            release_kind = "full_load" if load_batch_id else "manual_rebuild"
            release_notes = notes or (
                f"mv_refresh strategy={strategy or 'unknown'}"
                + (f"; load_batch_id={load_batch_id}" if load_batch_id else "")
            )
            snapshot_metadata: dict[str, Any] | None = None
            if forced_promotion:
                snapshot_metadata = {
                    "forced_promotion": True,
                    **dict(forced_promotion_metadata or {}),
                }
            row_counts = await _collect_row_counts_for_conn(conn)
            mv_hash = await _mv_hash_for_conn(conn, row_counts.get("mv_geocode_target"))
            return await _insert_dataset_snapshot_and_release(
                conn,
                snapshot_state="released",
                release_state="active",
                release_kind=release_kind,
                source_set=source_set,
                row_counts=row_counts,
                consistency_report_id=str(report["report_id"]) if report else None,
                consistency_gate=consistency_gate,
                created_by_job_id=job_id,
                activated_by_job_id=job_id,
                mv_hash=mv_hash,
                notes=release_notes,
                source_match_set_id=source_match_set_id,
                snapshot_metadata=snapshot_metadata,
            )

    async def ensure_load_batch_release_gate(self, load_batch_id: str | None) -> None:
        """Fail before MV swap when the latest load-batch consistency gate is blocking."""

        if not load_batch_id:
            return
        async with self.engine.connect() as conn:
            report = await _latest_consistency_gate_for_batch(conn, load_batch_id)
        if report is not None and report["severity_max"] == "ERROR":
            msg = "cannot release dataset with ERROR consistency gate"
            raise RuntimeError(msg)

    async def record_restore_candidate(
        self,
        *,
        restore_artifact_id: str,
        target_database: str,
        source_manifest: Mapping[str, Any],
        source_artifact_id: str | None = None,
        job_id: str | None = None,
    ) -> tuple[DatasetSnapshot, ServingRelease]:
        """Record a restored database as a validated pending release candidate."""

        database = _json_dict(source_manifest.get("database"))
        async with self.engine.begin() as conn:
            return await _insert_dataset_snapshot_and_release(
                conn,
                snapshot_state="validated",
                release_state="pending",
                release_kind="restore",
                source_set=_json_dict(source_manifest.get("source_set")),
                row_counts=_int_dict(source_manifest.get("row_counts")),
                backup_artifact_id=source_artifact_id,
                created_by_job_id=job_id,
                git_commit=_optional_text(source_manifest.get("git_commit")),
                postgres_version=_optional_text(database.get("postgres_version")),
                postgis_version=_optional_text(database.get("postgis_version")),
                notes=(
                    f"restore target_database={target_database}; "
                    f"restore_artifact_id={restore_artifact_id}"
                ),
            )

    async def record_hot_swap_release(
        self,
        *,
        current_database: str,
        restore_database: str,
        previous_alias: str,
        pre_swap_release_id: str | None = None,
        maintenance_window_id: str | None = None,
    ) -> ServingRelease:
        """Record the post-hot-swap restored DB as the active serving release (T-241).

        Runs against the now-current (restored) database after the rename, so
        ``_insert_dataset_snapshot_and_release`` supersedes that database's prior active
        release and sets ``previous_release_id`` lineage within it. The pre-swap serving
        release id and the rollback alias are kept in notes/metadata for cross-DB tracing.
        """
        async with self.engine.begin() as conn:
            _, release = await _insert_dataset_snapshot_and_release(
                conn,
                snapshot_state="released",
                release_state="active",
                release_kind="restore",
                source_set={
                    "hot_swap": {
                        "current_database": current_database,
                        "restore_database": restore_database,
                        "previous_alias": previous_alias,
                    }
                },
                row_counts={},
                notes=(
                    f"hot-swap restore_database={restore_database} "
                    f"previous_alias={previous_alias} pre_swap_release_id={pre_swap_release_id}"
                ),
                snapshot_metadata={
                    "hot_swap": {
                        "previous_alias": previous_alias,
                        "pre_swap_release_id": pre_swap_release_id,
                        "maintenance_window_id": maintenance_window_id,
                    }
                },
            )
            return release

    async def record_hot_swap_rollback_release(
        self,
        *,
        current_database: str,
        restore_database: str,
        previous_alias: str,
        pre_rollback_release_id: str | None = None,
        maintenance_window_id: str | None = None,
    ) -> ServingRelease:
        """Record a manual hot-swap rollback as the active serving release (T-264).

        Runs against the now-current (rolled-back/previous) database. ``release_kind='rollback'``
        with ``previous_release_id`` lineage; ``rollback_target`` (where the restored DB went)
        and the pre-rollback release id are kept in notes/metadata for cross-DB tracing.
        """
        async with self.engine.begin() as conn:
            _, release = await _insert_dataset_snapshot_and_release(
                conn,
                snapshot_state="released",
                release_state="active",
                release_kind="rollback",
                source_set={
                    "hot_swap_rollback": {
                        "current_database": current_database,
                        "rollback_target": restore_database,
                        "previous_alias": previous_alias,
                    }
                },
                row_counts={},
                notes=(
                    f"hot-swap rollback rollback_target={restore_database} "
                    f"previous_alias={previous_alias} "
                    f"pre_rollback_release_id={pre_rollback_release_id}"
                ),
                snapshot_metadata={
                    "hot_swap_rollback": {
                        "rollback_target": restore_database,
                        "previous_alias": previous_alias,
                        "pre_rollback_release_id": pre_rollback_release_id,
                        "maintenance_window_id": maintenance_window_id,
                    }
                },
            )
            return release

    async def rollback_plan(self, serving_release_id: str) -> RollbackPlan | None:
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    text(_RELEASE_SELECT + " WHERE serving_release_id = :serving_release_id"),
                    {"serving_release_id": serving_release_id},
                )
            ).mappings().first()
        if row is None:
            return None
        release = _serving_release(dict(row))
        blockers: tuple[str, ...] = ()
        if release.state == "failed":
            blockers = ("failed release는 rollback 기준으로 사용할 수 없다",)
        return RollbackPlan(
            serving_release_id=release.serving_release_id,
            dataset_snapshot_id=release.dataset_snapshot_id,
            typed_confirmation=f"ROLLBACK {release.serving_release_id}",
            blockers=blockers,
            steps=(
                "active maintenance window 확인",
                "현재 active release를 superseded로 전환",
                "대상 snapshot 기준 serving object swap",
                "rollback serving release row 생성",
                "ops.audit_events에 승인 근거 기록",
            ),
        )

    async def list_artifacts(
        self,
        *,
        limit: int = 50,
        artifact_type: str | None = None,
        state: str | None = None,
        expires_before: datetime | None = None,
    ) -> list[OpsArtifact]:
        clauses = []
        params: dict[str, Any] = {"limit": limit}
        if artifact_type is not None:
            clauses.append("artifact_type = :artifact_type")
            params["artifact_type"] = artifact_type
        if state is not None:
            clauses.append("state = :state")
            params["state"] = state
        if expires_before is not None:
            # NULL expires_at is excluded by ``<=``; the filter applies inside SQL so the
            # LIMIT acts on the already-filtered set (T-240 follow-up: not after LIMIT).
            clauses.append("expires_at IS NOT NULL AND expires_at <= :expires_before")
            params["expires_before"] = expires_before
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(_ARTIFACT_SELECT + where + " ORDER BY created_at DESC LIMIT :limit"),
                    params,
                )
            ).mappings().all()
        return [_ops_artifact(dict(row)) for row in rows]

    async def get_artifact(self, artifact_id: str) -> OpsArtifact | None:
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    text(_ARTIFACT_SELECT + " WHERE artifact_id = :artifact_id"),
                    {"artifact_id": artifact_id},
                )
            ).mappings().first()
        return _ops_artifact(dict(row)) if row else None

    async def insert_artifact(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        state: str,
        storage_kind: str,
        storage_uri: str | None = None,
        display_name: str | None = None,
        media_type: str | None = None,
        compression: str | None = None,
        size_bytes: int | None = None,
        sha256: str | None = None,
        retention_class: str | None = None,
        expires_at: datetime | None = None,
        job_id: str | None = None,
        dataset_snapshot_id: str | None = None,
        serving_release_id: str | None = None,
        manifest: dict[str, Any] | None = None,
        download_token_hash: str | None = None,
        callback_url: str | None = None,
        callback_state: str | None = None,
    ) -> OpsArtifact:
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    _json_text(
                        """
INSERT INTO ops.artifacts
  (artifact_id, artifact_type, state, storage_kind, storage_uri, display_name,
   media_type, compression, size_bytes, sha256, retention_class, expires_at,
   job_id, dataset_snapshot_id, serving_release_id, manifest, download_token_hash,
   callback_url, callback_state)
VALUES
  (:artifact_id, :artifact_type, :state, :storage_kind, :storage_uri, :display_name,
   :media_type, :compression, :size_bytes, :sha256, :retention_class, :expires_at,
   :job_id, :dataset_snapshot_id, :serving_release_id, :manifest, :download_token_hash,
   :callback_url, :callback_state)
RETURNING artifact_id, artifact_type, state, storage_kind, storage_uri,
          display_name, media_type, compression, size_bytes, sha256,
          retention_class, expires_at, job_id, dataset_snapshot_id, serving_release_id,
          manifest, callback_url, callback_state, created_at, finished_at
""",
                        "manifest",
                    ),
                    {
                        "artifact_id": artifact_id,
                        "artifact_type": artifact_type,
                        "state": state,
                        "storage_kind": storage_kind,
                        "storage_uri": storage_uri,
                        "display_name": display_name,
                        "media_type": media_type,
                        "compression": compression,
                        "size_bytes": size_bytes,
                        "sha256": sha256,
                        "retention_class": retention_class,
                        "expires_at": expires_at,
                        "job_id": job_id,
                        "dataset_snapshot_id": dataset_snapshot_id,
                        "serving_release_id": serving_release_id,
                        "manifest": manifest or {},
                        "download_token_hash": download_token_hash,
                        "callback_url": callback_url,
                        "callback_state": callback_state,
                    },
                )
            ).mappings().one()
        return _ops_artifact(dict(row))

    async def update_artifact(
        self,
        artifact_id: str,
        *,
        state: str | None = None,
        storage_uri: str | None = None,
        display_name: str | None = None,
        size_bytes: int | None = None,
        sha256: str | None = None,
        manifest: dict[str, Any] | None = None,
        retention_class: str | None = None,
        expires_at: datetime | None = None,
        dataset_snapshot_id: str | None = None,
        serving_release_id: str | None = None,
        callback_state: str | None = None,
        finished: bool = False,
    ) -> OpsArtifact | None:
        assignments = []
        params: dict[str, Any] = {"artifact_id": artifact_id}
        if state is not None:
            assignments.append("state = :state")
            params["state"] = state
        if storage_uri is not None:
            assignments.append("storage_uri = :storage_uri")
            params["storage_uri"] = storage_uri
        if display_name is not None:
            assignments.append("display_name = :display_name")
            params["display_name"] = display_name
        if size_bytes is not None:
            assignments.append("size_bytes = :size_bytes")
            params["size_bytes"] = size_bytes
        if sha256 is not None:
            assignments.append("sha256 = :sha256")
            params["sha256"] = sha256
        if manifest is not None:
            assignments.append("manifest = :manifest")
            params["manifest"] = manifest
        if retention_class is not None:
            assignments.append("retention_class = :retention_class")
            params["retention_class"] = retention_class
        if expires_at is not None:
            assignments.append("expires_at = :expires_at")
            params["expires_at"] = expires_at
        if dataset_snapshot_id is not None:
            assignments.append("dataset_snapshot_id = :dataset_snapshot_id")
            params["dataset_snapshot_id"] = dataset_snapshot_id
        if serving_release_id is not None:
            assignments.append("serving_release_id = :serving_release_id")
            params["serving_release_id"] = serving_release_id
        if callback_state is not None:
            assignments.append("callback_state = :callback_state")
            params["callback_state"] = callback_state
        if finished:
            assignments.append("finished_at = COALESCE(finished_at, now())")
        if not assignments:
            return await self.get_artifact(artifact_id)
        stmt = text(
            f"""
UPDATE ops.artifacts
   SET {', '.join(assignments)}
 WHERE artifact_id = :artifact_id
RETURNING artifact_id, artifact_type, state, storage_kind, storage_uri,
          display_name, media_type, compression, size_bytes, sha256,
          retention_class, expires_at, job_id, dataset_snapshot_id, serving_release_id,
          manifest, callback_url, callback_state, created_at, finished_at
"""
        )
        if manifest is not None:
            stmt = stmt.bindparams(bindparam("manifest", type_=JSONB))
        async with self.engine.begin() as conn:
            row = (await conn.execute(stmt, params)).mappings().first()
        return _ops_artifact(dict(row)) if row else None

    async def mark_artifact_deleted(self, artifact_id: str) -> OpsArtifact | None:
        return await self.update_artifact(artifact_id, state="deleted", finished=True)

    async def list_maintenance_windows(
        self,
        *,
        limit: int = 50,
        state: str | None = None,
    ) -> list[MaintenanceWindow]:
        where = " WHERE state = :state" if state is not None else ""
        params: dict[str, Any] = {"limit": limit}
        if state is not None:
            params["state"] = state
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(_MAINTENANCE_SELECT + where + " ORDER BY created_at DESC LIMIT :limit"),
                    params,
                )
            ).mappings().all()
        return [_maintenance_window(dict(row)) for row in rows]

    async def create_maintenance_window(
        self,
        req: MaintenanceWindowCreate,
    ) -> MaintenanceWindow:
        state = "active"
        blocks = req.blocks or _default_maintenance_blocks(req.kind)
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    _json_text(
                        """
INSERT INTO ops.maintenance_windows
  (maintenance_window_id, kind, state, starts_at, ends_at, actual_started_at,
   reason, requested_by, approved_by, confirmation_hash, blocks,
   created_by_job_id)
VALUES
  (:maintenance_window_id, :kind, :state, COALESCE(:starts_at, now()), :ends_at, now(),
   :reason, :requested_by, :approved_by, :confirmation_hash, :blocks,
   :created_by_job_id)
RETURNING maintenance_window_id, kind, state, starts_at, ends_at, actual_started_at,
          actual_ended_at, reason, requested_by, approved_by, blocks,
          created_by_job_id, closed_by_job_id, created_at
""",
                        "blocks",
                    ),
                    {
                        "maintenance_window_id": str(uuid4()),
                        "kind": req.kind,
                        "state": state,
                        "starts_at": req.starts_at,
                        "ends_at": req.ends_at,
                        "reason": req.reason,
                        "requested_by": req.requested_by,
                        "approved_by": req.approved_by,
                        "confirmation_hash": hash_confirmation(req.confirmation),
                        "blocks": blocks,
                        "created_by_job_id": req.created_by_job_id,
                    },
                )
            ).mappings().one()
        return _maintenance_window(dict(row))

    async def end_maintenance_window(
        self,
        *,
        maintenance_window_id: str,
        confirmation: str,
        closed_by_job_id: str | None = None,
    ) -> MaintenanceWindow | None:
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        """
UPDATE ops.maintenance_windows
   SET state = 'ended',
       actual_ended_at = now(),
       closed_by_job_id = :closed_by_job_id
 WHERE maintenance_window_id = :maintenance_window_id
   AND state IN ('scheduled','active','ending')
   AND confirmation_hash = :confirmation_hash
RETURNING maintenance_window_id, kind, state, starts_at, ends_at, actual_started_at,
          actual_ended_at, reason, requested_by, approved_by, blocks,
          created_by_job_id, closed_by_job_id, created_at
"""
                    ),
                    {
                        "maintenance_window_id": maintenance_window_id,
                        "confirmation_hash": hash_confirmation(confirmation),
                        "closed_by_job_id": closed_by_job_id,
                    },
                )
            ).mappings().first()
        return _maintenance_window(dict(row)) if row else None

    async def require_active_maintenance_window(
        self,
        *,
        kind: str,
        confirmation: str,
    ) -> MaintenanceWindow:
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        _MAINTENANCE_SELECT
                        + """
 WHERE kind = :kind
   AND state = 'active'
   AND starts_at <= now()
   AND (ends_at IS NULL OR ends_at >= now())
   AND confirmation_hash = :confirmation_hash
 ORDER BY actual_started_at DESC NULLS LAST, created_at DESC
 LIMIT 1
"""
                    ),
                    {
                        "kind": kind,
                        "confirmation_hash": hash_confirmation(confirmation),
                    },
                )
            ).mappings().first()
        if row is None:
            msg = f"active {kind} maintenance window with matching confirmation is required"
            raise InvalidInputError(msg)
        return _maintenance_window(dict(row))

    async def list_table_stats_snapshots(
        self,
        *,
        limit: int = 200,
        dataset_snapshot_id: str | None = None,
    ) -> list[TableStatsSnapshot]:
        where = (
            " WHERE dataset_snapshot_id = :dataset_snapshot_id"
            if dataset_snapshot_id is not None
            else ""
        )
        params: dict[str, Any] = {"limit": limit}
        if dataset_snapshot_id is not None:
            params["dataset_snapshot_id"] = dataset_snapshot_id
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        _TABLE_STATS_SNAPSHOT_SELECT
                        + where
                        + " ORDER BY captured_at DESC, schema_name, object_name LIMIT :limit"
                    ),
                    params,
                )
            ).mappings().all()
        return [_table_stats_snapshot(dict(row)) for row in rows]

    async def capture_table_stats_snapshots(
        self,
        *,
        dataset_snapshot_id: str | None = None,
        limit: int = 500,
        skip_if_locked: bool = True,
    ) -> list[TableStatsSnapshot]:
        captured_at = datetime.now(UTC)
        async with self.engine.begin() as conn:
            locked = await conn.scalar(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {"lock_key": _OPS_TABLE_STATS_ADVISORY_LOCK},
            )
            if locked is not True:
                if not skip_if_locked:
                    raise InvalidInputError(
                        TABLE_STATS_CAPTURE_LOCKED_MESSAGE,
                        code="E0409",
                        http_status=409,
                    )
                return []
            resolved_snapshot_id = dataset_snapshot_id
            snapshot_link = "explicit"
            if resolved_snapshot_id is None:
                resolved_snapshot_id = await _active_release_snapshot_id_for_conn(conn)
                snapshot_link = (
                    "active_serving_release"
                    if resolved_snapshot_id is not None
                    else "unlinked"
                )
            stats_rows = (
                await conn.execute(
                    text(
                        """
SELECT n.nspname AS schema_name,
       c.relname AS object_name,
       CASE c.relkind
         WHEN 'r' THEN 'table'
         WHEN 'p' THEN 'table'
         WHEN 'm' THEN 'materialized_view'
         WHEN 'i' THEN 'index'
         WHEN 'I' THEN 'index'
         WHEN 't' THEN 'toast'
         ELSE 'other'
       END AS object_kind,
       GREATEST(c.reltuples, 0)::bigint AS estimated_rows,
       pg_total_relation_size(c.oid)::bigint AS total_bytes,
       CASE WHEN c.relkind IN ('r','p','m')
            THEN pg_relation_size(c.oid)::bigint
            ELSE NULL
       END AS table_bytes,
       CASE WHEN c.relkind IN ('r','p','m')
            THEN pg_indexes_size(c.oid)::bigint
            WHEN c.relkind IN ('i','I')
            THEN pg_relation_size(c.oid)::bigint
            ELSE NULL
       END AS index_bytes,
       CASE WHEN c.relkind IN ('r','p','m')
            THEN GREATEST(
              pg_total_relation_size(c.oid)
              - pg_relation_size(c.oid)
              - pg_indexes_size(c.oid),
              0
            )::bigint
            ELSE NULL
       END AS toast_bytes,
       GREATEST(COALESCE(s.n_dead_tup, 0), 0)::bigint AS dead_tuples,
       s.last_vacuum,
       s.last_analyze
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
 WHERE n.nspname IN ('public', 'ops')
   AND c.relkind IN ('r','p','m','i','I','t')
 ORDER BY n.nspname, c.relname
 LIMIT :limit
"""
                    ),
                    {"limit": limit},
                )
            ).mappings().all()
            records = [
                {
                    "table_stats_snapshot_id": str(uuid4()),
                    "dataset_snapshot_id": resolved_snapshot_id,
                    "captured_at": captured_at,
                    "schema_name": row["schema_name"],
                    "object_name": row["object_name"],
                    "object_kind": row["object_kind"],
                    "estimated_rows": row["estimated_rows"],
                    "exact_rows": None,
                    "total_bytes": row["total_bytes"],
                    "table_bytes": row["table_bytes"],
                    "index_bytes": row["index_bytes"],
                    "toast_bytes": row["toast_bytes"],
                    "dead_tuples": row["dead_tuples"],
                    "last_vacuum": row["last_vacuum"],
                    "last_analyze": row["last_analyze"],
                    "stats": {
                        "source": "pg_class_pg_stat_user_tables",
                        "snapshot_link": snapshot_link,
                    },
                }
                for row in stats_rows
            ]
            if records:
                await conn.execute(
                    _json_text(
                        """
INSERT INTO ops.table_stats_snapshots
  (table_stats_snapshot_id, dataset_snapshot_id, captured_at, schema_name,
   object_name, object_kind,
   estimated_rows, exact_rows, total_bytes, table_bytes, index_bytes,
   toast_bytes, dead_tuples, last_vacuum, last_analyze, stats)
VALUES
  (:table_stats_snapshot_id, :dataset_snapshot_id, :captured_at, :schema_name,
   :object_name, :object_kind,
   :estimated_rows, :exact_rows, :total_bytes, :table_bytes, :index_bytes,
   :toast_bytes, :dead_tuples, :last_vacuum, :last_analyze, :stats)
""",
                        "stats",
                    ),
                    records,
                )
        return [_table_stats_snapshot(record) for record in records]

    async def list_pg_stat_statement_snapshots(
        self,
        *,
        limit: int = 20,
        latest_only: bool = True,
    ) -> list[PgStatStatementSnapshot]:
        params: dict[str, Any] = {"limit": limit}
        if latest_only:
            sql = text(
                """
WITH latest AS (
  SELECT captured_at
    FROM ops.pg_stat_statements_snapshots
   ORDER BY captured_at DESC
   LIMIT 1
)
"""
                + _PG_STAT_STATEMENTS_SNAPSHOT_SELECT
                + """
 WHERE captured_at = (SELECT captured_at FROM latest)
 ORDER BY rank
 LIMIT :limit
"""
            )
        else:
            sql = text(
                _PG_STAT_STATEMENTS_SNAPSHOT_SELECT
                + " ORDER BY captured_at DESC, rank LIMIT :limit"
            )
        async with self.engine.connect() as conn:
            rows = (await conn.execute(sql, params)).mappings().all()
        return [_pg_stat_statement_snapshot(dict(row)) for row in rows]

    async def capture_pg_stat_statement_snapshots(
        self,
        *,
        limit: int = 20,
        skip_if_locked: bool = True,
        retention_days: int | None = None,
    ) -> list[PgStatStatementSnapshot]:
        if retention_days is not None and retention_days < 1:
            raise InvalidInputError(
                "retention_days must be greater than or equal to 1",
                code="E0102",
                http_status=400,
            )

        captured_at = datetime.now(UTC)
        async with self.engine.begin() as conn:
            locked = await conn.scalar(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {"lock_key": _OPS_PG_STAT_STATEMENTS_ADVISORY_LOCK},
            )
            if locked is not True:
                if not skip_if_locked:
                    raise InvalidInputError(
                        PG_STAT_STATEMENTS_CAPTURE_LOCKED_MESSAGE,
                        code="E0409",
                        http_status=409,
                    )
                return []
            stats_rows = (
                await conn.execute(
                    text(
                        """
SELECT row_number() OVER (ORDER BY total_exec_time DESC, calls DESC)::integer AS rank,
       queryid::text AS queryid,
       query,
       GREATEST(calls, 0)::bigint AS calls,
       GREATEST(total_exec_time, 0)::double precision AS total_exec_time_ms,
       GREATEST(mean_exec_time, 0)::double precision AS mean_exec_time_ms,
       GREATEST(max_exec_time, 0)::double precision AS max_exec_time_ms,
       GREATEST(rows, 0)::bigint AS rows_returned,
       GREATEST(shared_blks_hit, 0)::bigint AS shared_blks_hit,
       GREATEST(shared_blks_read, 0)::bigint AS shared_blks_read,
       GREATEST(temp_blks_read, 0)::bigint AS temp_blks_read,
       GREATEST(temp_blks_written, 0)::bigint AS temp_blks_written,
       COALESCE(wal_bytes, 0)::numeric AS wal_bytes,
       COALESCE(blk_read_time, 0)::double precision AS blk_read_time_ms,
       COALESCE(blk_write_time, 0)::double precision AS blk_write_time_ms
  FROM x_extension.pg_stat_statements
 WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
   AND calls > 0
   AND query IS NOT NULL
   AND query NOT ILIKE '%pg_stat_statements%'
 ORDER BY total_exec_time DESC, calls DESC
 LIMIT :limit
"""
                    ),
                    {"limit": limit},
                )
            ).mappings().all()
            records = []
            for row in stats_rows:
                query = str(row["query"] or "")
                records.append(
                    {
                        "pg_stat_snapshot_id": str(uuid4()),
                        "captured_at": captured_at,
                        "rank": int(row["rank"]),
                        "queryid": _optional_str(row.get("queryid")),
                        "query_fingerprint": sql_fingerprint(query),
                        "operation": sql_operation(query),
                        "calls": int(row["calls"] or 0),
                        "total_exec_time_ms": float(row["total_exec_time_ms"] or 0.0),
                        "mean_exec_time_ms": float(row["mean_exec_time_ms"] or 0.0),
                        "max_exec_time_ms": float(row["max_exec_time_ms"] or 0.0),
                        "rows_returned": int(row["rows_returned"] or 0),
                        "shared_blks_hit": int(row["shared_blks_hit"] or 0),
                        "shared_blks_read": int(row["shared_blks_read"] or 0),
                        "temp_blks_read": int(row["temp_blks_read"] or 0),
                        "temp_blks_written": int(row["temp_blks_written"] or 0),
                        "query_preview": _pg_stat_query_preview(query),
                        "stats": {
                            "source": "pg_stat_statements",
                            "wal_bytes": float(row["wal_bytes"] or 0),
                            "blk_read_time_ms": float(row["blk_read_time_ms"] or 0.0),
                            "blk_write_time_ms": float(row["blk_write_time_ms"] or 0.0),
                        },
                    }
                )
            if records:
                await conn.execute(
                    _json_text(
                        """
INSERT INTO ops.pg_stat_statements_snapshots
  (pg_stat_snapshot_id, captured_at, rank, queryid, query_fingerprint,
   operation, calls, total_exec_time_ms, mean_exec_time_ms, max_exec_time_ms,
   rows_returned, shared_blks_hit, shared_blks_read, temp_blks_read,
   temp_blks_written, query_preview, stats)
VALUES
  (:pg_stat_snapshot_id, :captured_at, :rank, :queryid, :query_fingerprint,
   :operation, :calls, :total_exec_time_ms, :mean_exec_time_ms, :max_exec_time_ms,
   :rows_returned, :shared_blks_hit, :shared_blks_read, :temp_blks_read,
   :temp_blks_written, :query_preview, :stats)
""",
                        "stats",
                    ),
                    records,
                )
            if retention_days is not None:
                await conn.execute(
                    text(
                        """
DELETE FROM ops.pg_stat_statements_snapshots
 WHERE captured_at < now() - (:retention_days * interval '1 day')
"""
                    ),
                    {"retention_days": retention_days},
                )
        return [_pg_stat_statement_snapshot(record) for record in records]

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
            for index, (kind, child_payload) in enumerate(children):
                await conn.execute(
                    _json_text(
                        """
INSERT INTO load_jobs
  (job_id, kind, payload, state, load_batch_id, parent_job_id,
   payload_summary, created_at)
VALUES
  (:job_id, :kind, :payload, 'queued', :load_batch_id, :parent_job_id,
   :payload_summary,
   clock_timestamp() + (CAST(:child_order AS integer) * interval '1 microsecond'))
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
                        "child_order": index,
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

    async def insert_consistency_report(self, report: ConsistencyReport) -> None:
        sample_rows = _consistency_sample_rows(report)
        async with self.engine.begin() as conn:
            await conn.execute(
                _json_text(
                    """
INSERT INTO load_consistency_reports
  (report_id, scope, started_at, finished_at, source_set, cases, severity_max, generated_by)
VALUES
  (:report_id, :scope, :started_at, :finished_at, :source_set, :cases, :severity_max, :generated_by)
""",
                    "source_set",
                    "cases",
                ),
                report.model_dump(mode="json"),
            )
            if sample_rows:
                await _insert_consistency_sample_rows(conn, sample_rows)
                await _hydrate_consistency_sample_points(conn, report.report_id)

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
        severity_rank = {"OK": 0, "INFO": 1, "WARN": 2, "ERROR": 3}
        clauses = []
        params: dict[str, Any] = {"limit": limit}
        if severity_at_least is not None:
            clauses.append(
                """
CASE severity_max
  WHEN 'OK' THEN 0
  WHEN 'INFO' THEN 1
  WHEN 'WARN' THEN 2
  WHEN 'ERROR' THEN 3
  ELSE 0
END >= :min_severity_rank
"""
            )
            params["min_severity_rank"] = severity_rank[severity_at_least]
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        f"""
SELECT report_id, scope, severity_max, source_set, started_at, finished_at,
       cases, generated_by
  FROM load_consistency_reports
{where}
 ORDER BY started_at DESC
 LIMIT :limit
"""
                    ),
                    params,
                )
            ).mappings().all()
        return [map_consistency_report(dict(row)) for row in rows]

    async def ensure_consistency_case_samples(self, report_id: str) -> bool:
        async with self.engine.connect() as conn:
            count = await conn.scalar(
                text(
                    """
SELECT count(*)::bigint
  FROM ops.consistency_case_samples
 WHERE report_id = :report_id
"""
                ),
                {"report_id": report_id},
            )
        if int(count or 0) > 0:
            return True

        row = await self.consistency_report(report_id)
        if row is None:
            return False
        report = _consistency_report_dto(row)
        sample_rows = _consistency_sample_rows(report)
        if not sample_rows:
            return True
        async with self.engine.begin() as conn:
            await _insert_consistency_sample_rows(conn, sample_rows)
            await _hydrate_consistency_sample_points(conn, report_id)
        return True

    async def list_consistency_case_samples(
        self,
        *,
        report_id: str,
        case_code: str,
        severity: str | None = None,
        decision: str | None = None,
        sig_cd: str | None = None,
        bjd_cd: str | None = None,
        bd_mgt_sn: str | None = None,
        reason_code: str | None = None,
        source_kind: str | None = None,
        source_yyyymm: str | None = None,
        min_distance_m: float | None = None,
        max_distance_m: float | None = None,
        order_by: str = "sample_rank",
        desc: bool = False,
        page: int = 1,
        page_size: int = 100,
    ) -> ConsistencySamplePage:
        if not await self.ensure_consistency_case_samples(report_id):
            return ConsistencySamplePage(
                report_id=report_id,
                case_code=case_code,
                total=0,
                page=page,
                page_size=page_size,
                items=(),
            )
        clauses = ["report_id = :report_id", "case_code = :case_code"]
        params: dict[str, Any] = {
            "report_id": report_id,
            "case_code": case_code,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        }
        _append_optional_clause(clauses, params, "severity", severity)
        _append_optional_clause(clauses, params, "decision_state", decision, param_name="decision")
        _append_optional_clause(clauses, params, "sig_cd", sig_cd)
        _append_optional_clause(clauses, params, "bjd_cd", bjd_cd)
        _append_optional_clause(clauses, params, "bd_mgt_sn", bd_mgt_sn)
        _append_optional_clause(clauses, params, "reason_code", reason_code)
        _append_optional_clause(clauses, params, "source_kind", source_kind)
        _append_optional_clause(clauses, params, "source_yyyymm", source_yyyymm)
        if min_distance_m is not None:
            clauses.append("distance_m >= :min_distance_m")
            params["min_distance_m"] = min_distance_m
        if max_distance_m is not None:
            clauses.append("distance_m <= :max_distance_m")
            params["max_distance_m"] = max_distance_m

        order_expr = _consistency_sample_order_expr(order_by)
        direction = "DESC" if desc else "ASC"
        where = " AND ".join(clauses)
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        f"""
SELECT *, count(*) OVER()::bigint AS total_count
  FROM ({_CONSISTENCY_SAMPLE_SELECT}) s
 WHERE {where}
 ORDER BY {order_expr} {direction} NULLS LAST, sample_rank ASC
 LIMIT :limit OFFSET :offset
"""
                    ),
                    params,
                )
            ).mappings().all()
        total = int(rows[0]["total_count"]) if rows else 0
        return ConsistencySamplePage(
            report_id=report_id,
            case_code=case_code,
            total=total,
            page=page,
            page_size=page_size,
            items=tuple(_consistency_sample(dict(row)) for row in rows),
        )

    async def consistency_case_summary(
        self,
        *,
        report_id: str,
        case_code: str,
    ) -> ConsistencyCaseSummary:
        await self.ensure_consistency_case_samples(report_id)
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        """
WITH base AS (
  SELECT *
    FROM ops.consistency_case_samples
   WHERE report_id = :report_id
     AND case_code = :case_code
),
severity AS (
  SELECT COALESCE(jsonb_object_agg(severity, count), '{}'::jsonb) AS value
    FROM (
      SELECT severity, count(*)::bigint AS count
        FROM base
       GROUP BY severity
    ) s
),
decision AS (
  SELECT COALESCE(jsonb_object_agg(decision_state, count), '{}'::jsonb) AS value
    FROM (
      SELECT decision_state, count(*)::bigint AS count
        FROM base
       GROUP BY decision_state
    ) d
),
sig AS (
  SELECT COALESCE(jsonb_object_agg(sig_cd, count), '{}'::jsonb) AS value
    FROM (
      SELECT sig_cd, count(*)::bigint AS count
        FROM base
       WHERE sig_cd IS NOT NULL
       GROUP BY sig_cd
       ORDER BY count DESC
       LIMIT 50
    ) g
),
dist AS (
  SELECT count(distance_m)::bigint AS distance_count,
         min(distance_m)::float8 AS min_m,
         max(distance_m)::float8 AS max_m,
         avg(distance_m)::float8 AS avg_m,
         percentile_cont(0.95) WITHIN GROUP (ORDER BY distance_m)::float8 AS p95_m
    FROM base
   WHERE distance_m IS NOT NULL
)
SELECT (SELECT count(*)::bigint FROM base) AS total,
       (SELECT value FROM severity) AS by_severity,
       (SELECT value FROM decision) AS by_decision,
       (SELECT value FROM sig) AS by_sig_cd,
       jsonb_build_object(
         'count', distance_count,
         'min_m', min_m,
         'max_m', max_m,
         'avg_m', avg_m,
         'p95_m', p95_m
       ) AS distance
  FROM dist
"""
                    ),
                    {"report_id": report_id, "case_code": case_code},
                )
            ).mappings().one()
        return ConsistencyCaseSummary(
            report_id=report_id,
            case_code=case_code,
            total=int(row["total"] or 0),
            by_severity=_int_dict(row.get("by_severity")),
            by_decision=_int_dict(row.get("by_decision")),
            by_sig_cd=_int_dict(row.get("by_sig_cd")),
            distance=_float_dict(row.get("distance")),
        )

    async def update_consistency_sample_decision(
        self,
        *,
        report_id: str,
        case_code: str,
        sample_id: str,
        req: ConsistencySampleDecisionRequest,
        actor_type: str = "api",
        client_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> ConsistencyCaseSample | None:
        payload = {
            "report_id": report_id,
            "case_code": case_code,
            "sample_id": sample_id,
            "decision_state": req.decision_state,
            "reason_code": req.reason_code,
            "note": req.note,
            "reviewer": req.reviewer,
        }
        payload_redacted, payload_hash = redact_audit_payload(payload)
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    _json_text(
                        """
UPDATE ops.consistency_case_samples
   SET decision_state = :decision_state,
       reason_code = :reason_code,
       note = :note,
       reviewed_by = :reviewed_by,
       reviewed_at = now()
 WHERE report_id = :report_id
   AND case_code = :case_code
   AND sample_id::text = :sample_id
RETURNING *
""",
                    ),
                    {
                        "report_id": report_id,
                        "case_code": case_code,
                        "sample_id": sample_id,
                        "decision_state": req.decision_state,
                        "reason_code": req.reason_code,
                        "note": req.note,
                        "reviewed_by": req.reviewer,
                    },
                )
            ).mappings().first()
            if row is None:
                return None
            selected = (
                await conn.execute(
                    text(_CONSISTENCY_SAMPLE_SELECT + " WHERE sample_id::text = :sample_id"),
                    {"sample_id": sample_id},
                )
            ).mappings().one()
            await _insert_consistency_decision_audit(
                conn,
                action="consistency.sample.decision",
                actor_type=actor_type,
                actor_id=req.reviewer,
                client_ip=client_ip,
                user_agent=user_agent,
                request_id=request_id,
                trace_id=trace_id,
                resource_type="consistency_sample",
                resource_id=sample_id,
                payload_redacted=payload_redacted,
                payload_hash=payload_hash,
            )
        return _consistency_sample(dict(selected))

    async def bulk_update_consistency_sample_decisions(
        self,
        *,
        report_id: str,
        case_code: str,
        req: ConsistencyBulkDecisionRequest,
        actor_type: str = "api",
        client_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> ConsistencyBulkDecisionResponse:
        payload = {
            "report_id": report_id,
            "case_code": case_code,
            "sample_ids": req.sample_ids,
            "decision_state": req.decision_state,
            "reason_code": req.reason_code,
            "note": req.note,
            "reviewer": req.reviewer,
        }
        payload_redacted, payload_hash = redact_audit_payload(payload)
        async with self.engine.begin() as conn:
            updated_ids = (
                await conn.execute(
                    text(
                        """
UPDATE ops.consistency_case_samples
   SET decision_state = :decision_state,
       reason_code = :reason_code,
       note = :note,
       reviewed_by = :reviewed_by,
       reviewed_at = now()
 WHERE report_id = :report_id
   AND case_code = :case_code
   AND sample_id::text = ANY(:sample_ids)
RETURNING sample_id::text
"""
                    ),
                    {
                        "report_id": report_id,
                        "case_code": case_code,
                        "sample_ids": list(req.sample_ids),
                        "decision_state": req.decision_state,
                        "reason_code": req.reason_code,
                        "note": req.note,
                        "reviewed_by": req.reviewer,
                    },
                )
            ).mappings().all()
            ids = [str(row["sample_id"]) for row in updated_ids]
            if not ids:
                return ConsistencyBulkDecisionResponse(
                    report_id=report_id,
                    case_code=case_code,
                    updated_count=0,
                    items=(),
                )
            rows = (
                await conn.execute(
                    text(_CONSISTENCY_SAMPLE_SELECT + " WHERE sample_id::text = ANY(:sample_ids)"),
                    {"sample_ids": ids},
                )
            ).mappings().all()
            await _insert_consistency_decision_audit(
                conn,
                action="consistency.sample.bulk_decision",
                actor_type=actor_type,
                actor_id=req.reviewer,
                client_ip=client_ip,
                user_agent=user_agent,
                request_id=request_id,
                trace_id=trace_id,
                resource_type="consistency_sample_bulk",
                resource_id=f"{report_id}:{case_code}",
                payload_redacted=payload_redacted,
                payload_hash=payload_hash,
            )
        return ConsistencyBulkDecisionResponse(
            report_id=report_id,
            case_code=case_code,
            updated_count=len(rows),
            items=tuple(_consistency_sample(dict(row)) for row in rows),
        )

    async def recheck_consistency_sample(
        self,
        *,
        report_id: str,
        case_code: str,
        sample_id: str,
    ) -> ConsistencySampleRecheckResponse | None:
        await self.ensure_consistency_case_samples(report_id)
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        _CONSISTENCY_SAMPLE_SELECT
                        + """
 WHERE report_id = :report_id
   AND case_code = :case_code
   AND sample_id::text = :sample_id
"""
                    ),
                    {"report_id": report_id, "case_code": case_code, "sample_id": sample_id},
                )
            ).mappings().first()
            if row is None:
                return None
            current = None
            if row.get("bd_mgt_sn"):
                current = (
                    await conn.execute(
                        text(
                            """
SELECT bd_mgt_sn,
       CASE WHEN pt_4326 IS NULL THEN NULL ELSE ST_X(pt_4326) END AS lon,
       CASE WHEN pt_4326 IS NULL THEN NULL ELSE ST_Y(pt_4326) END AS lat,
       pt_source
  FROM mv_geocode_target
 WHERE bd_mgt_sn = :bd_mgt_sn
"""
                        ),
                        {"bd_mgt_sn": row["bd_mgt_sn"]},
                    )
                ).mappings().first()
        point = None
        if current and current.get("lon") is not None and current.get("lat") is not None:
            point = ConsistencySamplePoint(x=float(current["lon"]), y=float(current["lat"]))
        return ConsistencySampleRecheckResponse(
            sample_id=sample_id,
            report_id=report_id,
            case_code=case_code,
            exists_in_current_mv=current is not None,
            point=point,
            stale=_point_changed(dict(row), dict(current) if current is not None else None),
            evidence=dict(current) if current is not None else {},
        )


def _consistency_report_dto(row: ConsistencyReportRow) -> ConsistencyReport:
    return ConsistencyReport(
        report_id=row.report_id,
        scope=row.scope,
        severity_max=row.severity_max,
        source_set=row.source_set,
        started_at=row.started_at,
        finished_at=row.finished_at,
        generated_by=row.generated_by,
        cases=tuple(
            ConsistencyCase(
                code=case.code,
                name=case.name,
                severity=case.severity,
                count=case.count,
                ratio=case.ratio,
                threshold=case.threshold,
                metric=case.metric,
                sample=case.sample,
                note=case.note,
            )
            for case in row.cases
        ),
    )


def _consistency_sample_rows(report: ConsistencyReport) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in report.cases:
        for rank, sample in enumerate(case.sample):
            bd_mgt_sn = _optional_text(sample.get("bd_mgt_sn"))
            rows.append(
                {
                    "sample_id": _sample_uuid(report.report_id, case.code, rank, sample),
                    "report_id": report.report_id,
                    "case_code": case.code,
                    "severity": _sample_severity(case.code, case.severity, sample),
                    "sample_rank": rank,
                    "bd_mgt_sn": bd_mgt_sn,
                    "rncode_full": _optional_text(sample.get("rncode_full")),
                    "sig_cd": _sample_sig_cd(sample, bd_mgt_sn),
                    "bjd_cd": _optional_text(sample.get("bjd_cd") or sample.get("emd_cd")),
                    "distance_m": _sample_distance(sample),
                    "source_yyyymm": _optional_text(sample.get("source_yyyymm")),
                    "source_kind": _optional_text(
                        sample.get("source_kind") or sample.get("evidence")
                    ),
                    "case_metric": _sample_case_metric(case.metric, sample),
                    "source_snapshot": dict(sample),
                    "bbox_4326": {},
                    "has_polygon": case.code in {"C1", "C2", "C4", "C5", "C6", "C7"},
                    "has_line": case.code == "C8",
                }
            )
    return rows


async def _insert_consistency_sample_rows(conn: Any, rows: list[dict[str, Any]]) -> None:
    await conn.execute(
        _json_text(
            """
INSERT INTO ops.consistency_case_samples
  (sample_id, report_id, case_code, severity, sample_rank, bd_mgt_sn, rncode_full,
   sig_cd, bjd_cd, distance_m, source_yyyymm, source_kind, case_metric,
   source_snapshot, bbox_4326, has_polygon, has_line)
VALUES
  (:sample_id, :report_id, :case_code, :severity, :sample_rank, :bd_mgt_sn, :rncode_full,
   :sig_cd, :bjd_cd, :distance_m, :source_yyyymm, :source_kind, :case_metric,
   :source_snapshot, :bbox_4326, :has_polygon, :has_line)
ON CONFLICT (sample_id) DO NOTHING
""",
            "case_metric",
            "source_snapshot",
            "bbox_4326",
        ),
        rows,
    )


async def _hydrate_consistency_sample_points(conn: Any, report_id: str) -> None:
    exists = await conn.scalar(text("SELECT to_regclass('mv_geocode_target')"))
    if exists is None:
        return
    await conn.execute(
        text(
            """
UPDATE ops.consistency_case_samples s
   SET point_5179 = t.pt_5179,
       point_4326 = t.pt_4326
  FROM mv_geocode_target t
 WHERE s.report_id = :report_id
   AND s.bd_mgt_sn = t.bd_mgt_sn
   AND s.point_4326 IS NULL
"""
        ),
        {"report_id": report_id},
    )


async def _insert_consistency_decision_audit(
    conn: Any,
    *,
    action: str,
    actor_type: str,
    actor_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    request_id: str | None,
    trace_id: str | None,
    resource_type: str,
    resource_id: str,
    payload_redacted: dict[str, Any],
    payload_hash: str,
) -> None:
    await conn.execute(
        _json_text(
            """
INSERT INTO ops.audit_events
  (audit_event_id, actor_type, actor_id, client_ip_hash, user_agent_hash,
   request_id, trace_id, action, resource_type, resource_id, outcome,
   payload_redacted, payload_hash)
VALUES
  (:audit_event_id, :actor_type, :actor_id, :client_ip_hash, :user_agent_hash,
   :request_id, :trace_id, :action, :resource_type, :resource_id, 'succeeded',
   :payload_redacted, :payload_hash)
""",
            "payload_redacted",
        ),
        {
            "audit_event_id": str(uuid4()),
            "actor_type": actor_type,
            "actor_id": actor_id,
            "client_ip_hash": hash_identifier(client_ip) if client_ip else None,
            "user_agent_hash": hash_identifier(user_agent) if user_agent else None,
            "request_id": request_id,
            "trace_id": trace_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "payload_redacted": payload_redacted,
            "payload_hash": payload_hash,
        },
    )


async def _latest_consistency_gate_for_batch(
    conn: Any,
    load_batch_id: str | None,
) -> Mapping[str, Any] | None:
    if not load_batch_id:
        return None
    row = (
        await conn.execute(
            text(
                """
SELECT report_id, severity_max, source_set
  FROM load_consistency_reports
 WHERE source_set ->> 'load_batch_id' = :load_batch_id
 ORDER BY started_at DESC
 LIMIT 1
"""
            ),
            {"load_batch_id": load_batch_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _load_batch_source_set(conn: Any, load_batch_id: str | None) -> dict[str, Any]:
    if not load_batch_id:
        return {}
    payload = await conn.scalar(
        text(
            """
SELECT payload
  FROM load_jobs
 WHERE job_id = :load_batch_id
   AND kind = 'full_load_batch'
"""
        ),
        {"load_batch_id": load_batch_id},
    )
    if not isinstance(payload, Mapping):
        return {}
    source_set = payload.get("source_set")
    return _json_dict(source_set)


async def _infer_current_source_set(conn: Any) -> dict[str, Any]:
    tables = {
        "juso": "tl_juso_text",
        "parcel_link": "tl_juso_parcel_link",
        "locsum": "tl_locsum_entrc",
        "navi": "tl_navi_buld_centroid",
        "shp": "tl_spbd_buld_polygon",
        "roadaddr_entrance": "tl_roadaddr_entrc",
        "sppn_makarea": "tl_sppn_makarea",
    }
    yyyymm_by_kind: dict[str, str | None] = {}
    for kind, table_name in tables.items():
        exists = await conn.scalar(
            text("SELECT to_regclass(:name)"),
            {"name": f"public.{table_name}"},
        )
        if exists is None:
            yyyymm_by_kind[kind] = None
            continue
        value = await conn.scalar(text(f"SELECT max(source_yyyymm) FROM public.{table_name}"))
        yyyymm_by_kind[kind] = str(value) if value is not None else None
    values = {value for value in yyyymm_by_kind.values() if value}
    return {
        "yyyymm_by_kind": yyyymm_by_kind,
        "mixed_yyyymm": len(values) > 1,
        "source": "database_manifest_inference",
    }


async def _collect_row_counts_for_conn(conn: Any) -> dict[str, int]:
    row_counts: dict[str, int] = {}
    for name in _ROW_COUNT_OBJECTS:
        exists = await conn.scalar(text("SELECT to_regclass(:name)"), {"name": f"public.{name}"})
        if exists is None:
            continue
        count = await conn.scalar(text(f"SELECT count(*)::bigint FROM public.{name}"))
        row_counts[name] = int(count or 0)
    return row_counts


async def _runtime_versions_for_conn(conn: Any) -> dict[str, str | None]:
    row = (
        await conn.execute(
            text(
                """
SELECT current_setting('server_version') AS postgres_version,
       (SELECT extversion FROM pg_extension WHERE extname = 'postgis') AS postgis_version,
       to_regclass('public.alembic_version') AS alembic_version_table
"""
            )
        )
    ).mappings().one()
    alembic_revision = None
    if row["alembic_version_table"] is not None:
        alembic_revision = await conn.scalar(text("SELECT version_num FROM alembic_version"))
    return {
        "git_commit": os.environ.get("KTG_GIT_COMMIT", __version__),
        "alembic_revision": _optional_text(alembic_revision),
        "postgres_version": _optional_text(row.get("postgres_version")),
        "postgis_version": _optional_text(row.get("postgis_version")),
    }


async def _mv_hash_for_conn(conn: Any, mv_row_count: int | None = None) -> str | None:
    exists = await conn.scalar(
        text("SELECT to_regclass('public.mv_geocode_target')")
    )
    if exists is None:
        return None
    if mv_row_count is None:
        mv_row_count = int(
            await conn.scalar(text("SELECT count(*)::bigint FROM public.mv_geocode_target")) or 0
        )
    return _optional_text(
        await conn.scalar(
            text(
                """
SELECT md5(
  COALESCE(pg_get_viewdef('public.mv_geocode_target'::regclass, true), '')
  || ':'
  || CAST(:mv_row_count AS text)
)
"""
            ),
            {"mv_row_count": str(mv_row_count)},
        )
    )


async def _insert_dataset_snapshot_and_release(
    conn: Any,
    *,
    snapshot_state: str,
    release_state: str,
    release_kind: str,
    source_set: Mapping[str, Any],
    row_counts: Mapping[str, int],
    consistency_report_id: str | None = None,
    consistency_gate: Mapping[str, Any] | None = None,
    performance_gate: Mapping[str, Any] | None = None,
    backup_artifact_id: str | None = None,
    created_by_job_id: str | None = None,
    activated_by_job_id: str | None = None,
    git_commit: str | None = None,
    alembic_revision: str | None = None,
    postgres_version: str | None = None,
    postgis_version: str | None = None,
    mv_hash: str | None = None,
    notes: str | None = None,
    source_match_set_id: str | None = None,
    snapshot_metadata: Mapping[str, Any] | None = None,
) -> tuple[DatasetSnapshot, ServingRelease]:
    runtime = await _runtime_versions_for_conn(conn)
    previous = (
        await conn.execute(
            text(
                """
SELECT serving_release_id, dataset_snapshot_id
  FROM ops.serving_releases
 WHERE state = 'active'
 ORDER BY activated_at DESC NULLS LAST, created_at DESC
 LIMIT 1
 FOR UPDATE
"""
            )
        )
    ).mappings().first()
    parent_snapshot_id = _optional_str(previous["dataset_snapshot_id"]) if previous else None
    previous_release_id = _optional_str(previous["serving_release_id"]) if previous else None

    if release_state == "active":
        await conn.execute(
            text(
                """
UPDATE ops.serving_releases
   SET state = 'superseded'
 WHERE state = 'active'
"""
            )
        )

    snapshot_id = str(uuid4())
    release_id = str(uuid4())
    snapshot_row = (
        await conn.execute(
            _json_text(
                """
INSERT INTO ops.dataset_snapshots
  (dataset_snapshot_id, state, parent_dataset_snapshot_id, source_set, source_set_hash,
   git_commit, alembic_revision, postgres_version, postgis_version,
   row_counts, consistency_report_id, backup_artifact_id, source_match_set_id,
   created_by_job_id, validated_at)
VALUES
  (:dataset_snapshot_id, :state, :parent_dataset_snapshot_id, :source_set, :source_set_hash,
   :git_commit, :alembic_revision, :postgres_version, :postgis_version,
   :row_counts, :consistency_report_id, :backup_artifact_id, :source_match_set_id,
   :created_by_job_id, CASE WHEN :validated THEN now() ELSE NULL END)
RETURNING dataset_snapshot_id, state, parent_dataset_snapshot_id, source_set, source_set_hash,
          git_commit, alembic_revision, postgres_version, postgis_version,
          row_counts, table_stats_artifact_id, consistency_report_id,
          performance_artifact_id, backup_artifact_id, created_by_job_id,
          created_at, validated_at
""",
                "source_set",
                "row_counts",
            ),
            {
                "dataset_snapshot_id": snapshot_id,
                "state": snapshot_state,
                "parent_dataset_snapshot_id": parent_snapshot_id,
                "source_set": _snapshot_source_set(source_set, snapshot_metadata),
                "source_set_hash": canonical_payload_hash(source_set),
                "git_commit": git_commit or runtime["git_commit"],
                "alembic_revision": alembic_revision or runtime["alembic_revision"],
                "postgres_version": postgres_version or runtime["postgres_version"],
                "postgis_version": postgis_version or runtime["postgis_version"],
                "row_counts": dict(row_counts),
                "consistency_report_id": consistency_report_id,
                "backup_artifact_id": backup_artifact_id,
                "source_match_set_id": source_match_set_id,
                "created_by_job_id": created_by_job_id,
                "validated": snapshot_state in {"validated", "released"},
            },
        )
    ).mappings().one()

    release_row = (
        await conn.execute(
            _json_text(
                """
INSERT INTO ops.serving_releases
  (serving_release_id, dataset_snapshot_id, state, release_kind, previous_serving_release_id,
   mv_name, mv_hash, consistency_gate, performance_gate, activated_by_job_id,
   activated_at, notes)
VALUES
  (:serving_release_id, :dataset_snapshot_id, :state, :release_kind, :previous_serving_release_id,
   'mv_geocode_target', :mv_hash, :consistency_gate, :performance_gate,
   :activated_by_job_id, CASE WHEN :active THEN now() ELSE NULL END, :notes)
RETURNING serving_release_id, dataset_snapshot_id, state, release_kind, previous_serving_release_id,
          rollback_target_serving_release_id, mv_name, mv_hash, consistency_gate,
          performance_gate, activated_by_job_id, activated_at, notes, created_at
""",
                "consistency_gate",
                "performance_gate",
            ),
            {
                "serving_release_id": release_id,
                "dataset_snapshot_id": snapshot_id,
                "state": release_state,
                "release_kind": release_kind,
                "previous_serving_release_id": previous_release_id,
                "mv_hash": mv_hash if mv_hash is not None else (
                    await _mv_hash_for_conn(conn) if release_state == "active" else None
                ),
                "consistency_gate": dict(consistency_gate or {}),
                "performance_gate": dict(performance_gate or {}),
                "activated_by_job_id": activated_by_job_id if release_state == "active" else None,
                "active": release_state == "active",
                "notes": notes,
            },
        )
    ).mappings().one()

    await _insert_ops_audit_event(
        conn,
        action=(
            "serving_release.activate"
            if release_state == "active"
            else "serving_release.candidate"
        ),
        actor_type="system",
        outcome="succeeded",
        resource_type="serving_release",
        resource_id=release_id,
        job_id=activated_by_job_id or created_by_job_id,
        payload={
            "snapshot_id": snapshot_id,
            "release_id": release_id,
            "release_kind": release_kind,
            "release_state": release_state,
            "previous_release_id": previous_release_id,
            "source_set_hash": canonical_payload_hash(source_set),
        },
    )
    return _dataset_snapshot(dict(snapshot_row)), _serving_release(dict(release_row))


async def _active_release_snapshot_id_for_conn(conn: Any) -> str | None:
    value = await conn.scalar(
        text(
            """
SELECT dataset_snapshot_id::text
  FROM ops.serving_releases
 WHERE state = 'active'
 ORDER BY activated_at DESC NULLS LAST, created_at DESC
 LIMIT 1
"""
        )
    )
    return _optional_str(value)


async def _insert_ops_audit_event(
    conn: Any,
    *,
    action: str,
    actor_type: str,
    outcome: str,
    resource_type: str,
    resource_id: str,
    payload: Mapping[str, Any],
    job_id: str | None = None,
) -> None:
    payload_redacted, payload_hash = redact_audit_payload(payload)
    await conn.execute(
        _json_text(
            """
INSERT INTO ops.audit_events
  (audit_event_id, actor_type, action, resource_type, resource_id, job_id,
   outcome, payload_redacted, payload_hash)
VALUES
  (:audit_event_id, :actor_type, :action, :resource_type, :resource_id, :job_id,
   :outcome, :payload_redacted, :payload_hash)
""",
            "payload_redacted",
        ),
        {
            "audit_event_id": str(uuid4()),
            "actor_type": actor_type,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "job_id": job_id,
            "outcome": outcome,
            "payload_redacted": payload_redacted,
            "payload_hash": payload_hash,
        },
    )


def _consistency_sample(row: Mapping[str, Any]) -> ConsistencyCaseSample:
    lon = row.get("lon")
    lat = row.get("lat")
    point = None
    if lon is not None and lat is not None:
        point = ConsistencySamplePoint(x=float(lon), y=float(lat))
    return ConsistencyCaseSample(
        sample_id=str(row["sample_id"]),
        report_id=str(row["report_id"]),
        case_code=str(row["case_code"]),
        severity=row["severity"],
        sample_rank=int(row["sample_rank"] or 0),
        bd_mgt_sn=row.get("bd_mgt_sn"),
        rncode_full=row.get("rncode_full"),
        sig_cd=row.get("sig_cd"),
        bjd_cd=row.get("bjd_cd"),
        distance_m=float(row["distance_m"]) if row.get("distance_m") is not None else None,
        source_yyyymm=row.get("source_yyyymm"),
        source_kind=row.get("source_kind"),
        case_metric=_json_dict(row.get("case_metric")),
        source_snapshot=_json_dict(row.get("source_snapshot")),
        point=point,
        bbox_4326=_json_dict(row.get("bbox_4326")),
        has_polygon=bool(row.get("has_polygon")),
        has_line=bool(row.get("has_line")),
        decision_state=row.get("decision_state") or "unreviewed",
        reason_code=row.get("reason_code"),
        note=row.get("note"),
        reviewed_by=row.get("reviewed_by"),
        reviewed_at=row.get("reviewed_at"),
        created_at=row["created_at"],
    )


def _append_optional_clause(
    clauses: list[str],
    params: dict[str, Any],
    column: str,
    value: str | None,
    *,
    param_name: str | None = None,
) -> None:
    if value is None:
        return
    name = param_name or column
    clauses.append(f"{column} = :{name}")
    params[name] = value


def _consistency_sample_order_expr(order_by: str) -> str:
    allowed = {
        "sample_rank": "sample_rank",
        "distance_m": "distance_m",
        "severity": "severity",
        "decision_state": "decision_state",
        "reviewed_at": "reviewed_at",
        "created_at": "created_at",
        "sig_cd": "sig_cd",
    }
    return allowed.get(order_by, "sample_rank")


def _sample_uuid(report_id: str, case_code: str, rank: int, sample: Mapping[str, Any]) -> str:
    stable_payload = json.dumps(sample, default=str, ensure_ascii=True, sort_keys=True)
    stable_key = "|".join(
        (
            report_id,
            case_code,
            str(rank),
            str(sample.get("bd_mgt_sn") or ""),
            str(sample.get("rncode_full") or ""),
            str(sample.get("bjd_cd") or sample.get("emd_cd") or ""),
            stable_payload,
        )
    )
    return str(uuid5(NAMESPACE_URL, f"kortravelgeo/consistency/{stable_key}"))


def _sample_sig_cd(sample: Mapping[str, Any], bd_mgt_sn: str | None) -> str | None:
    sig_cd = _optional_text(sample.get("sig_cd"))
    if sig_cd:
        return sig_cd
    bjd_cd = _optional_text(sample.get("bjd_cd") or sample.get("emd_cd"))
    if bjd_cd and len(bjd_cd) >= 5:
        return bjd_cd[:5]
    if bd_mgt_sn and len(bd_mgt_sn) >= 5:
        return bd_mgt_sn[:5]
    return None


def _sample_distance(sample: Mapping[str, Any]) -> float | None:
    for key in ("distance_m", "dist_m"):
        value = sample.get(key)
        if value is not None:
            return float(value)
    return None


def _sample_case_metric(
    case_metric: Mapping[str, float] | None,
    sample: Mapping[str, Any],
) -> dict[str, Any]:
    metric: dict[str, Any] = {"case": dict(case_metric or {})}
    sample_metric: dict[str, Any] = {}
    for key, value in sample.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            sample_metric[str(key)] = float(value)
    if sample_metric:
        metric["sample"] = sample_metric
    return metric


def _sample_severity(
    case_code: str,
    case_severity: Literal["OK", "INFO", "WARN", "ERROR"],
    sample: Mapping[str, Any],
) -> Literal["OK", "INFO", "WARN", "ERROR"]:
    if case_code in {"C2", "C9"}:
        return "ERROR"
    if case_code == "C4":
        distance_m = _sample_distance(sample)
        return "ERROR" if distance_m is not None and distance_m > 500 else "WARN"
    if case_code in {"C6", "C7"}:
        reason = str(sample.get("reason") or "")
        return "ERROR" if reason.startswith("outside_") else "WARN"
    if case_code == "C3":
        return case_severity
    if case_code == "C10":
        return "WARN"
    return "WARN" if case_severity != "OK" else "OK"


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value)
    return text_value or None


def _float_dict(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, float] = {}
    for key, item in value.items():
        if item is not None:
            result[str(key)] = float(item)
    return result


def _point_changed(row: Mapping[str, Any], current: Mapping[str, Any] | None) -> bool:
    if current is None:
        return row.get("bd_mgt_sn") is not None
    if row.get("lon") is None or row.get("lat") is None:
        return current.get("lon") is not None or current.get("lat") is not None
    if current.get("lon") is None or current.get("lat") is None:
        return True
    return abs(float(row["lon"]) - float(current["lon"])) > 0.000001 or abs(
        float(row["lat"]) - float(current["lat"])
    ) > 0.000001


def _audit_event(row: Mapping[str, Any]) -> AuditEvent:
    return AuditEvent(
        audit_event_id=str(row["audit_event_id"]),
        occurred_at=row["occurred_at"],
        actor_type=row["actor_type"],
        actor_id=row.get("actor_id"),
        client_ip_hash=row.get("client_ip_hash"),
        user_agent_hash=row.get("user_agent_hash"),
        request_id=row.get("request_id"),
        trace_id=row.get("trace_id"),
        action=str(row["action"]),
        resource_type=row.get("resource_type"),
        resource_id=row.get("resource_id"),
        job_id=row.get("job_id"),
        outcome=row["outcome"],
        error_code=row.get("error_code"),
        payload_redacted=_json_dict(row.get("payload_redacted")),
        payload_hash=str(row["payload_hash"]),
    )


def _dataset_snapshot(row: Mapping[str, Any]) -> DatasetSnapshot:
    return DatasetSnapshot(
        dataset_snapshot_id=str(row["dataset_snapshot_id"]),
        state=row["state"],
        parent_dataset_snapshot_id=_optional_str(row.get("parent_dataset_snapshot_id")),
        source_set=_json_dict(row.get("source_set")),
        source_set_hash=str(row["source_set_hash"]),
        git_commit=row.get("git_commit"),
        alembic_revision=row.get("alembic_revision"),
        postgres_version=row.get("postgres_version"),
        postgis_version=row.get("postgis_version"),
        row_counts=_int_dict(row.get("row_counts")),
        table_stats_artifact_id=_optional_str(row.get("table_stats_artifact_id")),
        consistency_report_id=row.get("consistency_report_id"),
        performance_artifact_id=_optional_str(row.get("performance_artifact_id")),
        backup_artifact_id=_optional_str(row.get("backup_artifact_id")),
        created_by_job_id=row.get("created_by_job_id"),
        created_at=row["created_at"],
        validated_at=row.get("validated_at"),
    )


def _serving_release(row: Mapping[str, Any]) -> ServingRelease:
    return ServingRelease(
        serving_release_id=str(row["serving_release_id"]),
        dataset_snapshot_id=str(row["dataset_snapshot_id"]),
        state=row["state"],
        release_kind=row["release_kind"],
        previous_serving_release_id=_optional_str(row.get("previous_serving_release_id")),
        rollback_target_serving_release_id=_optional_str(
            row.get("rollback_target_serving_release_id")
        ),
        mv_name=str(row.get("mv_name") or "mv_geocode_target"),
        mv_hash=row.get("mv_hash"),
        consistency_gate=_json_dict(row.get("consistency_gate")),
        performance_gate=_json_dict(row.get("performance_gate")),
        activated_by_job_id=row.get("activated_by_job_id"),
        activated_at=row.get("activated_at"),
        notes=row.get("notes"),
        created_at=row["created_at"],
    )


def _ops_artifact(row: Mapping[str, Any]) -> OpsArtifact:
    return OpsArtifact(
        artifact_id=str(row["artifact_id"]),
        artifact_type=str(row["artifact_type"]),
        state=row["state"],
        storage_kind=row["storage_kind"],
        storage_uri=row.get("storage_uri"),
        display_name=row.get("display_name"),
        media_type=row.get("media_type"),
        compression=row.get("compression"),
        size_bytes=_optional_int(row.get("size_bytes")),
        sha256=row.get("sha256"),
        retention_class=row.get("retention_class"),
        expires_at=row.get("expires_at"),
        job_id=row.get("job_id"),
        dataset_snapshot_id=_optional_str(row.get("dataset_snapshot_id")),
        serving_release_id=_optional_str(row.get("serving_release_id")),
        manifest=_json_dict(row.get("manifest")),
        callback_url=row.get("callback_url"),
        callback_state=row.get("callback_state"),
        created_at=row["created_at"],
        finished_at=row.get("finished_at"),
    )


def _maintenance_window(row: Mapping[str, Any]) -> MaintenanceWindow:
    return MaintenanceWindow(
        maintenance_window_id=str(row["maintenance_window_id"]),
        kind=row["kind"],
        state=row["state"],
        starts_at=row.get("starts_at"),
        ends_at=row.get("ends_at"),
        actual_started_at=row.get("actual_started_at"),
        actual_ended_at=row.get("actual_ended_at"),
        reason=str(row["reason"]),
        requested_by=row.get("requested_by"),
        approved_by=row.get("approved_by"),
        blocks=_json_dict(row.get("blocks")),
        created_by_job_id=row.get("created_by_job_id"),
        closed_by_job_id=row.get("closed_by_job_id"),
        created_at=row["created_at"],
    )


def _table_stats_snapshot(row: Mapping[str, Any]) -> TableStatsSnapshot:
    return TableStatsSnapshot(
        table_stats_snapshot_id=str(row["table_stats_snapshot_id"]),
        dataset_snapshot_id=_optional_str(row.get("dataset_snapshot_id")),
        captured_at=row["captured_at"],
        schema_name=str(row["schema_name"]),
        object_name=str(row["object_name"]),
        object_kind=row["object_kind"],
        estimated_rows=_optional_int(row.get("estimated_rows")),
        exact_rows=_optional_int(row.get("exact_rows")),
        total_bytes=_optional_int(row.get("total_bytes")),
        table_bytes=_optional_int(row.get("table_bytes")),
        index_bytes=_optional_int(row.get("index_bytes")),
        toast_bytes=_optional_int(row.get("toast_bytes")),
        dead_tuples=_optional_int(row.get("dead_tuples")),
        last_vacuum=row.get("last_vacuum"),
        last_analyze=row.get("last_analyze"),
        stats=_json_dict(row.get("stats")),
    )


def _pg_stat_statement_snapshot(row: Mapping[str, Any]) -> PgStatStatementSnapshot:
    return PgStatStatementSnapshot(
        pg_stat_snapshot_id=str(row["pg_stat_snapshot_id"]),
        captured_at=row["captured_at"],
        rank=int(row["rank"]),
        queryid=_optional_str(row.get("queryid")),
        query_fingerprint=str(row["query_fingerprint"]),
        operation=str(row["operation"]),
        calls=int(row["calls"]),
        total_exec_time_ms=float(row["total_exec_time_ms"]),
        mean_exec_time_ms=float(row["mean_exec_time_ms"]),
        max_exec_time_ms=float(row["max_exec_time_ms"]),
        rows_returned=int(row["rows_returned"]),
        shared_blks_hit=int(row.get("shared_blks_hit") or 0),
        shared_blks_read=int(row.get("shared_blks_read") or 0),
        temp_blks_read=int(row.get("temp_blks_read") or 0),
        temp_blks_written=int(row.get("temp_blks_written") or 0),
        query_preview=str(row["query_preview"]),
        stats=_json_dict(row.get("stats")),
    )


def _pg_stat_query_preview(query: str) -> str:
    normalized = _SQL_SPACE_RE.sub(" ", query).strip()
    masked = _SQL_LITERAL_RE.sub("?", normalized)
    return (masked[:500] or "empty")


def _default_maintenance_blocks(kind: str) -> dict[str, Any]:
    if kind in {"restore", "schema_migration", "exclusive"}:
        return {"jobs": ["*"], "api": ["admin.loads", "admin.maintenance", "admin.ops"]}
    if kind == "full_load":
        return {"jobs": ["full_load_batch", "mv_refresh", "db_restore"]}
    if kind == "mv_refresh":
        return {"jobs": ["full_load_batch", "mv_refresh"]}
    if kind == "read_only":
        return {"jobs": ["full_load_batch", "mv_refresh", "db_restore"], "writes": ["admin"]}
    return {}


def _snapshot_source_set(
    source_set: Mapping[str, Any],
    snapshot_metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Merge read-only snapshot metadata (e.g. ``forced_promotion``) into the
    ``source_set`` JSONB. The ``source_set_hash`` is computed from the original
    ``source_set`` (not this merged copy) so provenance metadata never perturbs
    the canonical hash. The ``source_match_set_id`` FK column stays the 정본."""
    merged = dict(source_set)
    if snapshot_metadata:
        merged["rebuild_metadata"] = dict(snapshot_metadata)
    return merged


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _int_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for key, item in value.items():
        if isinstance(item, int):
            result[str(key)] = item
    return result


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


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
