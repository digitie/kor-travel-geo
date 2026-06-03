from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from kraddr.geo.dto.admin import (
    RustfsImportPrefixRequest,
    RustfsStorageConfigPatch,
    RustfsSyncLocalRequest,
    UploadSetCreateRequest,
)
from kraddr.geo.exceptions import InvalidInputError
from kraddr.geo.infra.rustfs import (
    EffectiveRustfsConfig,
    RustfsObject,
    describe_rustfs_config,
    load_rustfs_config,
    save_rustfs_config,
)
from kraddr.geo.infra.uploads import (
    create_upload_set,
    import_rustfs_prefix_as_upload_set,
    sync_local_to_rustfs,
)
from kraddr.geo.settings import Settings


def test_rustfs_config_patch_redacts_and_keeps_existing_secret(tmp_path: Path) -> None:
    settings = Settings(
        rustfs_config_path=tmp_path / "rustfs-config.json",
        rustfs_endpoint_url="http://127.0.0.1:9003",
        rustfs_access_key=SecretStr("env-access"),
        rustfs_secret_key=SecretStr("env-secret"),
    )

    first = save_rustfs_config(
        settings,
        RustfsStorageConfigPatch(
            enabled=True,
            bucket="kraddr-geo",
            prefix="../python-kraddr-geo//uploads",
            access_key="saved-access",
            secret_key="saved-secret",
        ),
    )

    assert first.enabled is True
    assert first.prefix == "python-kraddr-geo/uploads"
    assert first.access_key.configured is True
    assert first.access_key.hint == "cess"
    assert first.secret_key.hint == "cret"

    second = save_rustfs_config(
        settings,
        RustfsStorageConfigPatch(endpoint_url="http://rustfs.local:9003"),
    )
    loaded = load_rustfs_config(settings)

    assert second.endpoint_url == "http://rustfs.local:9003"
    assert loaded.access_key == "saved-access"
    assert loaded.secret_key == "saved-secret"


@pytest.mark.asyncio
async def test_create_rustfs_upload_set_uses_rustfs_uri(tmp_path: Path) -> None:
    config = _config()

    status = await create_upload_set(
        tmp_path,
        UploadSetCreateRequest(storage_kind="rustfs"),
        rustfs_config=config,
    )

    assert status.storage_kind == "rustfs"
    assert status.root_path.startswith("rustfs://kraddr-geo/python-kraddr-geo/uploads/")
    assert status.storage_prefix == f"python-kraddr-geo/uploads/{status.upload_set_id}"
    assert Path(status.materialized_path or "").name == "materialized"
    assert not (tmp_path / "uploads" / status.upload_set_id / "files").exists()


@pytest.mark.asyncio
async def test_sync_local_to_rustfs_rejects_path_outside_allowlist(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "navi.txt").write_text("x", encoding="utf-8")

    with pytest.raises(InvalidInputError, match="outside RustFS import roots"):
        await sync_local_to_rustfs(
            tmp_path,
            RustfsSyncLocalRequest(root_path=str(outside)),
            rustfs_client=_FakeRustfsClient(),
            rustfs_config=_config(),
            allowed_roots=(tmp_path / "allowed",),
        )


@pytest.mark.asyncio
async def test_sync_local_to_rustfs_uploads_allowed_tree(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    file_path = data_root / "202604_내비게이션용DB_전체분" / "navi.txt"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"hello")
    client = _FakeRustfsClient()

    result = await sync_local_to_rustfs(
        tmp_path,
        RustfsSyncLocalRequest(
            root_path=str(data_root),
            prefix="python-kraddr-geo/imports/test",
        ),
        rustfs_client=client,
        rustfs_config=_config(),
        allowed_roots=(data_root,),
    )

    assert result.uploaded_files == 1
    assert result.uploaded_bytes == 5
    assert result.upload_set.storage_kind == "rustfs"
    assert result.upload_set.files[0].source_kind == "navi"
    assert result.upload_set.files[0].object_key == (
        "python-kraddr-geo/imports/test/202604_내비게이션용DB_전체분/navi.txt"
    )
    assert client.uploaded_keys == (
        "python-kraddr-geo/imports/test/202604_내비게이션용DB_전체분/navi.txt",
    )


@pytest.mark.asyncio
async def test_sync_local_to_rustfs_rejects_empty_directory_without_manifest(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()

    with pytest.raises(InvalidInputError, match="has no files"):
        await sync_local_to_rustfs(
            tmp_path,
            RustfsSyncLocalRequest(root_path=str(data_root)),
            rustfs_client=_FakeRustfsClient(),
            rustfs_config=_config(),
            allowed_roots=(data_root,),
        )

    assert not (tmp_path / "uploads").exists()


@pytest.mark.asyncio
async def test_import_rustfs_prefix_restores_upload_set_files(tmp_path: Path) -> None:
    client = _FakeRustfsClient(
        objects=(
            RustfsObject(
                key="python-kraddr-geo/uploads/upload_1/files/202604_도로명주소 한글_전체분.zip",
                size=10,
                etag="abc",
            ),
        )
    )

    status = await import_rustfs_prefix_as_upload_set(
        tmp_path,
        RustfsImportPrefixRequest(prefix="python-kraddr-geo/uploads/upload_1"),
        rustfs_client=client,
        rustfs_config=_config(),
    )

    assert status.storage_kind == "rustfs"
    assert status.storage_uri == "rustfs://kraddr-geo/python-kraddr-geo/uploads/upload_1"
    assert status.files[0].relative_path == "202604_도로명주소 한글_전체분.zip"
    assert status.files[0].object_etag == "abc"
    assert status.files[0].source_kind == "juso"


def test_describe_rustfs_config_does_not_expose_secret_values() -> None:
    config = describe_rustfs_config(_config(access_key="abcd1234", secret_key="xyz9876"))

    assert config.access_key.configured is True
    assert config.access_key.hint == "1234"
    assert config.secret_key.hint == "9876"
    assert "abcd" not in config.model_dump_json()
    assert "xyz" not in config.model_dump_json()


class _FakeRustfsClient:
    def __init__(self, *, objects: tuple[RustfsObject, ...] = ()) -> None:
        self.objects = objects
        self.uploaded_keys: tuple[str, ...] = ()

    async def put_file(self, key: str, path: Path, *, sha256: str | None = None) -> str:
        self.uploaded_keys = (*self.uploaded_keys, key)
        return f"etag-{path.name}-{sha256 or ''}"

    async def list_objects(self, prefix: str) -> tuple[RustfsObject, ...]:
        return tuple(obj for obj in self.objects if obj.key.startswith(prefix))


def _config(
    *,
    access_key: str = "access",
    secret_key: str = "secret",
) -> EffectiveRustfsConfig:
    return EffectiveRustfsConfig(
        enabled=True,
        endpoint_url="http://127.0.0.1:9003",
        bucket="kraddr-geo",
        prefix="python-kraddr-geo",
        region="us-east-1",
        force_path_style=True,
        retention_days=0,
        access_key=access_key,
        secret_key=secret_key,
    )
