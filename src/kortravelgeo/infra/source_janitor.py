"""Upload-session janitor service (T-203c).

DB + RustFS glue around the pure decisions in ``core.source_janitor``. One pass
(:func:`run_source_upload_janitor`):

1. acquires the global ``SOURCE_JANITOR`` PostgreSQL advisory lock — if another
   process holds it, the run is skipped (doc line ~525);
2. loads non-terminal sessions, builds a ``JanitorSessionFact`` per session from
   its recorded parts;
3. for each session past ``expires_at`` aborts every unfinished multipart upload
   via RustFS ``abort_multipart_upload`` and marks the session ``expired`` /
   ``cancelled``; stored-but-unregistered objects past the registration deadline
   transition to a ``registration_expired`` marker. RustFS objects that finished
   storing are NEVER auto-deleted;
4. records the aggregate to an audit event (``SOURCE_JANITOR``) and metrics.

The actual RustFS abort and session-state writes are isolated so unit tests can
exercise the decision flow against fakes; the lock acquisition is mockable too.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.core.source_events import SOURCE_JANITOR
from kortravelgeo.core.source_janitor import (
    JanitorMultipartFact,
    JanitorRunSummary,
    JanitorSessionDecision,
    JanitorSessionFact,
    decide_session_fate,
)
from kortravelgeo.infra.concurrency import (
    AdvisoryLockKey,
    AdvisoryLockNamespace,
    ConcurrentExecutionError,
    cross_process_lock,
)
from kortravelgeo.infra.metrics import (
    record_source_janitor_abort,
    record_source_janitor_run,
    record_source_janitor_session,
)
from kortravelgeo.infra.rustfs import RustfsClient
from kortravelgeo.infra.source_audit import insert_source_audit_event

_LOGGER = logging.getLogger(__name__)


async def _load_session_facts(
    engine: AsyncEngine, *, limit: int
) -> tuple[JanitorSessionFact, ...]:
    """Load non-terminal sessions + their parts as janitor facts.

    ``stored_to_rustfs`` is true when every required slot has a completed part;
    ``open_multiparts`` are parts that hold a ``multipart_upload_id`` but whose
    slot never completed (storage-occupying abort candidates).
    """
    async with engine.connect() as conn:
        session_rows = (
            await conn.execute(
                text(
                    """
SELECT source_upload_session_id, state, created_at, expires_at,
       registration_deadline_at, registered_at, expected_file_count
  FROM ops.source_upload_sessions
 WHERE state NOT IN (
         'available', 'cancelled', 'expired', 'registered',
         'registration_expired', 'failed_upload', 'failed_extract', 'failed_hash'
       )
 ORDER BY created_at ASC
 LIMIT :limit
"""
                ),
                {"limit": limit},
            )
        ).mappings().all()

        facts: list[JanitorSessionFact] = []
        for row in session_rows:
            sid = str(row["source_upload_session_id"])
            part_rows = (
                await conn.execute(
                    text(
                        """
SELECT part_key, multipart_upload_id, completed_at
  FROM ops.source_upload_session_parts
 WHERE source_upload_session_id = :sid
"""
                    ),
                    {"sid": sid},
                )
            ).mappings().all()

            completed_slots: set[str] = set()
            open_multiparts: list[JanitorMultipartFact] = []
            seen_upload_ids: set[str] = set()
            for part in part_rows:
                part_key = str(part["part_key"])
                if part["completed_at"] is not None:
                    completed_slots.add(part_key)
            for part in part_rows:
                part_key = str(part["part_key"])
                upload_id = part["multipart_upload_id"]
                if (
                    upload_id
                    and part_key not in completed_slots
                    and str(upload_id) not in seen_upload_ids
                ):
                    seen_upload_ids.add(str(upload_id))
                    open_multiparts.append(
                        JanitorMultipartFact(
                            part_key=part_key,
                            object_key=_staging_object_key(sid, part_key),
                            multipart_upload_id=str(upload_id),
                        )
                    )

            expected = int(row["expected_file_count"])
            stored = expected > 0 and len(completed_slots) >= expected

            facts.append(
                JanitorSessionFact(
                    upload_session_id=sid,
                    state=str(row["state"]),
                    created_at=row["created_at"],
                    expires_at=row["expires_at"],
                    registration_deadline_at=row["registration_deadline_at"],
                    registered_at=row["registered_at"],
                    stored_to_rustfs=stored,
                    open_multiparts=tuple(open_multiparts),
                )
            )
    return tuple(facts)


def _staging_object_key(session_id: str, part_key: str) -> str:
    """Placeholder staging key recorded on the part (abort uses upload_id).

    The S3 ``AbortMultipartUpload`` API keys by object key + uploadId. The live
    upload path stores the slot object under a session-scoped key; the janitor
    only needs *a* key paired with the upload id, and RustFS treats abort as
    idempotent (404 tolerated), so a best-effort key derived from the session is
    sufficient. The session metadata is the source of truth in production; this
    keeps the janitor self-contained for the abort call.
    """
    return f"{session_id}/{part_key}"


async def _apply_session_decision(
    engine: AsyncEngine,
    decision: JanitorSessionDecision,
    *,
    rustfs: RustfsClient | None,
    summary: JanitorRunSummary,
) -> JanitorRunSummary:
    aborts_ok = summary.aborts_succeeded
    aborts_failed = summary.aborts_failed

    for mp in decision.aborts:
        if rustfs is None:
            aborts_failed += 1
            record_source_janitor_abort(outcome="failed")
            continue
        try:
            await rustfs.abort_multipart_upload(
                mp.object_key, upload_id=mp.multipart_upload_id
            )
            aborts_ok += 1
            record_source_janitor_abort(outcome="succeeded")
        except Exception:  # retried next pass; never auto-delete a stored object
            _LOGGER.warning(
                "janitor multipart abort failed",
                extra={
                    "upload_session_id": decision.upload_session_id,
                    "part_key": mp.part_key,
                },
            )
            aborts_failed += 1
            record_source_janitor_abort(outcome="failed")

    if decision.new_state is not None:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
UPDATE ops.source_upload_sessions
   SET state = :state,
       error_message = COALESCE(:error_message, error_message),
       updated_at = now()
 WHERE source_upload_session_id = :sid
   AND state NOT IN (
         'available', 'cancelled', 'expired', 'registered',
         'registration_expired', 'failed_upload', 'failed_extract', 'failed_hash'
       )
"""
                ),
                {
                    "sid": decision.upload_session_id,
                    "state": decision.new_state,
                    "error_message": decision.error_message,
                },
            )

    record_source_janitor_session(action=decision.action)
    expired = summary.expired_sessions + (1 if decision.action == "expire" else 0)
    cancelled = summary.cancelled_sessions + (1 if decision.action == "cancel" else 0)
    reg_expired = summary.registration_expired + (
        1 if decision.action == "registration_expired" else 0
    )
    processed = summary.processed_sessions + (0 if decision.action == "skip" else 1)
    return JanitorRunSummary(
        processed_sessions=processed,
        expired_sessions=expired,
        cancelled_sessions=cancelled,
        registration_expired=reg_expired,
        aborts_succeeded=aborts_ok,
        aborts_failed=aborts_failed,
        skipped_locked=False,
    )


async def _audit_janitor(engine: AsyncEngine, summary: JanitorRunSummary) -> None:
    async with engine.begin() as conn:
        await insert_source_audit_event(
            conn,
            action=SOURCE_JANITOR,
            outcome="completed",
            actor_type="system",
            actor_id="system:source_janitor",
            resource_type="source_upload_session",
            payload=summary.as_payload(),
        )


async def run_source_upload_janitor(
    engine: AsyncEngine,
    *,
    rustfs: RustfsClient | None,
    ttl_days: int,
    deadline_days: int,
    now: object | None = None,
    session_limit: int = 500,
    audit: bool = True,
) -> JanitorRunSummary:
    """Run one janitor pass under the ``SOURCE_JANITOR`` advisory lock.

    Returns a :class:`JanitorRunSummary`. If the advisory lock is already held
    (another janitor running), returns immediately with ``skipped_locked=True``
    and does not touch any session (doc line ~525).
    """
    from datetime import UTC, datetime

    effective_now = now if isinstance(now, datetime) else datetime.now(UTC)
    key = AdvisoryLockKey.global_key(AdvisoryLockNamespace.SOURCE_JANITOR)
    try:
        async with cross_process_lock(engine, key):
            facts = await _load_session_facts(engine, limit=session_limit)
            summary = JanitorRunSummary()
            for fact in facts:
                decision = decide_session_fate(
                    fact,
                    now=effective_now,
                    ttl_days=ttl_days,
                    deadline_days=deadline_days,
                )
                summary = await _apply_session_decision(
                    engine, decision, rustfs=rustfs, summary=summary
                )
            record_source_janitor_run(outcome="ran")
            if audit:
                await _audit_janitor(engine, summary)
            _LOGGER.info("source upload janitor completed", extra=summary.as_payload())
            return summary
    except ConcurrentExecutionError:
        record_source_janitor_run(outcome="skipped_locked")
        _LOGGER.info("source upload janitor skipped: lock held by another process")
        return JanitorRunSummary(skipped_locked=True)
