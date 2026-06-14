"""T-204 reconciliation DTO + infra-converter smoke tests (DB-free).

Validates the OpenAPI-facing DTO shapes and the pure ``infra`` converters that
turn ``core`` capacity math into the API DTO, without touching a DB or RustFS.
"""

from __future__ import annotations

from datetime import UTC, datetime

from kortravelgeo.core.source_reconcile import (
    CapacityUsage,
    CategoryCapacity,
    compute_capacity_usage,
)
from kortravelgeo.dto.source import (
    ReconcileResolveRequest,
    ReconcileRunRequest,
    SourceCapacityUsage,
    SourceReconcileItem,
    SourceReconcileRun,
)
from kortravelgeo.infra.source_reconcile import _capacity_dto


def test_reconcile_run_request_defaults_to_quick() -> None:
    req = ReconcileRunRequest()
    assert req.mode == "quick"
    assert req.prefix is None


def test_reconcile_run_request_rejects_unknown_mode() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ReconcileRunRequest(mode="turbo")  # type: ignore[arg-type]


def test_resolve_request_accepts_typed_confirmation_and_yyyymm() -> None:
    req = ReconcileResolveRequest(
        action="update_hash_after_verify",
        typed_confirmation="현재 RustFS object를 정본으로 인정",
    )
    assert req.action == "update_hash_after_verify"
    req2 = ReconcileResolveRequest(
        action="import_object", category="locsum_full", user_yyyymm="202604"
    )
    assert req2.user_yyyymm == "202604"


def test_resolve_request_rejects_bad_yyyymm() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ReconcileResolveRequest(action="import_object", user_yyyymm="2026")


def test_run_dto_serializes() -> None:
    run = SourceReconcileRun(
        source_storage_reconcile_run_id="r1",
        prefix="kor-travel-geo/source-files",
        mode="quick",
        state="completed",
        started_at=datetime(2026, 6, 14, tzinfo=UTC),
        scanned_objects=5,
        scanned_db_files=4,
        mismatch_count=1,
    )
    dumped = run.model_dump(mode="json")
    assert dumped["mode"] == "quick"
    assert dumped["mismatch_count"] == 1


def test_item_dto_carries_all_diff_columns() -> None:
    item = SourceReconcileItem(
        source_storage_reconcile_item_id="i1",
        source_storage_reconcile_run_id="r1",
        issue_type="hash_mismatch",
        source_file_id="f1",
        object_key="k",
        db_sha256="a" * 64,
        object_sha256="b" * 64,
        db_size_bytes=10,
        object_size_bytes=10,
        severity="error",
    )
    assert item.issue_type == "hash_mismatch"
    assert item.state == "open"


def test_capacity_dto_converts_core_usage() -> None:
    usage: CapacityUsage = compute_capacity_usage(
        (
            CategoryCapacity(
                category="locsum_full", object_count=2, total_bytes=600, quarantined_bytes=100
            ),
        ),
        unregistered_bytes=50,
        capacity_limit_bytes=1000,
    )
    dto = _capacity_dto(usage)
    assert isinstance(dto, SourceCapacityUsage)
    assert dto.total_bytes == 600
    assert dto.unregistered_bytes == 50
    assert dto.categories[0].category == "locsum_full"
    assert dto.capacity_limit_bytes == 1000
