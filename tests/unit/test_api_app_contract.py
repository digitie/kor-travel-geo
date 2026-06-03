from __future__ import annotations

import inspect

from kraddr.geo.api import app as app_module
from kraddr.geo.api.app import create_app


def test_create_app_exposes_expected_routes_without_starting_lifespan() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}

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
    assert "/v1/admin/uploads" in paths
    assert "/v1/admin/uploads/{upload_set_id}" in paths
    assert "/v1/admin/uploads/{upload_set_id}/files" in paths
    assert "/v1/admin/uploads/{upload_set_id}/cancel" in paths
    assert "/v1/admin/storage/rustfs/config" in paths
    assert "/v1/admin/storage/rustfs/check" in paths
    assert "/v1/admin/storage/rustfs/import-prefix" in paths
    assert "/v1/admin/storage/rustfs/sync-local" in paths
    assert "/v1/admin/load-sources/discover" in paths
    assert "/v1/admin/load-sources/plan" in paths
    assert "/v1/admin/backups" in paths
    assert "/v1/admin/backups/{artifact_id}" in paths
    assert "/v1/admin/backups/{artifact_id}/download" in paths
    assert "/v1/admin/backups/{artifact_id}/delete" in paths
    assert "/v1/admin/restores" in paths
    assert "/v1/admin/maintenance/refresh-mv" in paths
    assert "/v1/admin/consistency/run" in paths
    assert "/v1/admin/consistency/case-definitions" in paths
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
