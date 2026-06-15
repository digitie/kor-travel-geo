"""T-232/T-234 restore version compatibility (pure).

``check_restore_version_compatibility`` flags PostgreSQL **major** and PostGIS
**major.minor** differences (PostgreSQL minor/patch is allowed). The dry-run (T-232)
treats the notes as warnings; the version guard (T-234) escalates them to a blocker.
"""

from __future__ import annotations

from kortravelgeo.infra.backup import (
    _postgis_major_minor,
    _postgres_major,
    check_restore_version_compatibility,
)


def _notes(pg_src: str | None, pg_tgt: str | None, gis_src: str | None, gis_tgt: str | None):
    return check_restore_version_compatibility(
        manifest_postgres_version=pg_src,
        manifest_postgis_version=gis_src,
        target_postgres_version=pg_tgt,
        target_postgis_version=gis_tgt,
    )


def test_identical_versions_compatible() -> None:
    assert _notes("16.3", "16.3", "3.5.2", "3.5.2") == []


def test_postgres_minor_patch_is_allowed() -> None:
    assert _notes("16.3", "16.4", "3.5.2", "3.5.2") == []


def test_postgres_major_mismatch_flagged() -> None:
    notes = _notes("16.3", "17.1", "3.5.2", "3.5.2")
    assert len(notes) == 1
    assert "PostgreSQL major mismatch" in notes[0]


def test_postgis_major_minor_mismatch_flagged() -> None:
    notes = _notes("16.3", "16.3", "3.5.2", "3.4.1")
    assert len(notes) == 1
    assert "PostGIS major.minor mismatch" in notes[0]


def test_postgis_patch_difference_allowed() -> None:
    assert _notes("16.3", "16.3", "3.5.2", "3.5.0") == []


def test_missing_versions_produce_no_note() -> None:
    assert _notes(None, "16.3", None, "3.5.2") == []
    assert _notes("16.3", None, "3.5.2", None) == []


def test_both_mismatches_reported() -> None:
    notes = _notes("16.3", "17.0", "3.5.2", "3.4.0")
    assert len(notes) == 2


def test_version_parsers() -> None:
    assert _postgres_major("16.3 (Debian)") == 16
    assert _postgres_major("17rc1") == 17
    assert _postgres_major(None) is None
    assert _postgis_major_minor("3.5.2") == "3.5"
    assert _postgis_major_minor("3.4") == "3.4"
    assert _postgis_major_minor(None) is None
