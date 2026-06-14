from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kortravelgeo.dto.admin import UploadSetCreateRequest
from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra.source_set import infer_yyyymm
from kortravelgeo.infra.uploads import (
    cancel_upload_set,
    cleanup_upload_sets,
    create_upload_set,
    extract_upload_set_ids,
    get_upload_set,
    store_upload_file,
)


def test_infer_yyyymm_prefers_nearest_file_or_directory_name() -> None:
    path = Path(
        "/tmp/uploads/upload_20260527T000000Z_deadbeef/files/"
        "서울/202603_도로명주소 한글_전체분.zip"
    )

    assert infer_yyyymm(path) == "202603"
    assert infer_yyyymm(Path("RNENTDATA_2605_11.txt")) == "202605"


@pytest.mark.asyncio
async def test_upload_set_stores_files_safely_and_can_be_cancelled(tmp_path: Path) -> None:
    upload_set = await create_upload_set(tmp_path, UploadSetCreateRequest())
    file_status = await store_upload_file(
        tmp_path,
        upload_set.upload_set_id,
        filename="202603_도로명주소 한글_전체분.zip",
        relative_path="../서울/202603_도로명주소 한글_전체분.zip",
        chunks=_chunks(b"hello"),
        max_bytes=100,
    )

    assert file_status.state == "uploaded"
    assert file_status.size_bytes == 5
    assert file_status.uploaded_bytes == 5
    # T-201 removed source-kind auto-detection from the upload-set registry.
    assert file_status.source_kind is None
    assert file_status.inferred_yyyymm == "202603"
    assert ".." not in file_status.relative_path

    loaded = await get_upload_set(tmp_path, upload_set.upload_set_id)
    assert loaded.state == "uploaded"
    assert loaded.total_bytes == 5
    assert loaded.files[0].sha256 == file_status.sha256

    cancelled = await cancel_upload_set(tmp_path, upload_set.upload_set_id)
    assert cancelled.state == "cancelled"


@pytest.mark.asyncio
async def test_upload_set_marks_failed_file_when_size_limit_is_exceeded(
    tmp_path: Path,
) -> None:
    upload_set = await create_upload_set(tmp_path, UploadSetCreateRequest())

    with pytest.raises(InvalidInputError, match="upload exceeds"):
        await store_upload_file(
            tmp_path,
            upload_set.upload_set_id,
            filename="navi.txt",
            relative_path="202604_내비게이션용DB_전체분/navi.txt",
            chunks=_chunks(b"abcdef"),
            max_bytes=3,
        )

    loaded = await get_upload_set(tmp_path, upload_set.upload_set_id)
    assert loaded.state == "failed"
    assert loaded.files[0].state == "failed"
    assert loaded.files[0].uploaded_bytes == 6


@pytest.mark.asyncio
async def test_upload_set_cleanup_respects_ttl_and_active_job_refs(tmp_path: Path) -> None:
    now = datetime(2026, 5, 28, tzinfo=UTC)
    stale = now - timedelta(days=31)
    stale_upload = await create_upload_set(tmp_path, UploadSetCreateRequest())
    active_upload = await create_upload_set(tmp_path, UploadSetCreateRequest())
    recent_upload = await create_upload_set(tmp_path, UploadSetCreateRequest())

    _rewrite_upload_manifest(stale_upload, updated_at=stale)
    _rewrite_upload_manifest(active_upload, updated_at=stale)

    result = cleanup_upload_sets(
        tmp_path,
        ttl_days=30,
        active_grace_minutes=360,
        active_upload_set_ids={active_upload.upload_set_id},
        now=now,
    )

    assert result.scanned == 3
    assert result.deleted == 1
    assert result.skipped_active == 1
    assert result.skipped_recent == 1
    assert not Path(stale_upload.root_path).parent.exists()
    assert Path(active_upload.root_path).parent.exists()
    assert Path(recent_upload.root_path).parent.exists()


@pytest.mark.asyncio
async def test_upload_set_cleanup_dry_run_reports_without_deleting(tmp_path: Path) -> None:
    now = datetime(2026, 5, 28, tzinfo=UTC)
    stale_upload = await create_upload_set(tmp_path, UploadSetCreateRequest())
    _rewrite_upload_manifest(stale_upload, updated_at=now - timedelta(days=40))

    result = cleanup_upload_sets(
        tmp_path,
        ttl_days=30,
        active_grace_minutes=360,
        now=now,
        dry_run=True,
    )

    assert result.deleted == 0
    assert result.entries[0].reason == "ttl_expired"
    assert result.entries[0].deleted is False
    assert Path(stale_upload.root_path).parent.exists()


def test_extract_upload_set_ids_from_payload_paths() -> None:
    payload = {
        "upload_set_id": "upload_20260528T010203Z_abcdefabcdef",
        "children": [
            {
                "payload": {
                    "path": (
                        "/data/uploads/upload_20260528T040506Z_123456abcdef/"
                        "files/202605_도로명주소.zip"
                    )
                }
            }
        ],
    }

    assert extract_upload_set_ids(payload) == {
        "upload_20260528T010203Z_abcdefabcdef",
        "upload_20260528T040506Z_123456abcdef",
    }


async def _chunks(payload: bytes):
    yield payload


def _rewrite_upload_manifest(upload_set, *, updated_at: datetime) -> None:
    root = Path(upload_set.root_path).parent
    status = upload_set.model_copy(update={"updated_at": updated_at})
    (root / "upload-set.json").write_text(status.model_dump_json(), encoding="utf-8")


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
