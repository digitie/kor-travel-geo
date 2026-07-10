from __future__ import annotations

import asyncio
import shutil
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from starlette.requests import Request

from kortravelgeo.api import app as api_app
from kortravelgeo.api.routers import admin
from kortravelgeo.api.security import ROLE_REBUILD_OPERATOR, RequestContext
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.dto.source import SourceRebuildDbRequest, SourceRebuildDbResponse
from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra.source_rebuild_service import (
    RebuildFileRef,
    RebuildGroupRef,
    RebuildPlan,
    SourceRebuildService,
    _effective_materialize_concurrency,
    _extract_navi_7z,
)


class _FakeRustfs:
    def __init__(self, files: dict[str, Path]) -> None:
        self.files = files
        self.downloads: list[tuple[str, Path]] = []

    async def download_file(self, key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.files[key], destination)
        self.downloads.append((key, destination))


class _CancellingRustfs:
    async def download_file(self, key: str, destination: Path) -> None:
        del key, destination
        raise asyncio.CancelledError


class _FailingRustfs:
    async def download_file(self, key: str, destination: Path) -> None:
        del key, destination
        raise OSError(12, "Cannot allocate memory")


def test_rebuild_plan_fans_out_roadname_to_text_and_parcel_link() -> None:
    source_file = _file(
        source_file_id="f-road",
        object_key="registry/roadname/archive-roadname.zip",
    )
    group = _group("roadname_hangul_full", "juso_text_load", (source_file,))

    plan = _service()._assemble_plan("ms-1", (group,))

    assert [child["kind"] for child in plan.batch_payload["children"]] == [
        "juso_text_load",
        "juso_parcel_link_load",
    ]
    assert {
        Path(child["payload"]["path"]) for child in plan.batch_payload["children"]
    } == {Path("rebuild_staging") / "ms-1" / "roadname_hangul_full"}


@pytest.mark.asyncio
async def test_materialize_rebuild_plan_extracts_text_zip(tmp_path: Path) -> None:
    source_zip = tmp_path / "roadname.zip"
    _write_zip(source_zip, {"rnaddrkor_11.txt": b"row\n"})
    plan = _plan(
        "roadname_hangul_full",
        "juso_text_load",
        (
            _file(
                source_file_id="f-road",
                object_key="registry/roadname/archive-roadname.zip",
            ),
        ),
    )

    relocated = await _service().materialize_rebuild_plan(
        _FakeRustfs({"registry/roadname/archive-roadname.zip": source_zip}),
        plan,
        tmp_path / "stage",
    )

    target = tmp_path / "stage" / "roadname_hangul_full"
    assert (target / "rnaddrkor_11.txt").read_bytes() == b"row\n"
    assert (target / ".ktg-materialized-ok").is_file()
    assert relocated["staging_dir"] == str(tmp_path / "stage")
    assert [child["kind"] for child in relocated["children"]] == [
        "juso_text_load",
        "juso_parcel_link_load",
    ]
    assert relocated["children"][0]["payload"]["path"] == str(target)
    assert relocated["children"][1]["payload"]["path"] == str(target)


@pytest.mark.asyncio
async def test_materialize_rebuild_plan_extracts_electronic_map_by_part_label(
    tmp_path: Path,
) -> None:
    sejong_zip = tmp_path / "sejong.zip"
    seoul_zip = tmp_path / "seoul.zip"
    _write_zip(
        sejong_zip,
        {
            "36000/TL_SPBD_BULD.shp": b"shp",
            "36000/TL_SPBD_BULD.shx": b"shx",
            "36000/TL_SPBD_BULD.dbf": b"dbf",
        },
    )
    _write_zip(
        seoul_zip,
        {
            "11000/TL_SPBD_BULD.shp": b"seoul-shp",
            "11000/TL_SPBD_BULD.shx": b"seoul-shx",
            "11000/TL_SPBD_BULD.dbf": b"seoul-dbf",
        },
    )
    plan = _plan(
        "electronic_map_full",
        "shp_polygons_load",
        (
            _file(
                source_file_id="f-map-seoul",
                part_key="11",
                part_label="서울특별시",
                object_key="registry/electronic/11/archive",
                original_filename=None,
            ),
            _file(
                source_file_id="f-map",
                part_key="36",
                part_label="세종특별자치시",
                object_key="registry/electronic/36/archive",
                original_filename=None,
            ),
        ),
    )

    await _service().materialize_rebuild_plan(
        _FakeRustfs(
            {
                "registry/electronic/11/archive": seoul_zip,
                "registry/electronic/36/archive": sejong_zip,
            }
        ),
        plan,
        tmp_path / "stage",
    )

    seoul_target = tmp_path / "stage" / "electronic_map_full" / "서울특별시" / "11000"
    target = tmp_path / "stage" / "electronic_map_full" / "세종특별자치시" / "36000"
    assert (seoul_target / "TL_SPBD_BULD.shp").read_bytes() == b"seoul-shp"
    assert (target / "TL_SPBD_BULD.shp").read_bytes() == b"shp"
    assert (target / "TL_SPBD_BULD.shx").read_bytes() == b"shx"
    assert (target / "TL_SPBD_BULD.dbf").read_bytes() == b"dbf"


@pytest.mark.asyncio
async def test_materialize_rebuild_plan_keeps_zip_inputs_for_zip_aware_loaders(
    tmp_path: Path,
) -> None:
    seoul_zip = tmp_path / "entrance-seoul.zip"
    busan_zip = tmp_path / "entrance-busan.zip"
    _write_zip(seoul_zip, {"RNENTDATA_2404_11.txt": b"row\n"})
    _write_zip(busan_zip, {"RNENTDATA_2404_26.txt": b"row\n"})
    plan = _plan(
        "roadaddr_entrance_full",
        "roadaddr_entrance_load",
        (
            _file(
                source_file_id="f-ent",
                part_key="11",
                part_label="서울특별시",
                object_key="registry/entrance/11/archive",
                original_filename=None,
            ),
            _file(
                source_file_id="f-ent-26",
                part_key="26",
                part_label="부산광역시",
                object_key="registry/entrance/26/archive",
                original_filename=None,
            ),
        ),
    )

    await _service().materialize_rebuild_plan(
        _FakeRustfs(
            {
                "registry/entrance/11/archive": seoul_zip,
                "registry/entrance/26/archive": busan_zip,
            }
        ),
        plan,
        tmp_path / "stage",
    )

    target = tmp_path / "stage" / "roadaddr_entrance_full"
    assert (target / "11.zip").is_file()
    assert (target / "26.zip").is_file()
    assert not (target / "archive").exists()
    assert not (target / "RNENTDATA_2404_11.txt").exists()
    assert (target / ".ktg-materialized-ok").is_file()


@pytest.mark.asyncio
async def test_materialize_rebuild_plan_rejects_checksum_mismatch(
    tmp_path: Path,
) -> None:
    source_zip = tmp_path / "roadname.zip"
    _write_zip(source_zip, {"rnaddrkor_11.txt": b"row\n"})
    plan = _plan(
        "roadname_hangul_full",
        "juso_text_load",
        (
            _file(
                source_file_id="f-road",
                object_key="registry/roadname/archive-roadname.zip",
                sha256="0" * 64,
            ),
        ),
    )

    with pytest.raises(InvalidInputError, match="sha256 mismatch"):
        await _service().materialize_rebuild_plan(
            _FakeRustfs({"registry/roadname/archive-roadname.zip": source_zip}),
            plan,
            tmp_path / "stage",
        )

    assert not (tmp_path / "stage").exists()


@pytest.mark.asyncio
async def test_materialize_rebuild_plan_cleans_up_on_cancellation(
    tmp_path: Path,
) -> None:
    plan = _plan(
        "roadname_hangul_full",
        "juso_text_load",
        (
            _file(
                source_file_id="f-road",
                object_key="registry/roadname/archive-roadname.zip",
            ),
        ),
    )

    with pytest.raises(asyncio.CancelledError):
        await _service().materialize_rebuild_plan(
            _CancellingRustfs(),
            plan,
            tmp_path / "stage",
        )

    assert not (tmp_path / "stage").exists()


@pytest.mark.asyncio
async def test_materialize_rebuild_plan_adds_group_context_to_os_errors(
    tmp_path: Path,
) -> None:
    plan = _plan(
        "navi_full",
        "navi_load",
        (
            _file(
                source_file_id="f-navi",
                object_key="registry/navi/archive.7z",
                compression_format="7z",
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="navi_full/g-navi_full") as exc_info:
        await _service().materialize_rebuild_plan(
            _FailingRustfs(),
            plan,
            tmp_path / "stage",
        )

    assert "Cannot allocate memory" in str(exc_info.value)
    assert not (tmp_path / "stage").exists()


def test_heavy_rebuild_materialization_is_single_extract_at_a_time() -> None:
    heavy_group = _group(
        "electronic_map_full",
        "shp_polygons_load",
        (
            _file(
                source_file_id="f-map",
                object_key="registry/electronic/archive.zip",
            ),
        ),
    )
    light_group = _group(
        "roadaddr_entrance_full",
        "roadaddr_entrance_load",
        (
            _file(
                source_file_id="f-ent",
                object_key="registry/entrance/archive.zip",
            ),
        ),
    )

    assert _effective_materialize_concurrency((heavy_group,), 3) == 1
    assert _effective_materialize_concurrency((light_group,), 3) == 3
    assert _effective_materialize_concurrency((heavy_group,), 0) == 1


def test_extract_navi_7z_uses_single_thread_and_temp_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "navi.7z"
    archive.write_bytes(b"fake")
    captured: dict[str, Any] = {}

    def fake_which(name: str) -> str | None:
        return "/usr/bin/7z" if name == "7z" else None

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        stdout = kwargs["stdout"]
        stdout.write("ok\n")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)

    _extract_navi_7z(archive, tmp_path / "out")

    assert "-mmt=1" in captured["args"]
    assert captured["kwargs"]["stdout"] is not subprocess.PIPE
    assert captured["kwargs"]["stderr"] is subprocess.STDOUT


@pytest.mark.asyncio
async def test_prepare_rebuild_uses_attempt_scoped_staging_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_roots: list[Path] = []

    async def fake_prepare_rebuild(self: SourceRebuildService, msid: str) -> tuple[Any, Any]:
        del self
        return (
            RebuildPlan(
                source_match_set_id=msid,
                groups=(),
                batch_payload={
                    "children": [],
                    "source_match_set_id": msid,
                    "source_set": {},
                    "staging_dir": f"rebuild_staging/{msid}",
                },
            ),
            SimpleNamespace(stale_job_ids=()),
        )

    async def fake_integrity_checks(
        self: AsyncAddressClient, rustfs: Any, plan: Any
    ) -> tuple[Any, ...]:
        del self, rustfs, plan
        return ()

    async def fake_materialize(
        self: SourceRebuildService,
        rustfs: Any,
        plan: RebuildPlan,
        staging_root: Path,
        *,
        download_concurrency: int = 3,
        materialize_concurrency: int = 2,
    ) -> dict[str, Any]:
        del self, rustfs, plan, download_concurrency, materialize_concurrency
        captured_roots.append(staging_root)
        return {"children": [], "staging_dir": str(staging_root)}

    monkeypatch.setattr(
        SourceRebuildService,
        "prepare_rebuild",
        fake_prepare_rebuild,
    )
    monkeypatch.setattr(
        SourceRebuildService,
        "integrity_gate",
        lambda _self, _checks: SimpleNamespace(
            ok=True, failed_group_ids=(), reasons=()
        ),
    )
    monkeypatch.setattr(
        SourceRebuildService,
        "materialize_rebuild_plan",
        fake_materialize,
    )
    monkeypatch.setattr(
        AsyncAddressClient,
        "_rebuild_integrity_checks",
        fake_integrity_checks,
    )
    monkeypatch.setattr(
        "kortravelgeo.infra.rustfs.require_enabled_rustfs",
        lambda _settings: object(),
    )
    monkeypatch.setattr("kortravelgeo.infra.rustfs.RustfsClient", lambda _config: object())

    client = AsyncAddressClient(
        settings=cast(
            "Any",
            SimpleNamespace(rustfs_materialize_dir=tmp_path),
        ),
        engine=cast("Any", object()),
    )

    response, payload = await client.prepare_source_match_set_rebuild(
        "ms-1",
        actor="tester",
        force_promotion=False,
        typed_confirmation=None,
        reason=None,
    )

    assert response.enqueued is True
    assert payload is not None
    assert len(captured_roots) == 1
    root = captured_roots[0]
    assert root.parent == tmp_path / "rebuild_staging" / "ms-1"
    assert root.name.startswith("run_")
    assert root != tmp_path / "rebuild_staging" / "ms-1"
    assert payload["staging_dir"] == str(root)


@pytest.mark.asyncio
async def test_rebuild_route_enqueues_control_job_without_materializing() -> None:
    class FakeQueue:
        def __init__(self) -> None:
            self.enqueued: tuple[str, dict[str, Any]] | None = None
            self.enqueue_batch_called = False

        async def enqueue(self, kind: str, payload: dict[str, Any]) -> str:
            self.enqueued = (kind, payload)
            return "job-control"

        async def enqueue_batch(self, _payload: dict[str, Any]) -> str:
            self.enqueue_batch_called = True
            raise AssertionError("route must not enqueue full_load_batch synchronously")

    class FakeClient:
        def __init__(self) -> None:
            self.audit: dict[str, Any] | None = None

        async def prepare_source_match_set_rebuild(self, *_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("route must not materialize during the HTTP request")

        async def record_audit_event(self, **kwargs: Any) -> None:
            self.audit = kwargs

    queue = FakeQueue()
    client = FakeClient()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
    )
    ctx = RequestContext(
        actor="tester",
        roles=frozenset({ROLE_REBUILD_OPERATOR}),
    )

    response = await admin.rebuild_source_match_set_db(
        "ms-1",
        SourceRebuildDbRequest(),
        request,
        ctx=ctx,
        client=cast("Any", client),
        queue=cast("Any", queue),
    )

    assert response == SourceRebuildDbResponse(
        source_match_set_id="ms-1",
        enqueued=True,
        job_id="job-control",
        forced_promotion=False,
        message="rebuild prepare job queued; integrity gate will run asynchronously",
    )
    assert queue.enqueued == (
        "source_rebuild_db",
        {
            "source_match_set_id": "ms-1",
            "actor": "tester",
            "force_promotion": False,
            "reason": None,
            "download_concurrency": 3,
            "materialize_concurrency": 2,
        },
    )
    assert queue.enqueue_batch_called is False
    assert client.audit is not None
    assert client.audit["outcome"] == "started"
    assert client.audit["job_id"] == "job-control"


@pytest.mark.asyncio
async def test_source_rebuild_control_job_enqueues_full_load_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class QueueCapture:
        def __init__(self) -> None:
            self.handlers: dict[str, Any] = {}
            self.batch_payload: dict[str, Any] | None = None
            self.linked: tuple[str, str] | None = None

        def register(self, kind: str, handler: Any) -> None:
            self.handlers[kind] = handler

        async def enqueue_batch(self, payload: dict[str, Any]) -> str:
            self.batch_payload = payload
            return "batch-1"

        async def link_job_to_batch(self, job_id: str, load_batch_id: str) -> None:
            self.linked = (job_id, load_batch_id)

    class NoopLock:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> bool:
            return False

    async def fake_prepare(
        self: AsyncAddressClient,
        source_match_set_id: str,
        **kwargs: Any,
    ) -> tuple[SourceRebuildDbResponse, dict[str, Any]]:
        del self
        progress = kwargs["progress"]
        await progress(progress=0.70, stage="rebuild_materialized", message="ok")
        return (
            SourceRebuildDbResponse(
                source_match_set_id=source_match_set_id,
                enqueued=True,
                integrity_gate_ok=True,
            ),
            {
                "children": [{"kind": "juso_text_load", "payload": {"path": "/stage"}}],
                "source_match_set_id": source_match_set_id,
            },
        )

    record_calls: list[dict[str, Any]] = []

    async def fake_record_rebuild_enqueued(
        self: AsyncAddressClient,
        source_match_set_id: str,
        **kwargs: Any,
    ) -> None:
        del self
        record_calls.append({"source_match_set_id": source_match_set_id, **kwargs})

    monkeypatch.setattr(api_app, "cross_process_lock", lambda *_args, **_kwargs: NoopLock())
    monkeypatch.setattr(
        AsyncAddressClient,
        "prepare_source_match_set_rebuild",
        fake_prepare,
    )
    monkeypatch.setattr(
        AsyncAddressClient,
        "record_rebuild_enqueued",
        fake_record_rebuild_enqueued,
    )

    queue = QueueCapture()
    api_app._register_default_handlers(cast("Any", queue), cast("Any", object()))
    progress_events: list[dict[str, Any]] = []

    async def record_progress(**kwargs: Any) -> None:
        progress_events.append(kwargs)

    await queue.handlers["source_rebuild_db"](
        {
            "_job_id": "job-control",
            "source_match_set_id": "ms-1",
            "actor": "tester",
        },
        asyncio.Event(),
        record_progress,
    )

    assert queue.batch_payload is not None
    assert queue.batch_payload["source_match_set_id"] == "ms-1"
    assert queue.linked == ("job-control", "batch-1")
    assert record_calls == [
        {
            "source_match_set_id": "ms-1",
            "actor": "tester",
            "job_id": "batch-1",
            "load_batch_id": "batch-1",
            "forced_promotion": False,
            "reason": None,
        }
    ]
    assert any(event.get("stage") == "full_load_batch_queued" for event in progress_events)


@pytest.mark.asyncio
async def test_source_rebuild_control_job_fails_before_batch_on_integrity_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class QueueCapture:
        def __init__(self) -> None:
            self.handlers: dict[str, Any] = {}
            self.enqueue_batch_called = False

        def register(self, kind: str, handler: Any) -> None:
            self.handlers[kind] = handler

        async def enqueue_batch(self, _payload: dict[str, Any]) -> str:
            self.enqueue_batch_called = True
            raise AssertionError("integrity failure must not enqueue full_load_batch")

    class NoopLock:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> bool:
            return False

    async def fake_prepare(
        self: AsyncAddressClient,
        source_match_set_id: str,
        **_kwargs: Any,
    ) -> tuple[SourceRebuildDbResponse, None]:
        del self
        return (
            SourceRebuildDbResponse(
                source_match_set_id=source_match_set_id,
                enqueued=False,
                integrity_gate_ok=False,
                failed_group_ids=("g1",),
                message="pre-load integrity gate failed; groups quarantined",
            ),
            None,
        )

    audit_calls: list[dict[str, Any]] = []

    async def fake_record_audit_event(self: AsyncAddressClient, **kwargs: Any) -> None:
        del self
        audit_calls.append(kwargs)

    monkeypatch.setattr(api_app, "cross_process_lock", lambda *_args, **_kwargs: NoopLock())
    monkeypatch.setattr(
        AsyncAddressClient,
        "prepare_source_match_set_rebuild",
        fake_prepare,
    )
    monkeypatch.setattr(
        AsyncAddressClient,
        "record_audit_event",
        fake_record_audit_event,
    )

    queue = QueueCapture()
    api_app._register_default_handlers(cast("Any", queue), cast("Any", object()))
    progress_events: list[dict[str, Any]] = []

    async def record_progress(**kwargs: Any) -> None:
        progress_events.append(kwargs)

    with pytest.raises(RuntimeError, match="integrity gate failed"):
        await queue.handlers["source_rebuild_db"](
            {
                "_job_id": "job-control",
                "source_match_set_id": "ms-1",
                "actor": "tester",
            },
            asyncio.Event(),
            record_progress,
        )

    assert queue.enqueue_batch_called is False
    # audit outcome is the canonical lifecycle value ("failed"); the integrity-gate specifics
    # stay on the action / progress stage / payload (T-290 audit-outcome type-hardening).
    assert audit_calls[0]["outcome"] == "failed"
    assert audit_calls[0]["payload"] == {"failed_group_ids": ["g1"]}
    assert any(event.get("stage") == "integrity_gate_failed" for event in progress_events)


def _plan(
    category: str,
    load_kind: str,
    files: tuple[RebuildFileRef, ...],
) -> RebuildPlan:
    group = _group(category, load_kind, files)
    return RebuildPlan(
        source_match_set_id="ms-1",
        groups=(group,),
        batch_payload={
            "children": [
                {
                    "kind": kind,
                    "payload": {
                        "path": f"rebuild_staging/ms-1/{category}",
                        "source_file_group_id": group.source_file_group_id,
                    },
                }
                for kind in group.load_kinds
            ],
            "source_match_set_id": "ms-1",
            "source_set": {},
            "staging_dir": "rebuild_staging/ms-1",
        },
    )


def _group(
    category: str,
    load_kind: str,
    files: tuple[RebuildFileRef, ...],
) -> RebuildGroupRef:
    return RebuildGroupRef(
        category=category,
        source_file_group_id=f"g-{category}",
        group_sha256="a" * 64,
        user_yyyymm="202604",
        effective_yyyymm="202604",
        load_kinds=(
            ("juso_text_load", "juso_parcel_link_load")
            if category == "roadname_hangul_full"
            else (load_kind,)
        ),
        object_keys=tuple(file.object_key for file in files),
        file_ids=tuple(file.source_file_id for file in files),
        storage_uris=tuple(file.storage_uri or "" for file in files),
        files=files,
    )


def _service() -> SourceRebuildService:
    return SourceRebuildService(cast("Any", object()))


def _file(
    *,
    source_file_id: str,
    object_key: str,
    part_key: str = "archive",
    part_label: str | None = None,
    original_filename: str | None = "",
    sha256: str | None = None,
    compression_format: str | None = "zip",
) -> RebuildFileRef:
    filename = Path(object_key).name if original_filename == "" else original_filename
    return RebuildFileRef(
        source_file_id=source_file_id,
        part_key=part_key,
        part_label=part_label,
        original_filename=filename,
        object_key=object_key,
        storage_uri=f"rustfs://bucket/{object_key}",
        sha256=sha256,
        size_bytes=None,
        compression_format=compression_format,
    )


def _write_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as zip_file:
        for name, content in files.items():
            zip_file.writestr(name, content)
