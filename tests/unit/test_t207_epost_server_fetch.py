from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003
from typing import Any, ClassVar

import pytest

from kortravelgeo.dto.source import (
    EpostServerFetchRequest,
    RegisterResponse,
    UploadSessionFileSlot,
    UploadSessionStatus,
)
from kortravelgeo.exceptions import ConflictError, LoaderError
from kortravelgeo.infra.source_upload_repo import SessionCreateResult
from kortravelgeo.loaders import epost_server_fetch as service
from kortravelgeo.settings import Settings


class _FakeRustfsConfig:
    bucket = "source-bucket"
    prefix = "kor-travel-geo"

    def object_key(self, *parts: object) -> str:
        return "/".join((self.prefix, *(str(part).strip("/") for part in parts)))


class _FakeRustfsClient:
    put_calls: ClassVar[list[tuple[str, Path, str | None]]] = []
    fail_put: ClassVar[bool] = False

    def __init__(self, _config: object) -> None:
        pass

    async def ensure_bucket(self) -> None:
        return None

    async def put_file(self, key: str, path: Path, *, sha256: str | None = None) -> str:
        if self.fail_put:
            raise LoaderError("rustfs put failed")
        self.put_calls.append((key, path, sha256))
        return "etag-1"


class _FakeUploadRepo:
    instances: ClassVar[list[_FakeUploadRepo]] = []
    force_conflict: ClassVar[bool] = False

    def __init__(self, _engine: object) -> None:
        now = datetime(2026, 6, 15, tzinfo=UTC)
        self.session = UploadSessionStatus(
            upload_session_id="source_upload_t207",
            source_file_group_id="group-t207",
            category="epost_pobox_full",
            group_kind="single_file",
            user_yyyymm="202606",
            display_name="epost pobox",
            state="created",
            expected_file_count=1,
            uploaded_file_count=0,
            max_bytes=2 * 1024 * 1024 * 1024,
            part_size_bytes=64 * 1024 * 1024,
            file_slots=(UploadSessionFileSlot(slot="archive"),),
            bucket="source-bucket",
            prefix="kor-travel-geo",
            created_at=now,
            updated_at=now,
        )
        self.states: list[tuple[str, str | None]] = []
        self.parts: list[dict[str, Any]] = []
        self.instances.append(self)

    async def create_session(self, req: Any, **_kwargs: object) -> SessionCreateResult:
        category = req.category
        user_yyyymm = req.user_yyyymm
        self.session = self.session.model_copy(
            update={"category": category, "user_yyyymm": user_yyyymm}
        )
        return SessionCreateResult(
            session=self.session, parts=(), conflict=self.force_conflict
        )

    async def update_state(
        self,
        _session_id: str,
        *,
        state: str,
        error_message: str | None = None,
    ) -> UploadSessionStatus:
        self.states.append((state, error_message))
        self.session = self.session.model_copy(
            update={"state": state, "error_message": error_message}
        )
        return self.session

    async def record_part(self, _session_id: str, **kwargs: Any) -> None:
        self.parts.append(kwargs)

    async def get_session(self, _session_id: str) -> UploadSessionStatus:
        return self.session.model_copy(
            update={"state": "registered", "registered_at": datetime(2026, 6, 15, tzinfo=UTC)}
        )


class _FakeRegistrar:
    def __init__(self, _engine: object) -> None:
        pass

    async def register(self, **_kwargs: object) -> RegisterResponse:
        return RegisterResponse(
            source_file_group_id="group-t207",
            category="epost_pobox_full",
            group_kind="single_file",
            state="available",
            validation_state="passed",
            user_yyyymm="202606",
        )


@pytest.fixture(autouse=True)
def _patch_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeUploadRepo.instances.clear()
    _FakeRustfsClient.put_calls.clear()
    _FakeRustfsClient.fail_put = False
    _FakeUploadRepo.force_conflict = False
    monkeypatch.setattr(service, "require_enabled_rustfs", lambda _settings: _FakeRustfsConfig())
    monkeypatch.setattr(service, "RustfsClient", _FakeRustfsClient)
    monkeypatch.setattr(service, "SourceUploadSessionRepository", _FakeUploadRepo)
    monkeypatch.setattr(service, "SourceGroupRegistrar", _FakeRegistrar)
    monkeypatch.setattr(service, "_current_juso_source_yyyymm", _same_month)


async def _same_month(_engine: object) -> str:
    return "202606"


@pytest.mark.asyncio
async def test_epost_server_fetch_registers_pobox_and_prepares_load_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    extracted = tmp_path / "extract"
    extracted.mkdir()
    selected = extracted / "사서함.txt"
    selected.write_text("우편번호|사서함명\n12345|중앙우체국\n", encoding="utf-8")
    calls: dict[str, str] = {}

    async def fake_download(
        _settings: Settings,
        _output_dir: Path,
        *,
        download_kind: str,
    ) -> Path:
        calls["download_kind"] = download_kind
        return tmp_path / "epost.zip"

    monkeypatch.setattr(service, "download_epost_zip", fake_download)
    monkeypatch.setattr(service, "extract_epost_zip", lambda _zip, _out, **_kw: extracted)

    result = await service.fetch_epost_source_file(
        engine=object(),  # type: ignore[arg-type]
        settings=Settings(loader_data_dir=tmp_path, epost_api_key="secret"),
        req=EpostServerFetchRequest(category="epost_pobox_full", user_yyyymm="202606"),
        actor="tester",
    )

    repo = _FakeUploadRepo.instances[-1]
    assert calls["download_kind"] == "4"
    assert [state for state, _ in repo.states] == [
        "uploading",
        "extracting",
        "validating_structure",
        "storing_to_rustfs",
        "awaiting_registration",
    ]
    assert repo.parts[0]["part_sha256"]
    assert result.load_job_kind == "pobox_load"
    assert result.load_payload["path"] == str(selected)
    assert result.validation.row_count == 1
    assert _FakeRustfsClient.put_calls[0][1] == selected


@pytest.mark.asyncio
async def test_epost_server_fetch_marks_zip_structure_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    extracted = tmp_path / "extract"
    extracted.mkdir()

    async def fake_download(
        _settings: Settings,
        _output_dir: Path,
        *,
        download_kind: str,
    ) -> Path:
        assert download_kind == "1"
        return tmp_path / "epost.zip"

    monkeypatch.setattr(service, "download_epost_zip", fake_download)
    monkeypatch.setattr(service, "extract_epost_zip", lambda _zip, _out, **_kw: extracted)

    with pytest.raises(LoaderError, match="다량배달처"):
        await service.fetch_epost_source_file(
            engine=object(),  # type: ignore[arg-type]
            settings=Settings(loader_data_dir=tmp_path, epost_api_key="secret"),
            req=EpostServerFetchRequest(category="epost_bulk_full", user_yyyymm="202606"),
            actor="tester",
        )

    repo = _FakeUploadRepo.instances[-1]
    assert repo.states[-1][0] == "failed_structure"


def _pobox_setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    extracted = tmp_path / "extract"
    extracted.mkdir()
    selected = extracted / "사서함.txt"
    selected.write_text("우편번호|사서함명\n12345|중앙우체국\n", encoding="utf-8")

    async def fake_download(_settings: Settings, _output_dir: Path, *, download_kind: str) -> Path:
        return tmp_path / "epost.zip"

    monkeypatch.setattr(service, "download_epost_zip", fake_download)
    monkeypatch.setattr(service, "extract_epost_zip", lambda _zip, _out, **_kw: extracted)
    return selected


def _run_pobox(tmp_path: Path) -> Any:
    return service.fetch_epost_source_file(
        engine=object(),  # type: ignore[arg-type]
        settings=Settings(loader_data_dir=tmp_path, epost_api_key="secret"),
        req=EpostServerFetchRequest(category="epost_pobox_full", user_yyyymm="202606"),
        actor="tester",
    )


@pytest.mark.asyncio
async def test_epost_server_fetch_marks_failed_upload_on_download_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def fake_download(_settings: Settings, _output_dir: Path, *, download_kind: str) -> Path:
        raise LoaderError("upstream 503")

    monkeypatch.setattr(service, "download_epost_zip", fake_download)
    with pytest.raises(LoaderError, match="upstream 503"):
        await _run_pobox(tmp_path)
    repo = _FakeUploadRepo.instances[-1]
    assert repo.states[-1][0] == "failed_upload"


@pytest.mark.asyncio
async def test_epost_server_fetch_marks_failed_rustfs_put(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _pobox_setup(monkeypatch, tmp_path)
    _FakeRustfsClient.fail_put = True
    with pytest.raises(LoaderError, match="rustfs put failed"):
        await _run_pobox(tmp_path)
    repo = _FakeUploadRepo.instances[-1]
    assert repo.states[-1][0] == "failed_rustfs_put"


@pytest.mark.asyncio
async def test_epost_server_fetch_marks_failed_register(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _pobox_setup(monkeypatch, tmp_path)

    class _FailingRegistrar:
        def __init__(self, _engine: object) -> None:
            pass

        async def register(self, **_kwargs: object) -> RegisterResponse:
            raise LoaderError("register boom")

    monkeypatch.setattr(service, "SourceGroupRegistrar", _FailingRegistrar)
    with pytest.raises(LoaderError, match="register boom"):
        await _run_pobox(tmp_path)
    repo = _FakeUploadRepo.instances[-1]
    assert repo.states[-1][0] == "failed_register"


@pytest.mark.asyncio
async def test_epost_server_fetch_raises_conflict_on_active_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _pobox_setup(monkeypatch, tmp_path)
    _FakeUploadRepo.force_conflict = True
    with pytest.raises(ConflictError):
        await _run_pobox(tmp_path)
    repo = _FakeUploadRepo.instances[-1]
    # Conflict is detected before any state transition.
    assert repo.states == []


@pytest.mark.asyncio
async def test_epost_server_fetch_warns_on_yyyymm_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _pobox_setup(monkeypatch, tmp_path)

    async def _diff_month(_engine: object) -> str:
        return "202603"

    monkeypatch.setattr(service, "_current_juso_source_yyyymm", _diff_month)
    result = await _run_pobox(tmp_path)
    assert any("기준월" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_epost_server_fetch_bulk_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    extracted = tmp_path / "extract"
    extracted.mkdir()
    selected = extracted / "다량배달처.txt"
    selected.write_text(
        "우편번호|다량배달처명|건물관리번호|상세주소\n04524|서울기관|BD001|본관\n",
        encoding="utf-8",
    )
    captured: dict[str, str] = {}

    async def fake_download(_settings: Settings, _output_dir: Path, *, download_kind: str) -> Path:
        captured["download_kind"] = download_kind
        return tmp_path / "epost.zip"

    monkeypatch.setattr(service, "download_epost_zip", fake_download)
    monkeypatch.setattr(service, "extract_epost_zip", lambda _zip, _out, **_kw: extracted)

    result = await service.fetch_epost_source_file(
        engine=object(),  # type: ignore[arg-type]
        settings=Settings(loader_data_dir=tmp_path, epost_api_key="secret"),
        req=EpostServerFetchRequest(category="epost_bulk_full", user_yyyymm="202606"),
        actor="tester",
    )
    assert captured["download_kind"] == "1"
    assert result.load_job_kind == "bulk_load"
    assert result.load_payload["path"] == str(selected)
