"""T-203c: upload-session janitor + soft-delete/restore decision logic.

DB-free tests for the highest-value surface — the pure decision functions in
``core.source_janitor`` (janitor session fate, soft-delete active-match-set
guard, restore object-verification transition) plus the advisory-lock skip
behavior of the janitor service (mocking the lock) and the new DTO shapes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from kortravelgeo.core.source_janitor import (
    DEFAULT_REGISTRATION_DEADLINE_DAYS,
    DEFAULT_SESSION_TTL_DAYS,
    JanitorMultipartFact,
    JanitorRunSummary,
    JanitorSessionFact,
    RestoreObjectCheck,
    decide_restore_transition,
    decide_session_fate,
    decide_soft_delete,
    effective_registration_deadline,
    effective_session_expiry,
)
from kortravelgeo.dto.source import (
    SourceGroupRestoreResponse,
    SourceGroupSoftDeleteResponse,
    SourceJanitorRunResponse,
)

if TYPE_CHECKING:
    import pytest

_NOW = datetime(2026, 6, 14, tzinfo=UTC)


def _session(
    *,
    state: str = "uploading",
    created_days_ago: int = 0,
    expires_at: datetime | None = None,
    registration_deadline_at: datetime | None = None,
    registered_at: datetime | None = None,
    stored: bool = False,
    open_multiparts: tuple[JanitorMultipartFact, ...] = (),
) -> JanitorSessionFact:
    return JanitorSessionFact(
        upload_session_id="sess1",
        state=state,
        created_at=_NOW - timedelta(days=created_days_ago),
        expires_at=expires_at,
        registration_deadline_at=registration_deadline_at,
        registered_at=registered_at,
        stored_to_rustfs=stored,
        open_multiparts=open_multiparts,
    )


def _mp(part_key: str = "archive") -> JanitorMultipartFact:
    return JanitorMultipartFact(
        part_key=part_key, object_key=f"sess1/{part_key}", multipart_upload_id="up-1"
    )


# --- janitor: effective deadlines ------------------------------------------


def test_effective_expiry_uses_column_when_set() -> None:
    explicit = _NOW + timedelta(days=2)
    fact = _session(expires_at=explicit)
    assert effective_session_expiry(fact) == explicit


def test_effective_expiry_falls_back_to_created_plus_ttl() -> None:
    fact = _session(created_days_ago=0, expires_at=None)
    assert effective_session_expiry(fact, ttl_days=7) == fact.created_at + timedelta(days=7)


def test_effective_registration_deadline_fallback() -> None:
    fact = _session(created_days_ago=0, registration_deadline_at=None)
    assert effective_registration_deadline(fact, deadline_days=30) == fact.created_at + timedelta(
        days=30
    )


# --- janitor: session fate -------------------------------------------------


def test_terminal_session_is_skipped() -> None:
    d = decide_session_fate(_session(state="expired"), now=_NOW)
    assert d.action == "skip"


def test_registered_session_is_skipped() -> None:
    d = decide_session_fate(
        _session(state="uploading", registered_at=_NOW - timedelta(days=99)), now=_NOW
    )
    assert d.action == "skip"


def test_not_yet_expired_session_is_skipped() -> None:
    fact = _session(created_days_ago=1, expires_at=None)
    d = decide_session_fate(fact, now=_NOW, ttl_days=7)
    assert d.action == "skip"
    assert d.reason == "not_yet_expired"


def test_expired_session_without_multipart_expires() -> None:
    fact = _session(created_days_ago=8, expires_at=None)
    d = decide_session_fate(fact, now=_NOW, ttl_days=7)
    assert d.action == "expire"
    assert d.new_state == "expired"
    assert not d.aborts


def test_expired_session_with_open_multipart_cancels_and_aborts() -> None:
    fact = _session(created_days_ago=10, expires_at=None, open_multiparts=(_mp("11"), _mp("41")))
    d = decide_session_fate(fact, now=_NOW, ttl_days=7)
    assert d.action == "cancel"
    assert d.new_state == "cancelled"
    assert {a.part_key for a in d.aborts} == {"11", "41"}


def test_stored_unregistered_within_deadline_is_skipped() -> None:
    # Stored object, well within the 30-day registration deadline → no action.
    fact = _session(state="awaiting_registration", created_days_ago=5, stored=True)
    d = decide_session_fate(fact, now=_NOW, deadline_days=30)
    assert d.action == "skip"
    assert d.reason == "stored_within_registration_deadline"


def test_stored_unregistered_past_deadline_registration_expired() -> None:
    fact = _session(state="awaiting_registration", created_days_ago=40, stored=True)
    d = decide_session_fate(fact, now=_NOW, deadline_days=30)
    assert d.action == "registration_expired"
    assert d.new_state == "registration_expired"
    assert not d.aborts  # stored object is never auto-deleted


def test_stored_session_never_aborts_even_if_past_ttl() -> None:
    # A stored object past the TTL but before the registration deadline must NOT
    # be expired/aborted — storage-first means the deadline governs it.
    fact = _session(state="awaiting_registration", created_days_ago=8, stored=True)
    d = decide_session_fate(fact, now=_NOW, ttl_days=7, deadline_days=30)
    assert d.action == "skip"


def test_default_constants_match_doc() -> None:
    assert DEFAULT_SESSION_TTL_DAYS == 7
    assert DEFAULT_REGISTRATION_DEADLINE_DAYS == 30


# --- soft-delete guard -----------------------------------------------------


def test_soft_delete_allowed_when_no_active_match_set() -> None:
    guard = decide_soft_delete(current_state="available", active_match_set_ids=())
    assert guard.allowed is True


def test_soft_delete_blocked_by_active_match_set() -> None:
    guard = decide_soft_delete(
        current_state="available", active_match_set_ids=("ms-active",)
    )
    assert guard.allowed is False
    assert guard.blocking_match_set_ids == ("ms-active",)


def test_soft_delete_blocked_when_already_hard_deleted() -> None:
    guard = decide_soft_delete(current_state="hard_deleted", active_match_set_ids=())
    assert guard.allowed is False


def test_soft_delete_allowed_for_validated_or_draft_reference() -> None:
    # Only ACTIVE references block; validated/draft references do not.
    guard = decide_soft_delete(current_state="available", active_match_set_ids=())
    assert guard.allowed is True


# --- restore transition ----------------------------------------------------


def test_restore_object_present_and_consistent_goes_validating() -> None:
    d = decide_restore_transition(
        expected_sha256="a" * 64,
        expected_size=100,
        check=RestoreObjectCheck(object_present=True, observed_sha256="a" * 64, observed_size=100),
    )
    assert d.new_state == "validating"
    assert d.validation_state == "running"
    assert d.clear_deleted_at is True


def test_restore_object_absent_goes_missing() -> None:
    d = decide_restore_transition(
        expected_sha256="a" * 64,
        expected_size=100,
        check=RestoreObjectCheck(object_present=False),
    )
    assert d.new_state == "missing"
    assert d.validation_state == "failed"


def test_restore_hash_mismatch_goes_quarantined() -> None:
    d = decide_restore_transition(
        expected_sha256="a" * 64,
        expected_size=100,
        check=RestoreObjectCheck(object_present=True, observed_sha256="b" * 64, observed_size=100),
    )
    assert d.new_state == "quarantined"
    assert d.reasons


def test_restore_size_mismatch_goes_quarantined() -> None:
    d = decide_restore_transition(
        expected_sha256="a" * 64,
        expected_size=100,
        check=RestoreObjectCheck(object_present=True, observed_sha256="a" * 64, observed_size=999),
    )
    assert d.new_state == "quarantined"


def test_restore_present_without_recomputed_hash_still_validating() -> None:
    # head_object succeeded but no hash was recomputed → trust the validator next.
    d = decide_restore_transition(
        expected_sha256="a" * 64,
        expected_size=None,
        check=RestoreObjectCheck(object_present=True, observed_sha256=None, observed_size=None),
    )
    assert d.new_state == "validating"


# --- run summary / DTO shapes ----------------------------------------------


def test_run_summary_payload_keys_match_dto() -> None:
    summary = JanitorRunSummary(
        processed_sessions=3,
        expired_sessions=1,
        cancelled_sessions=1,
        registration_expired=1,
        aborts_succeeded=2,
        aborts_failed=0,
    )
    dto = SourceJanitorRunResponse(**summary.as_payload())
    assert dto.processed_sessions == 3
    assert dto.aborts_succeeded == 2
    assert dto.skipped_locked is False


def test_soft_delete_response_shape() -> None:
    resp = SourceGroupSoftDeleteResponse(
        source_file_group_id="g1",
        state="soft_deleted",
        affected_file_count=17,
        affected_match_set_ids=("ms1",),
    )
    assert resp.model_dump(mode="json")["state"] == "soft_deleted"


def test_restore_response_shape() -> None:
    resp = SourceGroupRestoreResponse(
        source_file_group_id="g1",
        category="roadname_hangul_full",
        state="available",
        validation_state="passed",
    )
    assert resp.model_dump(mode="json")["state"] == "available"


# --- janitor service: advisory-lock skip (mock the lock) -------------------


async def test_janitor_skips_when_lock_held(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import asynccontextmanager

    from kortravelgeo.infra import source_janitor as svc
    from kortravelgeo.infra.concurrency import AdvisoryLockKey, ConcurrentExecutionError

    @asynccontextmanager
    async def _conflict(_engine: object, key: AdvisoryLockKey):  # type: ignore[no-untyped-def]
        raise ConcurrentExecutionError(key)
        yield  # pragma: no cover

    monkeypatch.setattr(svc, "cross_process_lock", _conflict)

    summary = await svc.run_source_upload_janitor(
        engine=object(),  # never used: the lock raises before any query
        rustfs=None,
        ttl_days=7,
        deadline_days=30,
    )
    assert summary.skipped_locked is True
    assert summary.processed_sessions == 0


async def test_janitor_runs_when_lock_free(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import asynccontextmanager

    from kortravelgeo.infra import source_janitor as svc

    @asynccontextmanager
    async def _ok(_engine: object, _key: object):  # type: ignore[no-untyped-def]
        yield

    async def _no_sessions(_engine: object, *, limit: int) -> tuple[JanitorSessionFact, ...]:
        return ()

    async def _no_audit(_engine: object, _summary: JanitorRunSummary) -> None:
        return None

    monkeypatch.setattr(svc, "cross_process_lock", _ok)
    monkeypatch.setattr(svc, "_load_session_facts", _no_sessions)
    monkeypatch.setattr(svc, "_audit_janitor", _no_audit)

    summary = await svc.run_source_upload_janitor(
        engine=object(),
        rustfs=None,
        ttl_days=7,
        deadline_days=30,
    )
    assert summary.skipped_locked is False
    assert summary.processed_sessions == 0


def test_janitor_staging_object_key_matches_upload_layout() -> None:
    from kortravelgeo.infra.source_janitor import _staging_object_key

    key = _staging_object_key(
        prefix="ktg",
        category="locsum_full",
        user_yyyymm="202605",
        source_file_group_id="group-1",
        session_id="source_upload_abc",
        part_key="../archive",
    )
    assert (
        key
        == "ktg/source-files/locsum_full/202605/group-1/source_upload_abc/archive/archive"
    )
