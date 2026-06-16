"""Archive structure validator decision logic (T-203b).

Implements the category structure-validation profiles from
``docs/t109-backup-source-upload-management.md`` ("카테고리별 기대 구조").

The design split (doc lines ~970-977, "SHP/DBF partial read") keeps the *pure
decision logic* — given a member manifest, decide pass / warning / failed and
why — fully unit-testable **without GDAL or zip access**. The actual extraction
of a manifest from an archive on disk is a thin, lazily-imported adapter
(:mod:`kortravelgeo.infra.source_member_scan`) so that this module never imports
GDAL and can be exercised with synthetic manifests.

Layer-name lists are REUSED from the loader layer:

* electronic-map 11 master layers → :data:`loaders.juso_map.MASTER_LAYER_NAMES`
* 9 serving layers              → :data:`loaders.shp.polygons_loader.POLYGON_LAYER_NAMES`
* DBF-only road interval layer  → ``polygons_loader.ROAD_INTERVAL_LAYER_NAME``
* zone makarea layer            → ``loaders.sppn_makarea_loader.LAYER_NAME``
* bundle / detail-dong layers   → ``building_shape_bundle`` / ``extra_shape_layers``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from kortravelgeo.core.source_categories import SIDO_PARTS, category_by_code
from kortravelgeo.core.source_layers import (
    ADDRESS_BUNDLE_LAYER,
    BUNDLE_CONNECTION_LAYER,
    BUNDLE_ENTRANCE_LAYER,
    DETAIL_DONG_ENTRANCE_LAYER,
    DETAIL_DONG_POLYGON_LAYER,
    MASTER_LAYER_NAMES,
    POLYGON_LAYER_NAMES,
    ROAD_INTERVAL_LAYER_NAME,
)
from kortravelgeo.core.source_layers import (
    ZONE_MAKAREA_LAYER_NAME as ZONE_MAKAREA_LAYER,
)

#: Bumped whenever the decision logic / profile expectations change so that
#: previously ``passed`` validations can be re-run (doc "validator_version").
VALIDATOR_VERSION = "t127.1"

ValidationOutcome = Literal["passed", "warning", "failed"]

#: 17 sido part keys (doc multi_part coverage uses these as ``part_key``).
SIDO_PART_KEYS: tuple[str, ...] = tuple(code for code, _ in SIDO_PARTS)


# --- manifest model (what the GDAL/zip adapter produces) -------------------


@dataclass(frozen=True)
class ManifestMember:
    """One member observed inside an uploaded archive (a part).

    For SHP layers ``layer_name`` is the layer (e.g. ``TL_SPBD_BULD``) and
    ``suffixes`` is the set of sidecar extensions present (``.shp``/``.shx``/
    ``.dbf``/``.prj``). For TXT members ``member_path`` is the file name.
    """

    member_path: str
    member_kind: str = "file"
    layer_name: str | None = None
    suffixes: frozenset[str] = frozenset()
    detected_yyyymm: str | None = None


@dataclass(frozen=True)
class PartManifest:
    """The members of one uploaded part (a single_file archive, or one sido ZIP)."""

    part_key: str
    members: tuple[ManifestMember, ...] = ()

    def layer_names(self) -> frozenset[str]:
        return frozenset(m.layer_name for m in self.members if m.layer_name)

    def filenames(self) -> tuple[str, ...]:
        return tuple(m.member_path for m in self.members)


@dataclass(frozen=True)
class GroupManifest:
    """All parts of a group (1 part for single_file, up to 17 for multi_part)."""

    category: str
    group_kind: Literal["single_file", "multi_part"]
    parts: tuple[PartManifest, ...] = ()


# --- decision result -------------------------------------------------------


@dataclass(frozen=True)
class PartValidation:
    """Per-part structure decision (``scope='file'`` in source_file_validations)."""

    part_key: str
    outcome: ValidationOutcome
    reasons: tuple[str, ...] = ()
    present_layers: frozenset[str] = frozenset()
    missing_layers: frozenset[str] = frozenset()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class GroupValidation:
    """Group-level structure decision (``scope='group'``).

    ``outcome`` aggregates the parts plus group-wide checks (sido coverage).
    ``coverage`` maps each expected ``part_key`` → ``present|missing|failed`` so
    ``recompute_group_aggregates`` can persist it on
    ``ops.source_file_groups.coverage``.
    """

    category: str
    outcome: ValidationOutcome
    reasons: tuple[str, ...] = ()
    parts: tuple[PartValidation, ...] = ()
    coverage: dict[str, str] = field(default_factory=dict)

    @property
    def validation_state(self) -> str:
        """Map outcome to the ``ops`` ``validation_state`` vocabulary."""
        return self.outcome


# --- profile expectations --------------------------------------------------

#: electronic_map_full requires ALL 11 master layers for *structure* (M1
#: decision, doc line 35/965); the 9 serving layers are a documented subset.
ELECTRONIC_MAP_STRUCTURE_LAYERS: frozenset[str] = frozenset(MASTER_LAYER_NAMES)
ELECTRONIC_MAP_SERVING_LAYERS: frozenset[str] = frozenset(POLYGON_LAYER_NAMES)

#: Layers that are DBF-only (no geometry sample expected) — doc L2 / line 975.
DBF_ONLY_LAYERS: frozenset[str] = frozenset({ROAD_INTERVAL_LAYER_NAME})

#: SHP sidecars a geometry layer must ship (``.prj`` optional, warning only).
REQUIRED_SHP_SUFFIXES: frozenset[str] = frozenset({".shp", ".shx", ".dbf"})
REQUIRED_DBF_SUFFIXES: frozenset[str] = frozenset({".dbf"})


@dataclass(frozen=True)
class LayerProfile:
    """A multi_part SHP profile: required layers per sido ZIP."""

    required_layers: frozenset[str]
    serving_subset: frozenset[str] = frozenset()


@dataclass(frozen=True)
class TextMemberProfile:
    """A single_file / text profile: required filename prefixes per archive.

    Each entry is a ``(prefix, expected_count)`` rule; ``expected_count`` of
    ``None`` means "at least one". Counting matched members lets the 17-per-sido
    text categories (``rnaddrkor_*`` etc.) be checked structurally.
    """

    required_prefixes: tuple[tuple[str, int | None], ...]
    optional_prefixes: tuple[tuple[str, int | None], ...] = ()


@dataclass(frozen=True)
class SingleLayerProfile:
    """A single-file SHP profile whose layer name may include a 기준월 suffix."""

    required_layer_prefixes: tuple[str, ...] = ()
    expected_count: int | None = 1


#: multi_part SHP profiles keyed by category.
LAYER_PROFILES: dict[str, LayerProfile] = {
    "electronic_map_full": LayerProfile(
        required_layers=ELECTRONIC_MAP_STRUCTURE_LAYERS,
        serving_subset=ELECTRONIC_MAP_SERVING_LAYERS,
    ),
    "zone_shape_full": LayerProfile(
        required_layers=frozenset({ZONE_MAKAREA_LAYER}),
    ),
    "roadaddr_building_shape_bundle": LayerProfile(
        required_layers=frozenset(
            {ADDRESS_BUNDLE_LAYER, BUNDLE_ENTRANCE_LAYER, BUNDLE_CONNECTION_LAYER}
        ),
    ),
    "detail_dong_shape_bundle": LayerProfile(
        required_layers=frozenset({DETAIL_DONG_POLYGON_LAYER, DETAIL_DONG_ENTRANCE_LAYER}),
    ),
}

SINGLE_LAYER_PROFILES: dict[str, SingleLayerProfile] = {
    "civil_service_institution_map": SingleLayerProfile(
        required_layer_prefixes=("민원행정기관",),
    ),
}

#: multi_part text profiles (per sido ZIP) keyed by category.
TEXT_PART_PROFILES: dict[str, TextMemberProfile] = {
    "roadaddr_entrance_full": TextMemberProfile(
        required_prefixes=(("RNENTDATA_", None),),
    ),
}

#: single_file text profiles keyed by category. Counts are the nationwide member
#: count expected inside the one archive (17 sido text files, etc.).
SINGLE_FILE_TEXT_PROFILES: dict[str, TextMemberProfile] = {
    "roadname_hangul_full": TextMemberProfile(
        required_prefixes=(("rnaddrkor_", 17), ("jibun_rnaddrkor_", 17)),
    ),
    "locsum_full": TextMemberProfile(
        required_prefixes=(("entrc_", 17),),
    ),
    "navi_full": TextMemberProfile(
        required_prefixes=(("match_build_", 17), ("match_rs_entrc", 1)),
        optional_prefixes=(("match_jibun_", 17),),
    ),
    "detail_address_db_full": TextMemberProfile(
        required_prefixes=(("adrdc_", 17),),
    ),
    "national_point_grid_center": TextMemberProfile(
        required_prefixes=(("SPPN_", 1),),
    ),
    "address_db_full": TextMemberProfile(
        required_prefixes=(
            ("주소_", 17),
            ("부가정보_", 17),
            ("지번_", 17),
            ("개선_도로명코드_", 1),
        ),
    ),
    "building_db_full": TextMemberProfile(
        required_prefixes=(("build_", 17), ("jibun_", 17), ("road_code_total", 1)),
    ),
}

T127_GRID_SHAPE_LAYERS: frozenset[str] = frozenset(
    {
        "TL_SPPN_GRID_100KM",
        "TL_SPPN_GRID_10KM",
        "TL_SPPN_GRID_1KM",
        "TL_SPPN_GRID_100M",
    }
)

LAYER_PROFILES["national_point_grid_shape"] = LayerProfile(
    required_layers=T127_GRID_SHAPE_LAYERS,
)


# --- pure decision functions -----------------------------------------------


def _count_with_prefix(filenames: tuple[str, ...], prefix: str) -> int:
    lower = prefix.lower()
    return sum(1 for name in filenames if _basename(name).lower().startswith(lower))


def _basename(member_path: str) -> str:
    normalized = member_path.replace("\\", "/")
    return normalized.rsplit("/", 1)[-1]


def _validate_text_part(
    part: PartManifest, profile: TextMemberProfile
) -> PartValidation:
    filenames = part.filenames()
    reasons: list[str] = []
    warnings: list[str] = []
    outcome: ValidationOutcome = "passed"
    for prefix, expected in profile.required_prefixes:
        found = _count_with_prefix(filenames, prefix)
        if found == 0:
            reasons.append(f"필수 member 누락: {prefix}*")
            outcome = "failed"
        elif expected is not None and found != expected:
            warnings.append(f"{prefix}* {found}개 (기대 {expected}개)")
            if outcome == "passed":
                outcome = "warning"
    for prefix, _expected in profile.optional_prefixes:
        if _count_with_prefix(filenames, prefix) == 0:
            warnings.append(f"optional member 없음: {prefix}*")
            if outcome == "passed":
                outcome = "warning"
    yyyymm_warning = _detected_yyyymm_warning(part.members)
    if yyyymm_warning is not None:
        warnings.append(yyyymm_warning)
        if outcome == "passed":
            outcome = "warning"
    return PartValidation(
        part_key=part.part_key,
        outcome=outcome,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def _validate_layer_part(part: PartManifest, profile: LayerProfile) -> PartValidation:
    present = part.layer_names()
    missing = profile.required_layers - present
    reasons: list[str] = []
    warnings: list[str] = []
    outcome: ValidationOutcome = "passed"
    if missing:
        reasons.append("필수 layer 누락: " + ", ".join(sorted(missing)))
        outcome = "failed"
    # Sidecar completeness for each present required layer.
    for member in part.members:
        if member.layer_name is None or member.layer_name not in profile.required_layers:
            continue
        needed = (
            REQUIRED_DBF_SUFFIXES
            if member.layer_name in DBF_ONLY_LAYERS
            else REQUIRED_SHP_SUFFIXES
        )
        missing_suffixes = needed - member.suffixes
        if missing_suffixes:
            reasons.append(
                f"{member.layer_name} sidecar 누락: " + ", ".join(sorted(missing_suffixes))
            )
            outcome = "failed"
        if ".prj" not in member.suffixes and member.layer_name not in DBF_ONLY_LAYERS:
            warnings.append(f"{member.layer_name}.prj 없음 (EPSG:5179 가정)")
            if outcome == "passed":
                outcome = "warning"
    yyyymm_warning = _detected_yyyymm_warning(part.members)
    if yyyymm_warning is not None:
        warnings.append(yyyymm_warning)
        if outcome == "passed":
            outcome = "warning"
    return PartValidation(
        part_key=part.part_key,
        outcome=outcome,
        reasons=tuple(reasons),
        present_layers=present & profile.required_layers,
        missing_layers=missing,
        warnings=tuple(warnings),
    )


def _validate_single_layer_part(
    part: PartManifest, profile: SingleLayerProfile
) -> PartValidation:
    layers = tuple(m for m in part.members if m.member_kind == "shp_layer" and m.layer_name)
    reasons: list[str] = []
    warnings: list[str] = []
    outcome: ValidationOutcome = "passed"
    if not layers:
        reasons.append("필수 SHP layer 누락")
        outcome = "failed"
    elif profile.expected_count is not None and len(layers) != profile.expected_count:
        warnings.append(f"SHP layer {len(layers)}개 (기대 {profile.expected_count}개)")
        outcome = "warning"
    for member in layers:
        assert member.layer_name is not None
        if profile.required_layer_prefixes and not any(
            member.layer_name.startswith(prefix) for prefix in profile.required_layer_prefixes
        ):
            warnings.append(
                f"{member.layer_name} layer 이름이 기대 prefix와 다름: "
                + ", ".join(profile.required_layer_prefixes)
            )
            if outcome == "passed":
                outcome = "warning"
        missing_suffixes = REQUIRED_SHP_SUFFIXES - member.suffixes
        if missing_suffixes:
            reasons.append(
                f"{member.layer_name} sidecar 누락: " + ", ".join(sorted(missing_suffixes))
            )
            outcome = "failed"
        if ".prj" not in member.suffixes:
            warnings.append(f"{member.layer_name}.prj 없음 (EPSG:5179 가정)")
            if outcome == "passed":
                outcome = "warning"
    yyyymm_warning = _detected_yyyymm_warning(part.members)
    if yyyymm_warning is not None:
        warnings.append(yyyymm_warning)
        if outcome == "passed":
            outcome = "warning"
    present = frozenset(member.layer_name for member in layers if member.layer_name)
    return PartValidation(
        part_key=part.part_key,
        outcome=outcome,
        reasons=tuple(reasons),
        present_layers=present,
        warnings=tuple(warnings),
    )


def _detected_yyyymm_warning(members: tuple[ManifestMember, ...]) -> str | None:
    values = sorted({member.detected_yyyymm for member in members if member.detected_yyyymm})
    if len(values) <= 1:
        return None
    return "member 기준월 혼재: " + ", ".join(values)


def _expected_part_keys(group_kind: str) -> tuple[str, ...]:
    return SIDO_PART_KEYS if group_kind == "multi_part" else ("archive",)


def validate_group_manifest(manifest: GroupManifest) -> GroupValidation:
    """Pure structure decision for a whole group.

    Returns a :class:`GroupValidation` whose ``outcome`` and ``coverage`` feed
    :func:`recompute_group_aggregates`. Raises nothing for unknown categories;
    they validate as ``warning`` (no profile to check) so registration is not
    blocked but the gap is visible.
    """
    category = category_by_code.get(manifest.category)
    expected_keys = _expected_part_keys(manifest.group_kind)
    by_key = {part.part_key: part for part in manifest.parts}

    layer_profile = LAYER_PROFILES.get(manifest.category)
    single_layer_profile = SINGLE_LAYER_PROFILES.get(manifest.category)
    text_part_profile = TEXT_PART_PROFILES.get(manifest.category)
    single_profile = SINGLE_FILE_TEXT_PROFILES.get(manifest.category)

    part_results: list[PartValidation] = []
    coverage: dict[str, str] = {}
    reasons: list[str] = []
    group_outcome: ValidationOutcome = "passed"

    for key in expected_keys:
        part = by_key.get(key)
        if part is None:
            coverage[key] = "missing"
            group_outcome = "failed"
            continue
        if layer_profile is not None:
            result = _validate_layer_part(part, layer_profile)
        elif single_layer_profile is not None:
            result = _validate_single_layer_part(part, single_layer_profile)
        elif manifest.group_kind == "multi_part" and text_part_profile is not None:
            result = _validate_text_part(part, text_part_profile)
        elif single_profile is not None:
            result = _validate_text_part(part, single_profile)
        else:
            result = PartValidation(
                part_key=key,
                outcome="warning",
                warnings=(f"검증 profile 없음: {manifest.category}",),
            )
        part_results.append(result)
        coverage[key] = "present" if result.outcome != "failed" else "failed"
        group_outcome = _worsen(group_outcome, result.outcome)

    missing_keys = sorted(k for k, v in coverage.items() if v == "missing")
    if missing_keys:
        label = "시도 part" if manifest.group_kind == "multi_part" else "archive"
        reasons.append(f"{label} 누락: " + ", ".join(missing_keys))

    if category is None:
        reasons.append(f"알 수 없는 category: {manifest.category}")
        group_outcome = _worsen(group_outcome, "warning")

    return GroupValidation(
        category=manifest.category,
        outcome=group_outcome,
        reasons=tuple(reasons),
        parts=tuple(part_results),
        coverage=coverage,
    )


def validate_group_coverage(
    *,
    category: str,
    group_kind: str,
    present_part_keys: tuple[str, ...],
) -> GroupValidation:
    """Coverage-only register-time decision.

    Upload registration has not materialized archive members yet, so it can only
    decide whether the expected upload slots arrived. Full SHP/TXT member checks
    stay in :func:`validate_group_manifest`.
    """
    expected_keys = _expected_part_keys(group_kind)
    present = frozenset(present_part_keys)
    coverage = {key: "present" if key in present else "missing" for key in expected_keys}
    missing_keys = sorted(k for k, v in coverage.items() if v == "missing")
    reasons: list[str] = []
    outcome: ValidationOutcome = "passed"
    if missing_keys:
        label = "시도 part" if group_kind == "multi_part" else "archive"
        reasons.append(f"{label} 누락: " + ", ".join(missing_keys))
        outcome = "failed"
    if category_by_code.get(category) is None:
        reasons.append(f"알 수 없는 category: {category}")
        outcome = _worsen(outcome, "warning")
    return GroupValidation(
        category=category,
        outcome=outcome,
        parts=tuple(
            PartValidation(part_key=key, outcome="passed")
            for key in expected_keys
            if key in present
        ),
        coverage=coverage,
        reasons=tuple(reasons),
    )


_OUTCOME_RANK: dict[ValidationOutcome, int] = {"passed": 0, "warning": 1, "failed": 2}


def _worsen(current: ValidationOutcome, candidate: ValidationOutcome) -> ValidationOutcome:
    return current if _OUTCOME_RANK[current] >= _OUTCOME_RANK[candidate] else candidate
