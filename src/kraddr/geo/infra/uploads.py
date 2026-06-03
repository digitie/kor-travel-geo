"""Upload-set registry for admin source uploads."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from kraddr.geo.dto.admin import (
    RustfsImportPrefixRequest,
    RustfsSyncLocalRequest,
    RustfsSyncLocalResult,
    UploadFileStatus,
    UploadSetCreateRequest,
    UploadSetStatus,
    UploadStorageKind,
)
from kraddr.geo.exceptions import InvalidInputError, NotFoundError
from kraddr.geo.infra.rustfs import (
    EffectiveRustfsConfig,
    RustfsClient,
    RustfsObject,
    join_object_key,
    normalize_object_prefix,
    rustfs_uri,
    sha256_file,
)
from kraddr.geo.infra.source_set import guess_source_kind, infer_yyyymm

_MANIFEST = "upload-set.json"
_UPLOAD_SET_ID_RE = re.compile(r"upload_\d{8}T\d{6}Z_[0-9a-f]{12}")
_TERMINAL_STATES = {"uploaded", "cancelled", "failed"}


@dataclass(frozen=True)
class UploadSetCleanupEntry:
    upload_set_id: str
    state: str
    reason: str
    path: str
    updated_at: datetime | None = None
    deleted: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.updated_at is not None:
            payload["updated_at"] = self.updated_at.isoformat()
        return payload


@dataclass(frozen=True)
class UploadSetCleanupResult:
    scanned: int
    deleted: int
    skipped_active: int
    skipped_recent: int
    invalid_manifests: int
    dry_run: bool
    entries: tuple[UploadSetCleanupEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "deleted": self.deleted,
            "skipped_active": self.skipped_active,
            "skipped_recent": self.skipped_recent,
            "invalid_manifests": self.invalid_manifests,
            "dry_run": self.dry_run,
            "entries": [entry.to_dict() for entry in self.entries],
        }


async def create_upload_set(
    base_dir: Path,
    req: UploadSetCreateRequest,
    *,
    storage_kind: UploadStorageKind | None = None,
    rustfs_config: EffectiveRustfsConfig | None = None,
) -> UploadSetStatus:
    now = datetime.now(UTC)
    upload_set_id = f"upload_{now.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:12]}"
    root = _upload_root(base_dir, upload_set_id)
    root.mkdir(parents=True, exist_ok=False)
    selected_storage = storage_kind or req.storage_kind or "local"
    if selected_storage == "rustfs":
        if rustfs_config is None:
            msg = "RustFS config is required for rustfs upload set"
            raise InvalidInputError(msg)
        root_path = rustfs_config.upload_set_uri(upload_set_id)
        storage_prefix = rustfs_config.upload_set_prefix(upload_set_id)
        storage_uri = root_path
        materialized_path = str(root / "materialized")
        (root / "materialized").mkdir()
        (root / "spool").mkdir()
    else:
        root_path = str(root / "files")
        storage_prefix = None
        storage_uri = None
        materialized_path = None
        (root / "files").mkdir()
    status = UploadSetStatus(
        upload_set_id=upload_set_id,
        purpose=req.purpose,
        state="created",
        root_path=root_path,
        storage_kind=selected_storage,
        storage_uri=storage_uri,
        storage_prefix=storage_prefix,
        materialized_path=materialized_path,
        created_at=now,
        updated_at=now,
    )
    _write_status(root, status)
    return status


async def get_upload_set(base_dir: Path, upload_set_id: str) -> UploadSetStatus:
    return _read_status(_upload_root(base_dir, upload_set_id))


def cleanup_upload_sets(
    base_dir: Path,
    *,
    ttl_days: int,
    active_grace_minutes: int,
    active_upload_set_ids: set[str] | frozenset[str] = frozenset(),
    now: datetime | None = None,
    dry_run: bool = False,
) -> UploadSetCleanupResult:
    current = now or datetime.now(UTC)
    stale_cutoff = current - timedelta(days=ttl_days)
    active_cutoff = current - timedelta(minutes=active_grace_minutes)
    uploads_root = (base_dir / "uploads").resolve()
    entries: list[UploadSetCleanupEntry] = []
    if not uploads_root.exists():
        return UploadSetCleanupResult(
            scanned=0,
            deleted=0,
            skipped_active=0,
            skipped_recent=0,
            invalid_manifests=0,
            dry_run=dry_run,
            entries=(),
        )

    scanned = deleted = skipped_active = skipped_recent = invalid_manifests = 0
    for root in sorted(path for path in uploads_root.iterdir() if path.is_dir()):
        upload_set_id = root.name
        if not _UPLOAD_SET_ID_RE.fullmatch(upload_set_id):
            continue
        scanned += 1
        if upload_set_id in active_upload_set_ids:
            skipped_active += 1
            entries.append(
                UploadSetCleanupEntry(
                    upload_set_id=upload_set_id,
                    state="active",
                    reason="referenced_by_queued_or_running_job",
                    path=str(root),
                    deleted=False,
                )
            )
            continue

        status: UploadSetStatus | None = None
        try:
            status = _read_status(root)
            state: str = status.state
            updated_at = status.updated_at
        except Exception:
            invalid_manifests += 1
            state = "orphan"
            updated_at = datetime.fromtimestamp(root.stat().st_mtime, UTC)

        terminal = status is None or state in _TERMINAL_STATES
        stale_enough = updated_at <= stale_cutoff
        grace_elapsed = terminal or updated_at <= active_cutoff
        if not (stale_enough and grace_elapsed):
            skipped_recent += 1
            entries.append(
                UploadSetCleanupEntry(
                    upload_set_id=upload_set_id,
                    state=state,
                    reason="not_stale_enough",
                    path=str(root),
                    updated_at=updated_at,
                    deleted=False,
                )
            )
            continue

        if not dry_run:
            shutil.rmtree(root)
            deleted += 1
        entries.append(
            UploadSetCleanupEntry(
                upload_set_id=upload_set_id,
                state=state,
                reason="ttl_expired",
                path=str(root),
                updated_at=updated_at,
                deleted=not dry_run,
            )
        )

    return UploadSetCleanupResult(
        scanned=scanned,
        deleted=deleted,
        skipped_active=skipped_active,
        skipped_recent=skipped_recent,
        invalid_manifests=invalid_manifests,
        dry_run=dry_run,
        entries=tuple(entries),
    )


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
    rustfs_client: RustfsClient | None = None,
    rustfs_config: EffectiveRustfsConfig | None = None,
) -> UploadFileStatus:
    root = _upload_root(base_dir, upload_set_id)
    status = _read_status(root)
    if status.state == "cancelled":
        msg = f"upload set is cancelled: {upload_set_id}"
        raise InvalidInputError(msg)
    if status.storage_kind == "rustfs":
        if rustfs_client is None or rustfs_config is None:
            msg = "RustFS client and config are required for rustfs upload set"
            raise InvalidInputError(msg)
        return await _store_upload_file_rustfs(
            root,
            status,
            filename=filename,
            relative_path=relative_path,
            chunks=chunks,
            max_bytes=max_bytes,
            rustfs_client=rustfs_client,
            rustfs_config=rustfs_config,
        )

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


async def _store_upload_file_rustfs(
    root: Path,
    status: UploadSetStatus,
    *,
    filename: str,
    relative_path: str | None,
    chunks: AsyncIterator[bytes],
    max_bytes: int,
    rustfs_client: RustfsClient,
    rustfs_config: EffectiveRustfsConfig,
) -> UploadFileStatus:
    now = datetime.now(UTC)
    safe_relative = _safe_relative_path(relative_path or filename)
    object_key = rustfs_config.object_key(
        "uploads",
        status.upload_set_id,
        "files",
        safe_relative,
    )
    storage_uri = rustfs_uri(rustfs_config.bucket, object_key)
    part = (root / "spool" / f"{hashlib.sha256(safe_relative.encode('utf-8')).hexdigest()}.part")
    part.parent.mkdir(parents=True, exist_ok=True)
    file_id = hashlib.sha256(safe_relative.encode("utf-8")).hexdigest()[:16]
    initial = UploadFileStatus(
        upload_set_id=status.upload_set_id,
        file_id=file_id,
        filename=Path(filename).name,
        relative_path=safe_relative,
        path=storage_uri,
        state="uploading",
        storage_kind="rustfs",
        storage_uri=storage_uri,
        object_key=object_key,
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
        content_sha256 = digest.hexdigest()
        etag = await rustfs_client.put_file(object_key, part, sha256=content_sha256)
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
    finally:
        part.unlink(missing_ok=True)

    finished = initial.model_copy(
        update={
            "state": "uploaded",
            "size_bytes": size,
            "uploaded_bytes": size,
            "sha256": content_sha256,
            "object_etag": etag,
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
    root = _upload_root(base_dir, upload_set_id)
    status = _read_status(root)
    if status.storage_kind == "rustfs":
        if status.materialized_path:
            return Path(status.materialized_path)
        return root / "materialized"
    return root / "files"


async def materialize_upload_set(
    base_dir: Path,
    upload_set_id: str,
    *,
    rustfs_client: RustfsClient,
) -> Path:
    root = _upload_root(base_dir, upload_set_id)
    status = _read_status(root)
    if status.storage_kind != "rustfs":
        return root / "files"
    target_root = Path(status.materialized_path or root / "materialized")
    _ensure_dir(target_root)
    for file in status.files:
        if file.state != "uploaded" or not file.object_key:
            continue
        relative = _safe_relative_path(file.relative_path or file.filename)
        dest = (target_root / relative).resolve()
        _ensure_child(dest, _resolve_path(target_root))
        if dest.exists() and file.sha256 and await sha256_file(dest) == file.sha256:
            continue
        await rustfs_client.download_file(file.object_key, dest)
        if file.sha256 and await sha256_file(dest) != file.sha256:
            dest.unlink(missing_ok=True)
            msg = f"RustFS materialized file checksum mismatch: {relative}"
            raise InvalidInputError(msg)
    next_status = status.model_copy(
        update={
            "materialized_path": str(target_root),
            "updated_at": datetime.now(UTC),
        }
    )
    _write_status(root, next_status)
    return target_root


async def import_rustfs_prefix_as_upload_set(
    base_dir: Path,
    req: RustfsImportPrefixRequest,
    *,
    rustfs_client: RustfsClient,
    rustfs_config: EffectiveRustfsConfig,
) -> UploadSetStatus:
    prefix = normalize_object_prefix(req.prefix)
    objects = await rustfs_client.list_objects(prefix)
    if not objects:
        msg = f"RustFS prefix has no objects: {prefix}"
        raise InvalidInputError(msg)
    now = datetime.now(UTC)
    upload_set_id = f"upload_{now.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:12]}"
    root = _upload_root(base_dir, upload_set_id)
    root.mkdir(parents=True, exist_ok=False)
    (root / "materialized").mkdir()
    files = tuple(
        _rustfs_object_to_file_status(
            upload_set_id,
            obj,
            prefix=prefix,
            bucket=rustfs_config.bucket,
            now=now,
        )
        for obj in objects
    )
    status = UploadSetStatus(
        upload_set_id=upload_set_id,
        purpose=req.purpose,
        state="uploaded",
        root_path=rustfs_uri(rustfs_config.bucket, prefix),
        storage_kind="rustfs",
        storage_uri=rustfs_uri(rustfs_config.bucket, prefix),
        storage_prefix=prefix,
        materialized_path=str(root / "materialized"),
        files=files,
        total_bytes=sum(file.size_bytes for file in files),
        uploaded_bytes=sum(file.uploaded_bytes for file in files),
        created_at=now,
        updated_at=now,
    )
    _write_status(root, status)
    return status


async def sync_local_to_rustfs(
    base_dir: Path,
    req: RustfsSyncLocalRequest,
    *,
    rustfs_client: RustfsClient,
    rustfs_config: EffectiveRustfsConfig,
    allowed_roots: tuple[Path, ...],
) -> RustfsSyncLocalResult:
    source_root = _resolve_path(Path(req.root_path))
    _ensure_allowed_source_root(source_root, allowed_roots)
    _ensure_source_exists(source_root)
    paths = _iter_source_files(source_root)
    if not paths:
        msg = f"local path has no files: {source_root}"
        raise InvalidInputError(msg)
    now = datetime.now(UTC)
    upload_set_id = f"upload_{now.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:12]}"
    root = _upload_root(base_dir, upload_set_id)
    root.mkdir(parents=True, exist_ok=False)
    (root / "materialized").mkdir()
    prefix = normalize_object_prefix(
        req.prefix or rustfs_config.object_key("imports", upload_set_id)
    )
    files: list[UploadFileStatus] = []
    uploaded_bytes = 0
    for path in paths:
        relative = _local_relative_path(source_root, path)
        object_key = join_object_key(prefix, relative)
        digest = await sha256_file(path)
        etag = await rustfs_client.put_file(object_key, path, sha256=digest)
        size = path.stat().st_size
        uploaded_bytes += size
        file_id = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16]
        uri = rustfs_uri(rustfs_config.bucket, object_key)
        files.append(
            UploadFileStatus(
                upload_set_id=upload_set_id,
                file_id=file_id,
                filename=path.name,
                relative_path=relative,
                path=uri,
                state="uploaded",
                storage_kind="rustfs",
                storage_uri=uri,
                object_key=object_key,
                object_etag=etag,
                size_bytes=size,
                uploaded_bytes=size,
                sha256=digest,
                inferred_yyyymm=infer_yyyymm(Path(relative)),
                source_kind=guess_source_kind(Path(relative)),
                created_at=now,
                updated_at=now,
            )
        )
    status = UploadSetStatus(
        upload_set_id=upload_set_id,
        purpose=req.purpose,
        state="uploaded",
        root_path=rustfs_uri(rustfs_config.bucket, prefix),
        storage_kind="rustfs",
        storage_uri=rustfs_uri(rustfs_config.bucket, prefix),
        storage_prefix=prefix,
        materialized_path=str(root / "materialized"),
        files=tuple(files),
        total_bytes=uploaded_bytes,
        uploaded_bytes=uploaded_bytes,
        created_at=now,
        updated_at=now,
    )
    _write_status(root, status)
    return RustfsSyncLocalResult(
        upload_set=status,
        uploaded_files=len(files),
        uploaded_bytes=uploaded_bytes,
    )


def extract_upload_set_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, str):
        found.update(_UPLOAD_SET_ID_RE.findall(value))
    elif isinstance(value, dict):
        for key, child in value.items():
            if key == "upload_set_id" and isinstance(child, str):
                found.update(_UPLOAD_SET_ID_RE.findall(child))
            else:
                found.update(extract_upload_set_ids(child))
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            found.update(extract_upload_set_ids(child))
    return found


def _rustfs_object_to_file_status(
    upload_set_id: str,
    obj: RustfsObject,
    *,
    prefix: str,
    bucket: str,
    now: datetime,
) -> UploadFileStatus:
    relative = _relative_from_object_key(prefix, obj.key)
    file_id = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16]
    uri = rustfs_uri(bucket, obj.key)
    return UploadFileStatus(
        upload_set_id=upload_set_id,
        file_id=file_id,
        filename=Path(relative).name,
        relative_path=relative,
        path=uri,
        state="uploaded",
        storage_kind="rustfs",
        storage_uri=uri,
        object_key=obj.key,
        object_etag=obj.etag,
        size_bytes=obj.size,
        uploaded_bytes=obj.size,
        inferred_yyyymm=infer_yyyymm(Path(relative)),
        source_kind=guess_source_kind(Path(relative)),
        created_at=now,
        updated_at=now,
    )


def _relative_from_object_key(prefix: str, key: str) -> str:
    normalized_prefix = normalize_object_prefix(prefix).rstrip("/")
    relative = key
    if key == normalized_prefix:
        relative = Path(key).name
    elif key.startswith(f"{normalized_prefix}/"):
        relative = key[len(normalized_prefix) + 1 :]
    if relative.startswith("files/"):
        relative = relative[len("files/") :]
    return _safe_relative_path(relative)


def _ensure_allowed_source_root(path: Path, allowed_roots: tuple[Path, ...]) -> None:
    resolved_roots = tuple(root.resolve() for root in allowed_roots)
    if not resolved_roots:
        msg = "RustFS local import roots are not configured"
        raise InvalidInputError(msg)
    for root in resolved_roots:
        if _is_relative_to(path, root):
            return
    msg = f"local path is outside RustFS import roots: {path}"
    raise InvalidInputError(msg)


def _iter_source_files(root: Path) -> tuple[Path, ...]:
    if root.is_file():
        return (root,)
    return tuple(path for path in sorted(root.rglob("*")) if path.is_file())


def _local_relative_path(root: Path, path: Path) -> str:
    if root.is_file():
        return _safe_relative_path(path.name)
    return _safe_relative_path(str(path.relative_to(root)))


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


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _resolve_path(path: Path) -> Path:
    return path.resolve()


def _ensure_source_exists(path: Path) -> None:
    if not path.exists():
        msg = f"local path not found: {path}"
        raise InvalidInputError(msg)


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True
