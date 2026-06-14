"""Pure decision logic for ``rebuild-db`` + rollback (T-205b).

These are **pure functions** (no DB, no clock except an explicit ``now``) so the
forced-promotion gate, the pre-load source-archive integrity gate, the rollback
target resolution, and the stale-running-job detection can be unit-tested with
synthetic facts. The DB/loader/RustFS glue lives in
``infra/source_rebuild_service.py``; this module only decides *what* should
happen.

Decisions follow ``docs/t109-backup-source-upload-management.md`` "DB 재구성"
(lines ~1532-1562), the "운영 시나리오 커버리지 점검" rows (lines ~1613-1631), and
ADR-049 decision 13 (forced_promotion scope) + decision 18 (rollback one-active).

The cardinal forced-promotion rule (doc line ~1559, ~1630; ADR-049 #13):
``forced_promotion=true`` bypasses **only** the consistency ERROR promotion
block. It must NOT bypass the source-archive integrity gate
(hash/size/object presence), a ``source_file_group.state != 'available'``, or a
selected match set whose ``integrity_alert=true`` — those still hard-fail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# --- pre-load source-archive integrity gate --------------------------------


@dataclass(frozen=True)
class GroupArchiveCheck:
    """One referenced group's re-verified RustFS archive (doc line ~1544).

    The service materializes each group's archive(s) and re-computes
    ``sha256``/``size`` against the registry just before loader enqueue. These
    are the observations the gate decides on.
    """

    source_file_group_id: str
    category: str
    #: Registry ``ops.source_file_groups.state`` (must be ``available``).
    group_state: str
    #: Every child object is present in RustFS (``head_object`` succeeded).
    all_objects_present: bool
    #: Every child ``sha256`` matched the registry ``ops.source_files.sha256``.
    sha256_ok: bool
    #: Every child ``size_bytes`` matched the registry.
    size_ok: bool
    #: The recomputed group hash equalled the registry ``group_sha256``.
    group_sha256_ok: bool


@dataclass(frozen=True)
class IntegrityGateDecision:
    """Whether the pre-load integrity gate passed, and which groups failed."""

    ok: bool
    #: Group ids that failed the gate (mismatch/missing) → quarantine + propagate.
    failed_group_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


def _group_check_failures(check: GroupArchiveCheck) -> tuple[str, ...]:
    reasons: list[str] = []
    if check.group_state != "available":
        reasons.append(
            f"{check.category}: group state {check.group_state!r} != 'available'"
        )
    if not check.all_objects_present:
        reasons.append(f"{check.category}: one or more RustFS objects missing")
    if not check.sha256_ok:
        reasons.append(f"{check.category}: archive sha256 mismatch vs registry")
    if not check.size_ok:
        reasons.append(f"{check.category}: archive size mismatch vs registry")
    if not check.group_sha256_ok:
        reasons.append(f"{check.category}: group_sha256 mismatch vs registry")
    return tuple(reasons)


def decide_integrity_gate(
    checks: tuple[GroupArchiveCheck, ...],
) -> IntegrityGateDecision:
    """The pre-load source-archive integrity gate (doc line ~1544, ~1613).

    Every referenced (non-omitted) group must be ``available`` with all objects
    present and matching ``sha256``/``size``/``group_sha256``. On ANY mismatch or
    missing object the gate fails and names the failing groups so the service can
    transition them to ``quarantined`` and propagate via
    ``recompute_group_aggregates`` (active match set → ``integrity_alert``,
    non-active ``validated`` → ``invalid``). No child load jobs are created.
    """
    failed: list[str] = []
    reasons: list[str] = []
    for check in checks:
        failures = _group_check_failures(check)
        if failures:
            failed.append(check.source_file_group_id)
            reasons.extend(failures)
    return IntegrityGateDecision(
        ok=not failed,
        failed_group_ids=tuple(failed),
        reasons=tuple(reasons),
    )


# --- forced-promotion / consistency ERROR gate -----------------------------

ConsistencySeverity = Literal["OK", "INFO", "WARN", "ERROR"]

#: Which gate blocked promotion (or ``None`` when promotion is allowed).
PromotionBlocker = Literal[
    "source_integrity",  # source archive integrity gate (never bypassable)
    "match_set_integrity_alert",  # selected match set integrity_alert (never bypassable)
    "group_unavailable",  # a referenced group is not 'available' (never bypassable)
    "consistency_error",  # consistency severity_max=ERROR (bypassable by forced_promotion)
    "forced_promotion_unauthorized",  # forced requested without role/typed confirmation
]


@dataclass(frozen=True)
class PromotionFacts:
    """The facts the promotion gate sees after load + consistency (doc ~1558-1559).

    ``forced`` is the operator's explicit forced-promotion request;
    ``has_destructive_admin`` and ``typed_confirmation_ok`` are the two
    safety conditions a forced promotion additionally requires.
    """

    consistency_severity: ConsistencySeverity
    #: The pre-load source-archive integrity gate passed.
    source_integrity_ok: bool
    #: Every referenced group is ``available`` (state-level guard).
    all_groups_available: bool
    #: The selected match set carries ``integrity_alert=true``.
    match_set_integrity_alert: bool
    forced: bool = False
    has_destructive_admin: bool = False
    typed_confirmation_ok: bool = False


@dataclass(frozen=True)
class PromotionDecision:
    """Whether MV swap / active promotion / snapshot-FK write may proceed.

    ``allow`` gates ALL three of: MV swap, serving-release activation, and the
    ``ops.dataset_snapshots.source_match_set_id`` FK write (doc line ~1558).
    ``forced_promotion`` records that the ERROR block was bypassed (for the
    report + snapshot metadata, doc line ~1559). ``blocker`` names the gate that
    refused when ``allow`` is False.
    """

    allow: bool
    blocker: PromotionBlocker | None = None
    forced_promotion: bool = False
    reasons: tuple[str, ...] = ()


def decide_promotion(facts: PromotionFacts) -> PromotionDecision:
    """The consistency ERROR / forced-promotion gate (doc lines ~1558-1559, #13).

    Ordering is deliberate — the non-bypassable hard gates run FIRST, so a
    ``forced=true`` request can never slip past them:

    1. source-archive integrity gate failed → block ``source_integrity``
       (never bypassable, even with forced);
    2. a referenced group is not ``available`` → block ``group_unavailable``
       (never bypassable);
    3. the selected match set has ``integrity_alert=true`` → block
       ``match_set_integrity_alert`` (never bypassable);
    4. consistency ``severity_max=ERROR``:
       * not forced → block ``consistency_error``;
       * forced but missing ``destructive_admin`` or typed confirmation → block
         ``forced_promotion_unauthorized``;
       * forced + authorized → ALLOW with ``forced_promotion=true``;
    5. WARN/INFO/OK → auto-promote (allow).
    """
    # 1-3: the hard gates forced_promotion may never bypass (doc ~1559/#13).
    if not facts.source_integrity_ok:
        return PromotionDecision(
            allow=False,
            blocker="source_integrity",
            reasons=(
                "source archive integrity gate failed; not bypassable by "
                "forced_promotion",
            ),
        )
    if not facts.all_groups_available:
        return PromotionDecision(
            allow=False,
            blocker="group_unavailable",
            reasons=(
                "a referenced source_file_group is not 'available'; not "
                "bypassable by forced_promotion",
            ),
        )
    if facts.match_set_integrity_alert:
        return PromotionDecision(
            allow=False,
            blocker="match_set_integrity_alert",
            reasons=(
                "selected match set has integrity_alert=true; not bypassable by "
                "forced_promotion",
            ),
        )

    # 4: the ONLY gate forced_promotion may bypass.
    if facts.consistency_severity == "ERROR":
        if not facts.forced:
            return PromotionDecision(
                allow=False,
                blocker="consistency_error",
                reasons=(
                    "consistency severity_max=ERROR blocks promotion; a "
                    "destructive_admin may force with typed confirmation",
                ),
            )
        if not (facts.has_destructive_admin and facts.typed_confirmation_ok):
            return PromotionDecision(
                allow=False,
                blocker="forced_promotion_unauthorized",
                reasons=(
                    "forced_promotion requires the destructive_admin role and a "
                    "matching typed confirmation",
                ),
            )
        return PromotionDecision(
            allow=True,
            forced_promotion=True,
            reasons=("forced_promotion: consistency ERROR accepted by operator",),
        )

    # 5: WARN/INFO/OK auto-promote.
    return PromotionDecision(allow=True)


# --- rebuild precondition (selecting a match set) --------------------------


@dataclass(frozen=True)
class RebuildStartFacts:
    """Facts checked before a rebuild job is even enqueued (doc step 1, ~1542)."""

    state: str
    integrity_alert: bool
    source_set_hash: str | None
    all_groups_available: bool


@dataclass(frozen=True)
class RebuildStartDecision:
    ok: bool
    reasons: tuple[str, ...] = ()


def decide_rebuild_start(facts: RebuildStartFacts) -> RebuildStartDecision:
    """Whether a match set may be the input to ``rebuild-db`` (doc ~1538/1542).

    A rebuild consumes a ``validated`` or ``active`` match set whose referenced
    groups are all ``available`` with a computed ``source_set_hash``. The
    ``integrity_alert=true`` guard is repeated here (it is also a non-bypassable
    promotion gate) so the job never even starts a doomed load.
    """
    reasons: list[str] = []
    if facts.state not in {"validated", "active"}:
        reasons.append(
            f"rebuild requires a 'validated' or 'active' match set (state={facts.state!r})"
        )
    if facts.integrity_alert:
        reasons.append("match set has integrity_alert=true; resolve sources first")
    if not facts.all_groups_available:
        reasons.append("not all referenced groups are 'available'")
    if facts.source_set_hash is None:
        reasons.append("source_set_hash is NULL; re-run validate first")
    return RebuildStartDecision(ok=not reasons, reasons=tuple(reasons))


# --- stale running-job detection -------------------------------------------


@dataclass(frozen=True)
class RunningJobFacts:
    """One prior rebuild job that may need stale-closing (doc line ~1556)."""

    job_id: str
    state: str
    #: Seconds since the job's last heartbeat (``now - heartbeat_at``). ``None``
    #: when the job never heartbeated.
    seconds_since_heartbeat: float | None


@dataclass(frozen=True)
class StaleJobDecision:
    """Which prior jobs to force-``failed`` before re-initialising staging."""

    stale_job_ids: tuple[str, ...] = ()
    #: A still-live (within heartbeat timeout) running job blocks a new rebuild.
    live_blocking_job_id: str | None = None


def decide_stale_jobs(
    jobs: tuple[RunningJobFacts, ...],
    *,
    heartbeat_timeout_s: float,
) -> StaleJobDecision:
    """Classify prior rebuild jobs for the same match set / staging key.

    A ``running`` job whose last heartbeat exceeded ``heartbeat_timeout_s`` (or
    that never heartbeated) is STALE → force ``failed`` and re-init staging
    idempotently (doc line ~1556). A ``running`` job still within the timeout is
    LIVE → it blocks a new rebuild (the caller returns 409 / "already running").
    """
    stale: list[str] = []
    live: str | None = None
    for job in jobs:
        if job.state != "running":
            continue
        if job.seconds_since_heartbeat is None or (
            job.seconds_since_heartbeat > heartbeat_timeout_s
        ):
            stale.append(job.job_id)
        elif live is None:
            live = job.job_id
    return StaleJobDecision(stale_job_ids=tuple(stale), live_blocking_job_id=live)


# --- rollback target resolution --------------------------------------------

RollbackMode = Literal["match_set_swap", "legacy_estimate"]


@dataclass(frozen=True)
class RollbackTargetFacts:
    """The rollback target release + its snapshot (doc lines ~818, ~1530, #18)."""

    release_id: str
    snapshot_id: str
    release_state: str
    #: The target snapshot's ``source_match_set_id`` (정본) or ``None`` (legacy).
    target_source_match_set_id: str | None
    #: The currently-active match set id (to retire in the swap), or ``None``.
    current_active_match_set_id: str | None


@dataclass(frozen=True)
class RollbackTargetDecision:
    """Whether to swap match sets atomically, or only show legacy estimates.

    ``mode='match_set_swap'`` → in one transaction (under the match-activate
    lock) retire ``retire_match_set_id`` (if any) and restore
    ``activate_match_set_id`` to ``active``, recomputing its ``integrity_alert``
    from a pre-rollback source quick reconcile. ``mode='legacy_estimate'`` → the
    target snapshot has no FK, so NO match-set state is created; the UI shows
    ``알수없음/추정`` and the estimate is never promoted to a 정본 match set
    (doc ~818/1530, ADR-049 #18).
    """

    ok: bool
    mode: RollbackMode = "legacy_estimate"
    activate_match_set_id: str | None = None
    retire_match_set_id: str | None = None
    reasons: tuple[str, ...] = ()


def decide_rollback_target(facts: RollbackTargetFacts) -> RollbackTargetDecision:
    """Resolve a serving-release rollback's match-set side (doc ~818/1530, #18).

    * a ``failed`` target release cannot be a rollback basis;
    * target snapshot HAS ``source_match_set_id`` → ``match_set_swap``: retire the
      current active match set (if different) and restore the target one;
    * target snapshot has NO FK (legacy) → ``legacy_estimate``: no swap, no
      auto-promotion to a 정본 match set.
    """
    if facts.release_state == "failed":
        return RollbackTargetDecision(
            ok=False,
            reasons=("failed release cannot be a rollback basis",),
        )
    if facts.target_source_match_set_id is None:
        return RollbackTargetDecision(
            ok=True,
            mode="legacy_estimate",
            reasons=(
                "target snapshot has no source_match_set_id; legacy estimate only "
                "(no match set promotion)",
            ),
        )
    retire = (
        facts.current_active_match_set_id
        if facts.current_active_match_set_id is not None
        and facts.current_active_match_set_id != facts.target_source_match_set_id
        else None
    )
    return RollbackTargetDecision(
        ok=True,
        mode="match_set_swap",
        activate_match_set_id=facts.target_source_match_set_id,
        retire_match_set_id=retire,
    )


# --- rollback integrity_alert recompute (pre-rollback quick reconcile) ------


@dataclass(frozen=True)
class RollbackIntegrityFacts:
    """Target match set's referenced groups, observed by a quick reconcile."""

    #: True when every referenced (non-omitted) group is ``available``.
    all_groups_available: bool
    #: Group ids found not ``available`` (missing/quarantined) — the alert detail.
    unavailable_group_ids: tuple[str, ...] = field(default=())


def recompute_rollback_integrity_alert(facts: RollbackIntegrityFacts) -> bool:
    """Recompute the restored match set's ``integrity_alert`` (doc ~818, #18).

    The match set is restored to ``active``; if a pre-rollback source quick
    reconcile finds any referenced group is no longer ``available`` the active
    set is restored with ``integrity_alert=true`` (serving is kept, but the same
    DB can no longer be rebuilt). Otherwise the alert is cleared.
    """
    return not facts.all_groups_available
