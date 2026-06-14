"""Typer CLI entry point."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.backup import run_backup_job, run_restore_job
from kortravelgeo.infra.concurrency import (
    AdvisoryLockKey,
    AdvisoryLockNamespace,
    ConcurrentExecutionError,
    cross_process_lock,
)
from kortravelgeo.infra.geoip import build_geoip_reader, classify_ip
from kortravelgeo.loaders.bulk_loader import load_bulk_delivery
from kortravelgeo.loaders.consistency import DEFAULT_CASES, run_all_cases
from kortravelgeo.loaders.data_quality import (
    DATA_QUALITY_CASES,
    export_data_quality_samples,
)
from kortravelgeo.loaders.epost_downloader import (
    discover_epost_files,
    download_epost_zip,
    extract_epost_zip,
)
from kortravelgeo.loaders.pobox_loader import load_pobox
from kortravelgeo.loaders.postload import (
    refresh_mv,
    refresh_region_radius_parts,
    resolve_text_geometry_links,
)
from kortravelgeo.loaders.shp.polygons_loader import load_shp_polygons
from kortravelgeo.loaders.sppn_makarea_loader import load_sppn_makarea
from kortravelgeo.loaders.text.daily_juso_loader import load_daily_juso_delta
from kortravelgeo.loaders.text.juso_hangul_loader import load_juso_hangul
from kortravelgeo.loaders.text.locsum_loader import load_locsum
from kortravelgeo.loaders.text.navi_loader import load_navi
from kortravelgeo.loaders.text.parcel_link_loader import (
    load_daily_parcel_link_delta,
    load_juso_parcel_link_snapshot,
)
from kortravelgeo.loaders.text.roadaddr_entrance_loader import load_roadaddr_entrances
from kortravelgeo.settings import get_settings
from kortravelgeo.version import __version__

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

app = typer.Typer(help="ktgctl command line tools.")
load_app = typer.Typer(help="Load data sources.")
refresh_app = typer.Typer(help="Run post-load refresh operations.")
validate_app = typer.Typer(help="Validate loaded data.")
jobs_app = typer.Typer(help="Inspect persistent load jobs.")
backup_app = typer.Typer(help="Create and inspect DB backup artifacts.")
restore_app = typer.Typer(help="Restore DB backup artifacts.")
serving_app = typer.Typer(help="Plan serving database release operations.")
geoip_app = typer.Typer(help="Inspect Korea-only GeoIP gate decisions.")
janitor_app = typer.Typer(help="Run the source upload-session janitor.")
app.add_typer(load_app, name="load")
app.add_typer(refresh_app, name="refresh")
app.add_typer(validate_app, name="validate")
app.add_typer(jobs_app, name="jobs")
app.add_typer(backup_app, name="backup")
app.add_typer(restore_app, name="restore")
app.add_typer(serving_app, name="serving")
app.add_typer(geoip_app, name="geoip")
app.add_typer(janitor_app, name="janitor")


async def _run_with_cli_lock[T](
    engine: AsyncEngine,
    key: AdvisoryLockKey,
    operation: Callable[[], Awaitable[T]],
) -> T:
    try:
        async with cross_process_lock(engine, key):
            return await operation()
    except ConcurrentExecutionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc


def _global_lock(namespace: AdvisoryLockNamespace) -> AdvisoryLockKey:
    return AdvisoryLockKey.global_key(namespace)


def _path_lock(namespace: AdvisoryLockNamespace, path: Path) -> AdvisoryLockKey:
    return AdvisoryLockKey.for_resource(namespace, path.expanduser().resolve(strict=False))


def _value_lock(namespace: AdvisoryLockNamespace, value: object) -> AdvisoryLockKey:
    return AdvisoryLockKey.for_resource(namespace, value)


def _shp_namespace(mode: str) -> AdvisoryLockNamespace:
    return (
        AdvisoryLockNamespace.LOAD_SHP_DELTA
        if mode.lower() == "delta"
        else AdvisoryLockNamespace.LOAD_SHP_POLYGONS
    )


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@geoip_app.command("check")
def geoip_check(ip: str) -> None:
    """Print Korea-only gate decision for one IP address."""
    settings = get_settings()
    decision = classify_ip(
        ip,
        reader=build_geoip_reader(settings),
        mode=settings.geoip_gate_mode,
        allow_cidrs=settings.geoip_allow_cidrs,
        deny_cidrs=settings.geoip_deny_cidrs,
    )
    typer.echo(
        json.dumps(
            {
                "ip": decision.client_ip,
                "action": decision.action,
                "reason": decision.reason,
                "country_code": decision.country_code,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@janitor_app.command("run")
def janitor_run() -> None:
    """Run one upload-session janitor pass (T-203c, doc lines ~519-525).

    Aborts unfinished multipart uploads past ``expires_at`` and marks those
    sessions expired/cancelled; transitions stored-but-unregistered sessions past
    the registration deadline to ``registration_expired``. RustFS objects that
    finished storing are never auto-deleted. The pass runs under the
    ``SOURCE_JANITOR`` advisory lock and skips if another holds it.
    """

    async def run() -> None:
        async with AsyncAddressClient() as client:
            summary = await client.run_source_upload_janitor()
            typer.echo(summary.model_dump_json())

    asyncio.run(run())


@app.command("init-db")
def init_db() -> None:
    """Create schema, extensions, indexes, and empty MV via SCHEMA_SQL + INDEX_SQL + MV_SQL."""
    from sqlalchemy import text as sa_text

    from kortravelgeo.infra.sql import INDEX_SQL, MV_SQL, SCHEMA_SQL, iter_sql_statements

    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client._engine() is not None
            warnings = 0

            async def operation() -> None:
                nonlocal warnings
                for sql in iter_sql_statements(SCHEMA_SQL):
                    async with client._engine().begin() as conn:
                        await conn.execute(sa_text(sql))

                for sql in iter_sql_statements(INDEX_SQL):
                    try:
                        async with client._engine().begin() as conn:
                            await conn.execute(sa_text(sql))
                    except Exception as exc:
                        warnings += 1
                        typer.echo(f"  index warning (may already exist): {exc}")

                for sql in iter_sql_statements(MV_SQL):
                    try:
                        async with client._engine().begin() as conn:
                            await conn.execute(sa_text(sql))
                    except Exception as exc:
                        warnings += 1
                        typer.echo(f"  mv warning (may already exist): {exc}")

            await _run_with_cli_lock(
                client._engine(),
                _global_lock(AdvisoryLockNamespace.INIT_DB),
                operation,
            )

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
            assert client._engine() is not None
            count = await _run_with_cli_lock(
                client._engine(),
                _path_lock(AdvisoryLockNamespace.LOAD_JUSO_TEXT, path),
                lambda: load_juso_hangul(client._engine(), path, source_yyyymm=yyyymm),
            )
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
            assert client._engine() is not None
            result = await _run_with_cli_lock(
                client._engine(),
                _path_lock(AdvisoryLockNamespace.LOAD_DAILY_JUSO, path),
                lambda: load_daily_juso_delta(
                    client._engine(),
                    path,
                    source_yyyymm=yyyymm,
                    limit_per_file=limit_per_file,
                ),
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
            assert client._engine() is not None
            result = await _run_with_cli_lock(
                client._engine(),
                _path_lock(AdvisoryLockNamespace.LOAD_PARCEL_LINK, path),
                lambda: load_juso_parcel_link_snapshot(
                    client._engine(),
                    path,
                    source_yyyymm=yyyymm,
                    limit_per_file=limit_per_file,
                    replace=not append,
                ),
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
            assert client._engine() is not None
            result = await _run_with_cli_lock(
                client._engine(),
                _path_lock(AdvisoryLockNamespace.LOAD_DAILY_PARCEL, path),
                lambda: load_daily_parcel_link_delta(
                    client._engine(),
                    path,
                    source_yyyymm=yyyymm,
                    limit_per_file=limit_per_file,
                ),
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
            assert client._engine() is not None
            result = await _run_with_cli_lock(
                client._engine(),
                _path_lock(AdvisoryLockNamespace.LOAD_ROADADDR_ENTRANCES, path),
                lambda: load_roadaddr_entrances(
                    client._engine(),
                    path,
                    source_yyyymm=yyyymm,
                    limit_per_file=limit_per_file,
                    replace=not append,
                ),
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
            assert client._engine() is not None
            count = await _run_with_cli_lock(
                client._engine(),
                _path_lock(AdvisoryLockNamespace.LOAD_LOCSUM, path),
                lambda: load_locsum(client._engine(), path, source_yyyymm=yyyymm),
            )
            typer.echo(f"loaded tl_locsum_entrc rows: {count}")

    asyncio.run(run())


@load_app.command("navi")
def load_navi_command(path: Path, yyyymm: str | None = typer.Option(None, "--yyyymm")) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client._engine() is not None
            build_count, entrance_count = await _run_with_cli_lock(
                client._engine(),
                _path_lock(AdvisoryLockNamespace.LOAD_NAVI, path),
                lambda: load_navi(client._engine(), path, source_yyyymm=yyyymm),
            )
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
            assert client._engine() is not None

            async def operation() -> int:
                count = await load_shp_polygons(
                    client._engine(),
                    path,
                    mode=mode,
                    source_yyyymm=yyyymm,
                )
                await refresh_region_radius_parts(client._engine())
                return count

            count = await _run_with_cli_lock(
                client._engine(),
                _path_lock(_shp_namespace(mode), path),
                operation,
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
            assert client._engine() is not None

            async def operation() -> None:
                nonlocal total
                items = _shp_all_work_items(root, mode)
                for index, (sido_dir, effective_mode) in enumerate(items):
                    count = await load_shp_polygons(
                        client._engine(),
                        sido_dir,
                        mode=effective_mode,
                        source_yyyymm=yyyymm,
                        analyze=index == len(items) - 1,
                    )
                    total += count
                    typer.echo(f"{sido_dir.name}: {count} layers")
                await refresh_region_radius_parts(client._engine())

            await _run_with_cli_lock(
                client._engine(),
                _path_lock(_shp_namespace(mode), root),
                operation,
            )
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
            assert client._engine() is not None
            count = await _run_with_cli_lock(
                client._engine(),
                _path_lock(AdvisoryLockNamespace.LOAD_SPPN_MAKAREA, path),
                lambda: load_sppn_makarea(
                    client._engine(),
                    path,
                    mode=mode,
                    source_yyyymm=yyyymm,
                ),
            )
            typer.echo(f"loaded tl_sppn_makarea rows: {count}")

    asyncio.run(run())


@load_app.command("pobox")
def load_pobox_command(path: Path) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client._engine() is not None
            count = await _run_with_cli_lock(
                client._engine(),
                _path_lock(AdvisoryLockNamespace.LOAD_POBOX, path),
                lambda: load_pobox(client._engine(), path),
            )
            typer.echo(f"loaded postal_pobox rows: {count}")

    asyncio.run(run())


@load_app.command("bulk")
def load_bulk_command(path: Path) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client._engine() is not None
            count = await _run_with_cli_lock(
                client._engine(),
                _path_lock(AdvisoryLockNamespace.LOAD_BULK, path),
                lambda: load_bulk_delivery(client._engine(), path),
            )
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
    epost_lock_resource = source or output_dir.expanduser().resolve(strict=False)

    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client._engine() is not None

            async def operation() -> None:
                if kind != "full":
                    typer.echo(
                        "only --kind=full is supported for epost dataset 15000302",
                        err=True,
                    )
                    raise typer.Exit(2)
                resolved = source
                if resolved is None:
                    resolved = await download_epost_zip(
                        get_settings(),
                        output_dir,
                        download_kind="1",
                    )
                    typer.echo(f"downloaded epost ZIP: {resolved}")
                if resolved.suffix.lower() == ".zip":
                    resolved = extract_epost_zip(resolved, output_dir / resolved.stem)
                    typer.echo(f"extracted epost ZIP: {resolved}")
                pobox_file, bulk_file = discover_epost_files(resolved)
                if pobox_file is not None:
                    count = await load_pobox(client._engine(), pobox_file)
                    typer.echo(f"loaded postal_pobox rows: {count}")
                if bulk_file is not None:
                    count = await load_bulk_delivery(client._engine(), bulk_file)
                    typer.echo(f"loaded postal_bulk_delivery rows: {count}")
                if pobox_file is None and bulk_file is None:
                    typer.echo("no pobox/bulk text files found in epost dataset", err=True)
                    raise typer.Exit(2)

            await _run_with_cli_lock(
                client._engine(),
                _value_lock(
                    AdvisoryLockNamespace.LOAD_EPOST,
                    epost_lock_resource,
                ),
                operation,
            )

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
    full_batch_lock_resource = "|".join(
        str(path.expanduser().resolve(strict=False))
        for path in (juso_path, jibun_path or juso_path, locsum_path, navi_path)
    )

    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client._engine() is not None

            async def operation() -> None:
                juso_count = await load_juso_hangul(
                    client._engine(),
                    juso_path,
                    source_yyyymm=yyyymm,
                )
                typer.echo(f"loaded tl_juso_text rows: {juso_count}")
                parcel_result = await load_juso_parcel_link_snapshot(
                    client._engine(),
                    jibun_path or juso_path,
                    source_yyyymm=yyyymm,
                )
                typer.echo(f"loaded tl_juso_parcel_link rows: {parcel_result.upserted_rows}")
                locsum_count = await load_locsum(
                    client._engine(),
                    locsum_path,
                    source_yyyymm=yyyymm,
                )
                typer.echo(f"loaded tl_locsum_entrc rows: {locsum_count}")
                build_count, entrance_count = await load_navi(
                    client._engine(),
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
                            client._engine(),
                            sido_dir,
                            mode=_shp_mode_for_index("full", index),
                            source_yyyymm=yyyymm,
                            analyze=index == len(sido_dirs) - 1,
                        )
                    typer.echo(f"loaded SHP layers total: {shp_total}")
                    await refresh_region_radius_parts(client._engine())
                if pobox_path is not None:
                    count = await load_pobox(client._engine(), pobox_path)
                    typer.echo(f"loaded postal_pobox rows: {count}")
                if bulk_path is not None:
                    typer.echo(
                        f"loaded postal_bulk_delivery rows: "
                        f"{await load_bulk_delivery(client._engine(), bulk_path)}"
                    )
                await resolve_text_geometry_links(client._engine())
                report = await run_all_cases(client._engine(), generated_by="cli")
                typer.echo(report.model_dump_json())
                if report.severity_max == "ERROR" and not allow_consistency_error:
                    raise typer.Exit(2)
                if refresh:
                    await refresh_mv(
                        client._engine(),
                        concurrently=not swap,
                        strategy="swap" if swap else "concurrent",
                    )
                    typer.echo("refreshed mv_geocode_target")

            await _run_with_cli_lock(
                client._engine(),
                _value_lock(
                    AdvisoryLockNamespace.LOAD_FULL_BATCH,
                    full_batch_lock_resource,
                ),
                operation,
            )

    asyncio.run(run())


@refresh_app.command("mv")
def refresh_materialized_view(
    concurrently: bool = typer.Option(True, "--concurrently/--no-concurrently"),
    swap: bool = typer.Option(False, "--swap", help="Build shadow MV and rename-swap."),
) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client._engine() is not None
            async def operation() -> str:
                await refresh_mv(
                    client._engine(),
                    concurrently=concurrently and not swap,
                    strategy="swap" if swap else "concurrent",
                )
                _, release = await AdminRepository(client._engine()).record_mv_refresh_release(
                    strategy="swap" if swap else "concurrent",
                    notes="CLI refresh mv",
                )
                return release.release_id

            release_id = await _run_with_cli_lock(
                client._engine(),
                _global_lock(AdvisoryLockNamespace.MV_REFRESH),
                operation,
            )
            typer.echo(f"refreshed mv_geocode_target; release={release_id}")

    asyncio.run(run())


@validate_app.command("consistency")
def validate_consistency(
    cases: str | None = typer.Option(None, "--cases", help="Comma-separated case codes."),
    scope: str = typer.Option("full", "--scope"),
) -> None:
    async def run() -> None:
        async with AsyncAddressClient() as client:
            assert client._engine() is not None
            selected = tuple(part.strip() for part in cases.split(",")) if cases else DEFAULT_CASES
            report = await _run_with_cli_lock(
                client._engine(),
                _value_lock(AdvisoryLockNamespace.CONSISTENCY_RUN, f"{scope}:{','.join(selected)}"),
                lambda: run_all_cases(
                    client._engine(),
                    scope=scope,
                    cases=selected,
                    generated_by="cli",
                ),
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
            assert client._engine() is not None
            paths = await export_data_quality_samples(
                client._engine(),
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
            assert client._engine() is not None
            await _run_with_cli_lock(
                client._engine(),
                _global_lock(AdvisoryLockNamespace.BACKUP_CREATE),
                lambda: run_backup_job(
                    client._engine(),
                    client.settings,
                    payload,
                    asyncio.Event(),
                    _cli_progress,
                ),
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
            assert client._engine() is not None
            await _run_with_cli_lock(
                client._engine(),
                _value_lock(
                    AdvisoryLockNamespace.RESTORE_CREATE,
                    target_database or target_dsn or artifact_id or archive_path or "default",
                ),
                lambda: run_restore_job(
                    client._engine(),
                    client.settings,
                    payload,
                    asyncio.Event(),
                    _cli_progress,
                ),
            )

    asyncio.run(run())


@serving_app.command("hot-swap-plan")
def serving_hot_swap_plan(
    restore_database: str = typer.Option(..., "--restore-db"),
    previous_alias: str | None = typer.Option(None, "--previous-alias"),
    previous_alias_retention_days: int = typer.Option(
        7,
        "--previous-alias-retention-days",
        min=1,
        max=3650,
    ),
    maintenance_database: str = typer.Option("postgres", "--maintenance-db"),
) -> None:
    """Print a restore hot-swap preflight plan without executing ALTER DATABASE."""

    from kortravelgeo.dto.admin import RestoreHotSwapPlanRequest

    async def run() -> None:
        req = RestoreHotSwapPlanRequest(
            restore_database=restore_database,
            previous_alias=previous_alias,
            previous_alias_retention_days=previous_alias_retention_days,
            maintenance_database=maintenance_database,
        )
        async with AsyncAddressClient() as client:
            typer.echo((await client.restore_hot_swap_plan(req)).model_dump_json())

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
