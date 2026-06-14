"""Source file category catalog (T-200 / T-109).

Canonical list of upload categories with their group structure and default
match-set role. Codes and display names follow
``docs/t109-backup-source-upload-management.md`` and
``docs/backup-restore-source-inventory.md``.

This is a static catalog; per-upload state lives in ``ops.source_file_groups``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SourceGroupKind = Literal["single_file", "multi_part"]
SourceDefaultRole = Literal[
    "build_required",
    "build_recommended",
    "validation_optional",
    "enrichment_candidate",
]


@dataclass(frozen=True, slots=True)
class SourceCategory:
    """A single upload category and how it maps onto the registry model."""

    code: str
    display_name: str
    group_kind: SourceGroupKind
    default_role: SourceDefaultRole
    expected_member_kinds: tuple[str, ...] = field(default_factory=tuple)
    optional: bool = False


# Order: 6 build categories (serving_minimal then serving_recommended), then the
# optional validation / enrichment / postal-aux categories.
CATEGORY_CATALOG: tuple[SourceCategory, ...] = (
    # --- serving_minimal build set ---
    SourceCategory(
        code="roadname_hangul_full",
        display_name="도로명주소 한글_전체분",
        group_kind="single_file",
        default_role="build_required",
        expected_member_kinds=("rnaddrkor_txt", "jibun_rnaddrkor_txt"),
        optional=False,
    ),
    SourceCategory(
        code="locsum_full",
        display_name="위치정보요약DB_전체분",
        group_kind="single_file",
        default_role="build_required",
        expected_member_kinds=("entrc_txt",),
        optional=False,
    ),
    SourceCategory(
        code="navi_full",
        display_name="내비게이션용DB_전체분",
        group_kind="single_file",
        default_role="build_required",
        expected_member_kinds=("match_build_txt", "match_rs_entrc_txt", "match_jibun_txt"),
        optional=False,
    ),
    SourceCategory(
        code="electronic_map_full",
        display_name="도로명주소 전자지도",
        group_kind="multi_part",
        default_role="build_required",
        expected_member_kinds=("sido_zip", "shp_layer"),
        optional=False,
    ),
    # --- serving_recommended build set (currently optional in code) ---
    SourceCategory(
        code="roadaddr_entrance_full",
        display_name="도로명주소 출입구 정보",
        group_kind="multi_part",
        default_role="build_recommended",
        expected_member_kinds=("sido_zip", "rnentdata_txt"),
        optional=False,
    ),
    SourceCategory(
        code="zone_shape_full",
        display_name="구역의 도형",
        group_kind="multi_part",
        default_role="build_recommended",
        expected_member_kinds=("sido_zip", "tl_sppn_makarea_shp"),
        optional=False,
    ),
    # --- optional validation / enrichment categories ---
    SourceCategory(
        code="roadaddr_building_shape_bundle",
        display_name="도로명주소 건물 도형",
        group_kind="multi_part",
        default_role="validation_optional",
        expected_member_kinds=("sido_zip", "shp_layer"),
        optional=True,
    ),
    SourceCategory(
        code="detail_dong_shape_bundle",
        display_name="건물군 내 상세주소 동 도형",
        group_kind="multi_part",
        default_role="validation_optional",
        expected_member_kinds=("sido_zip", "shp_layer"),
        optional=True,
    ),
    SourceCategory(
        code="detail_address_db_full",
        display_name="상세주소DB_전체분",
        group_kind="single_file",
        default_role="validation_optional",
        expected_member_kinds=("detail_address_txt",),
        optional=True,
    ),
    SourceCategory(
        code="national_point_grid_shape",
        display_name="국가지점번호 도형",
        group_kind="single_file",
        default_role="validation_optional",
        expected_member_kinds=("grid_shp",),
        optional=True,
    ),
    SourceCategory(
        code="national_point_grid_center",
        display_name="국가지점번호 중심점",
        group_kind="single_file",
        default_role="validation_optional",
        expected_member_kinds=("grid_center_shp",),
        optional=True,
    ),
    SourceCategory(
        code="civil_service_institution_map",
        display_name="민원행정기관전자지도",
        group_kind="single_file",
        default_role="enrichment_candidate",
        expected_member_kinds=("institution_shp",),
        optional=True,
    ),
    SourceCategory(
        code="address_db_full",
        display_name="주소DB_전체분",
        group_kind="single_file",
        default_role="validation_optional",
        expected_member_kinds=("address_db_txt",),
        optional=True,
    ),
    SourceCategory(
        code="building_db_full",
        display_name="건물DB_전체분",
        group_kind="single_file",
        default_role="validation_optional",
        expected_member_kinds=("building_db_txt",),
        optional=True,
    ),
    # --- postal-aux categories (manual server-fetch flow) ---
    SourceCategory(
        code="epost_pobox_full",
        display_name="epost 사서함",
        group_kind="single_file",
        default_role="enrichment_candidate",
        expected_member_kinds=("pobox_txt",),
        optional=True,
    ),
    SourceCategory(
        code="epost_bulk_full",
        display_name="epost 다량배달처",
        group_kind="single_file",
        default_role="enrichment_candidate",
        expected_member_kinds=("bulk_txt",),
        optional=True,
    ),
)

category_by_code: dict[str, SourceCategory] = {c.code: c for c in CATEGORY_CATALOG}


# 17 시도 코드/명칭 (행정구역 시도 2자리 코드). ``multi_part`` 시도별 자료의
# upload session ``file_slots`` (``part_kind='sido'``)를 그릴 때 사용한다.
SIDO_PARTS: tuple[tuple[str, str], ...] = (
    ("11", "서울특별시"),
    ("26", "부산광역시"),
    ("27", "대구광역시"),
    ("28", "인천광역시"),
    ("29", "광주광역시"),
    ("30", "대전광역시"),
    ("31", "울산광역시"),
    ("36", "세종특별자치시"),
    ("41", "경기도"),
    ("43", "충청북도"),
    ("44", "충청남도"),
    ("46", "전라남도"),
    ("47", "경상북도"),
    ("48", "경상남도"),
    ("50", "제주특별자치도"),
    ("51", "강원특별자치도"),
    ("52", "전북특별자치도"),
)

#: Number of file slots an upload session for ``category`` must collect.
#: ``single_file`` is always 1; ``multi_part`` categories are sido-partitioned.
def expected_file_count(category: SourceCategory) -> int:
    return 1 if category.group_kind == "single_file" else len(SIDO_PARTS)
