"""Typer CLI entry point."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.loaders.bulk_loader import load_bulk_delivery
from kraddr.geo.loaders.consistency import DEFAULT_CASES, run_all_cases
from kraddr.geo.loaders.data_quality import (
    DATA_QUALITY_CASES,
    export_data_quality_samples,
)
from kraddr.geo.loaders.epost_downloader import (
    discover_epost_files,
    download_epost_zip,
    extract_epost_zip,
)
from kraddr.geo.loaders.pobox_loader import load_pobox
from kraddr.geo.loaders.postload import refresh_mv, resolve_text_geometry_links
from kraddr.geo.loaders.shp.polygons_loader import load_shp_polygons
from kraddr.geo.loaders.text.juso_hangul_loader import load_juso_hangul
from kraddr.geo.loaders.text.locsum_loader import load_locsum
from kraddr.geo.loaders.text.navi_loader import load_navi
from kraddr.geo.settings import get_settings
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


@app.command("init-db")
def init_db() -> None:
    """Create schema, extensions, indexes, and empty MV via SCHEMA_SQL + INDEX_SQL + MV_SQL."""
    from sqlalchemy import text as sa_text

    from kraddr.geo.infra.sql import INDEX_SQL, MV_SQL, SCHEMA_SQL, iter_sql_statements

    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            for sql in iter_sql_statements(SCHEMA_SQL):
                async with client.engine.begin() as conn:
                    await conn.execute(sa_text(sql))

            warnings = 0
            for sql in iter_sql_statements(INDEX_SQL):
                try:
                    async with client.engine.begin() as conn:
                        await conn.execute(sa_text(sql))
                except Exception as exc:
                    warnings += 1
                    typer.echo(f"  index warning (may already exist): {exc}")

            for sql in iter_sql_statements(MV_SQL):
                try:
                    async with client.engine.begin() as conn:
                        await conn.execute(sa_text(sql))
                except Exception as exc:
                    warnings += 1
                    typer.echo(f"  mv warning (may already exist): {exc}")

        if warnings:
            typer.echo(f"init-db: schema created with {warnings} warning(s).")
        else:
            typer.echo("init-db: schema, indexes, and MV created.")

    asyncio.run(run())


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


@load_app.command("shp")
def load_shp_command(
    path: Path,
    mode: str = typer.Option("full", "--mode", help="full 또는 delta"),
    yyyymm: str | None = typer.Option(None, "--yyyymm"),
) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            count = await load_shp_polygons(
                client.engine,
                path,
                mode=mode,
                source_yyyymm=yyyymm,
            )
            typer.echo(f"loaded SHP layers: {count}")

    asyncio.run(run())


@load_app.command("shp-all")
def load_shp_all_command(
    root: Path,
    mode: str = typer.Option("full", "--mode", help="full 또는 delta"),
    yyyymm: str | None = typer.Option(None, "--yyyymm"),
) -> None:
    async def run() -> None:
        total = 0
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            items = _shp_all_work_items(root, mode)
            for index, (sido_dir, effective_mode) in enumerate(items):
                count = await load_shp_polygons(
                    client.engine,
                    sido_dir,
                    mode=effective_mode,
                    source_yyyymm=yyyymm,
                    analyze=index == len(items) - 1,
                )
                total += count
                typer.echo(f"{sido_dir.name}: {count} layers")
        typer.echo(f"loaded SHP layers total: {total}")

    asyncio.run(run())


@load_app.command("pobox")
def load_pobox_command(path: Path) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            count = await load_pobox(client.engine, path)
            typer.echo(f"loaded postal_pobox rows: {count}")

    asyncio.run(run())


@load_app.command("bulk")
def load_bulk_command(path: Path) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            count = await load_bulk_delivery(client.engine, path)
            typer.echo(f"loaded postal_bulk_delivery rows: {count}")

    asyncio.run(run())


@load_app.command("epost")
def load_epost_command(
    source: Path | None = typer.Option(
        None,
        "--source",
        help="다운로드 ZIP 또는 압축 해제 디렉터리",
    ),
    output_dir: Path = typer.Option(Path("data/epost"), "--output-dir"),
    kind: str = typer.Option("full", "--kind", help="현재 full만 지원. downloadKnd=1"),
) -> None:
    async def run() -> None:
        if kind != "full":
            typer.echo("only --kind=full is supported for epost dataset 15000302", err=True)
            raise typer.Exit(2)
        resolved = source
        if resolved is None:
            resolved = await download_epost_zip(get_settings(), output_dir, download_kind="1")
            typer.echo(f"downloaded epost ZIP: {resolved}")
        if resolved.suffix.lower() == ".zip":
            resolved = extract_epost_zip(resolved, output_dir / resolved.stem)
            typer.echo(f"extracted epost ZIP: {resolved}")
        pobox_file, bulk_file = discover_epost_files(resolved)
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            if pobox_file is not None:
                count = await load_pobox(client.engine, pobox_file)
                typer.echo(f"loaded postal_pobox rows: {count}")
            if bulk_file is not None:
                count = await load_bulk_delivery(client.engine, bulk_file)
                typer.echo(f"loaded postal_bulk_delivery rows: {count}")
        if pobox_file is None and bulk_file is None:
            typer.echo("no pobox/bulk text files found in epost dataset", err=True)
            raise typer.Exit(2)

    asyncio.run(run())


@load_app.command("all-sidos")
def load_all_sidos_command(
    juso_path: Path = typer.Option(..., "--juso"),
    locsum_path: Path = typer.Option(..., "--locsum"),
    navi_path: Path = typer.Option(..., "--navi"),
    shp_root: Path | None = typer.Option(None, "--shp-root"),
    pobox_path: Path | None = typer.Option(None, "--pobox"),
    bulk_path: Path | None = typer.Option(None, "--bulk"),
    yyyymm: str | None = typer.Option(None, "--yyyymm"),
    refresh: bool = typer.Option(True, "--refresh/--no-refresh"),
    swap: bool = typer.Option(True, "--swap/--concurrent"),
    allow_consistency_error: bool = typer.Option(False, "--allow-consistency-error"),
) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            juso_count = await load_juso_hangul(client.engine, juso_path, source_yyyymm=yyyymm)
            typer.echo(f"loaded tl_juso_text rows: {juso_count}")
            locsum_count = await load_locsum(client.engine, locsum_path, source_yyyymm=yyyymm)
            typer.echo(f"loaded tl_locsum_entrc rows: {locsum_count}")
            build_count, entrance_count = await load_navi(
                client.engine,
                navi_path,
                source_yyyymm=yyyymm,
            )
            typer.echo(
                f"loaded navi rows: centroid={build_count}, entrance={entrance_count}"
            )
            if shp_root is not None:
                shp_total = 0
                sido_dirs = _sido_dirs(shp_root)
                for index, sido_dir in enumerate(sido_dirs):
                    shp_total += await load_shp_polygons(
                        client.engine,
                        sido_dir,
                        mode=_shp_mode_for_index("full", index),
                        source_yyyymm=yyyymm,
                        analyze=index == len(sido_dirs) - 1,
                    )
                typer.echo(f"loaded SHP layers total: {shp_total}")
            if pobox_path is not None:
                count = await load_pobox(client.engine, pobox_path)
                typer.echo(f"loaded postal_pobox rows: {count}")
            if bulk_path is not None:
                typer.echo(
                    f"loaded postal_bulk_delivery rows: "
                    f"{await load_bulk_delivery(client.engine, bulk_path)}"
                )
            await resolve_text_geometry_links(client.engine)
            report = await run_all_cases(client.engine, generated_by="cli")
            typer.echo(report.model_dump_json())
            if report.severity_max == "ERROR" and not allow_consistency_error:
                raise typer.Exit(2)
            if refresh:
                await refresh_mv(
                    client.engine,
                    concurrently=not swap,
                    strategy="swap" if swap else "concurrent",
                )
                typer.echo("refreshed mv_geocode_target")

    asyncio.run(run())


@refresh_app.command("mv")
def refresh_materialized_view(
    concurrently: bool = typer.Option(True, "--concurrently/--no-concurrently"),
    swap: bool = typer.Option(False, "--swap", help="Build shadow MV and rename-swap."),
) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            await refresh_mv(
                client.engine,
                concurrently=concurrently and not swap,
                strategy="swap" if swap else "concurrent",
            )
            typer.echo("refreshed mv_geocode_target")

    asyncio.run(run())


@validate_app.command("consistency")
def validate_consistency(
    cases: str | None = typer.Option(None, "--cases", help="Comma-separated case codes."),
    scope: str = typer.Option("full", "--scope"),
) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            selected = tuple(part.strip() for part in cases.split(",")) if cases else DEFAULT_CASES
            report = await run_all_cases(
                client.engine,
                scope=scope,
                cases=selected,
                generated_by="cli",
            )
            typer.echo(report.model_dump_json())

    asyncio.run(run())


@validate_app.command("data-quality-samples")
def validate_data_quality_samples(
    output_dir: Path = typer.Option(
        Path("artifacts/fullload/data-quality"),
        "--output-dir",
        help="CSV 산출물을 저장할 디렉터리",
    ),
    cases: str = typer.Option(
        ",".join(DATA_QUALITY_CASES),
        "--cases",
        help="Comma-separated case codes. 지원: C2,C4,C6,C7",
    ),
    limit: int = typer.Option(200, "--limit", min=1, max=10_000),
) -> None:
    async def run() -> None:
        try:
            selected = _data_quality_cases(cases)
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(2) from exc
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            paths = await export_data_quality_samples(
                client.engine,
                output_dir,
                cases=selected,
                limit=limit,
            )
        for path in paths:
            typer.echo(str(path))

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


def _sido_dirs(root: Path) -> tuple[Path, ...]:
    if not root.exists():
        typer.echo(f"path does not exist: {root}", err=True)
        raise typer.Exit(2)
    if any(root.glob("*.shp")):
        return (root,)
    dirs = tuple(sorted(path for path in root.iterdir() if path.is_dir()))
    if not dirs:
        typer.echo(f"no sido directories found: {root}", err=True)
        raise typer.Exit(2)
    return dirs


def _shp_mode_for_index(requested_mode: str, index: int) -> str:
    if requested_mode == "full" and index > 0:
        return "append"
    return requested_mode


def _shp_all_work_items(root: Path, requested_mode: str) -> tuple[tuple[Path, str], ...]:
    return tuple(
        (sido_dir, _shp_mode_for_index(requested_mode, index))
        for index, sido_dir in enumerate(_sido_dirs(root))
    )


def _data_quality_cases(raw: str) -> tuple[str, ...]:
    selected = tuple(dict.fromkeys(part.strip().upper() for part in raw.split(",") if part.strip()))
    unknown = tuple(code for code in selected if code not in DATA_QUALITY_CASES)
    if unknown:
        allowed = ",".join(DATA_QUALITY_CASES)
        joined = ",".join(unknown)
        msg = f"unsupported data quality case(s): {joined}; allowed: {allowed}"
        raise ValueError(msg)
    if not selected:
        msg = "at least one data quality case is required"
        raise ValueError(msg)
    return selected
