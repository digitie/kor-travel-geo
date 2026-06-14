from __future__ import annotations

import pytest

from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders.bulk_loader import iter_bulk_rows
from kortravelgeo.loaders.epost_validation import (
    ensure_postal_validation_passed,
    format_postal_validation_summary,
    validate_bulk_file,
    validate_pobox_file,
)
from kortravelgeo.loaders.pobox_loader import iter_pobox_rows


def test_validate_pobox_accepts_cp949_korean_aliases(tmp_path) -> None:
    path = tmp_path / "사서함.txt"
    path.write_bytes(
        (
            "우편번호|건물관리번호|구분|사서함명|사서함본번|사서함부번\n"
            "04524|BD001|po|서울사서함|1|0\n"
        ).encode("cp949")
    )

    summary = validate_pobox_file(path)
    rows = list(iter_pobox_rows(path))

    assert summary.passed
    assert summary.encoding == "cp949"
    assert summary.row_count == 1
    assert rows[0].zip_no == "04524"
    assert rows[0].pobox_kind == "PO"
    assert rows[0].pobox_no_mn == 1


def test_validate_bulk_accepts_utf8_bom_korean_aliases(tmp_path) -> None:
    path = tmp_path / "bulk.txt"
    path.write_text(
        "우편번호|다량배달처명|건물관리번호|상세주소\n04524|서울기관|BD001|본관\n",
        encoding="utf-8-sig",
    )

    summary = validate_bulk_file(path)
    rows = list(iter_bulk_rows(path))

    assert summary.passed
    assert summary.encoding == "utf-8-sig"
    assert summary.row_count == 1
    assert rows[0].bulk_name == "서울기관"
    assert rows[0].detail == "본관"


def test_validate_pobox_reports_format_and_duplicate_errors(tmp_path) -> None:
    path = tmp_path / "pobox.txt"
    path.write_text(
        "zip_no|bd_mgt_sn|pobox_kind|pobox_no_mn\n"
        "1234|BD001|PX|abc\n"
        "04524|BD001|PO|1\n",
        encoding="utf-8",
    )

    summary = validate_pobox_file(path)

    assert not summary.passed
    assert summary.invalid_zip_count == 1
    assert summary.invalid_kind_count == 1
    assert summary.invalid_integer_count == 1
    assert summary.duplicate_key_count == 1
    assert summary.duplicate_samples == ("BD001",)
    with pytest.raises(LoaderError, match="epost pobox validation failed"):
        ensure_postal_validation_passed(summary)


def test_validate_bulk_reports_missing_required_columns_and_values(tmp_path) -> None:
    path = tmp_path / "bulk.txt"
    path.write_text("zip_no|detail\n04524|본관\n", encoding="utf-8")

    summary = validate_bulk_file(path)
    formatted = format_postal_validation_summary(summary)

    assert not summary.passed
    assert summary.issue_count == 2
    assert summary.missing_required_count == 1
    assert "missing_required_column" in formatted
    assert "missing_required_value" in formatted
