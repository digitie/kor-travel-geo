from __future__ import annotations

from typer.testing import CliRunner

from kraddr.geo.cli.main import (
    _data_quality_cases,
    _shp_all_work_items,
    _shp_mode_for_index,
    app,
)


def test_cli_exposes_t018_operational_commands() -> None:
    runner = CliRunner()

    for command in (
        ["load", "--help"],
        ["load", "all-sidos", "--help"],
        ["load", "shp-all", "--help"],
        ["load", "epost", "--help"],
        ["refresh", "mv", "--help"],
        ["validate", "consistency", "--help"],
        ["validate", "data-quality-samples", "--help"],
    ):
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output


def test_shp_all_full_mode_truncates_once_then_appends() -> None:
    assert _shp_mode_for_index("full", 0) == "full"
    assert _shp_mode_for_index("full", 1) == "append"
    assert _shp_mode_for_index("delta", 1) == "delta"


def test_shp_all_work_items_apply_full_mode_only_to_first_sido(tmp_path) -> None:
    first = tmp_path / "11"
    second = tmp_path / "26"
    first.mkdir()
    second.mkdir()

    items = _shp_all_work_items(tmp_path, "full")

    assert items == ((first, "full"), (second, "append"))


def test_data_quality_case_parser_deduplicates_and_rejects_unknown() -> None:
    assert _data_quality_cases("c2,C4,c2") == ("C2", "C4")

    try:
        _data_quality_cases("C2,C99")
    except ValueError as exc:
        assert "unsupported data quality case(s): C99" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected ValueError")


def test_data_quality_case_parser_rejects_empty_list() -> None:
    try:
        _data_quality_cases(" , ")
    except ValueError as exc:
        assert "at least one data quality case" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected ValueError")
