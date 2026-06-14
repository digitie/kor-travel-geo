"""Pure decision logic for RustFS ⟷ DB registry reconciliation (T-204).

These are **pure functions** (no DB, no RustFS, no clock except an explicit
``now`` argument) so the issue classification, the quick-vs-deep / rolling-deep
rehash decision, the bucket-wide-loss propagation, and the resolve guards can be
unit-tested with synthetic facts. The DB / storage glue lives in
``infra/source_reconcile.py``; this module only decides *what* an issue is and
*whether* a resolve is permitted.

Everything follows ``docs/t109-backup-source-upload-management.md``:

* the 12 ``issue_type`` names + meanings (doc lines ~689-704);
* quick/deep mode + conditional rehash (doc lines ~708-715);
* ``last_deep_verified_at`` 경과 시 강제 deep / rolling deep
  (doc lines ~1605 "same-size/etag 변조 안전망");
* bucket-wide / prefix mass loss propagation (doc line ~1606, ~2026, ~2100);
* the resolve action set + duplicate active-정본 삭제 guard (doc lines ~1458-1479).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

# --- issue type vocabulary (doc table lines ~691-704) ----------------------

#: The 12 canonical ``ops.source_storage_reconcile_items.issue_type`` values.
#: Order matches the doc's issue_type table top-to-bottom.
ReconcileIssueType = Literal[
    "db_missing_object",
    "object_missing_db",
    "pending_registration",
    "registration_expired",
    "source_file_unavailable",
    "source_file_group_incomplete",
    "size_mismatch",
    "hash_mismatch",
    "etag_mismatch",
    "duplicate_object",
    "orphaned_multipart",
    "delete_failed",
]

#: All 12 issue_type strings as a frozenset (validation + tests).
RECONCILE_ISSUE_TYPES: frozenset[str] = frozenset(
    {
        "db_missing_object",
        "object_missing_db",
        "pending_registration",
        "registration_expired",
        "source_file_unavailable",
        "source_file_group_incomplete",
        "size_mismatch",
        "hash_mismatch",
        "etag_mismatch",
        "duplicate_object",
        "orphaned_multipart",
        "delete_failed",
    }
)

ReconcileMode = Literal["quick", "deep"]
ReconcileSeverity = Literal["info", "warning", "error"]

#: Default mismatch severity per issue_type. ``hash_mismatch`` and the loss
#: issues are errors (suspected corruption / cannot rebuild); ``etag_mismatch``
#: and ``pending_registration`` are informational; the rest are warnings.
_ISSUE_SEVERITY: dict[str, ReconcileSeverity] = {
    "db_missing_object": "error",
    "object_missing_db": "warning",
    "pending_registration": "info",
    "registration_expired": "warning",
    "source_file_unavailable": "error",
    "source_file_group_incomplete": "error",
    "size_mismatch": "error",
    "hash_mismatch": "error",
    "etag_mismatch": "info",
    "duplicate_object": "warning",
    "orphaned_multipart": "warning",
    "delete_failed": "error",
}

#: Default rolling-deep window: a quick scan force-deeps any object whose
#: ``last_deep_verified_at`` is older than this (doc same-size/etag 변조 안전망).
DEFAULT_ROLLING_DEEP_DAYS = 30


def issue_severity(issue_type: str) -> ReconcileSeverity:
    """Default severity for an ``issue_type`` (``warning`` when unknown)."""
    return _ISSUE_SEVERITY.get(issue_type, "warning")


# --- facts the classifier consumes -----------------------------------------


@dataclass(frozen=True)
class DbFileFact:
    """The subset of an ``ops.source_files`` row reconciliation compares.

    ``state`` is the registry storage state; the classifier only treats live
    states (``available``/``validating``/``missing``/``quarantined``) as
    expecting an object — ``soft_deleted``/``hard_deleted`` rows are not flagged
    as ``db_missing_object``.
    """

    source_file_id: str
    source_file_group_id: str
    object_key: str | None
    state: str
    sha256: str
    size_bytes: int
    object_etag: str | None = None
    last_verified_etag: str | None = None
    last_verified_size_bytes: int | None = None
    last_verified_at: datetime | None = None
    last_deep_verified_at: datetime | None = None


@dataclass(frozen=True)
class ObjectHeadFact:
    """The subset of a RustFS ``head_object`` result reconciliation compares.

    ``present=False`` means the HEAD failed / object is absent. ``rehash_sha256``
    is only populated when the scan re-read the body (deep or change-triggered);
    a quick scan that skips rehash leaves it ``None``.
    """

    present: bool
    size: int | None = None
    etag: str | None = None
    rehash_sha256: str | None = None


@dataclass(frozen=True)
class RehashDecision:
    """Whether a quick scan must re-read this object's body, and why."""

    rehash: bool
    reason: str = ""


def decide_rehash(
    db: DbFileFact,
    head: ObjectHeadFact,
    *,
    mode: ReconcileMode,
    now: datetime,
    rolling_deep_days: int = DEFAULT_ROLLING_DEEP_DAYS,
) -> RehashDecision:
    """Decide whether to stream-rehash an object body (doc lines ~708-715).

    * ``deep`` mode always rehashes a present object.
    * ``quick`` mode skips rehash when ``size`` and ``etag`` both equal the
      ``last_verified_*`` record (unchanged), UNLESS the rolling-deep window has
      elapsed since ``last_deep_verified_at`` (the same-size/etag 변조 안전망,
      doc line ~1605) — then it force-deeps that single object.
    * a changed ``size``/``etag``, or a missing prior verification record, forces
      a rehash of just that object.
    * an absent object is never rehashed (it becomes ``db_missing_object``).
    """
    if not head.present:
        return RehashDecision(rehash=False, reason="object_absent")
    if mode == "deep":
        return RehashDecision(rehash=True, reason="deep_mode")

    # quick mode below.
    no_prior = db.last_verified_etag is None and db.last_verified_size_bytes is None
    if no_prior:
        return RehashDecision(rehash=True, reason="no_prior_verification")

    size_changed = (
        db.last_verified_size_bytes is not None
        and head.size is not None
        and head.size != db.last_verified_size_bytes
    )
    etag_changed = (
        db.last_verified_etag is not None
        and head.etag is not None
        and head.etag != db.last_verified_etag
    )
    if size_changed or etag_changed:
        return RehashDecision(rehash=True, reason="size_or_etag_changed")

    # Unchanged since last verify: roll a forced deep if the deep window elapsed.
    if db.last_deep_verified_at is None:
        return RehashDecision(rehash=True, reason="never_deep_verified")
    if now - db.last_deep_verified_at >= timedelta(days=max(0, rolling_deep_days)):
        return RehashDecision(rehash=True, reason="rolling_deep_window_elapsed")
    return RehashDecision(rehash=False, reason="unchanged_within_deep_window")


@dataclass(frozen=True)
class IssueDecision:
    """A classified discrepancy for one DB file vs its RustFS object.

    ``issue_type`` of ``None`` means "no discrepancy" (the object matches the
    registry; ``rehash_performed`` records whether the body was re-read).
    """

    issue_type: ReconcileIssueType | None
    severity: ReconcileSeverity
    rehash_performed: bool = False
    reason: str = ""


_LIVE_DB_STATES: frozenset[str] = frozenset(
    {"available", "validating", "missing", "quarantined", "delete_failed"}
)


def classify_db_file(
    db: DbFileFact,
    head: ObjectHeadFact,
    *,
    mode: ReconcileMode,
    now: datetime,
    rolling_deep_days: int = DEFAULT_ROLLING_DEEP_DAYS,
) -> IssueDecision:
    """Classify one registry file against its RustFS object (doc lines ~691-715).

    Precedence (most-severe / most-certain first):

    1. live DB row, object absent → ``db_missing_object``.
    2. ``delete_failed`` registry state with object still present → ``delete_failed``.
    3. size mismatch → ``size_mismatch``.
    4. body rehashed (deep / change-triggered) and digest differs → ``hash_mismatch``.
    5. etag-only difference (size + (hash if rehashed) equal) → ``etag_mismatch``.
    6. otherwise no issue.

    The function never *assumes* the etag is the hash: ``hash_mismatch`` is only
    emitted when a real rehash digest is available and differs (doc line ~706).
    """
    # soft/hard-deleted rows do not expect an object; skip.
    if db.state not in _LIVE_DB_STATES:
        return IssueDecision(issue_type=None, severity="info", reason="not_live")

    if db.state == "delete_failed" and head.present:
        return IssueDecision(
            issue_type="delete_failed",
            severity=issue_severity("delete_failed"),
            reason="hard_delete_did_not_remove_object",
        )

    if not head.present:
        return IssueDecision(
            issue_type="db_missing_object",
            severity=issue_severity("db_missing_object"),
            reason="db_row_live_object_absent",
        )

    rehash = decide_rehash(
        db, head, mode=mode, now=now, rolling_deep_days=rolling_deep_days
    )
    rehashed = rehash.rehash and head.rehash_sha256 is not None

    if head.size is not None and head.size != db.size_bytes:
        return IssueDecision(
            issue_type="size_mismatch",
            severity=issue_severity("size_mismatch"),
            rehash_performed=rehashed,
            reason="object_size_differs",
        )

    if rehashed and head.rehash_sha256 != db.sha256:
        return IssueDecision(
            issue_type="hash_mismatch",
            severity=issue_severity("hash_mismatch"),
            rehash_performed=True,
            reason="rehash_digest_differs",
        )

    if (
        db.object_etag is not None
        and head.etag is not None
        and head.etag != db.object_etag
    ):
        return IssueDecision(
            issue_type="etag_mismatch",
            severity=issue_severity("etag_mismatch"),
            rehash_performed=rehashed,
            reason="etag_only_differs",
        )

    return IssueDecision(
        issue_type=None,
        severity="info",
        rehash_performed=rehashed,
        reason="consistent",
    )


# --- unregistered object classification (object_missing_db family) ----------


@dataclass(frozen=True)
class UnregisteredObjectFact:
    """A RustFS object whose key has no live ``ops.source_files`` row.

    ``has_live_session`` / ``past_registration_deadline`` come from the upload
    session whose prefix the object key falls under (doc lines ~1471-1478): a
    stored-but-unregistered object is NOT a deletion candidate until the
    registration deadline passes.
    """

    object_key: str
    has_live_session: bool = False
    past_registration_deadline: bool = False


def classify_unregistered_object(fact: UnregisteredObjectFact) -> IssueDecision:
    """Classify a RustFS object with no live DB row (doc lines ~694-696, ~1471-1478).

    * live upload session, before the registration deadline → ``pending_registration``
      (info; never a delete candidate).
    * stored object whose session passed the registration deadline →
      ``registration_expired`` (warning; user must re-register/extend/discard).
    * otherwise (no session / unknown origin) → ``object_missing_db`` (import or delete).
    """
    if fact.has_live_session and not fact.past_registration_deadline:
        return IssueDecision(
            issue_type="pending_registration",
            severity=issue_severity("pending_registration"),
            reason="stored_awaiting_registration",
        )
    if fact.past_registration_deadline:
        return IssueDecision(
            issue_type="registration_expired",
            severity=issue_severity("registration_expired"),
            reason="past_registration_deadline",
        )
    return IssueDecision(
        issue_type="object_missing_db",
        severity=issue_severity("object_missing_db"),
        reason="object_without_db_row",
    )


# --- bucket-wide / prefix mass loss ----------------------------------------

#: When at least this fraction of live registry objects are absent in one scan,
#: treat it as a bucket-wide / prefix mass loss rather than per-file corruption.
DEFAULT_BUCKET_LOSS_RATIO = 0.9
#: ...but only above this floor of scanned live files (avoid false alarm on a
#: handful of files where 1 missing is already 100%).
DEFAULT_BUCKET_LOSS_MIN_FILES = 3


@dataclass(frozen=True)
class BucketLossAssessment:
    """Whether a scan looks like a bucket-wide / prefix mass loss."""

    is_mass_loss: bool
    scanned_live_files: int
    missing_files: int
    reason: str = ""


def assess_bucket_loss(
    *,
    scanned_live_files: int,
    missing_files: int,
    loss_ratio: float = DEFAULT_BUCKET_LOSS_RATIO,
    min_files: int = DEFAULT_BUCKET_LOSS_MIN_FILES,
) -> BucketLossAssessment:
    """Decide whether en-masse absence is a mass-loss event (doc line ~1606).

    A mass loss is declared when the scan covered at least ``min_files`` live
    registry files and at least ``loss_ratio`` of them were absent. The caller
    then marks every absent file ``source_file_unavailable``/``db_missing_object``
    and propagates referenced groups to ``missing`` so active match sets raise
    ``integrity_alert`` and non-active ``validated`` sets go ``invalid``.
    """
    if scanned_live_files < max(1, min_files):
        return BucketLossAssessment(
            is_mass_loss=False,
            scanned_live_files=scanned_live_files,
            missing_files=missing_files,
            reason="below_min_files",
        )
    ratio = missing_files / scanned_live_files if scanned_live_files else 0.0
    if ratio >= loss_ratio:
        return BucketLossAssessment(
            is_mass_loss=True,
            scanned_live_files=scanned_live_files,
            missing_files=missing_files,
            reason="mass_loss_ratio_exceeded",
        )
    return BucketLossAssessment(
        is_mass_loss=False,
        scanned_live_files=scanned_live_files,
        missing_files=missing_files,
        reason="below_loss_ratio",
    )


def mass_loss_issue_type(*, present_in_registry_only: bool) -> ReconcileIssueType:
    """issue_type for an absent file during a mass loss (doc line ~1606).

    Backup-manifest stubs (registry metadata only, never had a live object in
    this bucket) are ``source_file_unavailable``; otherwise a previously-stored
    object that vanished is ``db_missing_object``.
    """
    return "source_file_unavailable" if present_in_registry_only else "db_missing_object"


# --- duplicate-object grouping ---------------------------------------------


@dataclass(frozen=True)
class DuplicateObjectFact:
    """One registry object considered for ``duplicate_object`` detection."""

    source_file_id: str
    object_key: str
    sha256: str
    size_bytes: int


def find_duplicate_object_groups(
    facts: tuple[DuplicateObjectFact, ...],
) -> tuple[tuple[DuplicateObjectFact, ...], ...]:
    """Group objects sharing ``(sha256, size_bytes)`` across >1 distinct key.

    Returns one tuple per duplicate set (each with 2+ distinct object keys). A
    set with a single key, or repeated rows for the same key, is not a
    duplicate. Order within a set is by ``object_key`` for determinism.
    """
    by_digest: dict[tuple[str, int], dict[str, DuplicateObjectFact]] = {}
    for fact in facts:
        by_digest.setdefault((fact.sha256, fact.size_bytes), {})[fact.object_key] = fact
    groups: list[tuple[DuplicateObjectFact, ...]] = []
    for members in by_digest.values():
        if len(members) > 1:
            groups.append(tuple(members[k] for k in sorted(members)))
    return tuple(groups)


# --- resolve actions + guards ----------------------------------------------

ResolveAction = Literal[
    "mark_db_missing",
    "soft_delete_db_row",
    "restore_soft_deleted",
    "import_object",
    "delete_object",
    "extend_registration_deadline",
    "retry_delete_object",
    "update_hash_after_verify",
]

RESOLVE_ACTIONS: frozenset[str] = frozenset(
    {
        "mark_db_missing",
        "soft_delete_db_row",
        "restore_soft_deleted",
        "import_object",
        "delete_object",
        "extend_registration_deadline",
        "retry_delete_object",
        "update_hash_after_verify",
    }
)

#: Resolve actions that destroy a stored object (hard-delete family). The doc
#: requires the ``destructive_admin`` role for these; the rest are
#: ``source_file_manager`` (doc lines ~1446-1447, ~1154).
DESTRUCTIVE_RESOLVE_ACTIONS: frozenset[str] = frozenset(
    {"delete_object", "retry_delete_object"}
)


def resolve_action_is_destructive(action: str) -> bool:
    return action in DESTRUCTIVE_RESOLVE_ACTIONS


@dataclass(frozen=True)
class ResolveGuard:
    """Whether a resolve action may proceed against an object/issue."""

    allowed: bool
    reason: str = ""
    blocking_match_set_ids: tuple[str, ...] = field(default_factory=tuple)


def guard_object_deletion(
    *,
    object_key: str,
    active_match_set_group_object_keys: frozenset[str],
    referenced_match_set_ids: tuple[str, ...] = (),
) -> ResolveGuard:
    """Refuse deleting an object an active match set's group references (doc 1479).

    The ``duplicate_object`` / ``delete_object`` resolve must never pick the
    canonical object that an active match set's group points at (regardless of
    that set's ``integrity_alert`` value). ``active_match_set_group_object_keys``
    is the set of object keys reachable from any active match set's referenced
    groups; deletion is blocked when ``object_key`` is in it.
    """
    if object_key in active_match_set_group_object_keys:
        return ResolveGuard(
            allowed=False,
            reason=(
                "active match set이 참조하는 정본 object는 삭제할 수 없습니다 "
                "(먼저 match set을 retire하세요)"
            ),
            blocking_match_set_ids=tuple(referenced_match_set_ids),
        )
    return ResolveGuard(allowed=True)


@dataclass(frozen=True)
class ReResolveCheck:
    """Read-after-write recheck before applying a resolve (doc line ~1479).

    Captures the live DB row presence + RustFS head so a resolve decided against
    a stale item is rejected (concurrent register/delete made it a false alarm).
    """

    db_row_present: bool
    object_present: bool


def resolve_still_applies(
    *,
    action: ResolveAction,
    recheck: ReResolveCheck,
) -> ResolveGuard:
    """Decide whether a resolve still applies after the read-after-write recheck.

    Rejects the obvious stale cases (doc line ~1479):

    * ``import_object`` / ``delete_object`` when the object vanished;
    * ``import_object`` when a DB row now exists (someone registered it);
    * ``mark_db_missing`` when the object reappeared;
    * ``restore_soft_deleted`` when the DB row is gone.

    Other actions are allowed through to their own handlers.
    """
    if action in {"import_object", "delete_object"} and not recheck.object_present:
        return ResolveGuard(
            allowed=False, reason="object가 더 이상 존재하지 않습니다 (재스캔 필요)"
        )
    if action == "import_object" and recheck.db_row_present:
        return ResolveGuard(
            allowed=False, reason="이미 DB registry에 등록된 object입니다"
        )
    if action == "mark_db_missing" and recheck.object_present:
        return ResolveGuard(
            allowed=False, reason="object가 다시 존재합니다 (missing 표시 불필요)"
        )
    if action == "restore_soft_deleted" and not recheck.db_row_present:
        return ResolveGuard(allowed=False, reason="대상 DB row가 없습니다")
    return ResolveGuard(allowed=True)


# --- capacity preflight -----------------------------------------------------


@dataclass(frozen=True)
class CategoryCapacity:
    """Per-category object-count / byte usage (doc line ~2107)."""

    category: str
    object_count: int
    total_bytes: int
    quarantined_bytes: int = 0
    soft_deleted_bytes: int = 0


@dataclass(frozen=True)
class CapacityUsage:
    """Aggregate storage capacity usage + optional threshold verdict.

    The retention POLICY is T-212; this is the computation + surfacing only
    (doc lines ~2107-2108, ~2132).
    """

    categories: tuple[CategoryCapacity, ...]
    total_object_count: int
    total_bytes: int
    quarantined_bytes: int
    soft_deleted_bytes: int
    unregistered_bytes: int = 0
    growth_30d_bytes: int = 0
    capacity_limit_bytes: int | None = None
    over_threshold: bool = False


def compute_capacity_usage(
    categories: tuple[CategoryCapacity, ...],
    *,
    unregistered_bytes: int = 0,
    growth_30d_bytes: int = 0,
    capacity_limit_bytes: int | None = None,
    threshold_ratio: float = 1.0,
) -> CapacityUsage:
    """Aggregate per-category usage into a capacity report (doc line ~2107).

    Sums object counts and bytes across categories and adds any unregistered
    (stored-but-not-in-registry) bytes plus the rolling 30-day byte growth.
    When ``capacity_limit_bytes`` is given, ``over_threshold`` is set once total
    (registry + unregistered) bytes exceed ``threshold_ratio`` of the limit, so
    callers can surface a preflight warning before an upload/register.
    """
    total_objects = sum(c.object_count for c in categories)
    total_bytes = sum(c.total_bytes for c in categories)
    quarantined = sum(c.quarantined_bytes for c in categories)
    soft_deleted = sum(c.soft_deleted_bytes for c in categories)
    effective_total = total_bytes + max(0, unregistered_bytes)
    over = (
        capacity_limit_bytes is not None
        and capacity_limit_bytes > 0
        and effective_total >= capacity_limit_bytes * threshold_ratio
    )
    return CapacityUsage(
        categories=tuple(sorted(categories, key=lambda c: c.category)),
        total_object_count=total_objects,
        total_bytes=total_bytes,
        quarantined_bytes=quarantined,
        soft_deleted_bytes=soft_deleted,
        unregistered_bytes=max(0, unregistered_bytes),
        growth_30d_bytes=max(0, growth_30d_bytes),
        capacity_limit_bytes=capacity_limit_bytes,
        over_threshold=bool(over),
    )


# --- observability: source-registry metric facts (T-211) --------------------


@dataclass(frozen=True)
class SourceRegistryMetricFacts:
    """Flat, prometheus-ready snapshot of the source registry (doc line ~2107).

    Pure projection of :class:`CapacityUsage` + upload-session state counts into
    the label/value pairs the ``/metrics`` feed sets. Kept DB-free so the
    metric-feed contract is unit-tested without a DB:

    * ``category_objects`` / ``category_bytes`` — per-category gauges;
    * ``total_*`` — bucket-wide byte breakdown (registry, quarantined,
      soft_deleted, unregistered, 30-day growth);
    * ``session_states`` — open upload sessions by lifecycle state.
    """

    category_objects: tuple[tuple[str, int], ...]
    category_bytes: tuple[tuple[str, int], ...]
    total_objects: int
    total_bytes: int
    quarantined_bytes: int
    soft_deleted_bytes: int
    unregistered_bytes: int
    growth_30d_bytes: int
    session_states: tuple[tuple[str, int], ...]


def build_source_registry_metric_facts(
    capacity: CapacityUsage,
    *,
    session_state_counts: Mapping[str, int] | None = None,
) -> SourceRegistryMetricFacts:
    """Project capacity usage + session-state counts into metric facts (T-211).

    ``session_state_counts`` maps an upload-session ``state`` to the number of
    sessions currently in it (DB ``GROUP BY state`` aggregate). Negative counts
    are clamped to 0 and ordering is made deterministic for stable scrapes.
    """
    counts = session_state_counts or {}
    return SourceRegistryMetricFacts(
        category_objects=tuple(
            (c.category, max(0, c.object_count)) for c in capacity.categories
        ),
        category_bytes=tuple(
            (c.category, max(0, c.total_bytes)) for c in capacity.categories
        ),
        total_objects=max(0, capacity.total_object_count),
        total_bytes=max(0, capacity.total_bytes),
        quarantined_bytes=max(0, capacity.quarantined_bytes),
        soft_deleted_bytes=max(0, capacity.soft_deleted_bytes),
        unregistered_bytes=max(0, capacity.unregistered_bytes),
        growth_30d_bytes=max(0, capacity.growth_30d_bytes),
        session_states=tuple(
            (state, max(0, int(count))) for state, count in sorted(counts.items())
        ),
    )
