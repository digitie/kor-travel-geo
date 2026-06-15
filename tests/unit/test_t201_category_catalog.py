"""T-201 category catalog endpoint + client method.

The legacy auto-detection upload-SET / load-source surface was removed; the new
``GET /v1/admin/source-file-categories`` endpoint serves the static
``CATEGORY_CATALOG`` so the UI can draw explicit per-category upload slots.
"""

from __future__ import annotations

import typing

import httpx
import pytest

from kortravelgeo.api.app import create_app
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.core.source_categories import (
    CATEGORY_CATALOG,
    SERVING_USAGE_BY_CODE,
    SourceServingUsage,
    serving_usage_for,
)
from kortravelgeo.dto.source import SourceServingUsage as DtoSourceServingUsage


async def _get_categories(headers: dict[str, str] | None = None) -> httpx.Response:
    # ASGITransport gives a loopback client IP, which the ADR-037 GeoIP gate
    # treats as internal (allowed); no lifespan/DB is required for this route.
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/v1/admin/source-file-categories", headers=headers)


@pytest.mark.asyncio
async def test_source_file_categories_endpoint_returns_full_catalog() -> None:
    response = await _get_categories()

    assert response.status_code == 200
    body = response.json()
    categories = body["categories"]
    assert len(categories) == len(CATEGORY_CATALOG)

    by_code = {item["category"]: item for item in categories}
    first = by_code["roadname_hangul_full"]
    assert first["label"] == "도로명주소 한글_전체분"
    assert first["group_kind"] == "single_file"
    assert first["default_role"] == "build_required"
    # role mirrors default_role; authoritative role lives on match-set items.
    assert first["role"] == "build_required"
    assert first["optional"] is False
    assert "rnaddrkor_txt" in first["expected_member_kinds"]

    optional = by_code["detail_address_db_full"]
    assert optional["optional"] is True
    assert optional["default_role"] == "validation_optional"

    # T-221: serving_usage (ADR-054) distinguishes serving vs validation-only vs no-go.
    assert first["serving_usage"] == "serving_core"
    assert by_code["roadaddr_building_shape_bundle"]["serving_usage"] == "promotion_blocked_no_go"
    assert by_code["national_point_grid_shape"]["serving_usage"] == "validation_only"
    assert by_code["civil_service_institution_map"]["serving_usage"] == "separate_feature_candidate"
    assert by_code["detail_address_db_full"]["serving_usage"] == "typed_feature_candidate"


def test_serving_usage_covers_every_category_and_matches_dto_literal() -> None:
    # Every catalog code has an explicit ADR-054 serving_usage (no silent default).
    codes = {c.code for c in CATEGORY_CATALOG}
    assert set(SERVING_USAGE_BY_CODE) == codes
    # core and dto SourceServingUsage Literals are kept in sync (dto cannot import core).
    core_values = set(typing.get_args(SourceServingUsage))
    dto_values = set(typing.get_args(DtoSourceServingUsage))
    assert core_values == dto_values
    assert set(SERVING_USAGE_BY_CODE.values()) <= core_values
    # unknown code falls back to validation_only (never implies active serving).
    assert serving_usage_for("does_not_exist") == "validation_only"


@pytest.mark.asyncio
async def test_source_file_categories_endpoint_is_ungated_like_other_admin_endpoints() -> None:
    # T-202 added require_role, but existing admin endpoints are not yet gated;
    # this endpoint follows that convention (no X-KTG-Actor/Roles headers needed).
    response = await _get_categories()
    assert response.status_code == 200


def test_client_list_source_file_categories_matches_catalog() -> None:
    client = AsyncAddressClient()
    categories = client.list_source_file_categories()

    assert len(categories) == len(CATEGORY_CATALOG)
    assert [item.category for item in categories] == [c.code for c in CATEGORY_CATALOG]
    for info, category in zip(categories, CATEGORY_CATALOG, strict=True):
        assert info.label == category.display_name
        assert info.group_kind == category.group_kind
        assert info.default_role == category.default_role
        assert info.role == category.default_role
        assert info.serving_usage == serving_usage_for(category.code)
        assert info.optional == category.optional
        assert info.expected_member_kinds == category.expected_member_kinds
