"""T-127 optional single-file source structure smoke (real archives, opt-in by data).

This reads ZIP central directories only. It never opens large TXT/SHP payloads and
skips when the preserved ``data/juso/unused`` source root is unavailable.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from kortravelgeo.core.source_validation import validate_group_manifest
from kortravelgeo.infra.source_member_scan import scan_group_manifest


def _unused_root() -> Path | None:
    candidates = []
    configured = os.getenv("KTG_T127_REAL_SOURCE_DIR")
    if configured:
        candidates.append(Path(configured))
    candidates.extend((Path("data/juso/unused"), Path("F:/dev/geodata/juso/unused")))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


@pytest.mark.parametrize(
    ("category", "filename", "expected_outcome"),
    (
        ("detail_address_db_full", "202604_상세주소DB_전체분.zip", "passed"),
        ("national_point_grid_shape", "국가지점번호도형_5월분.zip", "warning"),
        ("national_point_grid_center", "국가지점번호중심점_5월분.zip", "passed"),
        ("civil_service_institution_map", "민원행정기관전자지도_240124.zip", "passed"),
        ("address_db_full", "202605_주소DB_전체분.zip", "passed"),
        ("building_db_full", "202605_건물DB_전체분.zip", "passed"),
    ),
)
def test_t127_real_optional_single_file_archives_smoke(
    category: str, filename: str, expected_outcome: str
) -> None:
    root = _unused_root()
    if root is None:
        pytest.skip("data/juso/unused source root is unavailable")
    archive = root / filename
    if not archive.exists():
        pytest.skip(f"optional source archive is unavailable: {archive}")

    manifest = scan_group_manifest(
        category=category,
        group_kind="single_file",
        parts={"archive": archive},
    )
    result = validate_group_manifest(manifest)

    assert result.outcome == expected_outcome
    assert result.coverage == {"archive": "present"}
    assert not result.reasons
