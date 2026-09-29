"""T-312 DB lifecycle capability detection: role probe → supported/reason, cache, gate.

The shared control-plane instance's app role is NOSUPERUSER/NOCREATEDB with no CONNECT on the
``postgres`` maintenance DB (T-308, prod-verified 2026-09-29). Those facts must turn the DB
lifecycle features off in ``auto`` mode, while a dedicated superuser instance (dev/tests)
keeps everything on. ``enabled``/``disabled`` force the answer without touching the DB.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from kortravelgeo.exceptions import ConflictError, InvalidInputError, UnsupportedOnInstanceError
from kortravelgeo.infra import db_capabilities as caps_mod
from kortravelgeo.infra.db_capabilities import (
    DB_LIFECYCLE_FEATURES,
    DbRoleProbe,
    clear_db_capability_cache,
    db_lifecycle_capabilities,
    evaluate_db_lifecycle,
    probe_db_role,
    require_db_lifecycle,
)
from kortravelgeo.settings import Settings

_NOW = datetime(2026, 9, 29, tzinfo=UTC)
_SUPERUSER = DbRoleProbe(
    role="addr", is_superuser=True, can_create_database=True, can_connect_maintenance_database=True
)
#: kor-travel-shared-postgres, 2026-09-29: rolsuper=f, rolcreatedb=f, CONNECT postgres=f.
_SHARED_APP_ROLE = DbRoleProbe(
    role="kor_travel_geo_app",
    is_superuser=False,
    can_create_database=False,
    can_connect_maintenance_database=False,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_db_capability_cache()


def test_auto_superuser_keeps_every_lifecycle_feature_enabled() -> None:
    result = evaluate_db_lifecycle("auto", _SUPERUSER, checked_at=_NOW)

    assert result.supported is True
    assert result.reason is None
    assert result.is_superuser is True
    assert result.features == DB_LIFECYCLE_FEATURES
    assert result.maintenance_database == "postgres"


def test_auto_shared_instance_app_role_is_unsupported_with_both_reasons() -> None:
    result = evaluate_db_lifecycle("auto", _SHARED_APP_ROLE, checked_at=_NOW)

    assert result.supported is False
    assert result.role == "kor_travel_geo_app"
    assert result.can_create_database is False
    assert result.can_connect_maintenance_database is False
    assert result.reason is not None
    assert "kor_travel_geo_app" in result.reason
    assert "CREATEDB" in result.reason
    assert "'postgres' CONNECT" in result.reason


@pytest.mark.parametrize(
    ("can_create", "can_connect", "missing"),
    [
        (True, False, "CONNECT"),
        (False, True, "CREATEDB"),
    ],
)
def test_auto_needs_both_createdb_and_maintenance_connect(
    can_create: bool, can_connect: bool, missing: str
) -> None:
    probe = DbRoleProbe(
        role="ops",
        is_superuser=False,
        can_create_database=can_create,
        can_connect_maintenance_database=can_connect,
    )

    result = evaluate_db_lifecycle("auto", probe, checked_at=_NOW)

    assert result.supported is False
    assert result.reason is not None
    assert missing in result.reason


def test_auto_non_superuser_with_createdb_and_connect_is_supported() -> None:
    probe = DbRoleProbe(
        role="ops",
        is_superuser=False,
        can_create_database=True,
        can_connect_maintenance_database=True,
    )

    assert evaluate_db_lifecycle("auto", probe, checked_at=_NOW).supported is True


def test_enabled_and_disabled_modes_do_not_need_a_probe() -> None:
    enabled = evaluate_db_lifecycle("enabled", None, checked_at=_NOW)
    disabled = evaluate_db_lifecycle("disabled", None, checked_at=_NOW)

    assert enabled.supported is True
    assert enabled.role is None
    assert disabled.supported is False
    assert disabled.reason == "KTG_DB_LIFECYCLE_MODE=disabled"


def test_auto_without_probe_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="role probe"):
        evaluate_db_lifecycle("auto", None, checked_at=_NOW)


class _FakeUrl:
    def __init__(self, key: str) -> None:
        self.key = key

    def render_as_string(self, *, hide_password: bool) -> str:
        assert hide_password is True
        return self.key


class _FakeEngine:
    def __init__(self, key: str = "postgresql+psycopg://app:***@db:11000/kor_travel_geo") -> None:
        self.url = _FakeUrl(key)


@pytest.mark.asyncio
async def test_auto_probe_is_cached_per_engine_url_until_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probed: list[str] = []
    clock = {"now": 1_000.0}

    async def fake_probe(engine: _FakeEngine, _maintenance_database: str) -> DbRoleProbe:
        probed.append(engine.url.key)
        return _SHARED_APP_ROLE

    monkeypatch.setattr(caps_mod, "probe_db_role", fake_probe)
    monkeypatch.setattr(caps_mod, "monotonic", lambda: clock["now"])
    settings = Settings(_env_file=None)
    engine = _FakeEngine()

    first = await db_lifecycle_capabilities(engine, settings)  # type: ignore[arg-type]
    second = await db_lifecycle_capabilities(engine, settings)  # type: ignore[arg-type]
    assert first.supported is second.supported is False
    assert probed == [engine.url.key]  # second call served from the cache

    # a different role/instance (different URL) is probed on its own
    await db_lifecycle_capabilities(_FakeEngine("other"), settings)  # type: ignore[arg-type]
    assert probed == [engine.url.key, "other"]

    # past the TTL the same engine is probed again (e.g. the operator granted CREATEDB)
    clock["now"] += 301.0
    await db_lifecycle_capabilities(engine, settings)  # type: ignore[arg-type]
    assert probed == [engine.url.key, "other", engine.url.key]


@pytest.mark.asyncio
@pytest.mark.parametrize(("mode", "supported"), [("enabled", True), ("disabled", False)])
async def test_forced_modes_never_touch_the_database(
    monkeypatch: pytest.MonkeyPatch, mode: str, supported: bool
) -> None:
    async def fail_probe(_engine: object, _maintenance_database: str) -> DbRoleProbe:
        raise AssertionError("forced mode must not probe the DB")

    monkeypatch.setattr(caps_mod, "probe_db_role", fail_probe)
    settings = Settings(_env_file=None, db_lifecycle_mode=mode)

    result = await db_lifecycle_capabilities(object(), settings)  # type: ignore[arg-type]

    assert result.mode == mode
    assert result.supported is supported


@pytest.mark.asyncio
async def test_require_raises_e0410_conflict_with_feature_and_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_probe(_engine: object, _maintenance_database: str) -> DbRoleProbe:
        return _SHARED_APP_ROLE

    monkeypatch.setattr(caps_mod, "probe_db_role", fake_probe)

    with pytest.raises(UnsupportedOnInstanceError) as excinfo:
        await require_db_lifecycle(
            _FakeEngine(),  # type: ignore[arg-type]
            Settings(_env_file=None),
            "hot_swap",
        )

    exc = excinfo.value
    assert isinstance(exc, ConflictError)
    assert exc.code == "E0410"
    assert exc.http_status == 409
    assert exc.message.startswith("restore hot-swap: ")
    assert "공용 DB instance에서는 지원하지 않음" in exc.message
    assert "ktdctl" in exc.message
    assert exc.hint is not None
    assert "kor_travel_geo_app" in exc.hint


@pytest.mark.asyncio
async def test_require_passes_on_a_superuser_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_probe(_engine: object, _maintenance_database: str) -> DbRoleProbe:
        return _SUPERUSER

    monkeypatch.setattr(caps_mod, "probe_db_role", fake_probe)

    for feature in DB_LIFECYCLE_FEATURES:
        await require_db_lifecycle(
            _FakeEngine(),  # type: ignore[arg-type]
            Settings(_env_file=None),
            feature,
        )


class _FakeResult:
    def __init__(self, row: dict[str, Any]) -> None:
        self._row = row

    def mappings(self) -> _FakeResult:
        return self

    def one(self) -> dict[str, Any]:
        return self._row


class _FakeConn:
    def __init__(self, row: dict[str, Any], seen: dict[str, Any]) -> None:
        self._row = row
        self._seen = seen

    async def __aenter__(self) -> _FakeConn:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def execute(self, statement: Any, params: dict[str, Any]) -> _FakeResult:
        self._seen["sql"] = str(statement)
        self._seen["params"] = params
        return _FakeResult(self._row)


class _ProbeEngine:
    def __init__(self, row: dict[str, Any], seen: dict[str, Any]) -> None:
        self._row = row
        self._seen = seen

    def connect(self) -> _FakeConn:
        return _FakeConn(self._row, self._seen)


@pytest.mark.asyncio
async def test_probe_reads_role_attributes_and_maintenance_connect() -> None:
    seen: dict[str, Any] = {}
    engine = _ProbeEngine(
        {
            "role": "kor_travel_geo_app",
            "is_superuser": False,
            "can_create_database": False,
            "can_connect_maintenance_database": False,
            "maintenance_database_exists": True,
        },
        seen,
    )

    probe = await probe_db_role(engine)  # type: ignore[arg-type]

    assert probe == _SHARED_APP_ROLE
    assert seen["params"] == {"maintenance_database": "postgres"}
    # rolcreatedb OR rolsuper, and CONNECT resolved via pg_database (a missing DB → false)
    assert "rolcreatedb" in seen["sql"]
    assert "has_database_privilege(d.oid, 'CONNECT')" in seen["sql"]
    assert "current_user" in seen["sql"]
    assert "AS maintenance_database_exists" in seen["sql"]


# --- T-321: hot-swap probes the maintenance DB it will actually connect to ------------------


@pytest.mark.asyncio
async def test_probe_binds_the_requested_maintenance_database() -> None:
    seen: dict[str, Any] = {}
    engine = _ProbeEngine(
        {
            "role": "ops",
            "is_superuser": False,
            "can_create_database": True,
            "can_connect_maintenance_database": False,
            "maintenance_database_exists": False,
        },
        seen,
    )

    probe = await probe_db_role(engine, "kor_travel_geo_admin")  # type: ignore[arg-type]

    assert seen["params"] == {"maintenance_database": "kor_travel_geo_admin"}
    assert probe.maintenance_database_exists is False
    assert probe.can_connect_maintenance_database is False


def test_evaluate_names_the_requested_maintenance_database() -> None:
    probe = DbRoleProbe(
        role="ops",
        is_superuser=False,
        can_create_database=True,
        can_connect_maintenance_database=False,
    )

    result = evaluate_db_lifecycle(
        "auto", probe, checked_at=_NOW, maintenance_database="kor_travel_geo_admin"
    )

    assert result.supported is False
    assert result.maintenance_database == "kor_travel_geo_admin"
    assert result.reason == "role ops: maintenance DB 'kor_travel_geo_admin' CONNECT 권한 없음"


def test_evaluate_reports_a_missing_maintenance_database_as_missing() -> None:
    """A typo'd maintenance DB must not read as a privilege problem."""
    probe = DbRoleProbe(
        role="addr",
        is_superuser=True,
        can_create_database=True,
        can_connect_maintenance_database=False,
        maintenance_database_exists=False,
    )

    result = evaluate_db_lifecycle("auto", probe, checked_at=_NOW, maintenance_database="typo_db")

    assert result.supported is False
    assert result.reason == "role addr: maintenance DB 'typo_db' 없음"


@pytest.mark.parametrize("mode", ["enabled", "disabled"])
def test_forced_modes_echo_the_requested_maintenance_database(mode: str) -> None:
    result = evaluate_db_lifecycle(
        mode,  # type: ignore[arg-type]
        None,
        checked_at=_NOW,
        maintenance_database="kor_travel_geo_admin",
    )

    assert result.maintenance_database == "kor_travel_geo_admin"


def _hardened_cluster_probe(maintenance_database: str) -> DbRoleProbe:
    """CREATEDB role on a hardened cluster: ``postgres`` CONNECT revoked, an admin DB allowed."""
    return DbRoleProbe(
        role="ops",
        is_superuser=False,
        can_create_database=True,
        can_connect_maintenance_database=maintenance_database == "kor_travel_geo_admin",
    )


@pytest.mark.asyncio
async def test_require_probes_the_requested_maintenance_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probed: list[str] = []

    async def fake_probe(_engine: object, maintenance_database: str = "postgres") -> DbRoleProbe:
        probed.append(maintenance_database)
        return _hardened_cluster_probe(maintenance_database)

    monkeypatch.setattr(caps_mod, "probe_db_role", fake_probe)
    settings = Settings(_env_file=None)
    engine = _FakeEngine()

    # the hot-swap's own maintenance DB is connectable → the gate lets it through …
    await require_db_lifecycle(
        engine,  # type: ignore[arg-type]
        settings,
        "hot_swap",
        maintenance_database="kor_travel_geo_admin",
    )
    # … while the default `postgres` probe (capabilities endpoint, drill, scratch) still refuses
    with pytest.raises(UnsupportedOnInstanceError) as excinfo:
        await require_db_lifecycle(engine, settings, "hot_swap")  # type: ignore[arg-type]

    assert probed == ["kor_travel_geo_admin", "postgres"]
    assert excinfo.value.hint == "role ops: maintenance DB 'postgres' CONNECT 권한 없음"
    default = await db_lifecycle_capabilities(engine, settings)  # type: ignore[arg-type]
    assert default.supported is False
    assert default.maintenance_database == "postgres"
    assert probed == ["kor_travel_geo_admin", "postgres"]  # the default answer is cached


@pytest.mark.asyncio
async def test_only_the_default_maintenance_database_probe_is_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A request-chosen name is an arbitrary string — caching it would grow without bound."""
    probed: list[str] = []

    async def fake_probe(_engine: object, maintenance_database: str = "postgres") -> DbRoleProbe:
        probed.append(maintenance_database)
        return _SUPERUSER

    monkeypatch.setattr(caps_mod, "probe_db_role", fake_probe)
    settings = Settings(_env_file=None)
    engine = _FakeEngine()

    for name in ("admin_a", "admin_b", "admin_c", "admin_a"):
        await require_db_lifecycle(
            engine,  # type: ignore[arg-type]
            settings,
            "hot_swap",
            maintenance_database=name,
        )
    await require_db_lifecycle(engine, settings, "hot_swap")  # type: ignore[arg-type]
    await require_db_lifecycle(engine, settings, "hot_swap")  # type: ignore[arg-type]

    assert probed == ["admin_a", "admin_b", "admin_c", "admin_a", "postgres"]
    assert list(caps_mod._probe_cache) == [engine.url.key]


# --- T-321: a request-chosen maintenance DB missing from the cluster is an input error -----


def _createdb_role_without(maintenance_database_exists: bool) -> DbRoleProbe:
    return DbRoleProbe(
        role="addr",
        is_superuser=True,
        can_create_database=True,
        can_connect_maintenance_database=False,
        maintenance_database_exists=maintenance_database_exists,
    )


@pytest.mark.asyncio
async def test_missing_requested_maintenance_database_is_an_input_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_probe(_engine: object, _maintenance_database: str = "postgres") -> DbRoleProbe:
        return _createdb_role_without(maintenance_database_exists=False)

    monkeypatch.setattr(caps_mod, "probe_db_role", fake_probe)

    with pytest.raises(InvalidInputError) as excinfo:
        await require_db_lifecycle(
            _FakeEngine(),  # type: ignore[arg-type]
            Settings(_env_file=None),
            "hot_swap",
            maintenance_database="typo_db",
        )

    assert not isinstance(excinfo.value, UnsupportedOnInstanceError)
    assert excinfo.value.code == "E0100"
    assert excinfo.value.http_status == 400
    assert excinfo.value.message == "maintenance_database does not exist in cluster: typo_db"


@pytest.mark.asyncio
async def test_missing_default_maintenance_database_stays_an_instance_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drill/scratch/restore cannot pick another DB — a missing ``postgres`` is the instance's."""

    async def fake_probe(_engine: object, _maintenance_database: str = "postgres") -> DbRoleProbe:
        return _createdb_role_without(maintenance_database_exists=False)

    monkeypatch.setattr(caps_mod, "probe_db_role", fake_probe)

    with pytest.raises(UnsupportedOnInstanceError) as excinfo:
        await require_db_lifecycle(
            _FakeEngine(),  # type: ignore[arg-type]
            Settings(_env_file=None),
            "restore_drill",
        )

    assert excinfo.value.hint == "role addr: maintenance DB 'postgres' 없음"


@pytest.mark.asyncio
async def test_nocreatedb_role_is_refused_even_when_the_requested_db_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The instance limitation dominates — fixing the name would only lead to the same 409."""

    async def fake_probe(_engine: object, _maintenance_database: str = "postgres") -> DbRoleProbe:
        return DbRoleProbe(
            role="kor_travel_geo_app",
            is_superuser=False,
            can_create_database=False,
            can_connect_maintenance_database=False,
            maintenance_database_exists=False,
        )

    monkeypatch.setattr(caps_mod, "probe_db_role", fake_probe)

    with pytest.raises(UnsupportedOnInstanceError) as excinfo:
        await require_db_lifecycle(
            _FakeEngine(),  # type: ignore[arg-type]
            Settings(_env_file=None),
            "hot_swap",
            maintenance_database="typo_db",
        )

    assert excinfo.value.hint == (
        "role kor_travel_geo_app: CREATEDB 권한 없음, maintenance DB 'typo_db' 없음"
    )


# --- T-321: E0410 for db_restore carries the shared-instance restore procedure -------------


@pytest.mark.asyncio
async def test_db_restore_refusal_hint_carries_the_shared_instance_procedure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_probe(_engine: object, _maintenance_database: str = "postgres") -> DbRoleProbe:
        return _SHARED_APP_ROLE

    monkeypatch.setattr(caps_mod, "probe_db_role", fake_probe)

    with pytest.raises(UnsupportedOnInstanceError) as excinfo:
        await require_db_lifecycle(
            _FakeEngine(),  # type: ignore[arg-type]
            Settings(_env_file=None),
            "db_restore",
        )

    hint = excinfo.value.hint
    assert hint is not None
    reason, procedure = hint.split("; ", 1)
    assert reason.startswith("role kor_travel_geo_app: CREATEDB 권한 없음")
    assert procedure == caps_mod.DB_RESTORE_SHARED_INSTANCE_PROCEDURE
    assert "target_dsn" in procedure
    assert "ktgctl restore create --target-dsn" in procedure
    assert "docs/t046-db-backup-restore.md" in procedure


@pytest.mark.asyncio
@pytest.mark.parametrize("feature", ["hot_swap", "restore_drill", "scratch_full_load"])
async def test_features_without_an_alternative_keep_the_bare_reason(
    monkeypatch: pytest.MonkeyPatch, feature: str
) -> None:
    async def fake_probe(_engine: object, _maintenance_database: str = "postgres") -> DbRoleProbe:
        return _SHARED_APP_ROLE

    monkeypatch.setattr(caps_mod, "probe_db_role", fake_probe)

    with pytest.raises(UnsupportedOnInstanceError) as excinfo:
        await require_db_lifecycle(
            _FakeEngine(),  # type: ignore[arg-type]
            Settings(_env_file=None),
            feature,  # type: ignore[arg-type]
        )

    assert excinfo.value.hint is not None
    assert "target_dsn" not in excinfo.value.hint
