from __future__ import annotations

import inspect
import logging
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from kortravelgeo.api import app as app_module
from kortravelgeo.api.app import _install_performance_monitoring, create_app
from kortravelgeo.settings import Settings


def test_create_app_exposes_expected_routes_without_starting_lifespan() -> None:
    app = create_app()
    paths = set(app.openapi()["paths"])
    paths.update(
        path
        for route in app.routes
        if isinstance((path := getattr(route, "path", None)), str)
    )

    assert "/v1/address/geocode" in paths
    assert "/v1/address/reverse" in paths
    assert "/v1/address/search" in paths
    assert "/v1/address/zipcode" in paths
    assert "/v1/address/pobox" in paths
    assert "/v2/geocode" in paths
    assert "/v2/reverse" in paths
    assert "/v2/search" in paths
    assert "/v1/admin/loads" in paths
    assert "/v1/admin/jobs" in paths
    assert "/v1/admin/jobs/{job_id}/events" in paths
    assert "/v1/admin/tables" in paths
    assert "/v1/admin/explain" in paths
    assert "/v1/admin/cache/metrics" in paths
    assert "/v1/admin/logs" in paths
    assert "/v1/admin/upload/sido-zip" in paths
    assert "/v1/admin/source-file-categories" in paths
    assert "/v1/admin/storage/rustfs/config" in paths
    assert "/v1/admin/storage/rustfs/check" in paths
    assert "/v1/admin/storage/rustfs/import-prefix" in paths
    assert "/v1/admin/storage/rustfs/sync-local" in paths
    # T-201 removed the legacy auto-detection upload-SET + load-source surface.
    assert "/v1/admin/uploads" not in paths
    assert "/v1/admin/uploads/{upload_set_id}" not in paths
    assert "/v1/admin/uploads/{upload_set_id}/files" not in paths
    assert "/v1/admin/uploads/{upload_set_id}/cancel" not in paths
    assert "/v1/admin/load-sources/discover" not in paths
    assert "/v1/admin/load-sources/plan" not in paths
    assert "/v1/admin/backups" in paths
    assert "/v1/admin/backups/{artifact_id}" in paths
    assert "/v1/admin/backups/{artifact_id}/download" in paths
    assert "/v1/admin/backups/{artifact_id}/delete" in paths
    assert "/v1/admin/restores" in paths
    assert "/v1/admin/maintenance/refresh-mv" in paths
    assert "/v1/admin/consistency/run" in paths
    assert "/v1/admin/consistency/case-definitions" in paths
    assert "/v1/admin/source-match-sets/{source_match_set_id}/run-validation" in paths
    assert "/v1/admin/consistency/{report_id}/cases/{case_code}/samples" in paths
    assert "/v1/admin/consistency/{report_id}/cases/{case_code}/summary" in paths
    assert (
        "/v1/admin/consistency/{report_id}/cases/{case_code}/samples/{sample_id}/decision"
        in paths
    )
    assert "/v1/admin/consistency/{report_id}/cases/{case_code}/samples/bulk-decision" in paths
    assert (
        "/v1/admin/consistency/{report_id}/cases/{case_code}/samples/{sample_id}/recheck"
        in paths
    )
    assert "/v1/admin/ops/audit-events" in paths
    assert "/v1/admin/ops/snapshots" in paths
    assert "/v1/admin/ops/releases" in paths
    assert "/v1/admin/ops/releases/{release_id}/rollback-plan" in paths
    assert "/v1/admin/ops/artifacts" in paths
    assert "/v1/admin/ops/maintenance-windows" in paths
    assert "/v1/admin/ops/maintenance-windows/{window_id}/end" in paths
    assert "/v1/admin/ops/table-stats" in paths
    assert "/v1/admin/ops/table-stats/capture" in paths
    assert "/metrics" in paths


def test_api_queue_registers_sppn_makarea_loader() -> None:
    source = inspect.getsource(app_module._register_default_handlers)

    assert "load_sppn_makarea(" in source
    assert '"sppn_makarea_load"' in source
    assert "AdvisoryLockNamespace.LOAD_SPPN_MAKAREA" in source
    assert "sppn_makarea" in source


@pytest.mark.asyncio
async def test_performance_logging_uses_route_template_without_query(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, Any]:
        return {"item_id": item_id}

    _install_performance_monitoring(
        app,
        Settings(api_performance_logging_enabled=True),
    )

    caplog.set_level(logging.INFO, logger="kortravelgeo.api.performance")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/items/123?address=서울특별시 종로구 인사동")

    assert response.status_code == 200
    records = [
        record for record in caplog.records if record.name == "kortravelgeo.api.performance"
    ]
    assert records
    record = records[-1]
    assert record.__dict__["route"] == "/items/{item_id}"
    assert record.__dict__["status_code"] == 200
    assert "address" not in record.getMessage()
    assert "서울특별시" not in record.getMessage()
