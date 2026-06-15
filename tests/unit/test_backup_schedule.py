"""T-239 scheduled backup due-check policy (pure).

``decide_scheduled_backup`` is the unit-tested core of the cron ``run-due`` trigger:
given whether scheduling is enabled, when the last scheduled backup ran, and whether one
is in progress, it decides whether to enqueue another at ``now``. ``scheduled_backup_payload``
tags the enqueued job ``retention_class='scheduled'``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from kortravelgeo.infra.backup_schedule import (
    SCHEDULED_RETENTION_CLASS,
    decide_scheduled_backup,
    scheduled_backup_payload,
)
from kortravelgeo.settings import Settings

_NOW = datetime(2026, 6, 16, 12, 0, 0, tzinfo=UTC)


def _decide(**overrides: object):
    base: dict[str, object] = {
        "enabled": True,
        "last_scheduled_at": None,
        "has_active_scheduled_job": False,
        "interval_hours": 24.0,
        "keep_min": 3,
        "now": _NOW,
    }
    base.update(overrides)
    return decide_scheduled_backup(**base)  # type: ignore[arg-type]


def test_disabled_is_never_due() -> None:
    status = _decide(enabled=False, last_scheduled_at=_NOW - timedelta(days=10))
    assert status.enabled is False
    assert status.due is False
    assert status.reason == "disabled"


def test_never_run_is_due_initial() -> None:
    status = _decide(last_scheduled_at=None)
    assert status.due is True
    assert status.reason == "due_initial"
    assert status.last_scheduled_at is None
    assert status.next_due_at is None


def test_in_progress_blocks_even_when_interval_elapsed() -> None:
    status = _decide(
        last_scheduled_at=_NOW - timedelta(days=5),
        has_active_scheduled_job=True,
    )
    assert status.due is False
    assert status.reason == "in_progress"
    assert status.in_progress is True


def test_within_interval_is_not_due() -> None:
    last = _NOW - timedelta(hours=10)
    status = _decide(last_scheduled_at=last, interval_hours=24.0)
    assert status.due is False
    assert status.reason == "not_due"
    assert status.next_due_at == last + timedelta(hours=24)


def test_interval_elapsed_is_due() -> None:
    last = _NOW - timedelta(hours=25)
    status = _decide(last_scheduled_at=last, interval_hours=24.0)
    assert status.due is True
    assert status.reason == "due"
    assert status.next_due_at == last + timedelta(hours=24)


def test_exact_interval_boundary_is_due() -> None:
    last = _NOW - timedelta(hours=24)
    status = _decide(last_scheduled_at=last, interval_hours=24.0)
    assert status.due is True
    assert status.reason == "due"


def test_status_echoes_interval_and_keep_min() -> None:
    status = _decide(interval_hours=6.0, keep_min=5)
    assert status.interval_hours == 6.0
    assert status.keep_min == 5
    assert status.retention_class == SCHEDULED_RETENTION_CLASS


def test_payload_tags_scheduled_retention_class() -> None:
    payload = scheduled_backup_payload(Settings(pg_dsn="postgresql://a:b@localhost:5432/db"))
    assert payload["retention_class"] == SCHEDULED_RETENTION_CLASS
    # default profile is preserved so a scheduled backup is serving-ready by default
    assert payload["profile"] == "serving-ready"
