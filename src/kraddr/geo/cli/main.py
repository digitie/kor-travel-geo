"""Typer CLI entry point."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.exceptions import InvalidInputError
from kraddr.geo.infra.backup import run_backup_job, run_restore_job
from kraddr.geo.infra.source_set import (
    build_full_load_source_set_plan,
    confirmation_token_for,
    discover_load_sources,
)
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
from kraddr.geo.loaders.sppn_makarea_loader import load_sppn_makarea
from kraddr.geo.loaders.text.daily_juso_loader import load_daily_juso_delta
from kraddr.geo.loaders.text.juso_hangul_loader import load_juso_hangul
from kraddr.geo.loaders.text.locsum_loader import load_locsum
from kraddr.geo.loaders.text.navi_loader import load_navi
from kraddr.geo.loaders.text.parcel_link_loader import (
    load_daily_parcel_link_delta,
    load_juso_parcel_link_snapshot,
)
from kraddr.geo.loaders.text.roadaddr_entrance_loader import load_roadaddr_entrances
from kraddr.geo.settings import get_settings
from kraddr.geo.version import __version__

if TYPE_CHECKING:
    from kraddr.geo.dto.admin import SourceSetDiscovery

app = typer.Typer(help="kraddr-geo command line tools.")
load_app = typer.Typer(help="Load data sources.")
refresh_app = typer.Typer(help="Run post-load refresh operations.")
validate_app = typer.Typer(help="Validate loaded data.")
jobs_app = typer.Typer(help="Inspect persistent load jobs.")
backup_app = typer.Typer(help="Create and inspect DB backup artifacts.")
restore_app = typer.Typer(help="Restore DB backup artifacts.")
app.add_typer(load_app, name="load")
app.add_typer(refresh_app, name="refresh")
app.add_typer(validate_app, name="validate")
app.add_typer(jobs_app, name="jobs")
app.add_typer(backup_app, name="backup")
app.add_typer(restore_app, name="restore")


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


def _warn_limit_per_file(limit_per_file: int | None) -> None:
    if limit_per_file is not None:
        typer.echo(
            "warning: --limit-per-file is for parser/load smoke tests only; "
            "do not use it for production loads.",
            err=True,
        )


@load_app.command("juso")
def load_juso(path: Path, yyyymm: str | None = typer.Option(None, "--yyyymm")) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            count = await load_juso_hangul(client.engine, path, source_yyyymm=yyyymm)
            typer.echo(f"loaded tl_juso_text rows: {count}")

    asyncio.run(run())


@load_app.command("daily-juso")
def load_daily_juso_command(
    path: Path,
    yyyymm: str | None = typer.Option(None, "--yyyymm"),
    limit_per_file: int | None = typer.Option(None, "--limit-per-file", min=1),
) -> None:
    _warn_limit_per_file(limit_per_file)

    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            result = await load_daily_juso_delta(
                client.engine,
                path,
                source_yyyymm=yyyymm,
                limit_per_file=limit_per_file,
            )
            typer.echo(
                "loaded daily tl_juso_text delta: "
                f"processed={result.processed_rows}, "
                f"upserted={result.upserted_rows}, "
                f"deleted={result.deleted_rows}, "
                f"lnbr_skipped={result.unsupported_lnbr_rows}, "
                f"no_data_sources={result.skipped_no_data_sources}, "
                f"last_mvmn_de={result.last_mvmn_de or '-'}"
            )

    asyncio.run(run())


@load_app.command("parcel-links")
def load_parcel_links_command(
    path: Path,
    yyyymm: str | None = typer.Option(None, "--yyyymm"),
    limit_per_file: int | None = typer.Option(None, "--limit-per-file", min=1),
    append: bool = typer.Option(False, "--append", help="기존 링크를 비우지 않고 upsert한다."),
) -> None:
    _warn_limit_per_file(limit_per_file)

    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            result = await load_juso_parcel_link_snapshot(
                client.engine,
                path,
                source_yyyymm=yyyymm,
                limit_per_file=limit_per_file,
                replace=not append,
            )
            typer.echo(
                "loaded tl_juso_parcel_link snapshot: "
                f"processed={result.processed_rows}, "
                f"upserted={result.upserted_rows}, "
                f"source_count={result.source_count}"
            )

    asyncio.run(run())


@load_app.command("daily-parcel-links")
def load_daily_parcel_links_command(
    path: Path,
    yyyymm: str | None = typer.Option(None, "--yyyymm"),
    limit_per_file: int | None = typer.Option(None, "--limit-per-file", min=1),
) -> None:
    _warn_limit_per_file(limit_per_file)

    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            result = await load_daily_parcel_link_delta(
                client.engine,
                path,
                source_yyyymm=yyyymm,
                limit_per_file=limit_per_file,
            )
            typer.echo(
                "loaded daily tl_juso_parcel_link delta: "
                f"processed={result.processed_rows}, "
                f"upserted={result.upserted_rows}, "
                f"deleted={result.deleted_rows}, "
                f"no_data_sources={result.skipped_no_data_sources}, "
                f"last_mvmn_de={result.last_mvmn_de or '-'}"
            )

    asyncio.run(run())


@load_app.command("roadaddr-entrances")
def load_roadaddr_entrances_command(
    path: Path,
    yyyymm: str | None = typer.Option(None, "--yyyymm"),
    limit_per_file: int | None = typer.Option(None, "--limit-per-file", min=1),
    append: bool = typer.Option(False, "--append", help="기존 출입구를 비우지 않고 upsert한다."),
) -> None:
    _warn_limit_per_file(limit_per_file)

    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            result = await load_roadaddr_entrances(
                client.engine,
                path,
                source_yyyymm=yyyymm,
                limit_per_file=limit_per_file,
                replace=not append,
            )
            typer.echo(
                "loaded tl_roadaddr_entrc snapshot: "
                f"processed={result.processed_rows}, "
                f"upserted={result.upserted_rows}, "
                f"source_count={result.source_count}, "
                f"source_yyyymm={result.source_yyyymm or '-'}"
            )

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


@load_app.command("sppn-makarea")
def load_sppn_makarea_command(
    path: Path,
    mode: str = typer.Option("full", "--mode", help="full, append 또는 delta"),
    yyyymm: str | None = typer.Option(None, "--yyyymm"),
) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            count = await load_sppn_makarea(
                client.engine,
                path,
                mode=mode,
                source_yyyymm=yyyymm,
            )
            typer.echo(f"loaded tl_sppn_makarea rows: {count}")

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
    jibun_path: Path | None = typer.Option(None, "--jibun"),
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
            parcel_result = await load_juso_parcel_link_snapshot(
                client.engine,
                jibun_path or juso_path,
                source_yyyymm=yyyymm,
            )
            typer.echo(f"loaded tl_juso_parcel_link rows: {parcel_result.upserted_rows}")
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


@load_app.command("full-set")
def load_full_set_command(
    root_path: Path,
    juso_yyyymm: str | None = typer.Option(None, "--juso-yyyymm"),
    parcel_link_yyyymm: str | None = typer.Option(None, "--parcel-link-yyyymm"),
    locsum_yyyymm: str | None = typer.Option(None, "--locsum-yyyymm"),
    navi_yyyymm: str | None = typer.Option(None, "--navi-yyyymm"),
    shp_yyyymm: str | None = typer.Option(None, "--shp-yyyymm"),
    roadaddr_entrance_yyyymm: str | None = typer.Option(None, "--roadaddr-entrance-yyyymm"),
    allow_mixed_yyyymm: bool = typer.Option(False, "--allow-mixed-yyyymm"),
    confirm_source_set: str | None = typer.Option(None, "--confirm-source-set"),
    submit: bool = typer.Option(True, "--submit/--plan-only"),
) -> None:
    """Discover source files, confirm mixed yyyymm, and submit a full-load batch plan."""

    async def run() -> None:
        versions = {
            key: value
            for key, value in {
                "juso": juso_yyyymm,
                "parcel_link": parcel_link_yyyymm,
                "locsum": locsum_yyyymm,
                "navi": navi_yyyymm,
                "shp": shp_yyyymm,
                "roadaddr_entrance": roadaddr_entrance_yyyymm,
            }.items()
            if value is not None
        }
        discovery = discover_load_sources(root_path)
        _echo_source_discovery(discovery)
        confirmation = confirm_source_set
        yyyymm_preview = {**discovery.yyyymm_by_kind, **versions}
        preview_mixed = len({value for value in yyyymm_preview.values() if value}) > 1
        if allow_mixed_yyyymm and preview_mixed and confirmation is None:
            expected = confirmation_token_for(yyyymm_preview)
            if not sys.stdin.isatty():
                typer.echo(f"mixed source set requires --confirm-source-set: {expected}", err=True)
                raise typer.Exit(2)
            typer.echo("원천 자료 기준월이 서로 다릅니다.")
            typer.echo(f"의도적으로 혼합 적재를 진행하려면 다음 문구를 입력하십시오: {expected}")
            confirmation = typer.prompt("확인 문구")
        try:
            plan = build_full_load_source_set_plan(
                root_path=root_path,
                versions=versions,
                allow_mixed_yyyymm=allow_mixed_yyyymm,
                confirmation_token=confirmation,
                acknowledged_by="cli",
            )
        except InvalidInputError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(2) from exc
        typer.echo(plan.model_dump_json())
        if not submit:
            return
        async with AsyncAddressClient() as client:
            job = await client.submit_full_load_source_set(plan)
        typer.echo(f"submitted full_load_batch job: {job.job_id}")

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


@backup_app.command("create")
def create_backup(
    destination_dir: Path | None = typer.Option(None, "--destination-dir"),
    profile: str = typer.Option("serving-ready", "--profile"),
    jobs: int | None = typer.Option(None, "--jobs", min=1, max=64),
    compression_level: int | None = typer.Option(None, "--compression-level", min=1, max=19),
    callback_url: str | None = typer.Option(None, "--callback-url"),
    display_name: str | None = typer.Option(None, "--display-name"),
) -> None:
    """Run a foreground DB backup job and persist metadata in ops.artifacts."""

    async def run() -> None:
        payload = _without_none(
            {
                "destination_dir": str(destination_dir) if destination_dir else None,
                "profile": profile,
                "jobs": jobs,
                "compression_level": compression_level,
                "callback_url": callback_url,
                "display_name": display_name,
            }
        )
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            await run_backup_job(
                client.engine,
                client.settings,
                payload,
                asyncio.Event(),
                _cli_progress,
            )

    asyncio.run(run())


@backup_app.command("list")
def list_backups(limit: int = typer.Option(20, "--limit", min=1, max=200)) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            artifacts = await client.list_artifacts(
                artifact_type="db_backup",
                limit=limit,
            )
        for artifact in artifacts:
            typer.echo(
                f"{artifact.artifact_id}\t{artifact.state}\t"
                f"{artifact.size_bytes or 0}\t{artifact.display_name or '-'}"
            )

    asyncio.run(run())


@backup_app.command("show")
def show_backup(artifact_id: str) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            typer.echo((await client.get_artifact(artifact_id)).model_dump_json())

    asyncio.run(run())


@backup_app.command("delete")
def delete_backup(artifact_id: str) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            typer.echo((await client.delete_artifact(artifact_id)).model_dump_json())

    asyncio.run(run())


@restore_app.command("create")
def create_restore(
    artifact_id: str | None = typer.Option(None, "--artifact-id"),
    archive_path: Path | None = typer.Option(None, "--archive-path"),
    target_database: str | None = typer.Option(None, "--target-database"),
    target_dsn: str | None = typer.Option(None, "--target-dsn"),
    jobs: int | None = typer.Option(None, "--jobs", min=1, max=64),
    no_analyze: bool = typer.Option(False, "--no-analyze"),
    no_smoke_test: bool = typer.Option(False, "--no-smoke-test"),
) -> None:
    """Run a foreground restore job against a new empty target DB."""

    async def run() -> None:
        payload = _without_none(
            {
                "artifact_id": artifact_id,
                "archive_path": str(archive_path) if archive_path else None,
                "target_database": target_database,
                "target_dsn": target_dsn,
                "jobs": jobs,
                "run_analyze": not no_analyze,
                "run_smoke_test": not no_smoke_test,
            }
        )
        async with AsyncAddressClient() as client:
            assert client.engine is not None
            await run_restore_job(
                client.engine,
                client.settings,
                payload,
                asyncio.Event(),
                _cli_progress,
            )

    asyncio.run(run())


def _echo_source_discovery(discovery: SourceSetDiscovery) -> None:
    for candidate in discovery.candidates:
        typer.echo(
            f"{candidate.kind}\t{candidate.inferred_yyyymm or '-'}\t"
            f"{candidate.confidence}\t{candidate.path}"
        )


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


def _without_none(payload: dict[str, object | None]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if value is not None}


async def _cli_progress(
    *,
    progress: float | None = None,
    stage: str | None = None,
    message: str | None = None,
) -> None:
    value = f"{progress:.2%}" if progress is not None else "--"
    typer.echo(f"{value}\t{stage or '-'}\t{message or ''}")
    await asyncio.sleep(0)
