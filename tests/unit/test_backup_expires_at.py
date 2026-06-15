"""T-229 backup artifact TTL (expires_at / retention_class).

``artifact_expires_at`` anchors the TTL at finalize time: ``now + retention_days``
(falling back to ``settings.backup_artifact_ttl_days``). ``run_backup_job`` finalize
passes this plus ``retention_class`` to ``AdminRepository.update_artifact`` (which
gained those parameters), so the retention janitor (T-230) and the ``ops.artifacts``
``expired`` count have a real basis instead of an always-NULL ``expires_at``.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.backup import (
    DEFAULT_BACKUP_RETENTION_CLASS,
    artifact_expires_at,
)
from kortravelgeo.settings import Settings


def test_artifact_expires_at_uses_retention_days() -> None:
    settings = Settings(backup_artifact_ttl_days=30)
    before = datetime.now(UTC)
    expires = artifact_expires_at(settings, retention_days=5)
    delta = expires - before
    assert timedelta(days=4, hours=23) < delta < timedelta(days=5, minutes=1)
    assert expires.tzinfo is not None


def test_artifact_expires_at_falls_back_to_ttl_default() -> None:
    settings = Settings(backup_artifact_ttl_days=30)
    before = datetime.now(UTC)
    expires = artifact_expires_at(settings, retention_days=None)
    delta = expires - before
    assert timedelta(days=29, hours=23) < delta < timedelta(days=30, minutes=1)


def test_default_retention_class_is_not_pinned() -> None:
    # The janitor (T-230) only protects 'pinned'; a normal backup must be eligible.
    assert DEFAULT_BACKUP_RETENTION_CLASS != "pinned"


def test_update_artifact_accepts_expires_at_and_retention_class() -> None:
    # The gap T-229 fixes: update_artifact previously had no way to write these.
    params = inspect.signature(AdminRepository.update_artifact).parameters
    assert "expires_at" in params
    assert "retention_class" in params
