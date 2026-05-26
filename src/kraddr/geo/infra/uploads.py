"""Filesystem-backed upload-set registry for admin source uploads."""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from kraddr.geo.dto.admin import (
    UploadFileStatus,
    UploadSetCreateRequest,
    UploadSetStatus,
)
from kraddr.geo.exceptions import InvalidInputError, NotFoundError
from kraddr.geo.infra.source_set import guess_source_kind, infer_yyyymm

_MANIFEST = "upload-set.json"


async def create_upload_set(base_dir: Path, req: UploadSetCreateRequest) -> UploadSetStatus:
    now = datetime.now(UTC)
    upload_set_id = f"upload_{now.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:12]}"
    root = _upload_root(base_dir, upload_set_id)
    root.mkdir(parents=True, exist_ok=False)
    (root / "files").mkdir()
    status = UploadSetStatus(
        upload_set_id=upload_set_id,
        purpose=req.purpose,
        state="created",
        root_path=str(root / "files"),
        created_at=now,
        updated_at=now,
    )
    _write_status(root, status)
    return status


async def get_upload_set(base_dir: Path, upload_set_id: str) -> UploadSetStatus:
    return _read_status(_upload_root(base_dir, upload_set_id))


async def cancel_upload_set(base_dir: Path, upload_set_id: str) -> UploadSetStatus:
    root = _upload_root(base_dir, upload_set_id)
    status = _read_status(root)
    now = datetime.now(UTC)
    files = tuple(
        file.model_copy(update={"state": "cancelled", "updated_at": now})
        if file.state in {"pending", "uploading"}
        else file
        for file in status.files
    )
    next_status = _with_files(
        status.model_copy(update={"state": "cancelled", "updated_at": now}),
        files,
    )
    _write_status(root, next_status)
    return next_status


async def store_upload_file(
    base_dir: Path,
    upload_set_id: str,
    *,
    filename: str,
    relative_path: str | None,
    chunks: AsyncIterator[bytes],
    max_bytes: int,
) -> UploadFileStatus:
    root = _upload_root(base_dir, upload_set_id)
    status = _read_status(root)
    if status.state == "cancelled":
        msg = f"upload set is cancelled: {upload_set_id}"
        raise InvalidInputError(msg)

    now = datetime.now(UTC)
    safe_relative = _safe_relative_path(relative_path or filename)
    dest = (root / "files" / safe_relative).resolve()
    _ensure_child(dest, (root / "files").resolve())
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    file_id = hashlib.sha256(safe_relative.encode("utf-8")).hexdigest()[:16]
    initial = UploadFileStatus(
        upload_set_id=upload_set_id,
        file_id=file_id,
        filename=Path(filename).name,
        relative_path=safe_relative,
        path=str(dest),
        state="uploading",
        created_at=now,
        updated_at=now,
    )
    _write_status(root, _upsert_file(status, initial))

    digest = hashlib.sha256()
    size = 0
    try:
        with part.open("wb") as fh:
            async for chunk in chunks:
                if not chunk:
                    continue
                size += len(chunk)
                if size > max_bytes:
                    msg = f"upload exceeds {max_bytes} bytes limit"
                    raise InvalidInputError(msg)
                digest.update(chunk)
                fh.write(chunk)
    except Exception:
        part.unlink(missing_ok=True)
        failed = initial.model_copy(
            update={
                "state": "failed",
                "size_bytes": size,
                "uploaded_bytes": size,
                "updated_at": datetime.now(UTC),
            }
        )
        _write_status(root, _upsert_file(_read_status(root), failed))
        raise

    part.replace(dest)
    finished = initial.model_copy(
        update={
            "state": "uploaded",
            "size_bytes": size,
            "uploaded_bytes": size,
            "sha256": digest.hexdigest(),
            "inferred_yyyymm": infer_yyyymm(Path(safe_relative)),
            "source_kind": guess_source_kind(Path(safe_relative)),
            "updated_at": datetime.now(UTC),
        }
    )
    next_status = _upsert_file(_read_status(root), finished)
    next_state = "uploaded" if next_status.files else "created"
    _write_status(root, next_status.model_copy(update={"state": next_state}))
    return finished


def upload_set_root(base_dir: Path, upload_set_id: str) -> Path:
    return _upload_root(base_dir, upload_set_id) / "files"


def _upload_root(base_dir: Path, upload_set_id: str) -> Path:
    if not upload_set_id.startswith("upload_"):
        msg = f"invalid upload_set_id: {upload_set_id}"
        raise InvalidInputError(msg)
    root = (base_dir / "uploads" / upload_set_id).resolve()
    _ensure_child(root, (base_dir / "uploads").resolve())
    return root


def _read_status(root: Path) -> UploadSetStatus:
    manifest = root / _MANIFEST
    if not manifest.exists():
        raise NotFoundError(f"upload set not found: {root.name}")
    return UploadSetStatus.model_validate_json(manifest.read_text(encoding="utf-8"))


def _write_status(root: Path, status: UploadSetStatus) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = status.model_dump(mode="json")
    (root / _MANIFEST).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _upsert_file(status: UploadSetStatus, file: UploadFileStatus) -> UploadSetStatus:
    files = [current for current in status.files if current.file_id != file.file_id]
    files.append(file)
    return _with_files(status, tuple(files))


def _with_files(
    status: UploadSetStatus,
    files: tuple[UploadFileStatus, ...],
) -> UploadSetStatus:
    total = sum(file.size_bytes for file in files)
    uploaded = sum(file.uploaded_bytes for file in files)
    state = status.state
    if state != "cancelled" and files:
        if any(file.state == "failed" for file in files):
            state = "failed"
        elif all(file.state == "uploaded" for file in files):
            state = "uploaded"
        else:
            state = "uploading"
    return status.model_copy(
        update={
            "files": files,
            "state": state,
            "total_bytes": total,
            "uploaded_bytes": uploaded,
            "updated_at": datetime.now(UTC),
        }
    )


def _safe_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    parts = [
        part
        for part in PurePosixPath(normalized).parts
        if part not in {"", ".", "..", "/"} and ":" not in part
    ]
    if not parts:
        return "upload.bin"
    return str(PurePosixPath(*parts))


def _ensure_child(path: Path, base: Path) -> None:
    try:
        path.relative_to(base)
    except ValueError as exc:
        msg = "upload path escapes upload directory"
        raise InvalidInputError(msg) from exc
