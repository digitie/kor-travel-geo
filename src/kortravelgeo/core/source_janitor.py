"""Pure decision logic for the upload-session janitor and soft-delete/restore (T-203c).

These are **pure functions** (no DB, no RustFS, no clock except the explicit
``now`` argument) so the janitor's per-session fate, the soft-delete active-match-set
guard, and the restore object-verification transition can be unit-tested with
synthetic facts. The DB / storage glue lives in ``infra/source_janitor.py`` and
``infra/source_group_service.py``; this module only decides *what* should happen.

Decisions follow ``docs/t109-backup-source-upload-management.md``:

* janitor (lines ~519-525): ``expires_at`` 이후 미완 multipart upload abort 후
  session ``expired``/``cancelled`` 마감; RustFS 저장 완료 object는 자동 삭제 안 함;
  ``registration_deadline_at`` 지난 미등록 object는 ``pending_registration`` →
  ``registration_expired`` issue 전이.
* soft-delete / restore (lines ~1440-1445): active match set이 참조하는 group은
  소프트 삭제(및 하드 삭제) 차단; restore는 RustFS ``head_object`` + hash 검증으로
  ``soft_deleted`` → ``validating`` → ``available`` (object 없음 → ``missing``,
  hash mismatch → ``quarantined``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

# --- janitor: upload-session fate ------------------------------------------

#: Default TTL / deadline (settings mirror the doc 1차 기본값, lines ~523).
DEFAULT_SESSION_TTL_DAYS = 7
DEFAULT_REGISTRATION_DEADLINE_DAYS = 30

JanitorSessionAction = Literal[
    "skip",  # not yet expired / nothing to do
    "expire",  # past expires_at, never stored to RustFS → mark expired
    "cancel",  # past expires_at with abortable multipart → abort + cancel
    "registration_expired",  # stored, unregistered, past registration deadline
]


@dataclass(frozen=True)
class JanitorMultipartFact:
    """One in-progress multipart upload recorded on a session (abort candidate)."""

    part_key: str
    object_key: str
    multipart_upload_id: str


@dataclass(frozen=True)
class JanitorSessionFact:
    """The subset of a session row the janitor decision needs.

    ``expires_at`` / ``registration_deadline_at`` may be ``None`` when T-203a did
    not stamp them; the decision then derives an effective deadline from
    ``created_at`` + the configured TTL so a missing column never disables the
    janitor.
    """

    upload_session_id: str
    state: str
    created_at: datetime
    expires_at: datetime | None
    registration_deadline_at: datetime | None
    registered_at: datetime | None
    #: True once the session's object(s) finished storing to RustFS — those are
    #: NEVER auto-deleted; only their session marker may transition.
    stored_to_rustfs: bool
    #: Unfinished multipart uploads still occupying storage (abort candidates).
    open_multiparts: tuple[JanitorMultipartFact, ...] = ()


@dataclass(frozen=True)
class JanitorSessionDecision:
    """What the janitor should do with one session."""

    upload_session_id: str
    action: JanitorSessionAction
    new_state: str | None = None
    error_message: str | None = None
    #: Multipart uploads to abort (only for the ``cancel`` action).
    aborts: tuple[JanitorMultipartFact, ...] = ()
    reason: str = ""


#: Terminal states the janitor never touches (mirrors the doc + DTO terminal set
#: plus the already-stored/registered terminal markers).
_JANITOR_TERMINAL_STATES: frozenset[str] = frozenset(
    {
        "available",
        "cancelled",
        "expired",
        "registered",
        "registration_expired",
        "failed_upload",
        "failed_extract",
        "failed_hash",
    }
)


def effective_session_expiry(
    fact: JanitorSessionFact, *, ttl_days: int = DEFAULT_SESSION_TTL_DAYS
) -> datetime:
    """``expires_at`` if set, else ``created_at + ttl_days`` (doc default)."""
    if fact.expires_at is not None:
        return fact.expires_at
    return fact.created_at + timedelta(days=max(0, ttl_days))


def effective_registration_deadline(
    fact: JanitorSessionFact,
    *,
    deadline_days: int = DEFAULT_REGISTRATION_DEADLINE_DAYS,
) -> datetime:
    """``registration_deadline_at`` if set, else ``created_at + deadline_days``."""
    if fact.registration_deadline_at is not None:
        return fact.registration_deadline_at
    return fact.created_at + timedelta(days=max(0, deadline_days))


def decide_session_fate(
    fact: JanitorSessionFact,
    *,
    now: datetime,
    ttl_days: int = DEFAULT_SESSION_TTL_DAYS,
    deadline_days: int = DEFAULT_REGISTRATION_DEADLINE_DAYS,
) -> JanitorSessionDecision:
    """Decide one session's fate (doc lines ~519-525).

    Precedence:

    1. Terminal / already-registered sessions → ``skip``.
    2. Stored-but-unregistered objects past the registration deadline →
       ``registration_expired`` (object is NOT deleted; user must re-register,
       extend, or discard).
    3. Sessions past ``expires_at`` that never finished storing → abort any
       open multipart uploads and ``cancel`` (if there were aborts) else
       ``expire``. RustFS objects that finished storing are never auto-deleted.
    4. Otherwise → ``skip``.
    """
    if fact.state in _JANITOR_TERMINAL_STATES or fact.registered_at is not None:
        return JanitorSessionDecision(
            upload_session_id=fact.upload_session_id, action="skip", reason="terminal"
        )

    # Stored to RustFS but never registered: governed by the registration deadline,
    # not the upload TTL. Past the deadline the object becomes a registration_expired
    # issue; the object itself stays (storage-first).
    if fact.stored_to_rustfs:
        deadline = effective_registration_deadline(fact, deadline_days=deadline_days)
        if now >= deadline:
            return JanitorSessionDecision(
                upload_session_id=fact.upload_session_id,
                action="registration_expired",
                new_state="registration_expired",
                error_message=(
                    "등록 기한 만료: registry 등록 재시도, 기한 연장, 또는 폐기를 선택하세요"
                ),
                reason="past_registration_deadline",
            )
        return JanitorSessionDecision(
            upload_session_id=fact.upload_session_id,
            action="skip",
            reason="stored_within_registration_deadline",
        )

    expiry = effective_session_expiry(fact, ttl_days=ttl_days)
    if now >= expiry:
        if fact.open_multiparts:
            return JanitorSessionDecision(
                upload_session_id=fact.upload_session_id,
                action="cancel",
                new_state="cancelled",
                error_message="만료된 세션의 미완 multipart upload를 abort했습니다",
                aborts=fact.open_multiparts,
                reason="expired_with_open_multipart",
            )
        return JanitorSessionDecision(
            upload_session_id=fact.upload_session_id,
            action="expire",
            new_state="expired",
            error_message="세션이 만료되었습니다",
            reason="expired_no_open_multipart",
        )

    return JanitorSessionDecision(
        upload_session_id=fact.upload_session_id, action="skip", reason="not_yet_expired"
    )


@dataclass(frozen=True)
class JanitorRunSummary:
    """Aggregate counters for one janitor pass (audit payload + metrics)."""

    processed_sessions: int = 0
    expired_sessions: int = 0
    cancelled_sessions: int = 0
    registration_expired: int = 0
    aborts_succeeded: int = 0
    aborts_failed: int = 0
    skipped_locked: bool = False

    def as_payload(self) -> dict[str, object]:
        return {
            "processed_sessions": self.processed_sessions,
            "expired_sessions": self.expired_sessions,
            "cancelled_sessions": self.cancelled_sessions,
            "registration_expired": self.registration_expired,
            "aborts_succeeded": self.aborts_succeeded,
            "aborts_failed": self.aborts_failed,
            "skipped_locked": self.skipped_locked,
        }


# --- soft-delete guard -----------------------------------------------------


@dataclass(frozen=True)
class SoftDeleteGuard:
    """Decision whether a group/file may be soft-deleted (doc line ~1441/1445)."""

    allowed: bool
    reason: str = ""
    blocking_match_set_ids: tuple[str, ...] = ()


def decide_soft_delete(
    *,
    current_state: str,
    active_match_set_ids: tuple[str, ...],
) -> SoftDeleteGuard:
    """A group referenced by an ACTIVE match set cannot be soft-deleted.

    The application guard mirrors the DB ``ON DELETE RESTRICT`` FK: an active
    release must be retired before its source group leaves selection. Already
    soft/hard-deleted rows are a no-op error (idempotency is the caller's job).
    """
    if current_state in {"hard_deleted"}:
        return SoftDeleteGuard(allowed=False, reason="이미 hard delete된 대상입니다")
    if active_match_set_ids:
        return SoftDeleteGuard(
            allowed=False,
            reason="active match set이 참조하는 group은 먼저 retire해야 삭제할 수 있습니다",
            blocking_match_set_ids=tuple(active_match_set_ids),
        )
    return SoftDeleteGuard(allowed=True)


# --- restore transition ----------------------------------------------------

RestoreOutcomeState = Literal["available", "validating", "missing", "quarantined"]


@dataclass(frozen=True)
class RestoreObjectCheck:
    """Result of the RustFS ``head_object`` (+ optional hash) verification."""

    object_present: bool
    #: Recomputed/observed object SHA-256 (None when not recomputed). When
    #: provided it is compared against ``expected_sha256``.
    observed_sha256: str | None = None
    observed_size: int | None = None


@dataclass(frozen=True)
class RestoreDecision:
    """Where a ``soft_deleted`` child file should land after object verification."""

    new_state: RestoreOutcomeState
    validation_state: str
    clear_deleted_at: bool = True
    reasons: tuple[str, ...] = field(default_factory=tuple)


def decide_restore_transition(
    *,
    expected_sha256: str,
    expected_size: int | None,
    check: RestoreObjectCheck,
) -> RestoreDecision:
    """Decide a restored file's landing state (doc line ~1442).

    * object absent → ``missing`` (cannot recover from storage);
    * object present, hash/size mismatch → ``quarantined``;
    * object present and consistent → ``validating`` (recompute/revalidate then
      promotes to ``available`` per the group decision). When no hash was
      recomputed we still return ``validating`` so the downstream validator runs.
    """
    if not check.object_present:
        return RestoreDecision(
            new_state="missing",
            validation_state="failed",
            clear_deleted_at=True,
            reasons=("RustFS object를 찾을 수 없습니다",),
        )
    if check.observed_sha256 is not None and check.observed_sha256 != expected_sha256:
        return RestoreDecision(
            new_state="quarantined",
            validation_state="failed",
            clear_deleted_at=True,
            reasons=("RustFS object SHA-256이 등록 기록과 다릅니다",),
        )
    if (
        check.observed_size is not None
        and expected_size is not None
        and check.observed_size != expected_size
    ):
        return RestoreDecision(
            new_state="quarantined",
            validation_state="failed",
            clear_deleted_at=True,
            reasons=("RustFS object size가 등록 기록과 다릅니다",),
        )
    return RestoreDecision(
        new_state="validating",
        validation_state="running",
        clear_deleted_at=True,
        reasons=(),
    )
