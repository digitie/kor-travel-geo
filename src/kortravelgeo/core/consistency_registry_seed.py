"""Consistency case registry seed authority (T-206).

The DB table ``ops.consistency_case_definitions`` + ``ops.consistency_case_inputs``
is the runtime registry the admin API serves and the UI renders dynamically
(T-209). This module is the **pure** seed source for that registry:

* C1~C10 are derived from :data:`kortravelgeo.core.consistency_definitions.CASE_DEFINITIONS`
  (the t109 seed authority) so the registry never drifts from the in-code C1~C10
  definitions the existing consistency run uses.
* C11~C17 come from the T-118 phase-1 go/no-go confirmed spec table
  (``docs/t118-phase1-go-no-go.md`` lines ~98-106). Each row maps a prototype
  (``loaders/c1X_*.py``) to its registry columns: required/optional inputs,
  default severity, skip policy, and the primary metric description.

Everything here is a plain dataclass over literals — no DB, no clock — so the
seed-coverage / drift regression test runs without a database. The DB upsert
glue lives in ``infra/consistency_registry_service.py``; the prototype-metric
binding (the regression bridge) lives in
``loaders/consistency_run_validation.py``.

C11 ``roadaddr_entrance_full`` is encoded as a **conditional** input
(``required=false`` + ``metadata.conditional_inputs``) per the T-118 review note:
the bundle/electronic ``TL_SPBD_ENTRC`` full-key comparison plus the
``tl_locsum_entrc`` weak-key comparison are the always-on inputs, while the
direct ``roadaddr_entrance_full`` pair is only meaningful when its 기준월 matches
(otherwise the prototype keeps it as a weak ``sig_cd + ent_man_no`` pair, never a
serving promotion). See ``loaders/c11_entrance_sources.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kortravelgeo.core.consistency_definitions import CASE_DEFINITIONS

CaseState = str
Severity = str


@dataclass(frozen=True, slots=True)
class CaseInputSpec:
    """One registry input row (``ops.consistency_case_inputs``)."""

    category: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class CaseRegistryRow:
    """One registry definition row (``ops.consistency_case_definitions``).

    Mirrors the table columns 1:1 so the seed service is a plain column map.
    ``display_order`` orders C1, C2, ... C17 in the UI tab list.
    """

    consistency_case_code: str
    display_order: int
    name: str
    compares: str
    abnormal_criteria: str
    evidence: tuple[str, ...]
    likely_causes: tuple[str, ...]
    decision_guide: str
    threshold: str | None
    default_severity: Severity | None
    state: CaseState
    inputs: tuple[CaseInputSpec, ...] = ()
    skip_policy: dict[str, Any] = field(default_factory=dict)
    sample_schema: dict[str, Any] = field(default_factory=dict)
    introduced_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# --- C1~C10: derived from CASE_DEFINITIONS (the in-code seed authority) -----
# C1~C10 are run by the existing consistency run against the serving MV/tables;
# they have no optional source-archive validation inputs (their data is always
# present in the rebuilt DB), so they carry no ``consistency_case_inputs`` rows.
# default_severity is left NULL (their severity is computed per-run from the
# threshold prose, not a fixed registry default).


def _c1_to_c10_rows() -> tuple[CaseRegistryRow, ...]:
    rows: list[CaseRegistryRow] = []
    for index, case in enumerate(CASE_DEFINITIONS, start=1):
        rows.append(
            CaseRegistryRow(
                consistency_case_code=case.code,
                display_order=index,
                name=case.name,
                compares=case.compares,
                abnormal_criteria=case.abnormal_criteria,
                evidence=case.evidence,
                likely_causes=case.likely_causes,
                decision_guide=case.decision_guide,
                threshold=case.threshold,
                default_severity=None,
                state="enabled",
                inputs=(),
                skip_policy={},
                introduced_by="T-053",
                metadata={"family": "core_serving", "kind": "serving_consistency"},
            )
        )
    return tuple(rows)


# --- C11~C17: from the T-118 confirmed spec table --------------------------
# Each row's inputs/categories, default_severity, skip 조건, 주요 metric come from
# docs/t118-phase1-go-no-go.md (lines ~98-106) reconciled against the actual
# phase-① prototype outputs (loaders/c1X_*.py ``.metrics()``).

_C11_TO_C17_ROWS: tuple[CaseRegistryRow, ...] = (
    CaseRegistryRow(
        consistency_case_code="C11",
        display_order=11,
        name="출입구 원천 간 거리 검증",
        compares=(
            "roadaddr_building_shape_bundle TL_SPBD_ENTRC와 electronic_map_full "
            "TL_SPBD_ENTRC(full key), 그리고 tl_locsum_entrc/tl_roadaddr_entrc "
            "(weak sig_cd+ent_man_no key)"
        ),
        abnormal_criteria=(
            "동일 출입구 key의 좌표 거리가 크거나 key overlap이 낮다. "
            "weak key 비교는 full key 비교와 분리해 본다."
        ),
        evidence=(
            "sig_cd",
            "bul_man_no",
            "ent_man_no",
            "eqb_man_sn",
            "distance_m",
            "source_yyyymm",
        ),
        likely_causes=(
            "기준월 차이",
            "weak key 충돌",
            "좌표 원천 편차",
            "bundle/전자지도 갱신 시차",
        ),
        decision_guide="full key 거리 악화는 reject, weak key 노이즈는 defer + 분리 보고",
        threshold="full key p95 악화 또는 key overlap 저하 WARN",
        default_severity="WARN",
        state="enabled",
        inputs=(
            CaseInputSpec("roadaddr_building_shape_bundle", required=True),
            CaseInputSpec("electronic_map_full", required=True),
            CaseInputSpec("locsum_full", required=True),
            # Conditional: the direct roadaddr entrance pair is only a full
            # comparison when its 기준월 matches; otherwise it stays a weak key
            # pair. Encoded required=false + metadata.conditional_inputs.
            CaseInputSpec("roadaddr_entrance_full", required=False),
        ),
        skip_policy={
            "rule": "bundle 또는 비교 대상이 없으면 해당 pair skip",
            "skipped_when_absent": [
                "roadaddr_building_shape_bundle",
                "electronic_map_full",
                "locsum_full",
            ],
            "optional_absent_is_skip": ["roadaddr_entrance_full"],
        },
        sample_schema={
            "primary_metric": "key overlap, distance p50/p95/max, weak/full key 구분",
            "metric_path": "comparisons.<pair>.distance_m / comparisons.<pair>.key_overlap",
        },
        introduced_by="T-111",
        metadata={
            "family": "augment_validation",
            "prototype_task": "T-111",
            "serving_candidate": "conditional",
            "conditional_inputs": {
                "roadaddr_entrance_full": (
                    "기준월 일치 시에만 full 비교 후보; 불일치 시 weak sig_cd+ent_man_no "
                    "pair로만 사용하고 serving 승격하지 않음 (T-118 review note a)"
                )
            },
        },
    ),
    CaseRegistryRow(
        consistency_case_code="C12",
        display_order=12,
        name="건물 도형 connection line 검증",
        compares="roadaddr_building_shape_bundle TL_SPOT_CNTC와 electronic_map_full TL_SPRD_MANAGE",
        abnormal_criteria="road key overlap이 낮거나 connection line 거리/dangling 비율이 높다.",
        evidence=(
            "rncode_full",
            "rds_man_no",
            "line_distance_m",
            "dangling_ratio",
            "source_yyyymm",
        ),
        likely_causes=("도로 관리선 갱신 시차", "key 매핑 오류", "bundle 누락"),
        decision_guide="key mismatch는 reject, 경미한 dangling은 defer",
        threshold="road key overlap 저하 또는 dangling ratio 상승 WARN",
        default_severity="WARN",
        state="enabled",
        inputs=(
            CaseInputSpec("roadaddr_building_shape_bundle", required=True),
            CaseInputSpec("electronic_map_full", required=True),
        ),
        skip_policy={
            "rule": "bundle 없으면 skip",
            "skipped_when_absent": ["roadaddr_building_shape_bundle", "electronic_map_full"],
        },
        sample_schema={
            "primary_metric": "road key overlap, line distance, dangling ratio",
            "metric_path": "comparisons.<pair>.key_overlap / line_distance",
        },
        introduced_by="T-112",
        metadata={"family": "augment_validation", "prototype_task": "T-112"},
    ),
    CaseRegistryRow(
        consistency_case_code="C13",
        display_order=13,
        name="상세주소 동 containment 검증",
        compares="detail_dong_shape_bundle 동 polygon/point와 detail_address_db_full",
        abnormal_criteria="key overlap이 낮거나 출입구 point가 동 polygon 밖(ST_Covers 실패)이다.",
        evidence=("building_management_no", "bd_mgt_sn", "rncode_full", "covered", "source_yyyymm"),
        likely_causes=("상세주소DB 시차", "동 polygon 누락", "key 매핑 오류"),
        decision_guide="address-matched coverage 악화는 reject, 경계 인접은 defer",
        threshold="ST_Covers coverage 저하 WARN",
        default_severity="WARN",
        state="enabled",
        inputs=(
            CaseInputSpec("detail_dong_shape_bundle", required=True),
            CaseInputSpec("detail_address_db_full", required=True),
        ),
        skip_policy={
            "rule": "둘 중 하나 없으면 skip",
            "skipped_when_absent": ["detail_dong_shape_bundle", "detail_address_db_full"],
        },
        sample_schema={
            "primary_metric": "key overlap, ST_Covers coverage, address-matched coverage",
            "metric_path": "containment / key_overlaps",
        },
        introduced_by="T-113",
        metadata={"family": "augment_validation", "prototype_task": "T-113"},
    ),
    CaseRegistryRow(
        consistency_case_code="C14",
        display_order=14,
        name="국가지점번호 grid/center 검증",
        compares="national_point_grid_shape와 national_point_grid_center",
        abnormal_criteria=(
            "invalid code, bbox/center mismatch, formatter parent mismatch, coverage 부족."
        ),
        evidence=("grid_code", "bbox", "center", "formatter_parent", "source_yyyymm"),
        likely_causes=("parser/formatter 결함", "grid 갱신 시차", "center 파일 누락"),
        decision_guide="formatter parent mismatch는 reject, coverage 결손은 defer",
        threshold="invalid/mismatch 1건 이상 WARN",
        default_severity="WARN",
        state="enabled",
        inputs=(
            CaseInputSpec("national_point_grid_shape", required=True),
            CaseInputSpec("national_point_grid_center", required=True),
            CaseInputSpec("sppn_makarea", required=False),
        ),
        skip_policy={
            "rule": "둘 다 없으면 skip",
            "skipped_when_absent": [
                "national_point_grid_shape",
                "national_point_grid_center",
            ],
            "optional_absent_is_skip": ["sppn_makarea"],
        },
        sample_schema={
            "primary_metric": (
                "invalid code, bbox/center mismatch, formatter parent mismatch, coverage"
            ),
            "metric_path": "layers / center_file / coverage",
        },
        introduced_by="T-114",
        metadata={"family": "augment_validation", "prototype_task": "T-114"},
    ),
    CaseRegistryRow(
        consistency_case_code="C15",
        display_order=15,
        name="민원행정기관 POI 주소 거리 검증",
        compares="civil_service_institution_map 도로주소 geocode 결과와 기관 SHP point",
        abnormal_criteria="parse/geocode 실패가 많거나 geocode 결과와 기관 point 거리가 outlier다.",
        evidence=(
            "institution_address",
            "parsed_ratio",
            "match_ratio",
            "distance_m",
            "source_yyyymm",
        ),
        likely_causes=("주소 문자열 품질", "기관 좌표 이상치", "geocoder 미스매치"),
        decision_guide="실제 좌표 이상이면 approve+근거, 파싱/매핑 결함은 reject",
        threshold="outlier ratio 상승 또는 match ratio 저하 WARN",
        default_severity="WARN",
        state="enabled",
        inputs=(
            CaseInputSpec("civil_service_institution_map", required=True),
            # The geocoder result comes from the active serving MV, not an
            # uploaded archive, so it is not a source-archive integrity input.
        ),
        skip_policy={
            "rule": "원천 없으면 skip",
            "skipped_when_absent": ["civil_service_institution_map"],
            "requires_active_geocoder": True,
        },
        sample_schema={
            "primary_metric": "parse/geocode missing, distance p50/p95/max, outlier sample",
            "metric_path": "geocode_distance_m",
        },
        introduced_by="T-115",
        metadata={"family": "augment_validation", "prototype_task": "T-115"},
    ),
    CaseRegistryRow(
        consistency_case_code="C16",
        display_order=16,
        name="주소DB/건물DB row·key drift 검증",
        compares="address_db_full와 building_db_full의 distinct key/row",
        abnormal_criteria="distinct key overlap이 낮거나 left/right-only가 많다.",
        evidence=("distinct_key", "left_only", "right_only", "staging_row_count", "source_yyyymm"),
        likely_causes=("기준월 차이", "natural key 누락", "원천 row drift"),
        decision_guide="확인된 시차는 defer, key 누락/체계 오류는 reject",
        threshold="distinct key overlap 저하 WARN",
        default_severity="WARN",
        state="enabled",
        inputs=(
            CaseInputSpec("address_db_full", required=True),
            CaseInputSpec("building_db_full", required=True),
        ),
        skip_policy={
            "rule": "해당 자료 없으면 skip",
            "skipped_when_absent": ["address_db_full", "building_db_full"],
        },
        sample_schema={
            "primary_metric": "distinct key overlap, left/right-only sample, staging row count",
            "metric_path": "comparisons.<pair>.key_overlap",
        },
        introduced_by="T-116",
        metadata={"family": "augment_validation", "prototype_task": "T-116"},
    ),
    CaseRegistryRow(
        consistency_case_code="C17",
        display_order=17,
        name="내비 지번 member coverage 검증",
        compares="navi_full match_jibun_*.txt member와 tl_juso_parcel_link",
        abnormal_criteria="bd_mgt_sn+pnu / pnu+road key coverage가 낮다.",
        evidence=("bd_mgt_sn", "pnu", "rncode_full", "left_only", "source_yyyymm"),
        likely_causes=("navi 갱신 시차", "parcel link 누락", "key 해소 실패"),
        decision_guide="coverage 결손이 시차면 defer, key 해소 결함은 reject",
        threshold="coverage 저하 WARN",
        default_severity="WARN",
        state="enabled",
        inputs=(
            # match_jibun is an optional member inside navi_full, not its own
            # category; encode it as the member-flagged category navi_full.match_jibun.
            CaseInputSpec("navi_full.match_jibun", required=True),
            CaseInputSpec("tl_juso_parcel_link", required=True),
        ),
        skip_policy={
            "rule": "match_jibun_* member 없으면 skipped",
            "skipped_when_absent": ["navi_full.match_jibun", "tl_juso_parcel_link"],
            "member_flag": "navi_full.match_jibun",
        },
        sample_schema={
            "primary_metric": "bd_mgt_sn+pnu, pnu+road key coverage",
            "metric_path": "comparisons.<pair>.key_overlap",
        },
        introduced_by="T-117",
        metadata={"family": "augment_validation", "prototype_task": "T-117"},
    ),
)


def consistency_registry_seed_rows() -> tuple[CaseRegistryRow, ...]:
    """The full C1~C17 registry seed (C1~C10 derived + C11~C17 confirmed)."""
    return (*_c1_to_c10_rows(), *_C11_TO_C17_ROWS)


REGISTRY_SEED_ROWS: tuple[CaseRegistryRow, ...] = consistency_registry_seed_rows()
REGISTRY_SEED_BY_CODE: dict[str, CaseRegistryRow] = {
    row.consistency_case_code: row for row in REGISTRY_SEED_ROWS
}
