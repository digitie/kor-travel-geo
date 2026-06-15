"""T-230 backup retention janitor policy.

``select_expired_backups`` is the pure policy: newest ``keep_min_count`` and
``pinned`` backups are protected; the rest are eligible iff ``expires_at`` has
passed. Device/DB-independent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from kortravelgeo.dto.admin import OpsArtifact
from kortravelgeo.infra.backup_janitor import select_expired_backups

NOW = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)


def _backup(
    aid: str,
    *,
    created: datetime,
    expires: datetime | None = None,
    retention_class: str | None = None,
) -> OpsArtifact:
    return OpsArtifact(
        artifact_id=aid,
        artifact_type="db_backup",
        state="available",
        storage_kind="local_file",
        storage_uri=f"/backups/{aid}.tar.zst",
        retention_class=retention_class,
        expires_at=expires,
        created_at=created,
    )


def test_expired_non_pinned_outside_keep_min_are_eligible() -> None:
    arts = [
        _backup("b5", created=NOW - timedelta(days=1), expires=NOW - timedelta(hours=1)),
        _backup("b4", created=NOW - timedelta(days=2), expires=NOW - timedelta(hours=1)),
        _backup("b3", created=NOW - timedelta(days=3), expires=NOW - timedelta(hours=1)),
        _backup("b2", created=NOW - timedelta(days=4), expires=NOW + timedelta(days=1)),
        _backup("b1", created=NOW - timedelta(days=5), expires=NOW - timedelta(days=1)),
    ]
    sel = select_expired_backups(arts, now=NOW, keep_min_count=2)
    assert set(sel.protected_ids) == {"b5", "b4"}  # 2 newest protected
    assert set(sel.eligible_ids) == {"b3", "b1"}  # b2 unexpired


def test_pinned_is_never_eligible() -> None:
    arts = [
        _backup(
            "pinned",
            created=NOW - timedelta(days=10),
            expires=NOW - timedelta(days=5),
            retention_class="pinned",
        ),
        _backup("plain", created=NOW - timedelta(days=9), expires=NOW - timedelta(days=5)),
    ]
    sel = select_expired_backups(arts, now=NOW, keep_min_count=0)
    assert "pinned" not in sel.eligible_ids
    assert "plain" in sel.eligible_ids


def test_unexpired_or_no_expiry_not_eligible() -> None:
    arts = [
        _backup("future", created=NOW - timedelta(days=1), expires=NOW + timedelta(days=1)),
        _backup("no_expiry", created=NOW - timedelta(days=2), expires=None),
    ]
    sel = select_expired_backups(arts, now=NOW, keep_min_count=0)
    assert sel.eligible_ids == ()


def test_keep_min_zero_allows_all_expired() -> None:
    arts = [
        _backup(f"b{i}", created=NOW - timedelta(days=i + 1), expires=NOW - timedelta(hours=1))
        for i in range(3)
    ]
    sel = select_expired_backups(arts, now=NOW, keep_min_count=0)
    assert len(sel.eligible_ids) == 3


def test_keep_min_larger_than_count_protects_all() -> None:
    arts = [
        _backup(f"b{i}", created=NOW - timedelta(days=i + 1), expires=NOW - timedelta(hours=1))
        for i in range(2)
    ]
    sel = select_expired_backups(arts, now=NOW, keep_min_count=10)
    assert sel.eligible_ids == ()
    assert len(sel.protected_ids) == 2
