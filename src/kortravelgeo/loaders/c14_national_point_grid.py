"""C14 national point-number grid/center validation harness."""

from __future__ import annotations

import struct
import zipfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from kortravelgeo.core.sppn import (
    GRID_LETTERS,
    GRID_SIZE_M,
    X_ORIGIN_5179,
    Y_ORIGIN_5179,
    format_national_point_number_from_5179,
)
from kortravelgeo.dto.common import Point
from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders.augment_harness import (
    AugmentGroupPayload,
    AugmentGroupResult,
    AugmentReport,
    ShapeFeature,
    ShapeGeometry,
    ShapeKind,
)
from kortravelgeo.loaders.shape_dbf import DbfLayout, parse_dbf_header, zip_member

C14_GRID_SHAPE_SOURCE_KEY = "national_point_grid_shape"
C14_GRID_CENTER_SOURCE_KEY = "national_point_grid_center"


@dataclass(frozen=True, slots=True)
class GridLayerSpec:
    layer_name: str
    key_field: str
    resolution_m: int
    digits_per_axis: int


GRID_LAYER_SPECS: tuple[GridLayerSpec, ...] = (
    GridLayerSpec("TL_SPPN_GRID_100KM", "SPO_100KM", 100_000, 0),
    GridLayerSpec("TL_SPPN_GRID_10KM", "SPO_10KM", 10_000, 1),
    GridLayerSpec("TL_SPPN_GRID_1KM", "SPO_1KM", 1_000, 2),
    GridLayerSpec("TL_SPPN_GRID_100M", "SPO_100M", 100, 3),
)
GRID_LAYER_BY_NAME: Mapping[str, GridLayerSpec] = {
    spec.layer_name: spec for spec in GRID_LAYER_SPECS
}
RESOLUTION_BY_DIGITS_PER_AXIS: Mapping[int, int] = {
    spec.digits_per_axis: spec.resolution_m for spec in GRID_LAYER_SPECS
}


@dataclass(frozen=True, slots=True)
class GridCode:
    text: str
    x_letter: str
    y_letter: str
    digits_per_axis: int
    x_digits: str
    y_digits: str
    resolution_m: int
    min_x: float
    min_y: float

    @property
    def bbox_5179(self) -> tuple[float, float, float, float]:
        return (
            self.min_x,
            self.min_y,
            self.min_x + self.resolution_m,
            self.min_y + self.resolution_m,
        )

    @property
    def center_5179(self) -> Point:
        half = self.resolution_m / 2
        return Point(x=self.min_x + half, y=self.min_y + half)


@dataclass(frozen=True, slots=True)
class CenterRow:
    source_member: str
    line_number: int
    code_text: str
    point_5179: Point


@dataclass(frozen=True, slots=True)
class GridLayerValidation:
    layer_name: str
    key_field: str
    resolution_m: int
    digits_per_axis: int
    row_count: int
    checked_count: int
    limited: bool
    invalid_code_count: int
    bbox_mismatch_count: int
    formatter_parent_mismatch_count: int
    sample: tuple[Mapping[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class CenterFileValidation:
    member_name: str
    row_count: int
    checked_count: int
    limited: bool
    count_by_resolution_m: Mapping[int, int]
    invalid_row_count: int
    center_mismatch_count: int
    formatter_parent_mismatch_count: int
    sample: tuple[Mapping[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class GridCoverageItem:
    resolution_m: int
    shape_rows: int
    center_rows: int

    @property
    def row_count_delta(self) -> int:
        return self.center_rows - self.shape_rows

    @property
    def row_count_matches(self) -> bool:
        return self.row_count_delta == 0


@dataclass(frozen=True, slots=True)
class GridCoverageValidation:
    items: tuple[GridCoverageItem, ...]

    @property
    def total_shape_rows(self) -> int:
        return sum(item.shape_rows for item in self.items)

    @property
    def total_center_rows(self) -> int:
        return sum(item.center_rows for item in self.items)

    @property
    def all_row_counts_match(self) -> bool:
        return all(item.row_count_matches for item in self.items)


@dataclass(frozen=True, slots=True)
class C14NationalPointGridComparison:
    grid_shape_zip: str
    grid_center_zip: str
    source_yyyymm: str | None
    layer_validations: tuple[GridLayerValidation, ...]
    center_validation: CenterFileValidation
    coverage: GridCoverageValidation

    def metrics(self) -> dict[str, object]:
        limited = self.center_validation.limited or any(
            layer.limited for layer in self.layer_validations
        )
        return {
            "grid_shape_zip": self.grid_shape_zip,
            "grid_center_zip": self.grid_center_zip,
            "source_yyyymm": self.source_yyyymm,
            "layers": {
                layer.layer_name: _layer_metrics(layer) for layer in self.layer_validations
            },
            "center_file": _center_metrics(self.center_validation),
            "coverage": _coverage_metrics(self.coverage),
            "coverage_count_basis": "limited_sample" if limited else "full_stream",
            "notes": (
                "national_point_grid_shape and national_point_grid_center are "
                "validation/overlay sources. They verify parser/formatter parent-grid "
                "consistency and grid coverage, but they are not a 10m coordinate "
                "accuracy upgrade source."
            ),
            "serving_promotion": False,
        }

    def sample(self) -> tuple[Mapping[str, object], ...]:
        rows: list[Mapping[str, object]] = []
        for layer in self.layer_validations:
            for row in layer.sample:
                rows.append({"sample_kind": "grid_shape", "layer_name": layer.layer_name, **row})
        for row in self.center_validation.sample:
            rows.append({"sample_kind": "grid_center", **row})
        return tuple(rows)

    def to_payload(self) -> AugmentGroupPayload:
        return AugmentGroupPayload(
            metrics=self.metrics(),
            sample=self.sample(),
            source_yyyymm=self.source_yyyymm,
        )


def parse_grid_code(
    value: str,
    *,
    expected_digits_per_axis: int | None = None,
) -> GridCode | None:
    normalized = "".join(value.strip().replace("-", " ").split())
    if len(normalized) < 2:
        return None
    x_letter = normalized[0]
    y_letter = normalized[1]
    if x_letter not in GRID_LETTERS or y_letter not in GRID_LETTERS:
        return None
    digits = normalized[2:]
    if len(digits) not in {0, 2, 4, 6} or (digits and not digits.isdigit()):
        return None
    digits_per_axis = len(digits) // 2
    if expected_digits_per_axis is not None and digits_per_axis != expected_digits_per_axis:
        return None
    resolution_m = RESOLUTION_BY_DIGITS_PER_AXIS.get(digits_per_axis)
    if resolution_m is None:
        return None
    x_digits = digits[:digits_per_axis]
    y_digits = digits[digits_per_axis:]
    x_index = GRID_LETTERS.index(x_letter)
    y_index = GRID_LETTERS.index(y_letter)
    x_cell = int(x_digits) if x_digits else 0
    y_cell = int(y_digits) if y_digits else 0
    min_x = X_ORIGIN_5179 + x_index * GRID_SIZE_M + x_cell * resolution_m
    min_y = Y_ORIGIN_5179 + y_index * GRID_SIZE_M + y_cell * resolution_m
    return GridCode(
        text=f"{x_letter}{y_letter}{x_digits}{y_digits}",
        x_letter=x_letter,
        y_letter=y_letter,
        digits_per_axis=digits_per_axis,
        x_digits=x_digits,
        y_digits=y_digits,
        resolution_m=resolution_m,
        min_x=float(min_x),
        min_y=float(min_y),
    )


def parent_grid_code_from_point(point: Point, digits_per_axis: int) -> str | None:
    formatted = format_national_point_number_from_5179(point)
    if formatted is None:
        return None
    if digits_per_axis == 0:
        return f"{formatted.x_letter}{formatted.y_letter}"
    return (
        f"{formatted.x_letter}{formatted.y_letter}"
        f"{formatted.x_digits[:digits_per_axis]}"
        f"{formatted.y_digits[:digits_per_axis]}"
    )


def iter_center_rows(
    grid_center_zip: Path | str,
    *,
    member_name: str | None = None,
    encoding: str = "cp949",
) -> Iterator[CenterRow]:
    archive = Path(grid_center_zip)
    with zipfile.ZipFile(archive) as zip_file:
        member = _center_member(zip_file, member_name)
        with zip_file.open(member) as file:
            for line_number, raw_line in enumerate(file, start=1):
                line = raw_line.decode(encoding).rstrip("\r\n")
                if not line:
                    continue
                columns = line.split("|")
                if len(columns) != 3:
                    msg = f"{member}:{line_number} expected 3 columns, got {len(columns)}"
                    raise LoaderError(msg)
                try:
                    x = float(columns[1])
                    y = float(columns[2])
                except ValueError as exc:
                    msg = f"{member}:{line_number} invalid center coordinate"
                    raise LoaderError(msg) from exc
                yield CenterRow(
                    source_member=member,
                    line_number=line_number,
                    code_text=columns[0],
                    point_5179=Point(x=x, y=y),
                )


def validate_grid_layer_features(
    spec: GridLayerSpec,
    features: Iterable[ShapeFeature],
    *,
    total_rows: int | None = None,
    row_limit: int | None = None,
    sample_limit: int = 20,
    tolerance_m: float = 0.001,
) -> GridLayerValidation:
    checked_count = 0
    invalid_code_count = 0
    bbox_mismatch_count = 0
    formatter_parent_mismatch_count = 0
    samples: list[Mapping[str, object]] = []

    for feature in features:
        if row_limit is not None and checked_count >= row_limit:
            break
        checked_count += 1
        raw_code = feature.attributes.get(spec.key_field)
        code = parse_grid_code(
            raw_code or "",
            expected_digits_per_axis=spec.digits_per_axis,
        )
        if code is None:
            invalid_code_count += 1
            _append_sample(
                samples,
                sample_limit,
                issue="invalid_code",
                record_number=feature.record_number,
                code=raw_code,
            )
            continue

        expected_bbox = code.bbox_5179
        actual_bbox = feature.geometry.bbox
        if actual_bbox is None or not _bbox_close(actual_bbox, expected_bbox, tolerance_m):
            bbox_mismatch_count += 1
            _append_sample(
                samples,
                sample_limit,
                issue="bbox_mismatch",
                record_number=feature.record_number,
                code=code.text,
                expected_bbox=expected_bbox,
                actual_bbox=actual_bbox,
            )

        parent = parent_grid_code_from_point(code.center_5179, spec.digits_per_axis)
        if parent != code.text:
            formatter_parent_mismatch_count += 1
            _append_sample(
                samples,
                sample_limit,
                issue="formatter_parent_mismatch",
                record_number=feature.record_number,
                code=code.text,
                formatter_parent=parent,
            )

    row_count = total_rows if total_rows is not None else checked_count
    if row_limit is None:
        limited = False
    elif total_rows is not None:
        limited = checked_count < row_count
    else:
        limited = checked_count >= row_limit
    return GridLayerValidation(
        layer_name=spec.layer_name,
        key_field=spec.key_field,
        resolution_m=spec.resolution_m,
        digits_per_axis=spec.digits_per_axis,
        row_count=row_count,
        checked_count=checked_count,
        limited=limited,
        invalid_code_count=invalid_code_count,
        bbox_mismatch_count=bbox_mismatch_count,
        formatter_parent_mismatch_count=formatter_parent_mismatch_count,
        sample=tuple(samples),
    )


def validate_grid_shape_zip(
    grid_shape_zip: Path | str,
    *,
    row_limit_per_layer: int | None = None,
    sample_limit: int = 20,
) -> tuple[GridLayerValidation, ...]:
    path = Path(grid_shape_zip)
    validations: list[GridLayerValidation] = []
    with zipfile.ZipFile(path) as zip_file:
        row_counts = {
            spec.layer_name: _zip_grid_layer_row_count(zip_file, spec) for spec in GRID_LAYER_SPECS
        }
    for spec in GRID_LAYER_SPECS:
        validations.append(
            validate_grid_layer_features(
                spec,
                iter_grid_zip_shape_features(path, spec.layer_name, fields=(spec.key_field,)),
                total_rows=row_counts[spec.layer_name],
                row_limit=row_limit_per_layer,
                sample_limit=sample_limit,
            )
        )
    return tuple(validations)


def validate_center_rows(
    rows: Iterable[CenterRow],
    *,
    row_limit: int | None = None,
    member_name: str = "<stream>",
    sample_limit: int = 20,
    tolerance_m: float = 0.001,
) -> CenterFileValidation:
    row_count = 0
    checked_count = 0
    counts: dict[int, int] = {spec.resolution_m: 0 for spec in GRID_LAYER_SPECS}
    invalid_row_count = 0
    center_mismatch_count = 0
    formatter_parent_mismatch_count = 0
    samples: list[Mapping[str, object]] = []

    for row in rows:
        if row_limit is not None and checked_count >= row_limit:
            break
        checked_count += 1
        row_count += 1
        code = parse_grid_code(row.code_text)
        if code is None:
            invalid_row_count += 1
            _append_sample(
                samples,
                sample_limit,
                issue="invalid_code",
                line_number=row.line_number,
                code=row.code_text,
            )
            continue
        counts[code.resolution_m] = counts.get(code.resolution_m, 0) + 1
        expected = code.center_5179
        if (
            abs(row.point_5179.x - expected.x) > tolerance_m
            or abs(row.point_5179.y - expected.y) > tolerance_m
        ):
            center_mismatch_count += 1
            _append_sample(
                samples,
                sample_limit,
                issue="center_mismatch",
                line_number=row.line_number,
                code=code.text,
                expected_x=expected.x,
                expected_y=expected.y,
                actual_x=row.point_5179.x,
                actual_y=row.point_5179.y,
            )
        parent = parent_grid_code_from_point(row.point_5179, code.digits_per_axis)
        if parent != code.text:
            formatter_parent_mismatch_count += 1
            _append_sample(
                samples,
                sample_limit,
                issue="formatter_parent_mismatch",
                line_number=row.line_number,
                code=code.text,
                formatter_parent=parent,
            )

    limited = row_limit is not None and checked_count >= row_limit
    return CenterFileValidation(
        member_name=member_name,
        row_count=row_count,
        checked_count=checked_count,
        limited=limited,
        count_by_resolution_m=dict(counts),
        invalid_row_count=invalid_row_count,
        center_mismatch_count=center_mismatch_count,
        formatter_parent_mismatch_count=formatter_parent_mismatch_count,
        sample=tuple(samples),
    )


def validate_center_zip(
    grid_center_zip: Path | str,
    *,
    member_name: str | None = None,
    row_limit: int | None = None,
    sample_limit: int = 20,
) -> CenterFileValidation:
    path = Path(grid_center_zip)
    with zipfile.ZipFile(path) as zip_file:
        member = _center_member(zip_file, member_name)
    return validate_center_rows(
        iter_center_rows(path, member_name=member),
        row_limit=row_limit,
        member_name=member,
        sample_limit=sample_limit,
    )


def measure_count_coverage(
    layer_validations: Sequence[GridLayerValidation],
    center_validation: CenterFileValidation,
) -> GridCoverageValidation:
    by_resolution = {layer.resolution_m: layer.row_count for layer in layer_validations}
    return GridCoverageValidation(
        items=tuple(
            GridCoverageItem(
                resolution_m=spec.resolution_m,
                shape_rows=by_resolution.get(spec.resolution_m, 0),
                center_rows=int(center_validation.count_by_resolution_m.get(spec.resolution_m, 0)),
            )
            for spec in GRID_LAYER_SPECS
        )
    )


def compare_c14_national_point_grid(
    grid_shape_zip: Path | str,
    grid_center_zip: Path | str,
    *,
    source_yyyymm: str | None = None,
    row_limit_per_layer: int | None = None,
    center_row_limit: int | None = None,
    sample_limit: int = 20,
) -> C14NationalPointGridComparison:
    shape_path = Path(grid_shape_zip)
    center_path = Path(grid_center_zip)
    layer_validations = validate_grid_shape_zip(
        shape_path,
        row_limit_per_layer=row_limit_per_layer,
        sample_limit=sample_limit,
    )
    center_validation = validate_center_zip(
        center_path,
        row_limit=center_row_limit,
        sample_limit=sample_limit,
    )
    coverage = measure_count_coverage(layer_validations, center_validation)
    return C14NationalPointGridComparison(
        grid_shape_zip=str(shape_path),
        grid_center_zip=str(center_path),
        source_yyyymm=source_yyyymm,
        layer_validations=layer_validations,
        center_validation=center_validation,
        coverage=coverage,
    )


def build_c14_national_point_grid_report(
    grid_shape_zip: Path | str,
    grid_center_zip: Path | str,
    *,
    source_yyyymm: str | None = None,
    row_limit_per_layer: int | None = None,
    center_row_limit: int | None = None,
    sample_limit: int = 20,
    generated_at: datetime | None = None,
) -> AugmentReport:
    try:
        comparison = compare_c14_national_point_grid(
            grid_shape_zip,
            grid_center_zip,
            source_yyyymm=source_yyyymm,
            row_limit_per_layer=row_limit_per_layer,
            center_row_limit=center_row_limit,
            sample_limit=sample_limit,
        )
    except Exception as exc:
        result = AugmentGroupResult(
            group_id="national",
            sido_name="전국",
            status="failed",
            metrics={},
            error=f"{type(exc).__name__}: {exc}",
            source_yyyymm=source_yyyymm,
        )
    else:
        payload = comparison.to_payload()
        result = AugmentGroupResult(
            group_id="national",
            sido_name="전국",
            status="used",
            metrics=payload.metrics,
            sample=payload.sample,
            source_yyyymm=payload.source_yyyymm,
        )
    return AugmentReport(
        task_id="T-114",
        title="C14 national point grid/center validation",
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        groups=(result,),
        source_yyyymm=source_yyyymm,
    )


def _layer_metrics(value: GridLayerValidation) -> dict[str, object]:
    return {
        "key_field": value.key_field,
        "resolution_m": value.resolution_m,
        "digits_per_axis": value.digits_per_axis,
        "row_count": value.row_count,
        "checked_count": value.checked_count,
        "limited": value.limited,
        "invalid_code_count": value.invalid_code_count,
        "bbox_mismatch_count": value.bbox_mismatch_count,
        "formatter_parent_mismatch_count": value.formatter_parent_mismatch_count,
    }


def _center_metrics(value: CenterFileValidation) -> dict[str, object]:
    return {
        "member_name": value.member_name,
        "row_count": value.row_count,
        "checked_count": value.checked_count,
        "limited": value.limited,
        "count_by_resolution_m": dict(value.count_by_resolution_m),
        "invalid_row_count": value.invalid_row_count,
        "center_mismatch_count": value.center_mismatch_count,
        "formatter_parent_mismatch_count": value.formatter_parent_mismatch_count,
    }


def _coverage_metrics(value: GridCoverageValidation) -> dict[str, object]:
    return {
        "total_shape_rows": value.total_shape_rows,
        "total_center_rows": value.total_center_rows,
        "all_row_counts_match": value.all_row_counts_match,
        "by_resolution_m": {
            item.resolution_m: {
                "shape_rows": item.shape_rows,
                "center_rows": item.center_rows,
                "row_count_delta": item.row_count_delta,
                "row_count_matches": item.row_count_matches,
            }
            for item in value.items
        },
    }


def _center_member(zip_file: zipfile.ZipFile, member_name: str | None) -> str:
    if member_name is not None:
        names = set(zip_file.namelist())
        if member_name not in names:
            msg = f"missing national point center member: {member_name}"
            raise LoaderError(msg)
        return member_name
    candidates = sorted(name for name in zip_file.namelist() if name.upper().endswith(".TXT"))
    if len(candidates) != 1:
        msg = f"expected one national point center TXT, found {len(candidates)}"
        raise LoaderError(msg)
    return candidates[0]


def iter_grid_zip_shape_features(
    zip_path: Path | str,
    layer_name: str,
    *,
    fields: Sequence[str],
    encoding: str = "cp949",
) -> Iterator[ShapeFeature]:
    """Stream a grid SHP/DBF layer from a ZIP without inflating members in memory."""

    archive = Path(zip_path)
    with zipfile.ZipFile(archive) as zip_file:
        shp_member = zip_member(zip_file, layer_name, ".shp")
        dbf_member = zip_member(zip_file, layer_name, ".dbf")
        with zip_file.open(shp_member) as shp_file, zip_file.open(dbf_member) as dbf_file:
            _read_shp_header(shp_file, source_name=f"{archive}:{layer_name}.shp")
            layout = _read_dbf_layout(dbf_file, source_name=f"{archive}:{layer_name}.dbf")
            offsets = _dbf_offsets(layout, fields)
            for index in range(layout.row_count):
                geometry = _read_shp_record(
                    shp_file,
                    source_name=f"{archive}:{layer_name}.shp",
                )
                record = _read_exact(
                    dbf_file,
                    layout.record_length,
                    source_name=f"{archive}:{layer_name}.dbf",
                    detail=f"record {index + 1}",
                )
                if record[:1] == b"*":
                    continue
                yield ShapeFeature(
                    record_number=geometry.record_number,
                    attributes={
                        field: _decode_dbf_value(
                            record[offset : offset + length],
                            encoding=encoding,
                            source_name=f"{archive}:{layer_name}.dbf",
                            field_name=field,
                            record_number=geometry.record_number,
                        )
                        for field, (offset, length) in offsets.items()
                    },
                    geometry=geometry,
                )


def _zip_grid_layer_row_count(zip_file: zipfile.ZipFile, spec: GridLayerSpec) -> int:
    with zip_file.open(zip_member(zip_file, spec.layer_name, ".dbf")) as dbf_file:
        layout = _read_dbf_layout(dbf_file, source_name=f"{spec.layer_name}.dbf")
    _dbf_offsets(layout, (spec.key_field,))
    return layout.row_count


def _read_shp_header(file: IO[bytes], *, source_name: str) -> None:
    header = _read_exact(file, 100, source_name=source_name, detail="header")
    file_code = struct.unpack(">i", header[0:4])[0]
    if file_code != 9994:
        msg = f"invalid SHP file code for {source_name}: {file_code}"
        raise LoaderError(msg)


def _read_shp_record(file: IO[bytes], *, source_name: str) -> ShapeGeometry:
    header = _read_exact(file, 8, source_name=source_name, detail="record header")
    record_number, content_words = struct.unpack(">2i", header)
    content_length = content_words * 2
    content = _read_exact(
        file,
        content_length,
        source_name=source_name,
        detail=f"record {record_number}",
    )
    if len(content) < 4:
        msg = f"truncated SHP record {record_number} in {source_name}"
        raise LoaderError(msg)
    shape_type = struct.unpack("<i", content[:4])[0]
    if shape_type == 0:
        return ShapeGeometry(record_number, "Null", None, None, 0, 0)
    if shape_type == 1:
        if len(content) < 20:
            msg = f"truncated point SHP record {record_number} in {source_name}"
            raise LoaderError(msg)
        x, y = struct.unpack("<2d", content[4:20])
        return ShapeGeometry(record_number, "Point", None, (x, y, x, y), 1, 1)
    if shape_type in {3, 5}:
        if len(content) < 44:
            msg = f"truncated SHP record {record_number} in {source_name}"
            raise LoaderError(msg)
        min_x, min_y, max_x, max_y = struct.unpack("<4d", content[4:36])
        part_count, point_count = struct.unpack("<2i", content[36:44])
        shape_kind: ShapeKind = "PolyLine" if shape_type == 3 else "Polygon"
        return ShapeGeometry(
            record_number,
            shape_kind,
            None,
            (min_x, min_y, max_x, max_y),
            part_count,
            point_count,
        )
    msg = f"unsupported SHP shape type {shape_type} in {source_name} record {record_number}"
    raise LoaderError(msg)


def _read_dbf_layout(file: IO[bytes], *, source_name: str) -> DbfLayout:
    header = _read_exact(file, 32, source_name=source_name, detail="header")
    header_length = struct.unpack("<H", header[8:10])[0]
    if header_length < 32:
        msg = f"invalid DBF header length in {source_name}: {header_length}"
        raise LoaderError(msg)
    if header_length > 32:
        header += _read_exact(
            file,
            header_length - 32,
            source_name=source_name,
            detail="field descriptors",
        )
    return parse_dbf_header(header)


def _dbf_offsets(layout: DbfLayout, fields: Sequence[str]) -> dict[str, tuple[int, int]]:
    by_name = {field.name: (field.offset, field.length) for field in layout.fields}
    missing = [field for field in fields if field not in by_name]
    if missing:
        msg = "missing DBF field(s): " + ", ".join(missing)
        raise LoaderError(msg)
    return {field: by_name[field] for field in fields}


def _decode_dbf_value(
    raw: bytes,
    *,
    encoding: str,
    source_name: str,
    field_name: str,
    record_number: int,
) -> str | None:
    try:
        value = raw.rstrip(b"\x00").decode(encoding).strip()
    except UnicodeDecodeError as exc:
        msg = f"{source_name}:{record_number} field {field_name} failed {encoding} decode: {exc}"
        raise LoaderError(msg) from exc
    return value or None


def _read_exact(
    file: IO[bytes],
    size: int,
    *,
    source_name: str,
    detail: str,
) -> bytes:
    data = file.read(size)
    if len(data) != size:
        msg = f"truncated {detail} in {source_name}"
        raise LoaderError(msg)
    return data


def _bbox_close(
    actual: tuple[float, float, float, float],
    expected: tuple[float, float, float, float],
    tolerance_m: float,
) -> bool:
    return all(
        abs(left - right) <= tolerance_m for left, right in zip(actual, expected, strict=True)
    )


def _append_sample(
    samples: list[Mapping[str, object]],
    sample_limit: int,
    **row: object,
) -> None:
    if len(samples) < sample_limit:
        samples.append(row)
