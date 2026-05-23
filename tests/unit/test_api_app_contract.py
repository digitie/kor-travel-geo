from __future__ import annotations

from kraddr.geo.api.app import create_app


def test_create_app_exposes_expected_routes_without_starting_lifespan() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}

    assert "/v1/address/geocode" in paths
    assert "/v1/address/reverse" in paths
    assert "/v1/address/search" in paths
    assert "/v1/address/zipcode" in paths
    assert "/v1/address/pobox" in paths
    assert "/v1/admin/loads" in paths
    assert "/v1/admin/consistency/run" in paths

