"""Shared ``ops.audit_events`` writer for source-registry services (T-210).

The source-management services (``source_group_service``,
``source_match_set_service``, ``source_reconcile``, ``source_rebuild_service``,
``source_restore_service``, ``source_janitor``) all need to append one
``ops.audit_events`` row inside the caller's transaction. The table has two hard
DDL constraints those services originally ignored:

* ``payload_hash TEXT NOT NULL CHECK (char_length(payload_hash) = 64)`` — every
  row MUST carry a canonical SHA-256 of the payload; and
* ``outcome IN ('started','succeeded','failed','cancelled','denied')`` — the
  outcome column is a fixed lifecycle enum, not a free-text domain status.

The services express rich *domain* outcomes (``registered``, ``active``,
``integrity_gate_failed`` …) which are neither one of the five enum values nor a
hash. This helper bridges that gap once: it computes ``payload_redacted`` /
``payload_hash`` via :func:`redact_audit_payload`, maps the domain outcome onto
the lifecycle enum, and preserves the original domain outcome inside the payload
(``payload['domain_outcome']``) so no audit detail is lost. Mirrors the canonical
``admin_repo.record_audit_event`` insert, but runs inside an existing connection.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncConnection

from kortravelgeo.core.redaction import redact_audit_payload

#: The five lifecycle values the ``ops.audit_events.outcome`` CHECK permits.
AUDIT_OUTCOMES: frozenset[str] = frozenset(
    {"started", "succeeded", "failed", "cancelled", "denied"}
)

#: Domain-outcome substrings that map to ``denied`` (a guard/precondition
#: refused the action) rather than ``failed`` (the action was attempted and
#: errored). Checked before the generic failure markers.
_DENIED_MARKERS: tuple[str, ...] = (
    "blocked",
    "reject",
    "denied",
    "unauthorized",
    "stale",
    "ignored",
    "skipped_ineligible",
    "skipped_not_found",
)

#: Domain-outcome substrings that map to ``failed``.
_FAILED_MARKERS: tuple[str, ...] = (
    "fail",
    "error",
    "delete_failed",
    "quarantin",
    "invalid",
    "missing",
    "mismatch",
)

#: Domain-outcome substrings that map to ``cancelled``.
_CANCELLED_MARKERS: tuple[str, ...] = ("cancel", "expired", "abort")


def map_audit_outcome(domain_outcome: str) -> str:
    """Map a rich domain outcome onto the ``ops.audit_events`` lifecycle enum.

    Exact enum values pass through unchanged. Otherwise the domain outcome is
    classified by substring: refusals/guards → ``denied``; attempted-but-broke
    → ``failed``; cancellations/expiries → ``cancelled``; everything else
    (``registered``, ``active``, ``validated`` …) → ``succeeded``.
    """
    if domain_outcome in AUDIT_OUTCOMES:
        return domain_outcome
    lowered = domain_outcome.lower()
    if any(marker in lowered for marker in _DENIED_MARKERS):
        return "denied"
    if any(marker in lowered for marker in _CANCELLED_MARKERS):
        return "cancelled"
    if any(marker in lowered for marker in _FAILED_MARKERS):
        return "failed"
    return "succeeded"


async def insert_source_audit_event(
    conn: AsyncConnection,
    *,
    action: str,
    outcome: str,
    actor_type: str = "ui",
    actor_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    job_id: str | None = None,
    error_code: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append one source-management audit row inside the caller's transaction.

    Computes ``payload_redacted`` + ``payload_hash`` and maps ``outcome`` onto
    the lifecycle enum, recording the original domain outcome in the payload.
    """
    enriched: dict[str, Any] = dict(payload or {})
    enriched["domain_outcome"] = outcome
    payload_redacted, payload_hash = redact_audit_payload(enriched)
    stmt = text(
        """
INSERT INTO ops.audit_events
  (audit_event_id, actor_type, actor_id, action, resource_type, resource_id,
   job_id, outcome, error_code, payload_redacted, payload_hash)
VALUES
  (:audit_event_id, :actor_type, :actor_id, :action, :resource_type, :resource_id,
   :job_id, :outcome, :error_code, :payload_redacted, :payload_hash)
"""
    ).bindparams(bindparam("payload_redacted", type_=JSONB))
    await conn.execute(
        stmt,
        {
            "audit_event_id": str(uuid4()),
            "actor_type": actor_type,
            "actor_id": actor_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "job_id": job_id,
            "outcome": map_audit_outcome(outcome),
            "error_code": error_code,
            "payload_redacted": payload_redacted,
            "payload_hash": payload_hash,
        },
    )
