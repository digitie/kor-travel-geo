"""C11~C17 run-validation prototype-metric binding (T-206 regression bridge).

The T-118 contract is "prototype metric == run-validation metric": run-validation
for C11~C17 MUST reuse the SAME metric computation as the phase-① prototypes, not
a reimplementation (``docs/t118-phase1-go-no-go.md`` line ~108). Each prototype
exposes a pure ``.metrics()`` method on its comparison dataclass
(``loaders/c1X_*.py``); this module is the single registry that binds each
registry ``case_code`` to its prototype's comparison class so the orchestrator
(and the regression test) call exactly that method.

**Layer note.** ``infra ↛ loaders`` is forbidden by the import-linter layered
contract (loaders sits ABOVE infra). Run-validation needs the prototype metric
code, which lives in ``loaders``. So this binding module is placed in the
``loaders`` layer (it legally imports the sibling ``c1X_*`` prototypes), and the
orchestration entry point that consumes it is the **api admin router** — the one
edge with an existing allowed ignore (``api.routers.admin -> loaders``). This
keeps ``infra``/``client`` free of loader imports and the linter green, while the
metric code is reused (never duplicated). The pure run-validation *decision*
logic (gate / failed-vs-skipped / validator_version) stays DB-free in
``core/consistency_run_validation.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from kortravelgeo.loaders.c11_entrance_sources import C11EntranceComparison
from kortravelgeo.loaders.c12_connection_lines import C12ConnectionComparison
from kortravelgeo.loaders.c13_detail_dong import C13DetailDongComparison
from kortravelgeo.loaders.c14_national_point_grid import C14NationalPointGridComparison
from kortravelgeo.loaders.c15_civil_service_poi import C15CivilServicePoiComparison
from kortravelgeo.loaders.c16_address_building_drift import C16AddressBuildingDriftComparison
from kortravelgeo.loaders.c17_navi_jibun_coverage import C17NaviJibunCoverageComparison


class HasMetrics(Protocol):
    """Anything with the prototype's pure ``.metrics()`` contract."""

    def metrics(self) -> dict[str, object]: ...


#: Registry ``case_code`` → its phase-① prototype comparison class. The class's
#: ``.metrics()`` is the canonical metric; run-validation calls it directly.
PROTOTYPE_COMPARISON_BY_CASE: dict[str, type[HasMetrics]] = {
    "C11": C11EntranceComparison,
    "C12": C12ConnectionComparison,
    "C13": C13DetailDongComparison,
    "C14": C14NationalPointGridComparison,
    "C15": C15CivilServicePoiComparison,
    "C16": C16AddressBuildingDriftComparison,
    "C17": C17NaviJibunCoverageComparison,
}

AUGMENT_CASE_CODES: tuple[str, ...] = tuple(PROTOTYPE_COMPARISON_BY_CASE)


def prototype_metric(comparison: HasMetrics) -> dict[str, object]:
    """Compute the canonical prototype metric for a comparison.

    This is the SINGLE function run-validation uses to turn a prototype
    comparison into its metric dict; the regression test asserts that the
    run-validation metric for a synthetic case equals
    ``comparison.metrics()`` so the two can never diverge.
    """
    return comparison.metrics()


def is_augment_case(case_code: str) -> bool:
    """True for C11~C17 (the registry cases run by run-validation)."""
    return case_code in PROTOTYPE_COMPARISON_BY_CASE


def prototype_comparison_class(case_code: str) -> type[HasMetrics]:
    """The prototype comparison class bound to ``case_code`` (KeyError if none)."""
    return PROTOTYPE_COMPARISON_BY_CASE[case_code]


def metric_or_none(case_code: str, comparison: HasMetrics | None) -> Mapping[str, object] | None:
    """Convenience: prototype metric for a (case, comparison), or ``None``."""
    if comparison is None:
        return None
    return prototype_metric(comparison)
