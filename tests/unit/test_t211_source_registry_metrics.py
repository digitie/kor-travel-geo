"""T-211 source-registry observability tests (DB-free).

Covers the pure metric projection (``build_source_registry_metric_facts``), the
30-day growth threading through ``compute_capacity_usage``, and the prometheus
feed (``refresh_source_registry_metrics``) — including that the T-203c janitor
and T-204 reconcile metrics already exist and are NOT duplicated by T-211.
"""

from __future__ import annotations

from kortravelgeo.core.source_reconcile import (
    CapacityUsage,
    CategoryCapacity,
    build_source_registry_metric_facts,
    compute_capacity_usage,
)
from kortravelgeo.dto.source import SourceCapacityUsage, SourceCategoryCapacity
from kortravelgeo.infra import metrics


def _usage() -> CapacityUsage:
    return compute_capacity_usage(
        (
            CategoryCapacity(
                category="locsum_full",
                object_count=2,
                total_bytes=600,
                quarantined_bytes=100,
                soft_deleted_bytes=40,
            ),
            CategoryCapacity(
                category="navi_full",
                object_count=3,
                total_bytes=900,
            ),
        ),
        unregistered_bytes=50,
        growth_30d_bytes=300,
        capacity_limit_bytes=2000,
    )


# --- pure projection -------------------------------------------------------


def test_capacity_usage_threads_growth_30d() -> None:
    usage = _usage()
    assert usage.growth_30d_bytes == 300
    assert usage.total_bytes == 1500
    assert usage.unregistered_bytes == 50


def test_capacity_usage_clamps_negative_growth() -> None:
    usage = compute_capacity_usage((), growth_30d_bytes=-10)
    assert usage.growth_30d_bytes == 0


def test_build_metric_facts_projects_capacity_and_sessions() -> None:
    facts = build_source_registry_metric_facts(
        _usage(),
        session_state_counts={"uploading": 2, "created": 1},
    )
    assert dict(facts.category_objects) == {"locsum_full": 2, "navi_full": 3}
    assert dict(facts.category_bytes) == {"locsum_full": 600, "navi_full": 900}
    assert facts.total_objects == 5
    assert facts.total_bytes == 1500
    assert facts.quarantined_bytes == 100
    assert facts.soft_deleted_bytes == 40
    assert facts.unregistered_bytes == 50
    assert facts.growth_30d_bytes == 300
    # session states are sorted + clamped for a stable scrape.
    assert facts.session_states == (("created", 1), ("uploading", 2))


def test_build_metric_facts_handles_no_sessions() -> None:
    facts = build_source_registry_metric_facts(_usage())
    assert facts.session_states == ()


def test_build_metric_facts_clamps_negative_session_counts() -> None:
    facts = build_source_registry_metric_facts(
        compute_capacity_usage(()), session_state_counts={"failed_storage_state": -3}
    )
    assert facts.session_states == (("failed_storage_state", 0),)


# --- prometheus feed -------------------------------------------------------


def _capacity_dto() -> SourceCapacityUsage:
    return SourceCapacityUsage(
        categories=(
            SourceCategoryCapacity(
                category="locsum_full",
                object_count=2,
                total_bytes=600,
                quarantined_bytes=100,
                soft_deleted_bytes=40,
            ),
        ),
        total_object_count=2,
        total_bytes=600,
        quarantined_bytes=100,
        soft_deleted_bytes=40,
        unregistered_bytes=50,
        growth_30d_bytes=300,
        capacity_limit_bytes=2000,
        over_threshold=False,
    )


def test_refresh_source_registry_metrics_registers_gauges() -> None:
    metrics.refresh_source_registry_metrics(
        capacity=_capacity_dto(),
        session_state_counts={"uploading": 4},
    )
    body = metrics.render_prometheus().decode()

    # T-211 ADDED gauges.
    assert "kor_travel_geo_source_upload_sessions" in body
    assert 'state="uploading"' in body
    assert "kor_travel_geo_source_storage_objects" in body
    assert "kor_travel_geo_source_storage_bytes" in body
    assert 'category="locsum_full"' in body
    assert "kor_travel_geo_source_storage_total_bytes" in body
    assert "kor_travel_geo_source_storage_quarantined_bytes" in body
    assert "kor_travel_geo_source_storage_soft_deleted_bytes" in body
    assert "kor_travel_geo_source_storage_unregistered_bytes" in body
    assert "kor_travel_geo_source_storage_growth_30d_bytes" in body


def test_t203c_janitor_and_t204_reconcile_metrics_exist_and_are_not_duplicated() -> None:
    # Touch the pre-existing T-203c janitor + T-204 reconcile metrics so they
    # render; T-211 must NOT have redefined them (a duplicate Counter/Gauge
    # registration would raise on import).
    metrics.record_source_janitor_run(outcome="ran")
    metrics.record_source_janitor_session(action="expired")
    metrics.record_source_janitor_abort(outcome="succeeded")
    metrics.record_source_reconcile_run(mode="quick", outcome="completed")
    metrics.record_source_reconcile_item(issue_type="hash_mismatch", severity="error")
    metrics.record_source_reconcile_resolve(action="mark_db_missing", outcome="resolved")

    body = metrics.render_prometheus().decode()

    for name in (
        "kor_travel_geo_source_janitor_runs_total",
        "kor_travel_geo_source_janitor_sessions_total",
        "kor_travel_geo_source_janitor_multipart_aborts_total",
        "kor_travel_geo_source_reconcile_runs_total",
        "kor_travel_geo_source_reconcile_items_total",
        "kor_travel_geo_source_reconcile_resolves_total",
    ):
        # Exactly one HELP line per metric family → no duplicate registration.
        assert body.count(f"# HELP {name} ") == 1
