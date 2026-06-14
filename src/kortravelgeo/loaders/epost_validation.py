"""Shared validation helpers for epost postal auxiliary files."""

from __future__ import annotations

import csv
import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from kortravelgeo.exceptions import LoaderError

PostalDatasetKind = Literal["pobox", "bulk"]
PostalValidationSeverity = Literal["passed", "failed"]

EPOST_TEXT_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "cp949")
ZIP_NO_RE = re.compile(r"^\d{5}$")
INTEGER_RE = re.compile(r"^\d+$")

ZIP_NO_ALIASES = ("zip_no", "우편번호")
BD_MGT_SN_ALIASES = ("bd_mgt_sn", "건물관리번호")
POBOX_KIND_ALIASES = ("pobox_kind", "구분")
POBOX_NAME_ALIASES = ("pobox_name", "사서함명")
POBOX_NO_MN_ALIASES = ("pobox_no_mn", "사서함본번")
POBOX_NO_SL_ALIASES = ("pobox_no_sl", "사서함부번")
BULK_NAME_ALIASES = ("bulk_name", "다량배달처명", "기관명")
DETAIL_ALIASES = ("detail", "상세주소")

POBOX_KIND_VALUES = {"PO", "PG"}


@dataclass(frozen=True, slots=True)
class PostalValidationIssue:
    code: str
    message: str
    row_number: int | None = None
    field: str | None = None
    value: str | None = None


@dataclass(frozen=True, slots=True)
class PostalValidationSummary:
    kind: PostalDatasetKind
    path: str
    encoding: str | None
    header: tuple[str, ...]
    row_count: int
    valid_row_count: int
    issue_count: int
    missing_required_count: int
    invalid_zip_count: int
    invalid_kind_count: int
    invalid_integer_count: int
    duplicate_key_count: int
    duplicate_samples: tuple[str, ...]
    issues: tuple[PostalValidationIssue, ...]
    severity: PostalValidationSeverity

    @property
    def passed(self) -> bool:
        return self.severity == "passed"


@dataclass(frozen=True, slots=True)
class _RequiredField:
    field: str
    aliases: tuple[str, ...]


def detect_epost_text_encoding(path: Path | str) -> str:
    """Detect the text encoding used by an epost pipe-delimited text file."""

    sample = Path(path).read_bytes()[:64 * 1024]
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    for encoding in EPOST_TEXT_ENCODINGS:
        try:
            sample.decode(encoding)
        except UnicodeDecodeError:
            continue
        return encoding
    msg = f"epost text file is neither UTF-8 nor CP949: {path}"
    raise LoaderError(msg)


def iter_epost_dict_rows(path: Path | str) -> Iterator[dict[str, str]]:
    """Yield normalized CSV rows from an epost text file."""

    source = Path(path)
    encoding = detect_epost_text_encoding(source)
    with source.open("r", encoding=encoding, newline="") as file:
        reader = csv.DictReader(file, delimiter="|")
        if reader.fieldnames is None:
            return
        reader.fieldnames = [_normalize_field_name(field) for field in reader.fieldnames]
        for row in reader:
            yield _normalize_row(row)


def epost_row_value(row: Mapping[str, str], aliases: Iterable[str]) -> str | None:
    for alias in aliases:
        value = row.get(alias)
        if value is not None and value.strip():
            return value.strip()
    return None


def normalize_pobox_kind(value: str | None) -> Literal["PO", "PG"] | None:
    if value is None:
        return "PO"
    normalized = value.strip().upper()
    if normalized == "PO":
        return "PO"
    if normalized == "PG":
        return "PG"
    return None


def validate_pobox_file(path: Path | str, *, max_issues: int = 50) -> PostalValidationSummary:
    return _validate_postal_file(
        path,
        kind="pobox",
        required_fields=(_RequiredField("zip_no", ZIP_NO_ALIASES),),
        max_issues=max_issues,
    )


def validate_bulk_file(path: Path | str, *, max_issues: int = 50) -> PostalValidationSummary:
    return _validate_postal_file(
        path,
        kind="bulk",
        required_fields=(
            _RequiredField("zip_no", ZIP_NO_ALIASES),
            _RequiredField("bulk_name", BULK_NAME_ALIASES),
        ),
        max_issues=max_issues,
    )


def ensure_postal_validation_passed(summary: PostalValidationSummary) -> None:
    if summary.passed:
        return
    msg = (
        f"epost {summary.kind} validation failed: "
        f"rows={summary.row_count}, issues={summary.issue_count}, "
        f"missing_required={summary.missing_required_count}, "
        f"invalid_zip={summary.invalid_zip_count}, "
        f"invalid_kind={summary.invalid_kind_count}, "
        f"invalid_integer={summary.invalid_integer_count}, "
        f"duplicates={summary.duplicate_key_count}"
    )
    raise LoaderError(msg, hint=format_postal_validation_summary(summary))


def format_postal_validation_summary(summary: PostalValidationSummary) -> str:
    encoding = summary.encoding or "unknown"
    lines = [
        f"epost {summary.kind} validation: {summary.severity}",
        f"  path: {summary.path}",
        (
            "  rows: "
            f"total={summary.row_count}, valid={summary.valid_row_count}, "
            f"encoding={encoding}"
        ),
        (
            "  checks: "
            f"missing_required={summary.missing_required_count}, "
            f"invalid_zip={summary.invalid_zip_count}, "
            f"invalid_kind={summary.invalid_kind_count}, "
            f"invalid_integer={summary.invalid_integer_count}, "
            f"duplicates={summary.duplicate_key_count}"
        ),
    ]
    if summary.duplicate_samples:
        lines.append("  duplicate_samples: " + ", ".join(summary.duplicate_samples))
    for issue in summary.issues[:5]:
        location = f"row {issue.row_number}" if issue.row_number is not None else "header"
        field = f" field={issue.field}" if issue.field else ""
        value = f" value={issue.value}" if issue.value is not None else ""
        lines.append(f"  issue[{issue.code}] {location}{field}{value}: {issue.message}")
    if summary.issue_count > len(summary.issues):
        lines.append(f"  issue_samples_truncated: {summary.issue_count - len(summary.issues)}")
    return "\n".join(lines)


def _validate_postal_file(
    path: Path | str,
    *,
    kind: PostalDatasetKind,
    required_fields: tuple[_RequiredField, ...],
    max_issues: int,
) -> PostalValidationSummary:
    source = Path(path)
    issues: list[PostalValidationIssue] = []
    issue_count = 0
    missing_required_count = 0
    invalid_zip_count = 0
    invalid_kind_count = 0
    invalid_integer_count = 0
    duplicate_counter: Counter[str] = Counter()

    def add_issue(
        code: str,
        message: str,
        *,
        row_number: int | None = None,
        field: str | None = None,
        value: str | None = None,
    ) -> None:
        nonlocal issue_count
        issue_count += 1
        if len(issues) < max_issues:
            issues.append(
                PostalValidationIssue(
                    code=code,
                    message=message,
                    row_number=row_number,
                    field=field,
                    value=value,
                )
            )

    try:
        encoding = detect_epost_text_encoding(source)
    except LoaderError as exc:
        add_issue("unsupported_encoding", str(exc))
        return _summary(
            kind=kind,
            source=source,
            encoding=None,
            header=(),
            row_count=0,
            valid_row_count=0,
            issue_count=issue_count,
            missing_required_count=missing_required_count,
            invalid_zip_count=invalid_zip_count,
            invalid_kind_count=invalid_kind_count,
            invalid_integer_count=invalid_integer_count,
            duplicate_counter=duplicate_counter,
            issues=issues,
        )

    row_count = 0
    valid_row_count = 0
    with source.open("r", encoding=encoding, newline="") as file:
        reader = csv.DictReader(file, delimiter="|")
        if reader.fieldnames is None:
            add_issue("missing_header", "epost text file has no header row")
            header: tuple[str, ...] = ()
        else:
            header = tuple(_normalize_field_name(field) for field in reader.fieldnames)
            reader.fieldnames = list(header)
            for required in required_fields:
                if not _has_any_alias(header, required.aliases):
                    add_issue(
                        "missing_required_column",
                        f"required column is missing: {required.field}",
                        field=required.field,
                    )
            for row_number, raw_row in enumerate(reader, start=2):
                row_count += 1
                row = _normalize_row(raw_row)
                row_valid = True
                for required in required_fields:
                    if epost_row_value(row, required.aliases) is None:
                        missing_required_count += 1
                        row_valid = False
                        add_issue(
                            "missing_required_value",
                            f"required value is missing: {required.field}",
                            row_number=row_number,
                            field=required.field,
                        )
                zip_no = epost_row_value(row, ZIP_NO_ALIASES)
                if zip_no is not None and not ZIP_NO_RE.fullmatch(zip_no):
                    invalid_zip_count += 1
                    row_valid = False
                    add_issue(
                        "invalid_zip_no",
                        "zip_no must be exactly five digits",
                        row_number=row_number,
                        field="zip_no",
                        value=zip_no,
                    )
                if kind == "pobox":
                    raw_kind = epost_row_value(row, POBOX_KIND_ALIASES)
                    if raw_kind is not None and normalize_pobox_kind(raw_kind) is None:
                        invalid_kind_count += 1
                        row_valid = False
                        add_issue(
                            "invalid_pobox_kind",
                            "pobox_kind must be one of PO or PG",
                            row_number=row_number,
                            field="pobox_kind",
                            value=raw_kind,
                        )
                    for field, aliases in (
                        ("pobox_no_mn", POBOX_NO_MN_ALIASES),
                        ("pobox_no_sl", POBOX_NO_SL_ALIASES),
                    ):
                        raw_int = epost_row_value(row, aliases)
                        if raw_int is not None and INTEGER_RE.fullmatch(raw_int) is None:
                            invalid_integer_count += 1
                            row_valid = False
                            add_issue(
                                "invalid_integer",
                                f"{field} must be an unsigned integer",
                                row_number=row_number,
                                field=field,
                                value=raw_int,
                            )
                    duplicate_counter[_pobox_duplicate_key(row, row_count)] += 1
                else:
                    duplicate_counter[_bulk_duplicate_key(row)] += 1
                if row_valid:
                    valid_row_count += 1

    return _summary(
        kind=kind,
        source=source,
        encoding=encoding,
        header=header,
        row_count=row_count,
        valid_row_count=valid_row_count,
        issue_count=issue_count,
        missing_required_count=missing_required_count,
        invalid_zip_count=invalid_zip_count,
        invalid_kind_count=invalid_kind_count,
        invalid_integer_count=invalid_integer_count,
        duplicate_counter=duplicate_counter,
        issues=issues,
    )


def _summary(
    *,
    kind: PostalDatasetKind,
    source: Path,
    encoding: str | None,
    header: tuple[str, ...],
    row_count: int,
    valid_row_count: int,
    issue_count: int,
    missing_required_count: int,
    invalid_zip_count: int,
    invalid_kind_count: int,
    invalid_integer_count: int,
    duplicate_counter: Counter[str],
    issues: list[PostalValidationIssue],
) -> PostalValidationSummary:
    duplicate_samples = tuple(
        key for key, count in duplicate_counter.items() if key and count > 1
    )[:10]
    duplicate_key_count = sum(count - 1 for count in duplicate_counter.values() if count > 1)
    severity: PostalValidationSeverity = (
        "failed"
        if (
            issue_count > 0
            or row_count == 0
            or duplicate_key_count > 0
        )
        else "passed"
    )
    # Encoding failures return earlier as unsupported_encoding; empty_file means a readable
    # epost text file with a header or blank body but no data rows.
    if row_count == 0 and issue_count == 0:
        issues.append(
            PostalValidationIssue(
                code="empty_file",
                message="epost text file contains no data rows",
            )
        )
        issue_count = 1
    return PostalValidationSummary(
        kind=kind,
        path=str(source),
        encoding=encoding,
        header=header,
        row_count=row_count,
        valid_row_count=valid_row_count,
        issue_count=issue_count,
        missing_required_count=missing_required_count,
        invalid_zip_count=invalid_zip_count,
        invalid_kind_count=invalid_kind_count,
        invalid_integer_count=invalid_integer_count,
        duplicate_key_count=duplicate_key_count,
        duplicate_samples=duplicate_samples,
        issues=tuple(issues),
        severity=severity,
    )


def _normalize_field_name(field: str | None) -> str:
    return (field or "").strip()


def _normalize_row(row: Mapping[str | None, str | None]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized[_normalize_field_name(key)] = (value or "").strip()
    return normalized


def _has_any_alias(header: tuple[str, ...], aliases: tuple[str, ...]) -> bool:
    return any(alias in header for alias in aliases)


def _pobox_duplicate_key(row: Mapping[str, str], row_index: int) -> str:
    bd_mgt_sn = epost_row_value(row, BD_MGT_SN_ALIASES) or f"pobox:{row_index}"
    return bd_mgt_sn


def _bulk_duplicate_key(row: Mapping[str, str]) -> str:
    return "|".join(
        (
            epost_row_value(row, ZIP_NO_ALIASES) or "",
            epost_row_value(row, BULK_NAME_ALIASES) or "",
            epost_row_value(row, BD_MGT_SN_ALIASES) or "",
            epost_row_value(row, DETAIL_ALIASES) or "",
        )
    )
