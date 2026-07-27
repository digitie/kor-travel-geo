"""T-235 restore-target cleanup decision (pure).

On cancel/fail, a partially-filled ``new_database`` target the job owns (verified
empty at start) is dropped/quarantined per policy; ``replace_current`` (the live
serving DB) is **never** auto-cleaned. The actual drop/rename via a maintenance
connection is integration-tested in T-245.
"""

from __future__ import annotations

from typing import Any

import pytest

from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra import backup as backup_module
from kortravelgeo.infra.backup import (
    quarantine_restore_database_name,
    quote_database_identifier,
    restore_target_cleanup_action,
    validate_database_identifier,
)


def test_replace_current_is_never_cleaned() -> None:
    # even with an aggressive policy and an owned target.
    assert (
        restore_target_cleanup_action(
            mode="replace_current", policy="drop", job_owns_target=True
        )
        is None
    )


def test_unowned_target_is_not_cleaned() -> None:
    # the target was not verified empty (not new_database flow) → leave it.
    assert (
        restore_target_cleanup_action(
            mode="new_database", policy="drop", job_owns_target=False
        )
        is None
    )


def test_quarantine_policy_returns_quarantine() -> None:
    assert (
        restore_target_cleanup_action(
            mode="new_database", policy="quarantine", job_owns_target=True
        )
        == "quarantine"
    )


def test_drop_policy_returns_drop() -> None:
    assert (
        restore_target_cleanup_action(
            mode="new_database", policy="drop", job_owns_target=True
        )
        == "drop"
    )


def test_keep_and_unknown_policy_do_nothing() -> None:
    assert (
        restore_target_cleanup_action(
            mode="new_database", policy="keep", job_owns_target=True
        )
        is None
    )
    assert (
        restore_target_cleanup_action(
            mode="new_database", policy="bogus", job_owns_target=True
        )
        is None
    )


def test_restore_database_identifier_rejects_quotes() -> None:
    with pytest.raises(InvalidInputError, match="target_database must match"):
        validate_database_identifier('restore"db', "target_database")


def test_quote_database_identifier_only_quotes_valid_names() -> None:
    assert quote_database_identifier("kor_travel_geo_restore") == '"kor_travel_geo_restore"'


async def test_cleanup_orphan_restore_target_preserves_password_in_maintenance_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#299 (실 라이브 실행이 발견한 회귀): SQLAlchemy URL의 기본 __str__는 비밀번호를
    ``***``로 마스킹한다. maintenance 연결 DSN을 ``str(url)``로 만들면 실제 비밀번호
    대신 문자 그대로 ``***``로 인증을 시도해 항상 실패한다 — drop/quarantine cleanup이
    조용히 100% 실패하던 원인. render_as_string(hide_password=False) 고정을 회귀 방지."""
    captured_dsns: list[str] = []

    class _FakeConnection:
        async def __aenter__(self) -> _FakeConnection:
            return self

        async def __aexit__(self, *exc_info: object) -> bool:
            return False

        async def execute(self, *args: Any, **kwargs: Any) -> None:
            return None

    class _FakeEngine:
        def connect(self) -> _FakeConnection:
            return _FakeConnection()

        async def dispose(self) -> None:
            return None

    def fake_create_async_engine(dsn: str, **kwargs: Any) -> _FakeEngine:
        captured_dsns.append(dsn)
        return _FakeEngine()

    monkeypatch.setattr(backup_module, "create_async_engine", fake_create_async_engine)

    await backup_module.cleanup_orphan_restore_target(
        "postgresql+psycopg://addr:s3cr3t_pw@localhost:5432/ktg_restore_target",
        action="drop",
        timestamp="20260101T000000Z",
    )

    assert len(captured_dsns) == 1
    assert "s3cr3t_pw" in captured_dsns[0]
    assert "***" not in captured_dsns[0]


def test_quarantine_name_stays_within_postgres_identifier_limit() -> None:
    name = quarantine_restore_database_name(
        "a" * 63,
        "20260616T123456Z",
    )

    assert len(name) == 63
    assert name.endswith("_quarantine_20260616T123456Z")
