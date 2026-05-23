from __future__ import annotations

from typer.testing import CliRunner

from kraddr.geo.cli.main import app


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

