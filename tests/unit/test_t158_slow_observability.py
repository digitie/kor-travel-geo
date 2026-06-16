from __future__ import annotations

from datetime import UTC, datetime

from kortravelgeo.infra import slow_observability
from kortravelgeo.settings import Settings


def setup_function() -> None:
    slow_observability.reset_slow_observability_for_tests()


def teardown_function() -> None:
    slow_observability.reset_slow_observability_for_tests()


def test_slow_query_sample_redacts_preview_and_keeps_endpoint_context() -> None:
    slow_observability.configure_slow_observability(
        Settings(
            ops_slow_samples_enabled=True,
            ops_slow_query_ms=10,
            ops_slow_sample_min_interval_ms=0,
        )
    )
    token = slow_observability.set_request_observability_context(
        "POST",
        "/v2/geocode",
    )
    try:
        slow_observability.record_slow_query(
            statement=(
                "SELECT * FROM mv_geocode_target "
                "WHERE road_address = '서울특별시 강남구 테헤란로 152' "
                "AND buld_mnnm = 152"
            ),
            parameters=None,
            elapsed_s=0.025,
            status="success",
        )
    finally:
        slow_observability.reset_request_observability_context(token)

    samples = slow_observability.pop_slow_samples_for_tests()

    assert len(samples) == 1
    sample = samples[0]
    assert sample.sample_type == "db_query"
    assert sample.method == "POST"
    assert sample.route == "/v2/geocode"
    assert sample.operation == "select"
    assert sample.query_fingerprint
    assert sample.query_preview
    assert "서울특별시" not in sample.query_preview
    assert "152" not in sample.query_preview
    assert sample.context["status"] == "success"


def test_slow_sampling_min_interval_limits_duplicate_query_samples() -> None:
    slow_observability.configure_slow_observability(
        Settings(
            ops_slow_samples_enabled=True,
            ops_slow_query_ms=1,
            ops_slow_sample_min_interval_ms=60_000,
        )
    )

    for _ in range(2):
        slow_observability.record_slow_query(
            statement="SELECT * FROM mv_geocode_target WHERE bd_mgt_sn = 'x'",
            parameters=None,
            elapsed_s=0.010,
            status="success",
        )

    assert slow_observability.queued_slow_sample_count() == 1


def test_slow_request_and_overload_samples_are_bounded_and_typed() -> None:
    slow_observability.configure_slow_observability(
        Settings(
            ops_slow_samples_enabled=True,
            api_slow_request_ms=10,
            ops_slow_sample_min_interval_ms=0,
            ops_slow_sample_queue_size=1,
        )
    )

    slow_observability.record_slow_api_request(
        method="GET",
        route="/v1/address/geocode",
        status_code=200,
        elapsed_ms=25.0,
    )
    slow_observability.record_overload_event(
        method="GET",
        route="/v1/address/geocode",
        scope="geocode",
    )

    samples = slow_observability.pop_slow_samples_for_tests()

    assert len(samples) == 1
    assert samples[0].sample_type == "api_request"
    assert slow_observability.dropped_slow_sample_count() == 1


def test_slow_sample_record_excludes_raw_sql_statement() -> None:
    sample = slow_observability.SlowObservabilitySample(
        slow_sample_id="00000000-0000-0000-0000-000000000001",
        captured_at=datetime.now(UTC),
        sample_type="db_query",
        elapsed_ms=300.0,
        sample_rate=1.0,
        operation="select",
        query_fingerprint="abcdef123456",
        query_preview="SELECT * FROM mv_geocode_target WHERE road_address = ?",
        _statement="SELECT * FROM mv_geocode_target WHERE road_address = '서울'",
    )

    record = slow_observability.sample_record(sample)

    assert "_statement" not in record
    assert "서울" not in str(record)
    assert record["query_preview"].endswith("?")
