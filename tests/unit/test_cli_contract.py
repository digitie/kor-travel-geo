from __future__ import annotations

from typer.testing import CliRunner

from kraddr.geo.cli.main import _shp_all_work_items, _shp_mode_for_index, app


def test_cli_exposes_t018_operational_commands() -> None:
    runner = CliRunner()

    for command in (
        ["load", "--help"],
        ["load", "all-sidos", "--help"],
        ["load", "shp-all", "--help"],
        ["load", "epost", "--help"],
        ["refresh", "mv", "--help"],
        ["validate", "consistency", "--help"],
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
