"""Database backup/restore helpers for long-running admin jobs."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from kortravelgeo.core.redaction import hash_confirmation
from kortravelgeo.dto.admin import (
    BackupCreateRequest,
    OpsArtifact,
    RestoreCreateRequest,
)
from kortravelgeo.exceptions import InvalidInputError, NotFoundError
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.settings import Settings
from kortravelgeo.version import __version__

BACKUP_ARTIFACT_TYPE = "db_backup"
RESTORE_LOG_ARTIFACT_TYPE = "db_restore_log"
BACKUP_MEDIA_TYPE = "application/x-tar"
DEFAULT_BACKUP_DISPLAY_PREFIX = "kor_travel_geo_backup"
ROW_COUNT_OBJECTS = (
    "tl_juso_text",
    "tl_juso_parcel_link",
    "tl_locsum_entrc",
    "tl_roadaddr_entrc",
    "tl_navi_buld_centroid",
    "tl_navi_entrc",
    "tl_spbd_buld_polygon",
    "tl_spbd_eqb",
    "mv_geocode_target",
    "mv_geocode_text_search",
)


class ProgressReporter(Protocol):
    async def __call__(
        self,
        *,
        progress: float | None = None,
        stage: str | None = None,
        message: str | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class PreparedCommand:
    argv: tuple[str, ...]
    safe_argv: tuple[str, ...]
    env: Mapping[str, str] | None = None


@dataclass(frozen=True)
class CallbackDeliveryResult:
    state: str
    attempts: int
    callback_ids: tuple[str, ...]
    last_error: str | None = None


@dataclass(frozen=True)
class SizeProgressSample:
    current_bytes: int
    total_bytes: int | None = None


@dataclass
class SizeProgressProbe:
    path: Path
    label: str
    total_bytes: int | None = None
    emit_interval_s: float = 5.0
    sample_interval_s: float | None = None
    _last_emit_at: float = field(default=0.0, init=False, repr=False)
    _last_sample_at: float = field(default=0.0, init=False, repr=False)
    _last_sample: SizeProgressSample | None = field(default=None, init=False, repr=False)

    def sample(self, *, force: bool = False) -> SizeProgressSample:
        now = monotonic()
        interval = (
            self.emit_interval_s if self.sample_interval_s is None else self.sample_interval_s
        )
        if (
            not force
            and self._last_sample is not None
            and interval > 0
            and now - self._last_sample_at < interval
        ):
            return self._last_sample
        sample = SizeProgressSample(
            current_bytes=path_size_bytes(self.path),
            total_bytes=self.total_bytes,
        )
        self._last_sample = sample
        self._last_sample_at = now
        return sample

    def maybe_message(self, sample: SizeProgressSample, *, force: bool = False) -> str | None:
        now = monotonic()
        if not force and now - self._last_emit_at < self.emit_interval_s:
            return None
        self._last_emit_at = now
        if sample.total_bytes and sample.total_bytes > 0:
            return (
                f"{self.label} {format_bytes(sample.current_bytes)}"
                f"/{format_bytes(sample.total_bytes)}"
            )
        return f"{self.label} {format_bytes(sample.current_bytes)}"


async def run_backup_job(
    engine: AsyncEngine,
    settings: Settings,
    payload: dict[str, Any],
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
) -> None:
    req = BackupCreateRequest.model_validate(payload)
    callback_url = validate_callback_url(req.callback_url, settings.backup_callback_allowed_hosts)
    destination_dir = resolve_backup_destination(req.destination_dir, settings)
    jobs = req.jobs or settings.backup_default_jobs
    compression_level = req.compression_level or settings.backup_default_compression_level
    job_id = _payload_job_id(payload)
    artifact_id = str(uuid4())
    display_name = req.display_name or default_backup_filename(compression_level=compression_level)
    archive_path = safe_artifact_path(destination_dir, display_name)
    partial_archive_path = archive_path.with_name(f"{archive_path.name}.part")
    work_dir = (settings.backup_temp_dir / f"backup_{artifact_id}").resolve()
    dump_dir = work_dir / "dump"
    log_dir = work_dir / "logs"
    log_path = log_dir / "backup-job.ndjson"
    repo = AdminRepository(engine)
    artifact = await repo.insert_artifact(
        artifact_id=artifact_id,
        artifact_type=BACKUP_ARTIFACT_TYPE,
        state="creating",
        storage_kind="local_file",
        storage_uri=str(archive_path),
        display_name=archive_path.name,
        media_type=BACKUP_MEDIA_TYPE,
        compression="zstd",
        job_id=job_id,
        manifest={
            "artifact_schema_version": 1,
            "backup": {
                "format": req.format,
                "profile": req.profile,
                "jobs": jobs,
                "compression_level": compression_level,
            },
        },
        callback_url=callback_url,
        callback_state="pending" if callback_url else None,
    )
    try:
        await progress(progress=0.02, stage="preflight", message="backup preflight 시작")
        _preflight_backup_tools()
        _ensure_not_cancelled(cancel_event)
        destination_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(destination_dir, 0o700)
        work_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(work_dir, 0o700)
        dump_dir.mkdir()
        log_dir.mkdir()
        partial_archive_path.unlink(missing_ok=True)

        manifest = await build_backup_manifest(
            engine,
            settings=settings,
            req=req,
            artifact_id=artifact.artifact_id,
            jobs=jobs,
            compression_level=compression_level,
        )
        dump_cmd = build_pg_dump_command(
            settings.pg_dsn,
            dump_dir,
            profile=req.profile,
            jobs=jobs,
            include_materialized_views=req.include_materialized_views,
        )
        await progress(
            progress=0.05,
            stage="dump",
            message=f"pg_dump 시작: {' '.join(dump_cmd.safe_argv)}",
        )
        await run_process_with_progress(
            dump_cmd,
            cancel_event=cancel_event,
            progress=progress,
            stage="dump",
            bounds=(0.05, 0.65),
            log_path=log_path,
            size_probe=SizeProgressProbe(dump_dir, "dump 디렉터리"),
        )
        manifest_path = work_dir / "manifest.json"
        write_json(manifest_path, manifest)
        checksums_path = work_dir / "checksums.sha256"
        await progress(
            progress=0.65,
            stage="dump",
            message=f"dump checksum 생성 시작: {format_bytes(path_size_bytes(dump_dir))}",
        )
        await write_checksums(
            checksums_path,
            roots=(manifest_path, dump_dir),
            base_dir=work_dir,
            cancel_event=cancel_event,
            progress=progress,
            bounds=(0.65, 0.70),
        )

        archive_input_bytes = path_size_bytes(work_dir)
        tar_cmd = build_tar_create_command(
            partial_archive_path,
            work_dir,
            compression_level=compression_level,
        )
        await progress(
            progress=0.70,
            stage="archive",
            message=(
                f"archive 생성 시작: {' '.join(tar_cmd.safe_argv)} "
                f"(입력 {format_bytes(archive_input_bytes)})"
            ),
        )
        await run_process_with_progress(
            tar_cmd,
            cancel_event=cancel_event,
            progress=progress,
            stage="archive",
            bounds=(0.70, 0.90),
            log_path=log_path,
            size_probe=SizeProgressProbe(
                partial_archive_path,
                "archive 파일",
                total_bytes=archive_input_bytes,
            ),
        )
        os.chmod(partial_archive_path, 0o600)

        await progress(progress=0.90, stage="checksum", message="archive sha256 계산")
        archive_sha256 = await sha256_file(
            partial_archive_path,
            cancel_event=cancel_event,
            progress=progress,
            bounds=(0.90, 0.97),
        )
        size_bytes = partial_archive_path.stat().st_size
        partial_archive_path.replace(archive_path)
        os.chmod(archive_path, 0o600)
        manifest["checksums"] = {"archive_sha256": archive_sha256}
        manifest["artifact"] = {
            "artifact_id": artifact.artifact_id,
            "storage_uri": str(archive_path),
            "size_bytes": size_bytes,
            "sha256": archive_sha256,
        }

        await progress(progress=0.97, stage="finalize", message="artifact metadata 저장")
        updated_artifact = await repo.update_artifact(
            artifact.artifact_id,
            state="available",
            size_bytes=size_bytes,
            sha256=archive_sha256,
            manifest=manifest,
            finished=True,
        )
        if updated_artifact is None:
            msg = f"backup artifact disappeared: {artifact.artifact_id}"
            raise RuntimeError(msg)
        artifact = updated_artifact
        callback_result = await deliver_callback(
            artifact,
            settings=settings,
            event="db_backup.done",
        )
        if callback_result is not None:
            await record_callback_delivery(repo, artifact, callback_result)
        await progress(progress=1.0, stage="finalize", message=f"backup 완료: {archive_path}")
    except asyncio.CancelledError:
        await repo.update_artifact(
            artifact.artifact_id,
            state="failed",
            manifest={"error": "cancelled"},
            finished=True,
        )
        raise
    except Exception as exc:
        failed = await repo.update_artifact(
            artifact.artifact_id,
            state="failed",
            manifest={"error": str(exc)},
            finished=True,
        )
        if failed is not None:
            callback_result = await deliver_callback(
                failed,
                settings=settings,
                event="db_backup.failed",
            )
            if callback_result is not None:
                await record_callback_delivery(repo, failed, callback_result)
        raise
    finally:
        partial_archive_path.unlink(missing_ok=True)
        shutil.rmtree(work_dir, ignore_errors=True)


async def run_restore_job(
    engine: AsyncEngine,
    settings: Settings,
    payload: dict[str, Any],
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
) -> None:
    req = RestoreCreateRequest.model_validate(payload)
    callback_url = validate_callback_url(req.callback_url, settings.backup_callback_allowed_hosts)
    jobs = req.jobs or settings.backup_default_jobs
    repo = AdminRepository(engine)
    archive_path, source_artifact = await resolve_restore_archive(req, repo, settings)
    target_dsn = resolve_restore_target_dsn(req, settings)
    target_database = database_name_from_dsn(target_dsn)
    if target_database is None:
        msg = "restore target database name could not be resolved"
        raise InvalidInputError(msg)
    if req.mode == "replace_current":
        confirmation = validate_replace_current_restore_request(
            req,
            settings=settings,
            target_database=target_database,
        )
        window = await repo.require_active_maintenance_window(
            kind="restore",
            confirmation=confirmation,
        )
        await repo.record_audit_event(
            action="maintenance_window.authorize",
            actor_type="system",
            outcome="succeeded",
            payload={
                "kind": "restore",
                "mode": req.mode,
                "target_database": target_database,
                "confirmation_hash": hash_confirmation(confirmation),
                "source_artifact_id": source_artifact.artifact_id if source_artifact else None,
            },
            resource_type="maintenance_window",
            resource_id=window.window_id,
            job_id=_payload_job_id(payload),
        )
    else:
        current_database = database_name_from_dsn(settings.pg_dsn)
        if current_database == target_database:
            msg = "restore target_database must differ from the current database"
            raise InvalidInputError(msg)
        await ensure_target_database_empty(target_dsn)

    artifact_id = str(uuid4())
    work_dir = (settings.backup_temp_dir / f"restore_{artifact_id}").resolve()
    extract_dir = work_dir / "extract"
    log_dir = work_dir / "logs"
    log_path = log_dir / "restore-job.ndjson"
    restore_artifact = await repo.insert_artifact(
        artifact_id=artifact_id,
        artifact_type=RESTORE_LOG_ARTIFACT_TYPE,
        state="creating",
        storage_kind="none",
        display_name=f"restore_{target_database}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        media_type="application/x-ndjson",
        job_id=_payload_job_id(payload),
        manifest={
            "source_artifact_id": source_artifact.artifact_id if source_artifact else None,
            "archive_path": str(archive_path),
            "target_database": target_database,
        },
        callback_url=callback_url,
        callback_state="pending" if callback_url else None,
    )
    try:
        await progress(progress=0.02, stage="preflight", message="restore preflight 시작")
        _preflight_restore_tools()
        await verify_archive_checksum(archive_path, source_artifact)
        work_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(work_dir, 0o700)
        extract_dir.mkdir()
        log_dir.mkdir()

        extract_cmd = build_tar_extract_command(archive_path, extract_dir)
        archive_size_bytes = archive_path.stat().st_size
        await progress(
            progress=0.05,
            stage="extract",
            message=f"archive 해제 시작: {format_bytes(archive_size_bytes)}",
        )
        await run_process_with_progress(
            extract_cmd,
            cancel_event=cancel_event,
            progress=progress,
            stage="extract",
            bounds=(0.05, 0.20),
            log_path=log_path,
            size_probe=SizeProgressProbe(
                extract_dir,
                "extract 디렉터리",
                total_bytes=archive_size_bytes,
            ),
        )
        manifest = read_json(extract_dir / "manifest.json")
        await verify_internal_checksums(extract_dir, cancel_event=cancel_event)
        dump_dir = extract_dir / "dump"
        if not dump_dir.is_dir():
            msg = f"restore archive does not contain dump directory: {archive_path}"
            raise InvalidInputError(msg)

        restore_cmd = build_pg_restore_command(
            target_dsn,
            dump_dir,
            jobs=jobs,
        )
        await progress(
            progress=0.20,
            stage="restore",
            message=(
                f"pg_restore 시작: {' '.join(restore_cmd.safe_argv)} "
                f"(dump {format_bytes(path_size_bytes(dump_dir))})"
            ),
        )
        await run_process_with_progress(
            restore_cmd,
            cancel_event=cancel_event,
            progress=progress,
            stage="restore",
            bounds=(0.20, 0.80),
            log_path=log_path,
        )
        if req.run_analyze:
            await progress(progress=0.80, stage="analyze", message="target DB ANALYZE 시작")
            await analyze_database(target_dsn)
        if req.run_smoke_test:
            await progress(progress=0.90, stage="validate", message="restore smoke test 시작")
            await smoke_test_restore(target_dsn)
        if req.run_consistency:
            await progress(
                progress=0.95,
                stage="validate",
                message="복원 후 consistency는 별도 target API 연결에서 수행해야 함",
            )
        restore_manifest = {
            "source_artifact_id": source_artifact.artifact_id if source_artifact else None,
            "archive_path": str(archive_path),
            "target_database": target_database,
            "source_manifest": manifest,
        }
        updated_restore_artifact = await repo.update_artifact(
            restore_artifact.artifact_id,
            state="available",
            manifest=restore_manifest,
            finished=True,
        )
        if updated_restore_artifact is None:
            msg = f"restore artifact disappeared: {restore_artifact.artifact_id}"
            raise RuntimeError(msg)
        restore_artifact = updated_restore_artifact
        await progress(
            progress=0.98,
            stage="finalize",
            message="restore snapshot/release 후보 기록",
        )
        snapshot, release = await repo.record_restore_candidate(
            restore_artifact_id=restore_artifact.artifact_id,
            target_database=target_database,
            source_manifest=manifest,
            source_artifact_id=source_artifact.artifact_id if source_artifact else None,
            job_id=_payload_job_id(payload),
        )
        relinked_restore_artifact = await repo.update_artifact(
            restore_artifact.artifact_id,
            snapshot_id=snapshot.snapshot_id,
            release_id=release.release_id,
            manifest={
                **restore_manifest,
                "snapshot_id": snapshot.snapshot_id,
                "release_id": release.release_id,
                "release_state": release.state,
            },
        )
        if relinked_restore_artifact is not None:
            restore_artifact = relinked_restore_artifact
        await progress(
            progress=0.99,
            stage="finalize",
            message="복원 후 source quick reconcile (재구성 가능성 검증)",
        )
        source_verification = await run_restore_source_verification(
            settings,
            target_dsn=target_dsn,
            entrypoint="pg_restore",
            actor=f"system:{_payload_job_id(payload) or 'db_restore'}",
        )
        if source_verification is not None:
            restore_manifest = {
                **restore_manifest,
                "source_verification": source_verification,
            }
            await repo.update_artifact(
                restore_artifact.artifact_id,
                manifest={
                    **restore_manifest,
                    "snapshot_id": snapshot.snapshot_id,
                    "release_id": release.release_id,
                    "release_state": release.state,
                },
            )
        callback_result = await deliver_callback(
            restore_artifact,
            settings=settings,
            event="db_restore.done",
        )
        if callback_result is not None:
            await record_callback_delivery(repo, restore_artifact, callback_result)
        await progress(progress=1.0, stage="finalize", message=f"restore 완료: {target_database}")
    except asyncio.CancelledError:
        await repo.update_artifact(
            restore_artifact.artifact_id,
            state="failed",
            manifest={"error": "cancelled"},
            finished=True,
        )
        raise
    except Exception as exc:
        failed = await repo.update_artifact(
            restore_artifact.artifact_id,
            state="failed",
            manifest={"error": str(exc)},
            finished=True,
        )
        if failed is not None:
            callback_result = await deliver_callback(
                failed,
                settings=settings,
                event="db_restore.failed",
            )
            if callback_result is not None:
                await record_callback_delivery(repo, failed, callback_result)
        raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


async def run_restore_source_verification(
    settings: Settings,
    *,
    target_dsn: str,
    entrypoint: str,
    actor: str | None,
) -> dict[str, Any] | None:
    """Run the post-restore source verification matrix (T-208, doc ~1896-1902).

    Shared by BOTH restore entrypoints — the ``pg_restore`` manifest restore (this
    module) and the ADR-036 rename hot-swap (CLI/serving path). Opens an engine on
    the restored target DB, resolves its active snapshot's ``source_match_set_id``,
    and runs ONE source ``quick`` reconcile against RustFS object availability. A
    legacy snapshot (no FK) skips the reconcile. RustFS being disabled makes this a
    no-op (verification only runs when storage is reachable). Returns the
    verification result as a dict for the restore manifest, or ``None``.
    """
    from kortravelgeo.infra.rustfs import RustfsClient, load_rustfs_config
    from kortravelgeo.infra.source_restore_service import verify_restore_source

    engine = create_async_engine(normalize_sqlalchemy_dsn(target_dsn))
    try:
        config = load_rustfs_config(settings)
        rustfs = (
            RustfsClient(config)
            if config.enabled and config.credentials_configured
            else None
        )
        try:
            result = await verify_restore_source(
                engine,
                entrypoint=entrypoint,  # type: ignore[arg-type]
                rustfs=rustfs,
                actor=actor,
                rolling_deep_days=settings.source_reconcile_rolling_deep_days,
                object_limit=settings.source_reconcile_object_limit,
            )
        except Exception:  # source verification must never fail the restore itself
            return None
    finally:
        await engine.dispose()
    return result.model_dump()


def default_backup_filename(*, compression_level: int) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{DEFAULT_BACKUP_DISPLAY_PREFIX}_{timestamp}_zstd{compression_level}.tar.zst"


def resolve_backup_destination(destination_dir: str | None, settings: Settings) -> Path:
    roots = allowed_backup_roots(settings)
    if not roots:
        msg = "KTG_BACKUP_ALLOWED_DIRS must contain at least one directory"
        raise InvalidInputError(msg)
    if destination_dir:
        raw = Path(destination_dir).expanduser()
        candidate = raw if raw.is_absolute() else roots[0] / raw
    else:
        candidate = roots[0]
    resolved = candidate.resolve(strict=False)
    if not any(_is_relative_to(resolved, root) for root in roots):
        joined = ", ".join(str(root) for root in roots)
        msg = f"backup destination escapes allowed roots: {resolved}; allowed={joined}"
        raise InvalidInputError(msg)
    return resolved


def resolve_existing_archive_path(path: str, settings: Settings) -> Path:
    roots = allowed_backup_roots(settings)
    candidate = Path(path).expanduser().resolve(strict=True)
    if not any(_is_relative_to(candidate, root) for root in roots):
        msg = f"restore archive escapes allowed roots: {candidate}"
        raise InvalidInputError(msg)
    if not candidate.is_file():
        msg = f"restore archive is not a file: {candidate}"
        raise InvalidInputError(msg)
    return candidate


def allowed_backup_roots(settings: Settings) -> tuple[Path, ...]:
    return tuple(path.expanduser().resolve(strict=False) for path in settings.backup_allowed_dirs)


def safe_artifact_path(destination_dir: Path, display_name: str) -> Path:
    safe_name = Path(display_name).name
    if not safe_name.endswith(".tar.zst"):
        safe_name = f"{safe_name}.tar.zst"
    candidate = (destination_dir / safe_name).resolve(strict=False)
    if not _is_relative_to(candidate, destination_dir.resolve(strict=False)):
        msg = f"backup artifact path escapes destination: {display_name}"
        raise InvalidInputError(msg)
    if candidate.exists():
        stem = candidate.name.removesuffix(".tar.zst")
        candidate = candidate.with_name(f"{stem}_{uuid4().hex[:8]}.tar.zst")
    return candidate


def validate_callback_url(url: str | None, allowed_hosts: tuple[str, ...]) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        msg = "callback_url must be an http(s) URL"
        raise InvalidInputError(msg)
    allowed = {host.lower() for host in allowed_hosts}
    if parsed.hostname.lower() not in allowed:
        msg = f"callback host is not allowed: {parsed.hostname}"
        raise InvalidInputError(msg)
    return url


def build_pg_dump_command(
    dsn: str,
    dump_dir: Path,
    *,
    profile: str,
    jobs: int,
    include_materialized_views: bool = True,
) -> PreparedCommand:
    libpq_dsn, env = to_process_safe_libpq_dsn(dsn)
    argv: list[str] = [
        "pg_dump",
        "--format=directory",
        f"--jobs={jobs}",
        "--verbose",
        "--file",
        str(dump_dir),
        "--dbname",
        libpq_dsn,
    ]
    if profile == "lean-serving":
        argv.append("--exclude-table-data=geo_cache")
    if not include_materialized_views:
        argv.append("--exclude-table-data=mv_geocode_target")
        argv.append("--exclude-table-data=mv_geocode_text_search")
    return PreparedCommand(tuple(argv), tuple(redact_command(argv)), env or None)


def build_pg_restore_command(
    target_dsn: str,
    dump_dir: Path,
    *,
    jobs: int,
) -> PreparedCommand:
    libpq_dsn, env = to_process_safe_libpq_dsn(target_dsn)
    argv = [
        "pg_restore",
        "--format=directory",
        f"--jobs={jobs}",
        "--verbose",
        "--dbname",
        libpq_dsn,
        str(dump_dir),
    ]
    return PreparedCommand(tuple(argv), tuple(redact_command(argv)), env or None)


def build_tar_create_command(
    archive_path: Path,
    work_dir: Path,
    *,
    compression_level: int,
) -> PreparedCommand:
    argv = [
        "tar",
        f"--use-compress-program=zstd -T0 -{compression_level}",
        "-cf",
        str(archive_path),
        "-C",
        str(work_dir),
        "manifest.json",
        "checksums.sha256",
        "logs",
        "dump",
    ]
    return PreparedCommand(tuple(argv), tuple(argv))


def build_tar_extract_command(archive_path: Path, extract_dir: Path) -> PreparedCommand:
    argv = [
        "tar",
        "--use-compress-program=zstd",
        "-xf",
        str(archive_path),
        "-C",
        str(extract_dir),
    ]
    return PreparedCommand(tuple(argv), tuple(argv))


def redact_command(argv: list[str] | tuple[str, ...]) -> list[str]:
    redacted: list[str] = []
    redact_next = False
    for item in argv:
        if redact_next:
            redacted.append(redact_dsn(item))
            redact_next = False
            continue
        redacted.append(item)
        if item == "--dbname":
            redact_next = True
    return redacted


def to_libpq_dsn(dsn: str) -> str:
    url = make_url(dsn)
    if url.drivername.startswith("postgresql+"):
        url = url.set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


def to_process_safe_libpq_dsn(dsn: str) -> tuple[str, dict[str, str]]:
    url = make_url(dsn)
    if url.drivername.startswith("postgresql+"):
        url = url.set(drivername="postgresql")
    env: dict[str, str] = {}
    if url.password:
        env["PGPASSWORD"] = url.password
        url = URL.create(
            url.drivername,
            username=url.username,
            host=url.host,
            port=url.port,
            database=url.database,
            query=url.query,
        )
    return url.render_as_string(hide_password=False), env


def normalize_sqlalchemy_dsn(dsn: str) -> str:
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    return dsn


def redact_dsn(dsn: str) -> str:
    try:
        url = make_url(dsn)
    except Exception:
        return dsn
    if url.drivername.startswith("postgresql+"):
        url = url.set(drivername="postgresql")
    return url.render_as_string(hide_password=True)


def database_name_from_dsn(dsn: str) -> str | None:
    try:
        return make_url(dsn).database
    except Exception:
        return None


def resolve_restore_target_dsn(req: RestoreCreateRequest, settings: Settings) -> str:
    if req.target_dsn:
        return normalize_sqlalchemy_dsn(req.target_dsn)
    if not req.target_database:
        msg = "restore requires target_database or target_dsn"
        raise InvalidInputError(msg)
    current = make_url(settings.pg_dsn)
    return current.set(database=req.target_database).render_as_string(hide_password=False)


def validate_replace_current_restore_request(
    req: RestoreCreateRequest,
    *,
    settings: Settings,
    target_database: str,
) -> str:
    current_database = database_name_from_dsn(settings.pg_dsn)
    if current_database is None:
        msg = "current database name could not be resolved"
        raise InvalidInputError(msg)
    if req.target_dsn is not None:
        msg = "replace_current requires target_database, not target_dsn"
        raise InvalidInputError(msg)
    if req.target_database != current_database or target_database != current_database:
        msg = "replace_current target_database must match the current database"
        raise InvalidInputError(msg)
    expected = f"RESTORE {current_database}"
    if req.confirmation != expected:
        msg = f"replace_current requires confirmation: {expected}"
        raise InvalidInputError(msg)
    return expected


async def resolve_restore_archive(
    req: RestoreCreateRequest,
    repo: AdminRepository,
    settings: Settings,
) -> tuple[Path, OpsArtifact | None]:
    if req.artifact_id:
        artifact = await repo.get_artifact(req.artifact_id)
        if artifact is None or artifact.artifact_type != BACKUP_ARTIFACT_TYPE:
            raise NotFoundError(f"backup artifact not found: {req.artifact_id}")
        if artifact.state != "available" or not artifact.storage_uri:
            msg = f"backup artifact is not downloadable: {req.artifact_id}"
            raise InvalidInputError(msg)
        return resolve_existing_archive_path(artifact.storage_uri, settings), artifact
    if req.archive_path:
        return resolve_existing_archive_path(req.archive_path, settings), None
    msg = "restore requires artifact_id or archive_path"
    raise InvalidInputError(msg)


async def build_backup_manifest(
    engine: AsyncEngine,
    *,
    settings: Settings,
    req: BackupCreateRequest,
    artifact_id: str,
    jobs: int,
    compression_level: int,
) -> dict[str, Any]:
    async with engine.connect() as conn:
        db = (
            await conn.execute(
                text(
                    """
SELECT current_database() AS name,
       current_setting('server_version') AS postgres_version,
       pg_database_size(current_database())::bigint AS database_size_bytes,
       (SELECT extversion FROM pg_extension WHERE extname = 'postgis') AS postgis_version
"""
                )
            )
        ).mappings().one()
        row_counts = await collect_row_counts(conn)
    return {
        "artifact_schema_version": 1,
        "artifact_id": artifact_id,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "app_version": __version__,
        "git_commit": os.environ.get("KTG_GIT_COMMIT", "unknown"),
        "database": {
            "name": db["name"],
            "postgres_version": db["postgres_version"],
            "postgis_version": db["postgis_version"],
            "database_size_bytes": int(db["database_size_bytes"] or 0),
        },
        "backup": {
            "format": req.format,
            "compression": "zstd",
            "compression_level": compression_level,
            "jobs": jobs,
            "profile": req.profile,
            "include_materialized_views": req.include_materialized_views,
            "exclude_table_data": _excluded_table_data(req),
            "retention_days": req.retention_days or settings.backup_artifact_ttl_days,
        },
        "source_set": await infer_source_set(engine),
        "source_match_set": await _infer_source_match_set_block(engine),
        "row_counts": row_counts,
        "checksums": {},
}


async def _infer_source_match_set_block(engine: AsyncEngine) -> dict[str, Any] | None:
    """Active match set manifest block (T-208, doc ~1848-1886), or ``None``.

    Records "what source archives reconstruct this DB" — the active match set's
    id/name/profile/``source_set_hash``/``yyyymm_by_category`` + per-category group
    with per-file ``sha256``/``size_bytes``/``object_key``/``storage_uri`` +
    ``omitted_optional`` — WITHOUT copying the archives. ``None`` when there is no
    active match set (a legacy / fresh DB).
    """
    from kortravelgeo.infra.source_restore_service import read_active_match_set_block

    block = await read_active_match_set_block(engine)
    return block.as_manifest() if block is not None else None


def _excluded_table_data(req: BackupCreateRequest) -> list[str]:
    excluded: list[str] = []
    if req.profile == "lean-serving":
        excluded.append("geo_cache")
    if not req.include_materialized_views:
        excluded.extend(["mv_geocode_target", "mv_geocode_text_search"])
    return excluded


async def collect_row_counts(conn: Any) -> dict[str, int]:
    row_counts: dict[str, int] = {}
    for name in ROW_COUNT_OBJECTS:
        exists = await conn.scalar(text("SELECT to_regclass(:name)"), {"name": f"public.{name}"})
        if exists is None:
            continue
        count = await conn.scalar(text(f"SELECT count(*)::bigint FROM public.{name}"))
        row_counts[name] = int(count or 0)
    return row_counts


async def infer_source_set(engine: AsyncEngine) -> dict[str, Any]:
    tables = {
        "juso": "tl_juso_text",
        "parcel_link": "tl_juso_parcel_link",
        "locsum": "tl_locsum_entrc",
        "navi": "tl_navi_buld_centroid",
        "shp": "tl_spbd_buld_polygon",
        "roadaddr_entrance": "tl_roadaddr_entrc",
    }
    yyyymm_by_kind: dict[str, str | None] = {}
    async with engine.connect() as conn:
        for kind, table_name in tables.items():
            exists = await conn.scalar(
                text("SELECT to_regclass(:name)"),
                {"name": f"public.{table_name}"},
            )
            if exists is None:
                yyyymm_by_kind[kind] = None
                continue
            value = await conn.scalar(
                text(f"SELECT max(source_yyyymm) FROM public.{table_name}")
            )
            yyyymm_by_kind[kind] = str(value) if value is not None else None
    values = {value for value in yyyymm_by_kind.values() if value}
    return {
        "yyyymm_by_kind": yyyymm_by_kind,
        "mixed_yyyymm": len(values) > 1,
    }


async def run_process_with_progress(
    cmd: PreparedCommand,
    *,
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
    stage: str,
    bounds: tuple[float, float],
    log_path: Path,
    size_probe: SizeProgressProbe | None = None,
) -> None:
    with log_path.open("a", encoding="utf-8") as log_file:
        _write_log(log_file, stage=stage, message=f"exec: {' '.join(cmd.safe_argv)}")
        process = await asyncio.create_subprocess_exec(
            *cmd.argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, **(cmd.env or {})},
        )
        assert process.stdout is not None
        line_count = 0
        while True:
            if cancel_event.is_set():
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=10)
                except TimeoutError:
                    process.kill()
                    await process.wait()
                raise asyncio.CancelledError
            try:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=1)
            except TimeoutError:
                if process.returncode is not None:
                    break
                sample = size_probe.sample() if size_probe is not None else None
                await progress(
                    progress=_estimated_progress(bounds, line_count, sample),
                    stage=stage,
                    message=(
                        size_probe.maybe_message(sample)
                        if size_probe is not None and sample is not None
                        else None
                    ),
                )
                continue
            if not line:
                if process.returncode is not None or process.stdout.at_eof():
                    break
                continue
            line_count += 1
            decoded = line.decode("utf-8", errors="replace").rstrip()
            _write_log(log_file, stage=stage, message=decoded)
            sample = size_probe.sample() if size_probe is not None else None
            size_message = (
                size_probe.maybe_message(sample)
                if size_probe is not None and sample is not None
                else None
            )
            message = _trim_message(decoded)
            if size_message is not None:
                message = _trim_message(f"{message} ({size_message})")
            await progress(
                progress=_estimated_progress(bounds, line_count, sample),
                stage=stage,
                message=message,
            )
        return_code = await process.wait()
        if return_code != 0:
            _write_log(log_file, stage=stage, message=f"exit={return_code}")
            msg = f"{stage} command failed ({return_code}): {' '.join(cmd.safe_argv)}"
            raise RuntimeError(msg)


def _estimated_progress(
    bounds: tuple[float, float],
    line_count: int,
    sample: SizeProgressSample | None = None,
) -> float:
    start, end = bounds
    line_value = start + (end - start) * min(0.98, line_count / 200)
    if sample is None or sample.total_bytes is None or sample.total_bytes <= 0:
        return min(end, line_value)
    size_fraction = min(0.98, sample.current_bytes / sample.total_bytes)
    size_value = start + (end - start) * size_fraction
    return min(end, max(line_value, size_value))


def _trim_message(message: str) -> str:
    return message if len(message) <= 500 else f"{message[:497]}..."


def path_size_bytes(path: Path) -> int:
    if path.is_file():
        return _safe_path_size(path)
    if not path.is_dir():
        return 0
    total = 0
    try:
        for child in path.rglob("*"):
            if child.is_file():
                total += _safe_path_size(child)
    except OSError:
        return total
    return total


def _safe_path_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(max(0, value))
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{int(size)} B"


def _write_log(log_file: Any, *, stage: str, message: str) -> None:
    payload = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "stage": stage,
        "message": message,
    }
    log_file.write(json.dumps(payload, ensure_ascii=False) + "\n")
    log_file.flush()


async def sha256_file(
    path: Path,
    *,
    cancel_event: asyncio.Event,
    progress: ProgressReporter | None = None,
    bounds: tuple[float, float] | None = None,
) -> str:
    digest = hashlib.sha256()
    total = path.stat().st_size  # noqa: ASYNC240
    read_bytes = 0
    last_emit_at = 0.0
    with path.open("rb") as fh:
        while True:
            _ensure_not_cancelled(cancel_event)
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            read_bytes += len(chunk)
            if progress is not None and bounds is not None and total > 0:
                start, end = bounds
                value = start + (end - start) * min(1.0, read_bytes / total)
                now = monotonic()
                message = None
                if now - last_emit_at >= 5.0 or read_bytes >= total:
                    last_emit_at = now
                    message = (
                        f"checksum {format_bytes(read_bytes)}/{format_bytes(total)}"
                    )
                await progress(progress=value, stage="checksum", message=message)
    return digest.hexdigest()


async def write_checksums(
    target: Path,
    *,
    roots: tuple[Path, ...],
    base_dir: Path,
    cancel_event: asyncio.Event,
    progress: ProgressReporter | None = None,
    bounds: tuple[float, float] | None = None,
) -> None:
    lines: list[str] = []
    files = [path for root in roots for path in _iter_checksum_files(root)]
    total_bytes = sum(_safe_path_size(path) for path in files)
    processed_bytes = 0
    last_emit_at = 0.0
    for path in files:
        digest = await sha256_file(path, cancel_event=cancel_event)
        processed_bytes += _safe_path_size(path)
        lines.append(f"{digest}  {path.relative_to(base_dir).as_posix()}")
        if progress is not None and bounds is not None and total_bytes > 0:
            start, end = bounds
            value = start + (end - start) * min(1.0, processed_bytes / total_bytes)
            now = monotonic()
            message = None
            if now - last_emit_at >= 5.0 or processed_bytes >= total_bytes:
                last_emit_at = now
                message = (
                    f"dump checksum {format_bytes(processed_bytes)}"
                    f"/{format_bytes(total_bytes)}"
                )
            await progress(progress=value, stage="dump", message=message)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")  # noqa: ASYNC240
    os.chmod(target, 0o600)


async def verify_internal_checksums(
    extract_dir: Path,
    *,
    cancel_event: asyncio.Event,
) -> None:
    checksum_file = extract_dir / "checksums.sha256"
    if not checksum_file.is_file():
        msg = "restore archive is missing checksums.sha256"
        raise InvalidInputError(msg)
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split("  ", 1)
        path = extract_dir / relative
        if not path.is_file():
            msg = f"restore archive checksum target missing: {relative}"
            raise InvalidInputError(msg)
        actual = await sha256_file(path, cancel_event=cancel_event)
        if actual != digest:
            msg = f"restore archive checksum mismatch: {relative}"
            raise InvalidInputError(msg)


async def verify_archive_checksum(archive_path: Path, artifact: OpsArtifact | None) -> None:
    if artifact is None or artifact.sha256 is None:
        return
    event = asyncio.Event()

    async def noop(
        *,
        progress: float | None = None,
        stage: str | None = None,
        message: str | None = None,
    ) -> None:
        _ = (progress, stage, message)

    actual = await sha256_file(archive_path, cancel_event=event, progress=noop)
    if actual != artifact.sha256:
        msg = f"backup archive sha256 mismatch: {artifact.artifact_id}"
        raise InvalidInputError(msg)


def _iter_checksum_files(root: Path) -> tuple[Path, ...]:
    if root.is_file():
        return (root,)
    return tuple(sorted(path for path in root.rglob("*") if path.is_file()))


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(payload, encoding="utf-8")
    os.chmod(path, 0o600)


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        msg = f"manifest not found: {path}"
        raise InvalidInputError(msg)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        msg = f"manifest must be a JSON object: {path}"
        raise InvalidInputError(msg)
    return value


async def ensure_target_database_empty(target_dsn: str) -> None:
    engine = create_async_engine(target_dsn)
    try:
        async with engine.connect() as conn:
            count = await conn.scalar(
                text(
                    """
SELECT count(*)::bigint
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname IN ('public', 'ops')
   AND c.relkind IN ('r','p','m')
"""
                )
            )
    finally:
        await engine.dispose()
    if int(count or 0) > 0:
        msg = "restore target database is not empty"
        raise InvalidInputError(msg)


async def analyze_database(target_dsn: str) -> None:
    engine = create_async_engine(target_dsn)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("ANALYZE"))
    finally:
        await engine.dispose()


async def smoke_test_restore(target_dsn: str) -> None:
    engine = create_async_engine(target_dsn)
    try:
        async with engine.connect() as conn:
            table_count = await conn.scalar(
                text(
                    """
SELECT count(*)::bigint
  FROM information_schema.tables
 WHERE table_schema IN ('public', 'ops')
"""
                )
            )
            postgis = await conn.scalar(
                text("SELECT count(*)::bigint FROM pg_extension WHERE extname = 'postgis'")
            )
    finally:
        await engine.dispose()
    if int(table_count or 0) == 0:
        msg = "restore smoke test found no public/ops tables"
        raise InvalidInputError(msg)
    if int(postgis or 0) == 0:
        msg = "restore smoke test found no postgis extension"
        raise InvalidInputError(msg)


async def deliver_callback(
    artifact: OpsArtifact,
    *,
    settings: Settings,
    event: str,
) -> CallbackDeliveryResult | None:
    if not artifact.callback_url:
        return None
    validate_callback_url(artifact.callback_url, settings.backup_callback_allowed_hosts)
    attempts = max(1, settings.backup_callback_max_attempts)
    backoff_s = settings.backup_callback_backoff_ms / 1_000
    callback_ids: list[str] = []
    last_error: str | None = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for attempt in range(1, attempts + 1):
                callback_id = f"cb_{uuid4().hex}"
                callback_ids.append(callback_id)
                timestamp = datetime.now(UTC).isoformat(timespec="seconds")
                body = callback_payload_bytes(
                    artifact,
                    event=event,
                    callback_id=callback_id,
                    timestamp=timestamp,
                    attempt=attempt,
                    max_attempts=attempts,
                )
                headers = callback_headers(
                    settings,
                    event=event,
                    callback_id=callback_id,
                    timestamp=timestamp,
                    body=body,
                )
                try:
                    response = await client.post(
                        artifact.callback_url,
                        content=body,
                        headers=headers,
                    )
                    response.raise_for_status()
                    return CallbackDeliveryResult(
                        state="delivered",
                        attempts=attempt,
                        callback_ids=tuple(callback_ids),
                    )
                except Exception as exc:
                    last_error = str(exc)
                    if attempt < attempts and backoff_s > 0:
                        await asyncio.sleep(backoff_s * (2 ** (attempt - 1)))
    except Exception as exc:
        last_error = str(exc)
    return CallbackDeliveryResult(
        state="failed",
        attempts=len(callback_ids) or 1,
        callback_ids=tuple(callback_ids),
        last_error=last_error,
    )


async def record_callback_delivery(
    repo: AdminRepository,
    artifact: OpsArtifact,
    result: CallbackDeliveryResult,
) -> None:
    manifest = dict(artifact.manifest)
    manifest["callback_delivery"] = {
        "state": result.state,
        "attempts": result.attempts,
        "callback_ids": list(result.callback_ids),
        "last_error": result.last_error,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    await repo.update_artifact(
        artifact.artifact_id,
        callback_state=result.state,
        manifest=manifest,
    )


def callback_payload_bytes(
    artifact: OpsArtifact,
    *,
    event: str,
    callback_id: str,
    timestamp: str,
    attempt: int,
    max_attempts: int,
) -> bytes:
    payload = {
        "event": event,
        "callback_id": callback_id,
        "timestamp": timestamp,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "artifact_id": artifact.artifact_id,
        "artifact_type": artifact.artifact_type,
        "state": artifact.state,
        "size_bytes": artifact.size_bytes,
        "sha256": artifact.sha256,
        "job_id": artifact.job_id,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def callback_headers(
    settings: Settings,
    *,
    event: str,
    callback_id: str,
    timestamp: str,
    body: bytes,
) -> dict[str, str]:
    signature = callback_signature(
        settings,
        callback_id=callback_id,
        timestamp=timestamp,
        body=body,
    )
    return {
        "content-type": "application/json",
        "x-kor-travel-geo-event": event,
        "x-kor-travel-geo-callback-id": callback_id,
        "x-kor-travel-geo-timestamp": timestamp,
        "x-kor-travel-geo-signature": f"sha256={signature}",
    }


def callback_signature(
    settings: Settings,
    *,
    callback_id: str,
    timestamp: str,
    body: bytes,
) -> str:
    message = timestamp.encode() + b"." + callback_id.encode() + b"." + body
    return hmac.new(_callback_secret(settings), message, hashlib.sha256).hexdigest()


def backup_download_token(artifact: OpsArtifact, settings: Settings) -> str:
    key = _download_token_secret(settings)
    message = f"{artifact.artifact_id}:{artifact.sha256 or ''}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def validate_download_token(artifact: OpsArtifact, settings: Settings, token: str) -> None:
    expected = backup_download_token(artifact, settings)
    if not secrets.compare_digest(expected, token):
        msg = "invalid backup download token"
        raise InvalidInputError(msg)


def backup_download_url(artifact: OpsArtifact, settings: Settings) -> str:
    token = backup_download_token(artifact, settings)
    return f"/v1/admin/backups/{artifact.artifact_id}/download?token={token}"


def _download_token_secret(settings: Settings) -> bytes:
    secret = settings.backup_download_token_secret
    if secret is not None:
        return secret.get_secret_value().encode()
    return hashlib.sha256(settings.pg_dsn.encode()).digest()


def _callback_secret(settings: Settings) -> bytes:
    secret = settings.backup_callback_secret
    if secret is not None:
        return secret.get_secret_value().encode()
    return _download_token_secret(settings)


def _preflight_backup_tools() -> None:
    missing = [name for name in ("pg_dump", "tar", "zstd") if shutil.which(name) is None]
    if missing:
        msg = f"backup tools missing: {', '.join(missing)}"
        raise InvalidInputError(msg)


def _preflight_restore_tools() -> None:
    missing = [name for name in ("pg_restore", "tar", "zstd") if shutil.which(name) is None]
    if missing:
        msg = f"restore tools missing: {', '.join(missing)}"
        raise InvalidInputError(msg)


def _ensure_not_cancelled(cancel_event: asyncio.Event) -> None:
    if cancel_event.is_set():
        raise asyncio.CancelledError


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _payload_job_id(payload: Mapping[str, Any]) -> str | None:
    value = payload.get("_job_id")
    return str(value) if isinstance(value, str) and value else None


def artifact_expires_at(settings: Settings, retention_days: int | None) -> datetime:
    days = retention_days or settings.backup_artifact_ttl_days
    return datetime.now(UTC) + timedelta(days=days)
