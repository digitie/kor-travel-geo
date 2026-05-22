"""Typer CLI entry point."""

from __future__ import annotations

import typer

from kraddr.geo.version import __version__

app = typer.Typer(help="kraddr-geo command line tools.")


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()
