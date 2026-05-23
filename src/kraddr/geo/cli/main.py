"""Typer CLI entry point."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.loaders.consistency import run_all_cases
from kraddr.geo.loaders.postload import refresh_mv
from kraddr.geo.loaders.text.juso_hangul_loader import load_juso_hangul
from kraddr.geo.loaders.text.locsum_loader import load_locsum
from kraddr.geo.loaders.text.navi_loader import load_navi
from kraddr.geo.version import __version__

app = typer.Typer(help="kraddr-geo command line tools.")
load_app = typer.Typer(help="Load data sources.")
refresh_app = typer.Typer(help="Run post-load refresh operations.")
validate_app = typer.Typer(help="Validate loaded data.")
jobs_app = typer.Typer(help="Inspect persistent load jobs.")
app.add_typer(load_app, name="load")
app.add_typer(refresh_app, name="refresh")
app.add_typer(validate_app, name="validate")
app.add_typer(jobs_app, name="jobs")


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@load_app.command("juso")
def load_juso(path: Path, yyyymm: str | None = typer.Option(None, "--yyyymm")) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            count = await load_juso_hangul(client.engine, path, source_yyyymm=yyyymm)
            typer.echo(f"loaded tl_juso_text rows: {count}")

    asyncio.run(run())


@load_app.command("locsum")
def load_locsum_command(path: Path, yyyymm: str | None = typer.Option(None, "--yyyymm")) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            count = await load_locsum(client.engine, path, source_yyyymm=yyyymm)
            typer.echo(f"loaded tl_locsum_entrc rows: {count}")

    asyncio.run(run())


@load_app.command("navi")
def load_navi_command(path: Path, yyyymm: str | None = typer.Option(None, "--yyyymm")) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            build_count, entrance_count = await load_navi(client.engine, path, source_yyyymm=yyyymm)
            typer.echo(
                f"loaded tl_navi_buld_centroid rows: {build_count}, "
                f"tl_navi_entrc rows: {entrance_count}"
            )

    asyncio.run(run())


@refresh_app.command("mv")
def refresh_materialized_view(
    concurrently: bool = typer.Option(True, "--concurrently/--no-concurrently"),
) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            await refresh_mv(client.engine, concurrently=concurrently)
            typer.echo("refreshed mv_geocode_target")

    asyncio.run(run())


@validate_app.command("consistency")
def validate_consistency() -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            report = await run_all_cases(client.engine, generated_by="cli")
            typer.echo(report.model_dump_json())

    asyncio.run(run())


@jobs_app.command("list")
def list_jobs(limit: int = typer.Option(20, "--limit", min=1, max=200)) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            for job in await client.list_load_jobs(limit=limit):
                typer.echo(f"{job.job_id}\t{job.kind}\t{job.state}\t{job.progress:.2f}")

    asyncio.run(run())


@jobs_app.command("status")
def job_status(job_id: str) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            typer.echo((await client.load_status(job_id)).model_dump_json())

    asyncio.run(run())


@jobs_app.command("cancel")
def cancel_job(job_id: str) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            typer.echo((await client.cancel_load(job_id)).model_dump_json())

    asyncio.run(run())
