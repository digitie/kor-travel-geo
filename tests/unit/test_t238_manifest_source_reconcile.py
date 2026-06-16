"""T-238 backup manifest ↔ DB ↔ RustFS source reconcile tests.

The live DB/RustFS path is opt-in. These unit tests keep the core acceptance
surface DB-free by injecting DB facts and a fake RustFS HEAD client.
"""

from __future__ import annotations

import pytest

from kortravelgeo.core.source_restore import (
    ManifestSourceDbFileFact,
    ManifestSourceFile,
    ManifestSourceHeadFact,
    decide_manifest_source_file_reconcile,
)
from kortravelgeo.infra import source_restore_service as service

_SHA_A = "a" * 64


def _file(
    *,
    source_file_id: str = "file-1",
    object_key: str | None = "sources/file-1.zip",
    object_etag: str | None = "etag-1",
    size_bytes: int = 10,
) -> ManifestSourceFile:
    return ManifestSourceFile(
        source_file_id=source_file_id,
        filename="file-1.zip",
        sha256=_SHA_A,
        size_bytes=size_bytes,
        storage_uri=f"rustfs://bucket/{object_key or 'missing'}",
        object_key=object_key,
        object_etag=object_etag,
    )


def _db(
    *,
    source_file_id: str = "file-1",
    object_key: str | None = "sources/file-1.zip",
    object_etag: str | None = "etag-1",
    size_bytes: int = 10,
) -> ManifestSourceDbFileFact:
    return ManifestSourceDbFileFact(
        source_file_id=source_file_id,
        object_key=object_key,
        sha256=_SHA_A,
        size_bytes=size_bytes,
        object_etag=object_etag,
    )


def test_manifest_source_reconcile_classifies_present() -> None:
    decision = decide_manifest_source_file_reconcile(
        _file(),
        db=_db(),
        head=ManifestSourceHeadFact(present=True, size=10, etag="etag-1"),
    )

    assert decision.status == "present"
    assert decision.db_status == "matched"


def test_manifest_source_reconcile_classifies_missing_object() -> None:
    decision = decide_manifest_source_file_reconcile(
        _file(),
        db=_db(),
        head=ManifestSourceHeadFact(present=False),
    )

    assert decision.status == "missing"
    assert "RustFS HEAD" in decision.reasons[-1]


def test_manifest_source_reconcile_classifies_etag_mismatch() -> None:
    decision = decide_manifest_source_file_reconcile(
        _file(object_etag=None),
        db=_db(object_etag="etag-db"),
        head=ManifestSourceHeadFact(present=True, size=10, etag="etag-rustfs"),
    )

    assert decision.status == "etag_mismatch"
    assert decision.expected_etag == "etag-db"
    assert decision.observed_etag == "etag-rustfs"


class _FakeHead:
    def __init__(self, size: int, etag: str) -> None:
        self.size = size
        self.etag = etag


class _FakeRustfs:
    def __init__(self, heads: dict[str, _FakeHead]) -> None:
        self._heads = heads

    async def head_object(self, key: str) -> _FakeHead:
        if key not in self._heads:
            raise RuntimeError("not found")
        return self._heads[key]


def _manifest() -> dict[str, object]:
    return {
        "artifact_schema_version": 1,
        "source_match_set": {
            "source_match_set_id": "ms-1",
            "name": "backup",
            "profile": "serving_recommended",
            "source_set_hash": _SHA_A,
            "items": [
                {
                    "category": "roadname_hangul_full",
                    "source_file_group_id": "grp-1",
                    "group_kind": "single_file",
                    "role": "build_required",
                    "files": [
                        {
                            "source_file_id": "file-1",
                            "filename": "file-1.zip",
                            "sha256": _SHA_A,
                            "size_bytes": 10,
                            "storage_uri": "rustfs://bucket/sources/file-1.zip",
                            "object_key": "sources/file-1.zip",
                            "object_etag": "etag-1",
                        },
                        {
                            "source_file_id": "file-2",
                            "filename": "file-2.zip",
                            "sha256": _SHA_A,
                            "size_bytes": 20,
                            "storage_uri": "rustfs://bucket/sources/file-2.zip",
                            "object_key": "sources/file-2.zip",
                            "object_etag": "etag-2",
                        },
                    ],
                }
            ],
        },
    }


async def _fake_db_facts(
    _engine: object,
    files: tuple[ManifestSourceFile, ...],
) -> dict[str, ManifestSourceDbFileFact]:
    return {
        file.source_file_id: _db(
            source_file_id=file.source_file_id,
            object_key=file.object_key,
            object_etag=file.object_etag,
            size_bytes=file.size_bytes,
        )
        for file in files
    }


@pytest.mark.asyncio
async def test_manifest_source_reconcile_report_counts_one_missing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(service, "_manifest_source_db_facts", _fake_db_facts)
    rustfs = _FakeRustfs({"sources/file-1.zip": _FakeHead(size=10, etag="etag-1")})

    report = await service.reconcile_manifest_source_inventory(
        object(),  # type: ignore[arg-type]
        _manifest(),
        rustfs=rustfs,  # type: ignore[arg-type]
    )

    assert report.skipped is False
    assert report.ok is False
    assert report.total == 2
    assert report.counts == {"present": 1, "missing": 1}
    assert [row.decision.status for row in report.rows] == ["present", "missing"]


@pytest.mark.asyncio
async def test_manifest_source_reconcile_graceful_without_rustfs() -> None:
    report = await service.reconcile_manifest_source_inventory(
        object(),  # type: ignore[arg-type]
        _manifest(),
        rustfs=None,
    )

    assert report.skipped is True
    assert report.reason == "rustfs_unavailable"
    assert report.total == 2


@pytest.mark.asyncio
async def test_manifest_source_reconcile_graceful_legacy_manifest() -> None:
    report = await service.reconcile_manifest_source_inventory(
        object(),  # type: ignore[arg-type]
        {"artifact_schema_version": 1},
        rustfs=None,
    )

    assert report.skipped is True
    assert report.reason == "legacy_manifest_no_source_match_set"
