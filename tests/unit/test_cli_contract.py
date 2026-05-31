from __future__ import annotations

import inspect
from pathlib import Path

from typer.testing import CliRunner

from kraddr.geo.cli.main import (
    _data_quality_cases,
    _shp_all_work_items,
    _shp_mode_for_index,
    app,
    load_all_sidos_command,
    load_daily_juso_command,
    load_daily_parcel_links_command,
    load_full_set_command,
    load_parcel_links_command,
    load_roadaddr_entrances_command,
    load_shp_all_command,
    load_sppn_makarea_command,
)


def test_cli_exposes_t018_operational_commands() -> None:
    runner = CliRunner()

    for command in (
        ["load", "--help"],
        ["load", "all-sidos", "--help"],
        ["load", "daily-juso", "--help"],
        ["load", "parcel-links", "--help"],
        ["load", "daily-parcel-links", "--help"],
        ["load", "full-set", "--help"],
        ["load", "roadaddr-entrances", "--help"],
        ["load", "shp-all", "--help"],
        ["load", "sppn-makarea", "--help"],
        ["load", "epost", "--help"],
        ["refresh", "mv", "--help"],
        ["validate", "consistency", "--help"],
        ["validate", "data-quality-samples", "--help"],
        ["backup", "create", "--help"],
        ["backup", "list", "--help"],
        ["backup", "show", "--help"],
        ["restore", "create", "--help"],
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


def test_multi_sido_shp_load_analyzes_only_after_last_sido() -> None:
    shp_all_source = inspect.getsource(load_shp_all_command)
    all_sidos_source = inspect.getsource(load_all_sidos_command)

    assert "items = _shp_all_work_items(root, mode)" in shp_all_source
    assert "analyze=index == len(items) - 1" in shp_all_source
    assert "sido_dirs = _sido_dirs(shp_root)" in all_sidos_source
    assert "analyze=index == len(sido_dirs) - 1" in all_sidos_source


def test_sppn_makarea_cli_load_exposes_source_yyyymm_and_mode() -> None:
    source = inspect.getsource(load_sppn_makarea_command)

    assert "load_sppn_makarea(" in source
    assert "--yyyymm" in source
    assert "--mode" in source
    assert 'typer.echo(f"loaded tl_sppn_makarea rows: {count}")' in source


def test_limit_per_file_commands_warn_test_only() -> None:
    for command in (
        load_daily_juso_command,
        load_parcel_links_command,
        load_daily_parcel_links_command,
        load_roadaddr_entrances_command,
    ):
        source = inspect.getsource(command)
        assert "_warn_limit_per_file(limit_per_file)" in source


def test_data_quality_case_parser_deduplicates_and_rejects_unknown() -> None:
    assert _data_quality_cases("c2,C4,c2") == ("C2", "C4")

    try:
        _data_quality_cases("C2,C99")
    except ValueError as exc:
        assert "unsupported data quality case(s): C99" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected ValueError")


def test_full_set_command_requires_specific_mixed_confirmation() -> None:
    source = inspect.getsource(load_full_set_command)

    assert "--allow-mixed-yyyymm" in source
    assert "--confirm-source-set" in source
    assert "confirmation_token_for(yyyymm_preview)" in source
    assert "not sys.stdin.isatty()" in source


def test_data_quality_case_parser_rejects_empty_list() -> None:
    try:
        _data_quality_cases(" , ")
    except ValueError as exc:
        assert "at least one data quality case" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected ValueError")


def test_full_load_smoke_uses_v2_client_contract() -> None:
    script = Path("scripts/fullload_test.sh").read_text(encoding="utf-8")

    assert "r.candidates" in script
    assert "await client.reverse(" in script
    assert "reverse_geocode" not in script
    assert "r.result" not in script
