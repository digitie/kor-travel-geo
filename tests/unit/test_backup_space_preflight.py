"""T-228 backup disk-space fail-fast preflight.

``estimate_backup_space_requirement`` is conservative: dump (temp) and archive
(destination) are each estimated at ``db_size x backup_space_safety_factor``; when
temp and destination share a filesystem their requirements are summed against the
single free figure. Tests mock ``shutil.disk_usage`` so they are device-independent.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from kortravelgeo.infra import backup
from kortravelgeo.infra.backup import estimate_backup_space_requirement
from kortravelgeo.settings import Settings


def _settings(factor: float = 1.3) -> Settings:
    return Settings(backup_space_safety_factor=factor)


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    temp = tmp_path / "temp"
    dest = tmp_path / "dest"
    temp.mkdir()
    dest.mkdir()
    return temp, dest


def _fixed_free(monkeypatch: pytest.MonkeyPatch, free: int) -> None:
    monkeypatch.setattr(
        backup.shutil, "disk_usage", lambda _p: SimpleNamespace(total=free * 10, used=0, free=free)
    )


def test_required_bytes_apply_safety_factor(
    monkeypatch: pytest.MonkeyPatch, dirs: tuple[Path, Path]
) -> None:
    temp, dest = dirs
    _fixed_free(monkeypatch, 1_000_000)
    est = estimate_backup_space_requirement(
        db_size_bytes=100, settings=_settings(1.3), temp_dir=temp, destination_dir=dest
    )
    assert est.required_temp_bytes == 130
    assert est.required_dest_bytes == 130
    assert est.ok is True


def test_same_filesystem_requires_dump_plus_archive(
    monkeypatch: pytest.MonkeyPatch, dirs: tuple[Path, Path]
) -> None:
    temp, dest = dirs  # both under tmp_path → same device
    # need temp(130) + dest(130) = 260 on the single filesystem.
    _fixed_free(monkeypatch, 200)
    est = estimate_backup_space_requirement(
        db_size_bytes=100, settings=_settings(1.3), temp_dir=temp, destination_dir=dest
    )
    assert est.same_filesystem is True
    assert est.ok is False  # 200 < 260

    _fixed_free(monkeypatch, 300)
    est_ok = estimate_backup_space_requirement(
        db_size_bytes=100, settings=_settings(1.3), temp_dir=temp, destination_dir=dest
    )
    assert est_ok.ok is True  # 300 >= 260


def test_different_filesystem_checks_each_independently(
    monkeypatch: pytest.MonkeyPatch, dirs: tuple[Path, Path]
) -> None:
    temp, dest = dirs
    monkeypatch.setattr(backup, "_same_filesystem", lambda _a, _b: False)
    # temp has plenty (200 >= 130) but dest is short (100 < 130) → overall fail.
    monkeypatch.setattr(
        backup.shutil,
        "disk_usage",
        lambda p: SimpleNamespace(
            total=0, used=0, free=100 if Path(p).name == "dest" else 200
        ),
    )
    est = estimate_backup_space_requirement(
        db_size_bytes=100, settings=_settings(1.3), temp_dir=temp, destination_dir=dest
    )
    assert est.same_filesystem is False
    assert est.ok is False


def test_zero_size_database_is_trivially_ok(
    monkeypatch: pytest.MonkeyPatch, dirs: tuple[Path, Path]
) -> None:
    temp, dest = dirs
    _fixed_free(monkeypatch, 0)
    est = estimate_backup_space_requirement(
        db_size_bytes=0, settings=_settings(), temp_dir=temp, destination_dir=dest
    )
    assert est.required_temp_bytes == 0
    assert est.ok is True


def test_existing_ancestor_walks_up_to_existing_dir(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c"  # does not exist
    assert backup._existing_ancestor(nested) == tmp_path.resolve()


def test_settings_defaults() -> None:
    settings = Settings()
    assert settings.backup_require_free_space_check is True
    assert settings.backup_space_safety_factor == pytest.approx(1.3)
