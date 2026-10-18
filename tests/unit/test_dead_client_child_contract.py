"""통합시험 child에는 DSN을 argv로 넣지 않고 기존 환경을 사용한다."""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from tests.integration import test_dead_client_statement_cancel as target


def _owned_dsn():
    return "postgresql+psycopg://" + "owned:fixture_only@" + "fixture.invalid/geo_test"


async def test_dead_client_child_arguments_exclude_dsn(monkeypatch, capsys):
    dsn = _owned_dsn()
    monkeypatch.setenv("KTG_TEST_PG_DSN", dsn)
    child = SimpleNamespace(
        stdout=SimpleNamespace(readline=AsyncMock(return_value=b"READY\n")),
        send_signal=Mock(),
        wait=AsyncMock(return_value=0),
    )
    spawn = AsyncMock(return_value=child)
    monkeypatch.setattr(target.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(target, "_sleeping", AsyncMock(return_value=True))

    app = await target._kill_child_mid_query(object(), interval_ms=500)

    args, kwargs = spawn.call_args
    assert len(args) == 5
    assert args[:3] == (sys.executable, "-c", target._CHILD)
    assert args[3:] == (app, "500")
    assert dsn not in repr((args, kwargs))
    assert "env" not in kwargs
    assert dsn not in "".join(capsys.readouterr())
    child.send_signal.assert_called_once()


def test_dead_client_payload_reads_inherited_dsn_and_logs_no_value(monkeypatch, capsys):
    dsn = _owned_dsn()
    monkeypatch.setenv("KTG_TEST_PG_DSN", dsn)
    monkeypatch.setattr(sys, "argv", ["-c", "owned-app", "500"])
    received = {}
    statements = []

    class OwnedSettings:
        def __init__(self, *, pg_dsn):
            received["dsn"] = pg_dsn

        def model_copy(self, *, update):
            received["options"] = update
            return self

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def execute(self, statement):
            statements.append(str(statement))

    fake_settings = SimpleNamespace(Settings=OwnedSettings)
    fake_engine = SimpleNamespace(
        make_async_engine=lambda _: SimpleNamespace(connect=Connection),
    )
    monkeypatch.setitem(sys.modules, "kortravelgeo.settings", fake_settings)
    monkeypatch.setitem(sys.modules, "kortravelgeo.infra.engine", fake_engine)
    exec(compile(target._CHILD, "<owned-dead-client-child>", "exec"), {})

    assert received == {
        "dsn": dsn,
        "options": {
            "pg_statement_timeout_ms": 0,
            "pg_client_connection_check_interval_ms": 500,
        },
    }
    assert statements == ["SET application_name = 'owned-app'", "SELECT pg_sleep(60)"]
    captured = capsys.readouterr()
    assert captured.out == "READY\n"
    assert captured.err == ""
    assert dsn not in repr(captured)
