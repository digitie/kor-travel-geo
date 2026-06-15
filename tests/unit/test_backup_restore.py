from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from kortravelgeo.dto.admin import OpsArtifact, RestoreCreateRequest
from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra import backup as backup_module
from kortravelgeo.infra.backup import (
    SizeProgressProbe,
    SizeProgressSample,
    backup_download_token,
    build_pg_dump_command,
    build_pg_restore_command,
    build_tar_create_command,
    callback_headers,
    callback_payload_bytes,
    callback_signature,
    deliver_callback,
    format_bytes,
    path_size_bytes,
    read_json,
    resolve_backup_destination,
    resolve_restore_target_dsn,
    safe_artifact_path,
    validate_callback_url,
    validate_download_token,
    validate_replace_current_restore_request,
    verify_internal_checksums,
    write_checksums,
    write_json,
)
from kortravelgeo.settings import Settings

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
        "postgresql+psycopg://addr:secret@localhost:5432/kor_travel_geo",
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
    assert "postgresql://addr@localhost:5432/kor_travel_geo" in " ".join(cmd.safe_argv)


def test_pg_restore_and_tar_commands_are_parallel_archive_oriented(tmp_path: Path) -> None:
    restore = build_pg_restore_command(
        "postgresql+psycopg://addr:secret@localhost:5432/kor_travel_geo_restore",
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
    settings = Settings(pg_dsn="postgresql://addr:secret@localhost:5432/kor_travel_geo")
    req = RestoreCreateRequest(target_database="kor_travel_geo_restore")

    target = resolve_restore_target_dsn(req, settings)

    assert target == "postgresql+psycopg://addr:secret@localhost:5432/kor_travel_geo_restore"


def test_restore_target_database_rejects_unsafe_identifier() -> None:
    settings = Settings(pg_dsn="postgresql://addr:secret@localhost:5432/kor_travel_geo")
    req = RestoreCreateRequest(target_database='kor_travel_geo"restore')

    with pytest.raises(InvalidInputError, match="target_database must match"):
        resolve_restore_target_dsn(req, settings)


@pytest.mark.asyncio
async def test_restore_dry_run_target_check_failure_is_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(pg_dsn="postgresql://addr:secret@localhost:5432/kor_travel_geo")
    req = RestoreCreateRequest(
        archive_path="missing.tar.zst",
        target_database="kor_travel_geo_restore",
    )

    async def fail_empty_check(_target_dsn: str) -> None:
        raise RuntimeError("connection refused")

    async def fail_archive(*_args: object, **_kwargs: object) -> None:
        raise backup_module.NotFoundError("missing archive")

    monkeypatch.setattr(backup_module, "ensure_target_database_empty", fail_empty_check)
    monkeypatch.setattr(backup_module, "resolve_restore_archive", fail_archive)

    result = await backup_module.run_restore_dry_run(object(), settings, req)  # type: ignore[arg-type]

    assert result.can_restore is False
    assert any(
        "target not restorable" in blocker and "connection refused" in blocker
        for blocker in result.blockers
    )


@pytest.mark.asyncio
async def test_query_cluster_versions_uses_target_dsn_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[str] = []
    disposed: list[str] = []

    class FakeEngine:
        def __init__(self, dsn: str) -> None:
            self.dsn = dsn

        async def dispose(self) -> None:
            disposed.append(self.dsn)

    def fake_create_async_engine(dsn: str) -> FakeEngine:
        created.append(dsn)
        return FakeEngine(dsn)

    async def fake_query(engine: FakeEngine) -> tuple[str, str]:
        return engine.dsn, "3.5.2"

    monkeypatch.setattr(backup_module, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(backup_module, "_query_cluster_versions", fake_query)

    pg_version, postgis_version = await backup_module._query_cluster_versions_for_dsn(
        "postgresql://addr:secret@remote:5432/kor_travel_geo_restore"
    )

    assert created == [
        "postgresql+psycopg://addr:secret@remote:5432/kor_travel_geo_restore"
    ]
    assert disposed == created
    assert pg_version == created[0]
    assert postgis_version == "3.5.2"


def test_replace_current_restore_requires_exact_target_and_confirmation() -> None:
    settings = Settings(pg_dsn="postgresql://addr:secret@localhost:5432/kor_travel_geo")
    req = RestoreCreateRequest(
        target_database="kor_travel_geo",
        mode="replace_current",
        confirmation="RESTORE kor_travel_geo",
    )

    confirmation = validate_replace_current_restore_request(
        req,
        settings=settings,
        target_database="kor_travel_geo",
    )

    assert confirmation == "RESTORE kor_travel_geo"

    wrong_target = req.model_copy(update={"target_database": "kor_travel_geo_restore"})
    with pytest.raises(InvalidInputError, match="must match the current database"):
        validate_replace_current_restore_request(
            wrong_target,
            settings=settings,
            target_database="kor_travel_geo_restore",
        )

    dsn_target = req.model_copy(
        update={
            "target_database": None,
            "target_dsn": "postgresql+psycopg://addr:secret@otherhost:5432/kor_travel_geo",
        }
    )
    with pytest.raises(InvalidInputError, match="requires target_database"):
        validate_replace_current_restore_request(
            dsn_target,
            settings=settings,
            target_database="kor_travel_geo",
        )

    wrong_confirmation = req.model_copy(update={"confirmation": "RESTORE other"})
    with pytest.raises(InvalidInputError, match="requires confirmation: RESTORE kor_travel_geo"):
        validate_replace_current_restore_request(
            wrong_confirmation,
            settings=settings,
            target_database="kor_travel_geo",
        )


def test_download_token_is_deterministic_and_validates() -> None:
    settings = Settings(
        pg_dsn="postgresql://addr:secret@localhost:5432/kor_travel_geo",
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


def test_size_progress_helpers_report_file_and_directory_bytes(tmp_path: Path) -> None:
    (tmp_path / "a.bin").write_bytes(b"a" * 1024)
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.bin").write_bytes(b"b" * 512)

    assert path_size_bytes(tmp_path) == 1536
    assert format_bytes(1536) == "1.5 KiB"

    probe = SizeProgressProbe(
        tmp_path,
        "dump 디렉터리",
        total_bytes=2048,
        emit_interval_s=0,
    )
    sample = probe.sample()

    assert sample.current_bytes == 1536
    assert probe.maybe_message(sample) == "dump 디렉터리 1.5 KiB/2.0 KiB"


def test_size_progress_probe_throttles_directory_walks(tmp_path: Path) -> None:
    data_file = tmp_path / "a.bin"
    data_file.write_bytes(b"a" * 1024)
    probe = SizeProgressProbe(
        tmp_path,
        "dump 디렉터리",
        total_bytes=4096,
        emit_interval_s=60,
    )

    first = probe.sample()
    data_file.write_bytes(b"a" * 2048)
    cached = probe.sample()
    refreshed = probe.sample(force=True)

    assert first.current_bytes == 1024
    assert cached.current_bytes == 1024
    assert refreshed.current_bytes == 2048


def test_estimated_progress_uses_size_sample_when_available() -> None:
    value = backup_module._estimated_progress(
        (0.70, 0.90),
        line_count=0,
        sample=SizeProgressSample(current_bytes=50, total_bytes=100),
    )

    assert value == pytest.approx(0.80)


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
    assert headers["x-kor-travel-geo-event"] == "db_backup.done"
    assert headers["x-kor-travel-geo-callback-id"] == "cb_test"
    assert headers["x-kor-travel-geo-signature"] == "sha256=" + callback_signature(
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
    first_callback_id = calls[0][2]["x-kor-travel-geo-callback-id"]
    second_callback_id = calls[1][2]["x-kor-travel-geo-callback-id"]
    assert first_callback_id != second_callback_id
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
