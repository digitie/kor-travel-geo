"""run_db_restore_op wiring test (T-290i): op config -> bridge, no DB / no real restore."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from dagster import Failure, build_op_context
from kortravelgeo.exceptions import UnsupportedOnInstanceError
from kortravelgeo.settings import Settings

from kortravelgeo_dagster import db_restore_execute


class _FakeClient:
    def __init__(self, engine: object, *, lifecycle_error: Exception | None = None) -> None:
        self._eng = engine
        self._lifecycle_error = lifecycle_error
        self.lifecycle_checks: list[str] = []

    def _engine(self) -> object:
        return self._eng

    async def require_db_lifecycle(self, feature: str) -> None:
        self.lifecycle_checks.append(feature)
        if self._lifecycle_error is not None:
            raise self._lifecycle_error


async def _noop_progress(*, progress=None, stage=None, message=None):
    return None


@pytest.mark.asyncio
async def test_run_db_restore_op_wires_bridge_and_passes_job_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_execute_load_job(*, job_id, orchestrator_run_id, engine, leaf):
        captured["job_id"] = job_id
        captured["orchestrator_run_id"] = orchestrator_run_id
        captured["engine"] = engine
        # Drive the leaf to confirm it wraps run_restore_job with the injected payload.
        await leaf(asyncio.Event(), _noop_progress)

    async def fake_run_restore_job(
        engine, settings, payload, cancel_event, progress, *, job_id=None
    ):
        captured["payload"] = payload
        captured["settings"] = settings
        captured["leaf_engine"] = engine
        captured["leaf_job_id"] = job_id

    monkeypatch.setattr(db_restore_execute, "execute_load_job", fake_execute_load_job)
    monkeypatch.setattr(db_restore_execute, "run_restore_job", fake_run_restore_job)

    sentinel_engine = object()
    settings = Settings(_env_file=None)

    with build_op_context(
        resources={"client": _FakeClient(sentinel_engine), "settings": settings},
        op_config={
            "job_id": "job-42",
            "payload": {"artifact_id": "art-1", "target_database": "kor_travel_geo_restore"},
        },
    ) as ctx:
        result = await db_restore_execute.run_db_restore_op(ctx)

    assert result == {"job_id": "job-42"}
    assert captured["job_id"] == "job-42"
    assert captured["engine"] is sentinel_engine
    assert captured["leaf_engine"] is sentinel_engine
    assert captured["orchestrator_run_id"]  # a Dagster run id was passed through
    # The leaf received the load_jobs id explicitly; the request payload stays clean.
    assert captured["leaf_job_id"] == "job-42"
    assert captured["payload"] == {
        "artifact_id": "art-1",
        "target_database": "kor_travel_geo_restore",
    }
    assert captured["settings"] is settings


@pytest.mark.asyncio
async def test_run_db_restore_op_refuses_unsupported_instance_inside_the_leaf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T-312: a run launched straight from Dagster (bypassing the API's E0410 gate) fails the
    adopted load_jobs row with the capability reason and never reaches run_restore_job."""
    failed: dict[str, Any] = {}

    async def fake_execute_load_job(*, job_id, orchestrator_run_id, engine, leaf):
        try:
            await leaf(asyncio.Event(), _noop_progress)
        except Exception as exc:  # the real bridge marks the row failed with str(exc)
            failed["message"] = str(exc)
            raise

    async def fail_run_restore_job(*_args, **_kwargs):
        raise AssertionError("run_restore_job must not run on an unsupported instance")

    monkeypatch.setattr(db_restore_execute, "execute_load_job", fake_execute_load_job)
    monkeypatch.setattr(db_restore_execute, "run_restore_job", fail_run_restore_job)
    client = _FakeClient(
        object(),
        lifecycle_error=UnsupportedOnInstanceError(
            "DB 복원: 공용 DB instance에서는 지원하지 않음 — 운영자가 manager ktdctl로 수행",
            hint="role kor_travel_geo_app: CREATEDB 권한 없음",
        ),
    )

    with (
        build_op_context(
            resources={"client": client, "settings": Settings(_env_file=None)},
            op_config={"job_id": "job-43", "payload": {"target_database": "kor_travel_geo_r"}},
        ) as ctx,
        pytest.raises(Failure) as excinfo,
    ):
        await db_restore_execute.run_db_restore_op(ctx)

    assert client.lifecycle_checks == ["db_restore"]
    assert "공용 DB instance에서는 지원하지 않음" in failed["message"]
    assert "CREATEDB" in failed["message"]
    assert "CREATEDB" in (excinfo.value.description or "")


def test_db_restore_job_is_registered_in_definitions() -> None:
    from kortravelgeo_dagster.definitions import defs

    job_names = {job.name for job in defs.resolve_all_job_defs()}
    assert "db_restore" in job_names
    assert defs.get_job_def("db_restore").name == "db_restore"
