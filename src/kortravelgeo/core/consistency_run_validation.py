"""Pure run-validation decision logic (T-206).

``POST /v1/admin/source-match-sets/{id}/run-validation`` materializes the
optional C11~C17 validation inputs for a match set and runs the registry cases
*without* rebuilding the serving DB
(``docs/t109-backup-source-upload-management.md`` lines ~1564-1578 + the "사후
검증" coverage rows ~1618-1620). The DB/RustFS/loader glue lives in the api/infra
layers; this module decides — with synthetic facts, no DB — three things:

1. **사용 직전 무결성 게이트 → failed vs skipped.** Before reading an optional
   input's archive, its RustFS object integrity is re-verified (the same
   pre-load gate reused from T-204/T-205). The distinction (doc ~1562, ~1576,
   ~1618-1619):

   * input **absent** from the match set → ``skipped`` (not a success, not a
     failure; UI shows the 생략 사유);
   * input present but **integrity mismatch / corrupt / missing object** →
     ``failed`` with ``failure_reason='source_integrity_mismatch'`` (NOT
     skipped). No new DB / snapshot / release; the failing group is quarantined.

2. **validator_version change → revert prior ``passed``.** When the validator
   that produced a prior ``passed`` differs from the current one, that case /
   group's ``validation_state`` reverts to ``not_started`` (or ``validating``)
   and referencing match sets are marked needing re-validation (doc ~1620). The
   service then calls ``recompute_group_aggregates(..., trigger=
   'validator_version_change')``.

3. The per-input states roll up to an overall job outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Per-input run-validation state (doc ~1576/1618-1620). ``passed``/``warning``
# come from the validator; ``skipped``/``failed``/``not_started`` from the gate
# + version logic decided here.
InputValidationState = Literal[
    "passed",
    "warning",
    "skipped",
    "failed",
    "not_started",
    "validating",
]

#: Recorded on a failed input so the report explains why (doc ~1576).
INTEGRITY_FAILURE_REASON = "source_integrity_mismatch"


@dataclass(frozen=True, slots=True)
class CaseInputFacts:
    """What the run-validation orchestrator observed for one registry input.

    ``required`` mirrors ``ops.consistency_case_inputs.required`` (a conditional
    C11 input is ``required=false``). ``present`` is whether the match set
    actually carries a non-omitted group for this category. ``integrity_ok`` is
    the 사용 직전 게이트 result — only meaningful when ``present`` is True.
    """

    category: str
    required: bool
    present: bool
    integrity_ok: bool = True
    #: The group id backing this input (for quarantine + recompute), if present.
    source_file_group_id: str | None = None


@dataclass(frozen=True, slots=True)
class CaseInputDecision:
    """The decided state of one input + (when failed) the group to quarantine."""

    category: str
    state: InputValidationState
    required: bool = True
    failure_reason: str | None = None
    #: Group id to quarantine + recompute (only set for an integrity ``failed``).
    quarantine_group_id: str | None = None


def decide_input_state(facts: CaseInputFacts) -> CaseInputDecision:
    """Decide one input's state from the gate (doc ~1562, ~1576, ~1618-1619).

    * absent (required or optional) → ``skipped``;
    * present + integrity failure → ``failed`` (``source_integrity_mismatch``),
      and name the group to quarantine;
    * present + integrity ok → ``not_started`` (validator runs next).
    """
    if not facts.present:
        return CaseInputDecision(
            category=facts.category, state="skipped", required=facts.required
        )
    if not facts.integrity_ok:
        return CaseInputDecision(
            category=facts.category,
            state="failed",
            required=facts.required,
            failure_reason=INTEGRITY_FAILURE_REASON,
            quarantine_group_id=facts.source_file_group_id,
        )
    return CaseInputDecision(
        category=facts.category, state="not_started", required=facts.required
    )


@dataclass(frozen=True, slots=True)
class CaseRunDecision:
    """The decided run-validation outcome for one registry case.

    ``runnable`` is True when every *required* input is present + integrity-ok
    (so the validator can run). ``skipped`` is True when a required input is
    absent (the whole case is 생략). ``failed`` is True when any present input's
    archive integrity failed. ``inputs`` carries the per-input decisions; the
    quarantine group ids are surfaced for the integrity-failure propagation.
    """

    case_code: str
    runnable: bool
    skipped: bool
    failed: bool
    inputs: tuple[CaseInputDecision, ...]
    quarantine_group_ids: tuple[str, ...]


def decide_case_run(
    case_code: str,
    inputs: tuple[CaseInputFacts, ...],
) -> CaseRunDecision:
    """Roll per-input decisions up to a case outcome (doc ~1575-1576, ~1618-1619).

    Precedence: an integrity ``failed`` on ANY present input fails the case (no
    DB build) even if a required input is also absent — a corrupt archive is a
    harder signal than a missing one and must be surfaced as ``failed`` not
    ``skipped`` (doc ~1562). Otherwise, a missing *required* input makes the case
    ``skipped``. Only when every required input is present + integrity-ok is the
    case ``runnable``.
    """
    decisions = tuple(decide_input_state(f) for f in inputs)
    quarantine = tuple(
        d.quarantine_group_id for d in decisions if d.quarantine_group_id is not None
    )
    any_failed = any(d.state == "failed" for d in decisions)
    required_absent = any(f.required and not f.present for f in inputs)
    if any_failed:
        return CaseRunDecision(
            case_code=case_code,
            runnable=False,
            skipped=False,
            failed=True,
            inputs=decisions,
            quarantine_group_ids=quarantine,
        )
    if required_absent:
        return CaseRunDecision(
            case_code=case_code,
            runnable=False,
            skipped=True,
            failed=False,
            inputs=decisions,
            quarantine_group_ids=(),
        )
    return CaseRunDecision(
        case_code=case_code,
        runnable=True,
        skipped=False,
        failed=False,
        inputs=decisions,
        quarantine_group_ids=(),
    )


# --- validator_version change ----------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidatorVersionFacts:
    """A prior validation result + the current validator version (doc ~1620)."""

    case_code: str
    prior_state: InputValidationState
    prior_validator_version: str | None
    current_validator_version: str


@dataclass(frozen=True, slots=True)
class ValidatorVersionDecision:
    """Whether a prior result must be re-validated under a new validator."""

    case_code: str
    #: True when a prior ``passed`` (or ``warning``) no longer trusted.
    needs_revalidation: bool
    #: The state to revert to (``not_started`` per doc; ``validating`` once
    #: re-run is enqueued). ``None`` when no revert is required.
    revert_state: InputValidationState | None
    reason: str | None = None


def decide_validator_version_change(
    facts: ValidatorVersionFacts,
) -> ValidatorVersionDecision:
    """Revert a stale ``passed`` to ``not_started`` (doc ~1620).

    "validator version이 바뀌어 기존 passed 결과를 신뢰할 수 없음" → 해당
    category/group은 ``not_started``/``validating`` 후보로 되돌리고, 참조 match
    set은 재검증 필요 상태를 표시한다. Only a prior trusted result
    (``passed``/``warning``) under a *different* version triggers a revert;
    same-version or non-trusted priors are left untouched.
    """
    is_trusted = facts.prior_state in ("passed", "warning")
    version_changed = facts.prior_validator_version != facts.current_validator_version
    if is_trusted and version_changed:
        return ValidatorVersionDecision(
            case_code=facts.case_code,
            needs_revalidation=True,
            revert_state="not_started",
            reason=(
                f"validator_version changed "
                f"{facts.prior_validator_version!r} -> "
                f"{facts.current_validator_version!r}; prior "
                f"{facts.prior_state!r} no longer trusted"
            ),
        )
    return ValidatorVersionDecision(
        case_code=facts.case_code,
        needs_revalidation=False,
        revert_state=None,
    )
