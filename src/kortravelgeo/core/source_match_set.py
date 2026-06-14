"""Pure decision logic for source match set validate / activate / retire (T-205a).

These are **pure functions** (no DB, no clock except an explicit ``now``) so the
``POST /validate`` state-split, the ``activate`` precondition + atomic-swap
sequence, and the create-time item invariants can be unit-tested with synthetic
facts. The DB glue lives in ``infra/source_match_set_service.py``; this module
only decides *what* should happen.

Decisions follow ``docs/t109-backup-source-upload-management.md`` "ops.source_match_sets"
state-transition rules (lines ~804-818) and "ops.source_match_set_items" invariants
(lines ~820-857). The canonical ``source_set_hash`` itself is *not* recomputed here:
it is owned by ``core.source_match_propagation.compute_source_set_hash`` and reused
(no duplication).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

MatchSetState = Literal[
    "draft",
    "validated",
    "active",
    "retired",
    "invalid",
    "revalidatable",
    "restored_from_backup",
]

MatchSetItemRole = Literal[
    "build_required",
    "build_recommended",
    "validation_optional",
    "enrichment_candidate",
]

#: Role set permitted on a match-set item (CHECK ``chk_ops_source_match_set_items_role``).
VALID_ITEM_ROLES: frozenset[str] = frozenset(
    {"build_required", "build_recommended", "validation_optional", "enrichment_candidate"}
)


# --- item invariants (create-time validation) ------------------------------


@dataclass(frozen=True)
class MatchSetItemSpec:
    """One requested ``ops.source_match_set_items`` row at create time."""

    category: str
    role: str
    source_file_group_id: str | None = None
    omitted: bool = False
    omitted_reason: str | None = None
    required: bool = False
    validation_enabled: bool = True
    load_order: int | None = None


@dataclass(frozen=True)
class ItemInvariantError:
    category: str
    reason: str


def validate_item_invariants(
    items: tuple[MatchSetItemSpec, ...],
) -> tuple[ItemInvariantError, ...]:
    """Check the DB CHECK/UNIQUE invariants *before* hitting the database.

    Mirrors the three DDL constraints on ``ops.source_match_set_items``:

    * ``role`` ∈ VALID_ITEM_ROLES (``chk_ops_source_match_set_items_role``);
    * the omitted XOR group-id rule (``chk_ops_source_match_set_items_omitted``):
      ``omitted=false`` ⇒ ``source_file_group_id IS NOT NULL`` and
      ``omitted=true`` ⇒ ``source_file_group_id IS NULL``;
    * ``UNIQUE (source_match_set_id, category)`` — at most one item per category.
    """
    errors: list[ItemInvariantError] = []
    seen: set[str] = set()
    for item in items:
        if item.role not in VALID_ITEM_ROLES:
            errors.append(
                ItemInvariantError(item.category, f"invalid role: {item.role!r}")
            )
        if item.omitted:
            if item.source_file_group_id is not None:
                errors.append(
                    ItemInvariantError(
                        item.category,
                        "omitted=true requires source_file_group_id IS NULL",
                    )
                )
        elif item.source_file_group_id is None:
            errors.append(
                ItemInvariantError(
                    item.category,
                    "omitted=false requires a source_file_group_id",
                )
            )
        if item.category in seen:
            errors.append(
                ItemInvariantError(
                    item.category, "duplicate category (UNIQUE per match set)"
                )
            )
        seen.add(item.category)
    return tuple(errors)


# --- validate: state-split decision ----------------------------------------

#: States that cannot be validated directly — they must first recover to
#: ``revalidatable`` via ``recompute_group_aggregates`` (doc lines ~806/810/816).
NON_VALIDATABLE_STATES: frozenset[str] = frozenset(
    {"retired", "invalid", "restored_from_backup"}
)

ValidateAction = Literal[
    "validate_draft",  # draft → validated (compute fresh hash)
    "revalidate",  # revalidatable → validated (re-check pre-computed hash)
    "validate_in_place",  # active + integrity_alert → clear alert, stay active
    "reject",  # not in a validatable state
]


@dataclass(frozen=True)
class ValidateCoverage:
    """Coverage facts the service gathered (referenced groups + required gaps)."""

    #: Every non-omitted referenced group is ``available`` with ``group_sha256``.
    all_groups_available: bool
    #: Referenced group ids that are NOT available (or missing a hash).
    unavailable_group_ids: tuple[str, ...] = ()
    #: Categories the profile requires that are neither present nor explicitly omitted.
    missing_required_categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidateFacts:
    """The ``ops.source_match_sets`` row + coverage the validate endpoint sees."""

    source_match_set_id: str
    state: MatchSetState
    integrity_alert: bool
    coverage: ValidateCoverage


@dataclass(frozen=True)
class ValidateDecision:
    """What ``POST /validate`` should do (no DB writes here)."""

    action: ValidateAction
    #: For draft/revalidate success: the resulting state. ``None`` for in-place
    #: (stays active) and for reject.
    next_state: MatchSetState | None
    #: True when coverage/hash check passed and the action may proceed.
    ok: bool
    #: When True (active validate-in-place success), clear ``integrity_alert``.
    clear_integrity_alert: bool = False
    reasons: tuple[str, ...] = ()


def _coverage_reasons(coverage: ValidateCoverage) -> tuple[str, ...]:
    reasons: list[str] = []
    if not coverage.all_groups_available:
        reasons.append(
            "referenced groups not all available: "
            + (", ".join(coverage.unavailable_group_ids) or "<unknown>")
        )
    if coverage.missing_required_categories:
        reasons.append(
            "required categories missing (neither present nor omitted): "
            + ", ".join(coverage.missing_required_categories)
        )
    return tuple(reasons)


def decide_validate(facts: ValidateFacts) -> ValidateDecision:
    """The ``POST .../{id}/validate`` state-split (doc lines ~806/813-815).

    * ``draft`` → coverage ok ⇒ ``validate_draft`` → ``validated`` (compute hash);
    * ``revalidatable`` → coverage ok ⇒ ``revalidate`` → ``validated`` (re-check
      the hash that was pre-computed before the ``revalidatable`` transition);
    * ``active`` *with* ``integrity_alert`` → ``validate_in_place``: coverage ok ⇒
      clear the alert and STAY ``active`` (no slot change); coverage not ok ⇒
      keep ``active`` + alert (failure audited by the service);
    * ``active`` *without* ``integrity_alert`` → ``reject`` (nothing to do);
    * ``retired`` / ``invalid`` / ``restored_from_backup`` → ``reject`` (must go
      through ``revalidatable`` first).
    """
    coverage = facts.coverage
    coverage_ok = coverage.all_groups_available and not coverage.missing_required_categories
    reasons = _coverage_reasons(coverage)

    if facts.state == "draft":
        return ValidateDecision(
            action="validate_draft",
            next_state="validated" if coverage_ok else None,
            ok=coverage_ok,
            reasons=reasons,
        )
    if facts.state == "revalidatable":
        return ValidateDecision(
            action="revalidate",
            next_state="validated" if coverage_ok else None,
            ok=coverage_ok,
            reasons=reasons,
        )
    if facts.state == "active":
        if not facts.integrity_alert:
            return ValidateDecision(
                action="reject",
                next_state=None,
                ok=False,
                reasons=("active match set has no integrity_alert to clear",),
            )
        # validate-in-place: success clears the alert, state stays 'active'.
        return ValidateDecision(
            action="validate_in_place",
            next_state=None,  # stays active in both branches
            ok=coverage_ok,
            clear_integrity_alert=coverage_ok,
            reasons=reasons,
        )
    # retired / invalid / restored_from_backup
    return ValidateDecision(
        action="reject",
        next_state=None,
        ok=False,
        reasons=(
            f"state {facts.state!r} is not directly validatable; "
            "recover to 'revalidatable' first",
        ),
    )


# --- activate: precondition + atomic-swap sequence -------------------------


@dataclass(frozen=True)
class ActivateFacts:
    """Target match-set facts the activate endpoint sees (under advisory lock)."""

    source_match_set_id: str
    state: MatchSetState
    #: The hash persisted on the row right now.
    stored_source_set_hash: str | None
    #: The canonical hash re-computed from current items/groups just before swap.
    recomputed_source_set_hash: str | None
    #: The id of the currently-active match set, or ``None`` if none is active.
    current_active_id: str | None


ActivateStepKind = Literal["retire_current", "activate_target"]


@dataclass(frozen=True)
class ActivateStep:
    """One ordered step of the single-transaction atomic swap."""

    kind: ActivateStepKind
    source_match_set_id: str
    new_state: MatchSetState


@dataclass(frozen=True)
class ActivateDecision:
    """Whether activation may proceed, and the exact swap step sequence.

    ``ok=False`` carries the refusal reason and an empty ``steps``. When ``ok``,
    ``steps`` is the ordered sequence the service must apply in ONE transaction
    under the ``SOURCE_MATCH_ACTIVATE`` advisory lock: retire the current active
    (if any) FIRST, then set the target ``active``. Because the one-active partial
    unique index is NOT deferrable, retire-before-activate avoids a transient
    two-active violation; the single transaction means no externally-observable
    active gap (doc line ~807).
    """

    ok: bool
    steps: tuple[ActivateStep, ...] = ()
    reasons: tuple[str, ...] = ()


def decide_activate(facts: ActivateFacts) -> ActivateDecision:
    """Precondition + atomic-swap sequence for ``POST .../{id}/activate``.

    * only ``validated`` may be activated (doc line ~806); any other state refuses;
    * the hash recomputed just before activate must equal the stored hash —
      otherwise the items/groups drifted since validate and we refuse (stale-hash
      guard, doc line ~764/807);
    * the swap is ``retire_current`` (when a different set is active) then
      ``activate_target``. Re-activating the already-active set is a no-op refusal
      (its own retire+activate would be incoherent).
    """
    if facts.state != "validated":
        return ActivateDecision(
            ok=False,
            reasons=(
                f"only 'validated' match sets can be activated (state={facts.state!r})",
            ),
        )
    if facts.recomputed_source_set_hash is None or facts.stored_source_set_hash is None:
        return ActivateDecision(
            ok=False,
            reasons=("source_set_hash missing; re-run validate before activate",),
        )
    if facts.recomputed_source_set_hash != facts.stored_source_set_hash:
        return ActivateDecision(
            ok=False,
            reasons=(
                "source_set_hash is stale: items/groups changed since validate; "
                "re-validate before activate",
            ),
        )
    if facts.current_active_id == facts.source_match_set_id:
        return ActivateDecision(
            ok=False, reasons=("match set is already active",)
        )

    steps: list[ActivateStep] = []
    if facts.current_active_id is not None:
        steps.append(
            ActivateStep(
                kind="retire_current",
                source_match_set_id=facts.current_active_id,
                new_state="retired",
            )
        )
    steps.append(
        ActivateStep(
            kind="activate_target",
            source_match_set_id=facts.source_match_set_id,
            new_state="active",
        )
    )
    return ActivateDecision(ok=True, steps=tuple(steps))


# --- retire ----------------------------------------------------------------

#: States from which a plain ``retire`` is a no-op (already terminal/retired).
_ALREADY_RETIRED: frozenset[str] = frozenset({"retired"})


@dataclass(frozen=True)
class RetireDecision:
    ok: bool
    next_state: MatchSetState | None = None
    #: True when the retired set was the active one (UI "현재 구성=알수없음").
    was_active: bool = False
    reasons: tuple[str, ...] = ()


def decide_retire(*, state: MatchSetState) -> RetireDecision:
    """Decide a standalone ``POST .../{id}/retire`` (doc line ~808).

    Any non-retired state may be retired to ``retired``. Retiring the ``active``
    set empties the one-active slot (UI shows 현재 구성=알수없음); the doc prefers
    replacement-activate in the same transaction, but a standalone retire is still
    permitted for non-active sets and for deliberately clearing the slot.
    """
    if state in _ALREADY_RETIRED:
        return RetireDecision(ok=False, reasons=("already retired",))
    return RetireDecision(
        ok=True, next_state="retired", was_active=(state == "active")
    )


# --- yyyymm aggregation (derived match-set fields) -------------------------


@dataclass(frozen=True)
class YyyymmAggregate:
    yyyymm_by_category: dict[str, str]
    mixed_yyyymm: bool = field(default=False)


def aggregate_yyyymm(
    items: tuple[tuple[str, str | None], ...],
) -> YyyymmAggregate:
    """Compute ``yyyymm_by_category`` + ``mixed_yyyymm`` from item effective months.

    ``items`` is ``(category, effective_yyyymm)``; ``None`` months are skipped
    (omitted items). ``mixed_yyyymm`` is True when two present months differ
    (doc line ~857).
    """
    by_category: dict[str, str] = {}
    for category, yyyymm in items:
        if yyyymm:
            by_category[category] = yyyymm
    distinct = set(by_category.values())
    return YyyymmAggregate(
        yyyymm_by_category=by_category, mixed_yyyymm=len(distinct) > 1
    )
