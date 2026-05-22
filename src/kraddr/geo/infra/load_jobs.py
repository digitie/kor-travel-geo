"""Persistent load job state helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import TextClause, text

if TYPE_CHECKING:
    from uuid import UUID


class LoadJobState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class StartupRecoveryDecision:
    state: LoadJobState
    should_enqueue: bool
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class LoadJobRecord:
    job_id: UUID
    kind: str
    payload: dict[str, Any]
    state: LoadJobState
    progress: float = 0.0
    current_stage: str | None = None
    error_message: str | None = None
    source_checksum: str | None = None


CREATE_LOAD_JOBS_TABLE_SQL: TextClause = text(
    """
    CREATE TABLE IF NOT EXISTS load_jobs (
      job_id          UUID PRIMARY KEY,
      kind            TEXT NOT NULL,
      payload         JSONB NOT NULL,
      state           TEXT NOT NULL CHECK (
        state IN ('PENDING','RUNNING','SUCCESS','FAILED','CANCELLED')
      ),
      progress        NUMERIC(5,4) NOT NULL DEFAULT 0,
      current_stage   TEXT,
      error_message   TEXT,
      source_checksum TEXT,
      heartbeat_at    TIMESTAMPTZ,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
      started_at      TIMESTAMPTZ,
      finished_at     TIMESTAMPTZ,
      updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """
)

CREATE_LOAD_JOBS_STATE_INDEX_SQL: TextClause = text(
    """
    CREATE INDEX IF NOT EXISTS idx_load_jobs_state_created
      ON load_jobs (state, created_at)
    """
)

MARK_INTERRUPTED_RUNNING_FAILED_SQL: TextClause = text(
    """
    UPDATE load_jobs
       SET state = 'FAILED',
           error_message = COALESCE(error_message, :error_message),
           finished_at = COALESCE(finished_at, now()),
           updated_at = now()
     WHERE state = 'RUNNING'
    """
)


def decide_startup_recovery(
    state: LoadJobState,
    *,
    payload_file_exists: bool = False,
    checksum_matches: bool = False,
) -> StartupRecoveryDecision:
    """Return how a persisted job should be treated when the API process starts."""

    if state is LoadJobState.RUNNING:
        return StartupRecoveryDecision(
            state=LoadJobState.FAILED,
            should_enqueue=False,
            error_message="Process stopped while the load job was running.",
        )

    if state is LoadJobState.PENDING:
        if payload_file_exists and checksum_matches:
            return StartupRecoveryDecision(state=LoadJobState.PENDING, should_enqueue=True)
        return StartupRecoveryDecision(
            state=LoadJobState.FAILED,
            should_enqueue=False,
            error_message="Pending load job payload is missing or checksum mismatched.",
        )

    return StartupRecoveryDecision(state=state, should_enqueue=False)
