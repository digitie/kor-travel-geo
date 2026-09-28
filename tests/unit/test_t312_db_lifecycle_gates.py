"""T-312: DB lifecycle features are refused early (E0410/409) where the role cannot run them.

Each gate is exercised with ``KTG_DB_LIFECYCLE_MODE=disabled`` (no DB probe) and asserts the
refusal happens BEFORE the side effect it guards — the load_jobs row / Dagster launch, the
scratch ``CREATE DATABASE``, the hot-swap/drill infra call, the archive resolution. The
positive direction (a supported instance still reaches the side effect) is asserted too, so a
gate that blocks everything would fail here.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from kortravelgeo import client as client_mod
from kortravelgeo.api import _full_load_launch as launch_mod
from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.api.routers import admin as admin_mod
from kortravelgeo.api.security import ROLE_DESTRUCTIVE_ADMIN
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.dto.admin import (
    RestoreCreateRequest,
    RestoreHotSwapExecuteRequest,
    RestoreHotSwapPlanRequest,
    RestoreHotSwapRollbackRequest,
)
from kortravelgeo.exceptions import UnsupportedOnInstanceError
from kortravelgeo.infra import backup as backup_mod
from kortravelgeo.infra import db_capabilities as caps_mod
from kortravelgeo.infra import hotswap as hotswap_mod
from kortravelgeo.infra import restore_drill as drill_mod
from kortravelgeo.infra.restore_toc import RestoreTargetRole
from kortravelgeo.settings import Settings, get_settings

if TYPE_CHECKING:
    from pathlib import Path

_DISABLED = Settings(_env_file=None, db_lifecycle_mode="disabled")
_ENABLED = Settings(_env_file=None, db_lifecycle_mode="enabled")
_BATCH = {"children": [{"kind": "juso_text_load", "payload": {"path": "/data/juso"}}]}


@pytest.fixture(autouse=True)
def _clear_capability_cache() -> None:
    caps_mod.clear_db_capability_cache()


class _SentinelError(Exception):
    """Raised by a stubbed side effect to prove the gate let the call through."""


# --- pg_dump / pg_restore flags ------------------------------------------------------


def test_pg_dump_keeps_owners_and_acls(tmp_path: Path) -> None:
    cmd = backup_mod.build_pg_dump_command(
        "postgresql+psycopg://app:pw@db:11000/kor_travel_geo",
        tmp_path / "dump",
        profile="serving-ready",
        jobs=2,
    )

    # The admin's GRANT USAGE ON SCHEMA x_extension TO <app role> lives only in the dump's ACL
    # entry; a superuser `pg_restore --clean` recreates x_extension from the dump, so dropping
    # ACLs at dump time would strip the app role's access to PostGIS. Ownership/ACLs are
    # stripped at restore time instead, and only for a non-superuser restore (role_neutral).
    assert "--no-privileges" not in cmd.argv
    assert "--no-acl" not in cmd.argv
    # pg_dump ignores --no-owner for archive formats (owners stay in the TOC) anyway.
    assert "--no-owner" not in cmd.argv


def test_pg_restore_role_neutral_only_when_asked(tmp_path: Path) -> None:
    dsn = "postgresql+psycopg://app:pw@db:11000/kor_travel_geo_restore"
    default = backup_mod.build_pg_restore_command(dsn, tmp_path, jobs=2)
    neutral = backup_mod.build_pg_restore_command(dsn, tmp_path, jobs=2, role_neutral=True)

    assert "--no-owner" not in default.argv
    assert "--no-privileges" not in default.argv
    assert "--no-owner" in neutral.argv
    assert "--no-privileges" in neutral.argv
    # the flags precede the positional dump dir
    assert neutral.argv[-1] == str(tmp_path)


# --- smoke test: DB owner must reach the extension schema -------------------------------


class _SmokeResult:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    def mappings(self) -> _SmokeResult:
        return self

    def all(self) -> list[dict[str, str]]:
        return self._rows


class _SmokeConn:
    def __init__(self, no_usage: list[dict[str, str]]) -> None:
        self._no_usage = no_usage

    async def __aenter__(self) -> _SmokeConn:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def scalar(self, _stmt: object) -> int:
        return 5  # public/ops table count and postgis extension count are both present

    async def execute(self, stmt: object) -> _SmokeResult:
        assert "has_schema_privilege" in str(stmt)
        return _SmokeResult(self._no_usage)


class _SmokeEngine:
    def __init__(self, no_usage: list[dict[str, str]]) -> None:
        self._no_usage = no_usage
        self.disposed = False

    def connect(self) -> _SmokeConn:
        return _SmokeConn(self._no_usage)

    async def dispose(self) -> None:
        self.disposed = True


@pytest.mark.asyncio
async def test_smoke_test_fails_when_the_db_owner_lost_extension_schema_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A superuser restore that dropped the admin's x_extension grant must not pass smoke."""
    engine = _SmokeEngine([{"db_owner": "kor_travel_geo_app", "schema_name": "x_extension"}])
    monkeypatch.setattr(backup_mod, "create_async_engine", lambda _dsn: engine)

    with pytest.raises(backup_mod.InvalidInputError) as excinfo:
        await backup_mod.smoke_test_restore("postgresql+psycopg://adm:pw@db/kor_travel_geo_r")

    message = str(excinfo.value)
    assert "kor_travel_geo_app" in message
    assert "GRANT USAGE ON SCHEMA x_extension TO kor_travel_geo_app" in message
    assert engine.disposed


@pytest.mark.asyncio
async def test_smoke_test_passes_when_the_db_owner_reaches_every_extension_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _SmokeEngine([])
    monkeypatch.setattr(backup_mod, "create_async_engine", lambda _dsn: engine)

    await backup_mod.smoke_test_restore("postgresql+psycopg://adm:pw@db/kor_travel_geo_r")

    assert engine.disposed


# --- restore TOC filter wiring ----------------------------------------------------------

_TOC = [
    "; Selected TOC Entries:",
    "10; 2615 19715 SCHEMA - x_extension shared_admin",
    "2; 3079 19716 EXTENSION - postgis ",
    "252; 1259 21170 TABLE public geo_cache kor_travel_geo_app",
]


@pytest.mark.asyncio
async def test_superuser_target_keeps_the_existing_use_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail_capture(_dump_dir: Path) -> list[str]:
        raise AssertionError("a superuser restore must not rewrite the TOC")

    monkeypatch.setattr(backup_mod, "capture_pg_restore_toc", fail_capture)

    path, skipped = await backup_mod._apply_preprovisioned_toc_filter(
        tmp_path, tmp_path, None, RestoreTargetRole(is_superuser=True)
    )

    assert path is None
    assert skipped == ()


@pytest.mark.asyncio
async def test_non_superuser_target_writes_a_filtered_use_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_capture(_dump_dir: Path) -> list[str]:
        return list(_TOC)

    monkeypatch.setattr(backup_mod, "capture_pg_restore_toc", fake_capture)
    role = RestoreTargetRole(
        is_superuser=False,
        unmanaged_extensions=("postgis",),
        unmanaged_extension_schemas=("x_extension",),
    )

    path, skipped = await backup_mod._apply_preprovisioned_toc_filter(
        tmp_path, tmp_path, None, role
    )

    assert path == tmp_path / "restore-use-list.txt"
    assert len(skipped) == 2
    written = path.read_text(encoding="utf-8").splitlines()
    assert ";10; 2615 19715 SCHEMA - x_extension shared_admin" in written
    assert ";2; 3079 19716 EXTENSION - postgis " in written
    assert "252; 1259 21170 TABLE public geo_cache kor_travel_geo_app" in written


@pytest.mark.asyncio
async def test_filter_reads_an_existing_partial_restore_use_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail_capture(_dump_dir: Path) -> list[str]:
        raise AssertionError("must filter the partial-restore list, not the full TOC")

    monkeypatch.setattr(backup_mod, "capture_pg_restore_toc", fail_capture)
    partial = tmp_path / "partial-use-list.txt"
    partial.write_text(";252; 0 1 TABLE DATA public geo_cache app\n" + "\n".join(_TOC) + "\n")
    role = RestoreTargetRole(is_superuser=False, unmanaged_extensions=("postgis",))

    path, skipped = await backup_mod._apply_preprovisioned_toc_filter(
        tmp_path, tmp_path, partial, role
    )

    assert path is not None and path != partial
    written = path.read_text(encoding="utf-8").splitlines()
    assert written[0] == ";252; 0 1 TABLE DATA public geo_cache app"  # T-243 skip survives
    assert skipped == ("2; 3079 19716 EXTENSION - postgis",)


# --- run_restore_job / dry-run -----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"artifact_id": "art-1", "target_database": "kor_travel_geo_restore"},
        # "" falls back to the app's own credentials (resolve_restore_target_dsn) → gated too
        {"artifact_id": "art-1", "target_database": "kor_travel_geo_restore", "target_dsn": ""},
    ],
)
async def test_run_restore_job_refuses_before_touching_the_archive(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    async def fail_resolve(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("gate must run before the archive is resolved")

    monkeypatch.setattr(backup_mod, "resolve_restore_archive", fail_resolve)

    with pytest.raises(UnsupportedOnInstanceError, match="DB 복원"):
        await backup_mod.run_restore_job(
            object(),  # type: ignore[arg-type]
            _DISABLED,
            payload,
            asyncio.Event(),
            _noop_progress,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("settings", "payload"),
    [
        # supported instance → gate passes
        (_ENABLED, {"artifact_id": "art-1", "target_database": "kor_travel_geo_restore"}),
        # explicit target_dsn carries its own credentials → not gated even when disabled
        (_DISABLED, {"artifact_id": "art-1", "target_dsn": "postgresql://adm:pw@h/x"}),
    ],
)
async def test_run_restore_job_passes_the_gate_when_allowed(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, payload: dict[str, Any]
) -> None:
    async def sentinel_resolve(*_args: object, **_kwargs: object) -> None:
        raise _SentinelError

    monkeypatch.setattr(backup_mod, "resolve_restore_archive", sentinel_resolve)

    with pytest.raises(_SentinelError):
        await backup_mod.run_restore_job(
            object(),  # type: ignore[arg-type]
            settings,
            payload,
            asyncio.Event(),
            _noop_progress,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("target_dsn", [None, ""])
async def test_restore_dry_run_reports_the_capability_as_a_blocker(
    monkeypatch: pytest.MonkeyPatch, target_dsn: str | None
) -> None:
    async def empty_ok(_target_dsn: str) -> None:
        return None

    async def missing_archive(*_args: object, **_kwargs: object) -> None:
        raise backup_mod.NotFoundError("missing archive")

    monkeypatch.setattr(backup_mod, "ensure_target_database_empty", empty_ok)
    monkeypatch.setattr(backup_mod, "resolve_restore_archive", missing_archive)
    req = RestoreCreateRequest(
        archive_path="x.tar.zst", target_database="kor_travel_geo_r", target_dsn=target_dsn
    )

    result = await backup_mod.run_restore_dry_run(object(), _DISABLED, req)  # type: ignore[arg-type]

    assert result.can_restore is False
    assert any("공용 DB instance에서는 지원하지 않음" in b for b in result.blockers)


# --- blue-green scratch full-load --------------------------------------------------------


@pytest.mark.asyncio
async def test_scratch_full_load_refused_before_the_scratch_db_is_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_ensure(*_args: object) -> None:
        raise AssertionError("scratch DB must not be created on an unsupported instance")

    async def fail_launch(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("no Dagster run may be launched")

    monkeypatch.setattr(launch_mod, "ensure_scratch_database", fail_ensure)
    monkeypatch.setattr(launch_mod, "launch_dagster_run", fail_launch)

    with pytest.raises(UnsupportedOnInstanceError, match="scratch full-load"):
        await launch_mod.launch_full_load_batch_dagster_run(
            object(),  # type: ignore[arg-type]
            _DISABLED,
            {**_BATCH, "target_database": "kor_travel_geo_fullload_e2e"},
        )


@pytest.mark.asyncio
async def test_serving_full_load_is_not_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    """A full-load without target_database runs against serving — no CREATE DATABASE needed."""

    class _Repo:
        def __init__(self, _engine: object) -> None:
            pass

        async def insert_load_batch(self, **_kwargs: object) -> Any:
            raise _SentinelError

    monkeypatch.setattr(launch_mod, "AdminRepository", _Repo)

    with pytest.raises(_SentinelError):
        await launch_mod.launch_full_load_batch_dagster_run(
            object(),  # type: ignore[arg-type]
            _DISABLED,
            dict(_BATCH),
        )


# --- client: hot-swap plan/execute/rollback + restore drill ----------------------------


def _disabled_client() -> AsyncAddressClient:
    return AsyncAddressClient(settings=_DISABLED, engine=object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_hot_swap_plan_refused_before_the_maintenance_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_plan(*_args: object) -> None:
        raise AssertionError("must not connect to the maintenance DB")

    monkeypatch.setattr(client_mod, "inspect_restore_hot_swap_plan", fail_plan)

    with pytest.raises(UnsupportedOnInstanceError, match="hot-swap"):
        await _disabled_client().restore_hot_swap_plan(
            RestoreHotSwapPlanRequest(restore_database="kor_travel_geo_restore")
        )


@pytest.mark.asyncio
async def test_hot_swap_execute_and_rollback_refused_before_rename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not reach ALTER DATABASE RENAME")

    monkeypatch.setattr(hotswap_mod, "execute_restore_hot_swap", fail)
    monkeypatch.setattr(hotswap_mod, "execute_hot_swap_rollback", fail)
    client = _disabled_client()

    with pytest.raises(UnsupportedOnInstanceError):
        await client.execute_restore_hot_swap(
            RestoreHotSwapExecuteRequest(
                restore_database="kor_travel_geo_restore", typed_confirmation="HOT_SWAP x"
            )
        )
    with pytest.raises(UnsupportedOnInstanceError):
        await client.execute_hot_swap_rollback(
            RestoreHotSwapRollbackRequest(
                previous_alias="kor_travel_geo_previous",
                restore_database="kor_travel_geo_restore",
                rollback_confirmation="ROLLBACK_HOT_SWAP x",
            )
        )


@pytest.mark.asyncio
async def test_hot_swap_plan_reaches_the_planner_when_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def sentinel_plan(*_args: object) -> None:
        raise _SentinelError

    monkeypatch.setattr(client_mod, "inspect_restore_hot_swap_plan", sentinel_plan)
    client = AsyncAddressClient(settings=_ENABLED, engine=object())  # type: ignore[arg-type]

    with pytest.raises(_SentinelError):
        await client.restore_hot_swap_plan(
            RestoreHotSwapPlanRequest(restore_database="kor_travel_geo_restore")
        )


@pytest.mark.asyncio
async def test_restore_drill_refused_before_creating_the_throwaway_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_drill(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not CREATE DATABASE")

    monkeypatch.setattr(drill_mod, "run_restore_drill", fail_drill)

    with pytest.raises(UnsupportedOnInstanceError, match="restore drill"):
        await _disabled_client().run_restore_drill(timestamp="20260929T000000Z")


# --- HTTP: admin envelope + early refusal before the load_jobs row ----------------------

_TRUSTED_PEER = ("127.0.0.1", 12345)
_ADMIN_HEADERS = {"X-KTG-Actor": "ui-admin", "X-KTG-Roles": ROLE_DESTRUCTIVE_ADMIN}


def _trusted_settings() -> Settings:
    return Settings(_env_file=None, admin_trusted_proxy_cidrs="127.0.0.0/8", geoip_gate_mode="off")


async def _post(app: Any, path: str, body: dict[str, Any]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, client=_TRUSTED_PEER)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        return await http.post(path, json=body, headers=_ADMIN_HEADERS)


def _app_with(client: object) -> Any:
    app = create_app()
    app.dependency_overrides[get_settings] = _trusted_settings
    app.dependency_overrides[get_client] = lambda: client
    return app


@pytest.mark.asyncio
async def test_db_capabilities_endpoint_reports_the_disabled_instance() -> None:
    app = _app_with(_disabled_client())
    transport = httpx.ASGITransport(app=app, client=_TRUSTED_PEER)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        resp = await http.get("/v1/admin/db-capabilities", headers=_ADMIN_HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    assert body["supported"] is False
    assert body["mode"] == "disabled"
    assert body["reason"] == "KTG_DB_LIFECYCLE_MODE=disabled"
    assert set(body["features"]) == {"hot_swap", "restore_drill", "scratch_full_load", "db_restore"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"artifact_id": "art-1", "target_database": "kor_travel_geo_restore"},
        # an empty target_dsn means "the app's own credentials" — must not skip the gate
        {"artifact_id": "art-1", "target_database": "kor_travel_geo_restore", "target_dsn": ""},
    ],
)
async def test_restore_submit_returns_409_e0410_without_creating_a_job(
    monkeypatch: pytest.MonkeyPatch, body: dict[str, Any]
) -> None:
    launched: list[object] = []

    async def record_launch(*args: object) -> str:
        launched.append(args)
        return "job-1"

    monkeypatch.setattr(admin_mod, "_launch_db_restore_dagster_run", record_launch)

    resp = await _post(_app_with(_disabled_client()), "/v1/admin/restores", body)

    assert resp.status_code == 409
    error = resp.json()["response"]
    assert error["errorCode"] == "E0410"
    assert "공용 DB instance에서는 지원하지 않음" in error["errorMessage"]
    assert error["hint"] == "KTG_DB_LIFECYCLE_MODE=disabled"
    assert launched == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/v1/admin/restores/hot-swap-plan", {"restore_database": "kor_travel_geo_restore"}),
        (
            "/v1/admin/restores/hot-swap",
            {"restore_database": "kor_travel_geo_restore", "typed_confirmation": "HOT_SWAP x"},
        ),
        (
            "/v1/admin/restores/hot-swap-rollback",
            {
                "previous_alias": "kor_travel_geo_previous",
                "restore_database": "kor_travel_geo_restore",
                "rollback_confirmation": "ROLLBACK_HOT_SWAP x",
            },
        ),
    ],
)
async def test_hot_swap_endpoints_return_409_e0410(path: str, body: dict[str, Any]) -> None:
    resp = await _post(_app_with(_disabled_client()), path, body)

    assert resp.status_code == 409
    assert resp.json()["response"]["errorCode"] == "E0410"


async def _noop_progress(
    *, progress: float | None = None, stage: str | None = None, message: str | None = None
) -> None:
    return None
