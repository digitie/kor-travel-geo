from __future__ import annotations

import pytest

from pykraddr.postgis import (
    LEGAL_DONG_BOUNDARY_TABLE,
    LEGAL_DONG_TABLE,
    boundary_level_from_path,
    make_postgis_metadata,
)


def test_boundary_level_from_path() -> None:
    assert boundary_level_from_path("N3A_G0010000.zip") == "sido"
    assert boundary_level_from_path("N3A_G0100000.zip") == "sigungu"
    assert boundary_level_from_path("N3A_G0110000.zip") == "eup_myeon_dong"


def test_make_postgis_metadata_has_fk_and_nullable_unmatched_code() -> None:
    pytest.importorskip("geoalchemy2")

    metadata = make_postgis_metadata(schema="kraddr", srid=5179)
    legal = metadata.tables["kraddr." + LEGAL_DONG_TABLE]
    boundary = metadata.tables["kraddr." + LEGAL_DONG_BOUNDARY_TABLE]

    assert legal.c.legal_dong_code.primary_key
    assert boundary.c.legal_dong_code.nullable is True
    assert list(boundary.c.legal_dong_code.foreign_keys)[0].column is legal.c.legal_dong_code
    assert boundary.c.geom.type.srid == 5179
