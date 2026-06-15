from __future__ import annotations

import io
import zipfile
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders import epost_downloader
from kortravelgeo.settings import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable
    from pathlib import Path


def _zip_payload(
    members: Iterable[tuple[str, str]] = (("pobox.txt", "zip_no|bd_mgt_sn\n04524|BD001\n"),),
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in members:
            archive.writestr(name, content)
    return buffer.getvalue()


class _FakeStream:
    """Async context manager mimicking ``httpx.AsyncClient.stream`` responses."""

    def __init__(self, url: str, body: bytes, *, chunk: int = 64) -> None:
        self._response = httpx.Response(200, content=body, request=httpx.Request("GET", url))
        self._body = body
        self._chunk = chunk

    async def __aenter__(self) -> _FakeStream:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    @property
    def url(self) -> httpx.URL:
        return self._response.url

    def raise_for_status(self) -> None:
        self._response.raise_for_status()

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        for start in range(0, max(len(self._body), 1), self._chunk):
            yield self._body[start : start + self._chunk]


def _fake_async_client(responses: list[bytes], urls: list[str]) -> type:
    class _Client:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def stream(
            self, _method: str, url: str, *, params: dict[str, str] | None = None
        ) -> _FakeStream:
            urls.append(url)
            return _FakeStream(url, responses.pop(0))

    return _Client


@pytest.mark.asyncio
async def test_download_epost_zip_keeps_direct_zip_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls: list[str] = []
    monkeypatch.setattr(
        epost_downloader.httpx, "AsyncClient", _fake_async_client([_zip_payload()], urls)
    )
    settings = Settings(epost_api_key="secret")
    result = await epost_downloader.download_epost_zip(settings, tmp_path)
    assert result.read_bytes().startswith(b"PK")
    assert urls == [settings.epost_download_url]


@pytest.mark.asyncio
async def test_download_epost_zip_follows_file_location_xml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls: list[str] = []
    xml = (
        b"<response><fileLocplc>http://files.example/zipcode.zip</fileLocplc></response>"
    )
    monkeypatch.setattr(
        epost_downloader.httpx,
        "AsyncClient",
        _fake_async_client([xml, _zip_payload()], urls),
    )
    settings = Settings(epost_api_key="secret")
    result = await epost_downloader.download_epost_zip(settings, tmp_path)
    assert result.read_bytes().startswith(b"PK")
    assert urls == [settings.epost_download_url, "http://files.example/zipcode.zip"]


@pytest.mark.asyncio
async def test_download_epost_zip_rejects_oversized_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls: list[str] = []
    monkeypatch.setattr(
        epost_downloader.httpx,
        "AsyncClient",
        _fake_async_client([_zip_payload()], urls),
    )
    settings = Settings(epost_api_key="secret", api_max_upload_bytes=8)
    with pytest.raises(LoaderError, match="exceeds max bytes"):
        await epost_downloader.download_epost_zip(settings, tmp_path)


def test_extract_epost_zip_rejects_zip_slip(tmp_path: Path) -> None:
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("../escape.txt", "owned")
    with pytest.raises(LoaderError, match="unsafe path"):
        epost_downloader.extract_epost_zip(zip_path, tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()


def test_extract_epost_zip_enforces_size_budget(tmp_path: Path) -> None:
    zip_path = tmp_path / "big.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("pobox.txt", "x" * 4096)
    with pytest.raises(LoaderError, match="exceeds limit"):
        epost_downloader.extract_epost_zip(zip_path, tmp_path / "out", max_total_bytes=16)


def test_extract_epost_zip_extracts_safe_archive(tmp_path: Path) -> None:
    zip_path = tmp_path / "ok.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("nested/pobox.txt", "data")
    out = epost_downloader.extract_epost_zip(zip_path, tmp_path / "out", max_total_bytes=4096)
    assert (out / "nested" / "pobox.txt").read_text() == "data"
