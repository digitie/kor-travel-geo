from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from kraddr.geo.dto.admin import OpsArtifact, RestoreCreateRequest
from kraddr.geo.exceptions import InvalidInputError
from kraddr.geo.infra import backup as backup_module
from kraddr.geo.infra.backup import (
    backup_download_token,
    build_pg_dump_command,
    build_pg_restore_command,
    build_tar_create_command,
    callback_headers,
    callback_payload_bytes,
    callback_signature,
    deliver_callback,
    read_json,
    resolve_backup_destination,
    resolve_restore_target_dsn,
    safe_artifact_path,
    validate_callback_url,
    validate_download_token,
    verify_internal_checksums,
    write_checksums,
    write_json,
)
from kraddr.geo.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path


def test_backup_destination_accepts_allowed_root_and_rejects_escape(tmp_path: Path) -> None:
    root = tmp_path / "backups"
    root.mkdir()
    settings = Settings(backup_allowed_dirs=(root,))

    assert resolve_backup_destination(None, settings) == root.resolve()
    assert resolve_backup_destination("daily", settings) == (root / "daily").resolve()

    with pytest.raises(InvalidInputError, match="escapes allowed roots"):
        resolve_backup_destination(str(tmp_path / "outside"), settings)


def test_backup_destination_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "backups"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "link"
    link.symlink_to(outside, target_is_directory=True)
    settings = Settings(backup_allowed_dirs=(root,))

    with pytest.raises(InvalidInputError, match="escapes allowed roots"):
        resolve_backup_destination(str(link), settings)


def test_safe_artifact_path_keeps_tar_zst_inside_destination(tmp_path: Path) -> None:
    destination = tmp_path / "backups"
    destination.mkdir()

    path = safe_artifact_path(destination, "../db.sql")

    assert path.name == "db.sql.tar.zst"
    assert path.parent == destination.resolve()


def test_callback_url_must_use_allowed_host() -> None:
    assert (
        validate_callback_url("http://localhost:9000/hooks/backup", ("localhost",))
        == "http://localhost:9000/hooks/backup"
    )
    with pytest.raises(InvalidInputError, match="not allowed"):
        validate_callback_url("http://169.254.169.254/latest", ("localhost",))
    with pytest.raises(InvalidInputError, match="http"):
        validate_callback_url("file:///tmp/hook", ("localhost",))


def test_pg_dump_command_uses_directory_format_and_redacts_password(tmp_path: Path) -> None:
    cmd = build_pg_dump_command(
        "postgresql+psycopg://addr:secret@localhost:5432/kraddr_geo",
        tmp_path / "dump",
        profile="lean-serving",
        jobs=4,
        include_materialized_views=False,
    )

    assert cmd.argv[:4] == ("pg_dump", "--format=directory", "--jobs=4", "--verbose")
    assert "--exclude-table-data=geo_cache" in cmd.argv
    assert "--exclude-table-data=mv_geocode_target" in cmd.argv
    assert "--exclude-table-data=mv_geocode_text_search" in cmd.argv
    assert "secret" not in " ".join(cmd.argv)
    assert "secret" not in " ".join(cmd.safe_argv)
    assert cmd.env == {"PGPASSWORD": "secret"}
    assert "postgresql://addr@localhost:5432/kraddr_geo" in " ".join(cmd.safe_argv)


def test_pg_restore_and_tar_commands_are_parallel_archive_oriented(tmp_path: Path) -> None:
    restore = build_pg_restore_command(
        "postgresql+psycopg://addr:secret@localhost:5432/kraddr_geo_restore",
        tmp_path / "dump",
        jobs=8,
    )
    tar = build_tar_create_command(tmp_path / "backup.tar.zst", tmp_path, compression_level=5)

    assert restore.argv[:4] == ("pg_restore", "--format=directory", "--jobs=8", "--verbose")
    assert "secret" not in " ".join(restore.argv)
    assert "secret" not in " ".join(restore.safe_argv)
    assert restore.env == {"PGPASSWORD": "secret"}
    assert "zstd -T0 -5" in tar.argv[1]


async def test_manifest_and_internal_checksums_round_trip(tmp_path: Path) -> None:
    dump_dir = tmp_path / "dump"
    dump_dir.mkdir()
    (dump_dir / "toc.dat").write_text("toc", encoding="utf-8")
    (dump_dir / "123.dat").write_bytes(b"rows")
    manifest = tmp_path / "manifest.json"
    write_json(manifest, {"artifact_schema_version": 1, "row_counts": {"tl_juso_text": 1}})

    checksum = tmp_path / "checksums.sha256"
    await write_checksums(
        checksum,
        roots=(manifest, dump_dir),
        base_dir=tmp_path,
        cancel_event=asyncio.Event(),
    )

    assert read_json(manifest)["row_counts"]["tl_juso_text"] == 1
    assert "manifest.json" in checksum.read_text(encoding="utf-8")
    await verify_internal_checksums(tmp_path, cancel_event=asyncio.Event())

    (dump_dir / "123.dat").write_bytes(b"changed")
    with pytest.raises(InvalidInputError, match="checksum mismatch"):
        await verify_internal_checksums(tmp_path, cancel_event=asyncio.Event())


def test_restore_target_dsn_is_built_from_current_settings() -> None:
    settings = Settings(pg_dsn="postgresql://addr:secret@localhost:5432/kraddr_geo")
    req = RestoreCreateRequest(target_database="kraddr_geo_restore")

    target = resolve_restore_target_dsn(req, settings)

    assert target == "postgresql+psycopg://addr:secret@localhost:5432/kraddr_geo_restore"


def test_download_token_is_deterministic_and_validates() -> None:
    settings = Settings(
        pg_dsn="postgresql://addr:secret@localhost:5432/kraddr_geo",
        backup_download_token_secret="test-secret",
    )
    artifact = OpsArtifact(
        artifact_id="artifact-1",
        artifact_type="db_backup",
        state="available",
        storage_kind="local_file",
        sha256="a" * 64,
        created_at="2026-05-27T00:00:00Z",
    )

    token = backup_download_token(artifact, settings)

    validate_download_token(artifact, settings, token)
    with pytest.raises(InvalidInputError, match="invalid"):
        validate_download_token(artifact, settings, "0" * 64)


def test_callback_payload_is_signed_with_timestamp_and_callback_id() -> None:
    settings = Settings(backup_callback_secret="callback-secret")
    artifact = OpsArtifact(
        artifact_id="artifact-1",
        artifact_type="db_backup",
        state="available",
        storage_kind="local_file",
        size_bytes=10,
        sha256="a" * 64,
        job_id="job-1",
        created_at="2026-05-27T00:00:00Z",
    )
    body = callback_payload_bytes(
        artifact,
        event="db_backup.done",
        callback_id="cb_test",
        timestamp="2026-05-28T00:00:00+00:00",
        attempt=1,
        max_attempts=3,
    )

    headers = callback_headers(
        settings,
        event="db_backup.done",
        callback_id="cb_test",
        timestamp="2026-05-28T00:00:00+00:00",
        body=body,
    )

    assert b"callback-secret" not in body
    assert headers["x-kraddr-geo-event"] == "db_backup.done"
    assert headers["x-kraddr-geo-callback-id"] == "cb_test"
    assert headers["x-kraddr-geo-signature"] == "sha256=" + callback_signature(
        settings,
        callback_id="cb_test",
        timestamp="2026-05-28T00:00:00+00:00",
        body=body,
    )


@pytest.mark.asyncio
async def test_callback_delivery_retries_with_fresh_callback_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, bytes, dict[str, str]]] = []

    class _Response:
        def raise_for_status(self) -> None:
            return None

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            assert timeout == 5.0

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            content: bytes,
            headers: dict[str, str],
        ) -> _Response:
            calls.append((url, content, headers))
            if len(calls) == 1:
                raise RuntimeError("temporary callback failure")
            return _Response()

    monkeypatch.setattr(backup_module.httpx, "AsyncClient", _FakeAsyncClient)
    settings = Settings(
        backup_callback_allowed_hosts=("localhost",),
        backup_callback_secret="callback-secret",
        backup_callback_max_attempts=2,
        backup_callback_backoff_ms=0,
    )
    artifact = OpsArtifact(
        artifact_id="artifact-1",
        artifact_type="db_backup",
        state="available",
        storage_kind="local_file",
        callback_url="http://localhost:9000/hooks/backup",
        sha256="a" * 64,
        created_at="2026-05-27T00:00:00Z",
    )

    result = await deliver_callback(artifact, settings=settings, event="db_backup.done")

    assert result is not None
    assert result.state == "delivered"
    assert result.attempts == 2
    assert len(calls) == 2
    assert calls[0][2]["x-kraddr-geo-callback-id"] != calls[1][2]["x-kraddr-geo-callback-id"]
    assert all(call[0] == "http://localhost:9000/hooks/backup" for call in calls)


@pytest.mark.asyncio
async def test_callback_delivery_records_failed_retry_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            assert timeout == 5.0

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            content: bytes,
            headers: dict[str, str],
        ) -> object:
            assert content.startswith(b"{")
            calls.append(headers)
            raise RuntimeError(f"still failing: {url}")

    monkeypatch.setattr(backup_module.httpx, "AsyncClient", _FakeAsyncClient)
    settings = Settings(
        backup_callback_allowed_hosts=("localhost",),
        backup_callback_secret="callback-secret",
        backup_callback_max_attempts=2,
        backup_callback_backoff_ms=0,
    )
    artifact = OpsArtifact(
        artifact_id="artifact-1",
        artifact_type="db_backup",
        state="available",
        storage_kind="local_file",
        callback_url="http://localhost:9000/hooks/backup",
        created_at="2026-05-27T00:00:00Z",
    )

    result = await deliver_callback(artifact, settings=settings, event="db_backup.done")

    assert result is not None
    assert result.state == "failed"
    assert result.attempts == 2
    assert result.last_error == "still failing: http://localhost:9000/hooks/backup"
    assert len(result.callback_ids) == 2
    assert len(calls) == 2
