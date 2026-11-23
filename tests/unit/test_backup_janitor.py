"""T-230 backup retention janitor policy.

``select_expired_backups`` is the pure policy: newest ``keep_min_count`` and
``pinned`` backups are protected; the rest are eligible iff ``expires_at`` has
passed. Device/DB-independent.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from kortravelgeo.dto.admin import BackupRetentionResult, OpsArtifact
from kortravelgeo.infra import backup_janitor
from kortravelgeo.infra.backup_janitor import (
    find_missing_archives,
    is_orphaned_creating_backup,
    select_expired_backups,
)
from kortravelgeo.settings import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

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


# --- catalog reconciliation (2026-11-24): missing archives + orphaned ``creating`` rows ---

ROOT = Path("/backups")


def _art(
    aid: str,
    *,
    state: str = "available",
    uri: str | None = None,
    kind: str = "local_file",
    created: datetime | None = None,
    expires: datetime | None = None,
    job_id: str | None = None,
) -> OpsArtifact:
    return OpsArtifact(
        artifact_id=aid,
        artifact_type="db_backup",
        state=state,  # type: ignore[arg-type]
        storage_kind=kind,  # type: ignore[arg-type]
        storage_uri=uri if uri is not None else f"/backups/{aid}.tar.zst",
        expires_at=expires,
        job_id=job_id,
        created_at=created or NOW,
    )


def _missing(arts: list[OpsArtifact], *, files: set[str], root_exists: bool = True) -> set[str]:
    return set(
        find_missing_archives(
            arts,
            roots=[ROOT],
            is_dir=lambda p: root_exists and p == ROOT,
            is_file=lambda p: str(p) in files,
        )
    )


def test_missing_archive_under_present_root_is_reported() -> None:
    arts = [_art("gone"), _art("here")]
    assert _missing(arts, files={"/backups/here.tar.zst"}) == {"gone"}


def test_nested_path_under_root_counts_as_owned() -> None:
    # the 2026-10-29 odroid backup landed at <root>/data/backups/<name> (UI destination_dir)
    arts = [_art("nested", uri="/backups/data/backups/x.tar.zst")]
    assert _missing(arts, files=set()) == {"nested"}


def test_absent_root_never_reads_as_every_archive_deleted() -> None:
    # a container started without the backup mount must not wipe the catalog
    arts = [_art("a"), _art("b")]
    assert _missing(arts, files=set(), root_exists=False) == set()


def test_rows_outside_allowed_roots_or_non_local_are_left_alone() -> None:
    arts = [
        _art("elsewhere", uri="/mnt/other/x.tar.zst"),
        _art("s3", kind="s3", uri="/backups/x.tar.zst"),
        _art("no_uri", uri=""),
        _art("creating", state="creating"),
    ]
    assert _missing(arts, files=set()) == set()


@pytest.mark.parametrize(
    ("state", "job_state", "expected"),
    [
        ("creating", "failed", True),
        ("creating", "cancelled", True),
        ("creating", "running", False),
        ("creating", "queued", False),
        ("creating", "done", False),
        ("creating", None, False),
        ("available", "failed", False),
    ],
)
def test_orphaned_creating_policy(state: str, job_state: str | None, expected: bool) -> None:
    assert is_orphaned_creating_backup(_art("x", state=state), job_state) is expected


class _FakeRepo:
    def __init__(self, artifacts: list[OpsArtifact], jobs: dict[str, str]) -> None:
        self.artifacts = {a.artifact_id: a for a in artifacts}
        self.jobs = jobs
        self.updates: list[tuple[str, str]] = []
        self.audits: list[dict[str, Any]] = []

    async def list_artifacts(
        self, *, limit: int, artifact_type: str, state: str
    ) -> list[OpsArtifact]:
        return [a for a in self.artifacts.values() if a.state == state]

    async def get_load_job(self, job_id: str) -> SimpleNamespace | None:
        state = self.jobs.get(job_id)
        return SimpleNamespace(job_id=job_id, state=state) if state else None

    async def update_artifact(self, artifact_id: str, *, state: str) -> None:
        self.updates.append((artifact_id, state))
        current = self.artifacts[artifact_id]
        self.artifacts[artifact_id] = current.model_copy(update={"state": state})

    async def record_audit_event(self, **kwargs: Any) -> None:
        self.audits.append(kwargs)


@asynccontextmanager
async def _no_lock(engine: object, key: object) -> AsyncIterator[None]:
    yield


def _run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: _FakeRepo, *, dry_run: bool = False
) -> BackupRetentionResult:
    monkeypatch.setattr(backup_janitor, "AdminRepository", lambda engine: repo)
    monkeypatch.setattr(backup_janitor, "cross_process_lock", _no_lock)
    settings = Settings(backup_allowed_dirs=(tmp_path,), backup_retention_keep_min=1)
    return asyncio.run(
        backup_janitor.run_backup_retention_janitor(
            object(),  # type: ignore[arg-type]
            settings,
            dry_run=dry_run,
            now=NOW,
        )
    )


def test_pass_marks_missing_deleted_and_keep_min_protects_a_real_archive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real = tmp_path / "old.tar.zst"
    real.write_bytes(b"x")
    repo = _FakeRepo(
        [
            # newest row is a phantom: before the fix it took the only keep_min slot
            _art(
                "phantom",
                uri=str(tmp_path / "gone.tar.zst"),
                created=NOW - timedelta(days=1),
                expires=NOW - timedelta(hours=1),
            ),
            _art(
                "real",
                uri=str(real),
                created=NOW - timedelta(days=9),
                expires=NOW - timedelta(days=2),
            ),
        ],
        jobs={},
    )
    result = _run(monkeypatch, tmp_path, repo)
    assert result.missing_artifact_ids == ("phantom",)
    assert result.missing_count == 1
    assert ("phantom", "deleted") in repo.updates
    assert [a["action"] for a in repo.audits] == ["db_backup.archive_missing"]
    # the real archive is now the newest present backup -> protected, not expired
    assert result.expired_count == 0
    assert real.exists()


def test_pass_settles_orphaned_creating_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _FakeRepo(
        [
            _art("zombie", state="creating", job_id="job_failed"),
            _art("live", state="creating", job_id="job_running"),
            _art("nojob", state="creating", job_id=None),
        ],
        jobs={"job_failed": "failed", "job_running": "running"},
    )
    result = _run(monkeypatch, tmp_path, repo)
    assert result.orphaned_artifact_ids == ("zombie",)
    assert repo.updates == [("zombie", "failed")]
    assert repo.audits[0]["action"] == "db_backup.orphan_settled"
    assert repo.audits[0]["payload"]["job_state"] == "failed"


def test_dry_run_reports_without_touching_the_catalog(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _FakeRepo(
        [
            _art("phantom", uri=str(tmp_path / "gone.tar.zst")),
            _art("zombie", state="creating", job_id="j"),
        ],
        jobs={"j": "cancelled"},
    )
    result = _run(monkeypatch, tmp_path, repo, dry_run=True)
    assert result.missing_artifact_ids == ("phantom",)
    assert result.orphaned_artifact_ids == ("zombie",)
    assert repo.updates == []
    assert repo.audits == []
