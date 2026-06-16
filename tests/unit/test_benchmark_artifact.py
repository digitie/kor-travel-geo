"""T-265: benchmark/perf artifact registration (precursor to T-222 Admin UI)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from kortravelgeo.api.app import create_app
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.dto.admin import (
    BENCHMARK_ARTIFACT_TYPE,
    BenchmarkArtifactRegisterRequest,
    BenchmarkMetrics,
    OpsArtifact,
)
from kortravelgeo.infra import admin_repo


def _ops_artifact(**over: Any) -> OpsArtifact:
    base: dict[str, Any] = {
        "artifact_id": "bench-1",
        "artifact_type": BENCHMARK_ARTIFACT_TYPE,
        "state": "available",
        "storage_kind": "local_file",
        "created_at": datetime(2026, 6, 16, tzinfo=UTC),
    }
    base.update(over)
    return OpsArtifact(**base)


@pytest.mark.asyncio
async def test_register_benchmark_artifact_builds_manifest_and_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_insert(self: admin_repo.AdminRepository, **kwargs: Any) -> OpsArtifact:
        captured.update(kwargs)
        return _ops_artifact(
            manifest=kwargs["manifest"],
            storage_kind=kwargs["storage_kind"],
            storage_uri=kwargs.get("storage_uri"),
        )

    monkeypatch.setattr(admin_repo.AdminRepository, "insert_artifact", fake_insert)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]

    request = BenchmarkArtifactRegisterRequest(
        run_id="20260616-r1",
        kind="load_matrix",
        display_name="T-141 actual_mix steady",
        profile="actual_mix/steady",
        workload="actual_mix",
        phase="steady",
        metrics=BenchmarkMetrics(
            p95_ms=12.3, p99_ms=20.1, error_rate=0.0, qps=512.0, samples=10_000
        ),
        baseline_artifact_id="bench-0",
        storage_uri="F:/dev/geodata/t141/20260616-r1/report.json",
        captured_at=datetime(2026, 6, 16, 1, 0, tzinfo=UTC),
    )
    artifact = await client.register_benchmark_artifact(request)

    assert captured["artifact_type"] == BENCHMARK_ARTIFACT_TYPE
    assert captured["state"] == "available"
    assert captured["storage_kind"] == "local_file"  # storage_uri present
    manifest = captured["manifest"]
    assert manifest["run_id"] == "20260616-r1"
    assert manifest["kind"] == "load_matrix"
    assert manifest["workload"] == "actual_mix"
    assert manifest["metrics"]["p95_ms"] == 12.3
    assert manifest["metrics"]["p99_ms"] == 20.1
    # exclude_none drops unset metric fields.
    assert "max_ms" not in manifest["metrics"]
    assert manifest["baseline_artifact_id"] == "bench-0"
    assert manifest["captured_at"].startswith("2026-06-16")
    assert artifact.artifact_type == BENCHMARK_ARTIFACT_TYPE


@pytest.mark.asyncio
async def test_register_benchmark_artifact_without_storage_uri_uses_none_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_insert(self: admin_repo.AdminRepository, **kwargs: Any) -> OpsArtifact:
        captured.update(kwargs)
        return _ops_artifact(storage_kind=kwargs["storage_kind"])

    monkeypatch.setattr(admin_repo.AdminRepository, "insert_artifact", fake_insert)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]

    await client.register_benchmark_artifact(
        BenchmarkArtifactRegisterRequest(run_id="r", kind="sql", display_name="sql run")
    )
    assert captured["storage_kind"] == "none"
    assert captured["storage_uri"] is None


def test_benchmark_metrics_reject_out_of_range_error_rate() -> None:
    with pytest.raises(ValidationError):
        BenchmarkMetrics(error_rate=1.5)
    with pytest.raises(ValidationError):
        BenchmarkMetrics(p95_ms=-1.0)


def test_benchmark_artifact_endpoint_is_registered() -> None:
    # app.routes wraps included routers lazily, so assert via the resolved OpenAPI schema.
    spec = create_app().openapi()
    path = spec["paths"].get("/v1/admin/ops/benchmark-artifacts", {})
    assert "post" in path
