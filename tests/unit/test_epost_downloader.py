from __future__ import annotations

import io
import zipfile
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from kortravelgeo.loaders import epost_downloader
from kortravelgeo.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path


def _zip_payload() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("pobox.txt", "zip_no|bd_mgt_sn\n04524|BD001\n")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_download_epost_zip_follows_file_location_xml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[str] = []

    class _FakeAsyncClient:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(
            self,
            url: str,
            *,
            params: dict[str, str] | None = None,
        ) -> httpx.Response:
            requests.append(url)
            request = httpx.Request("GET", url, params=params)
            if len(requests) == 1:
                return httpx.Response(
                    200,
                    text=(
                        "<response><fileLocplc>"
                        "http://files.example/zipcode.zip"
                        "</fileLocplc></response>"
                    ),
                    request=request,
                )
            return httpx.Response(200, content=_zip_payload(), request=request)

    monkeypatch.setattr(epost_downloader.httpx, "AsyncClient", _FakeAsyncClient)

    settings = Settings(epost_api_key="secret")
    result = await epost_downloader.download_epost_zip(settings, tmp_path)

    assert result.read_bytes().startswith(b"PK")
    assert requests == [
        settings.epost_download_url,
        "http://files.example/zipcode.zip",
    ]


@pytest.mark.asyncio
async def test_download_epost_zip_keeps_direct_zip_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[str] = []

    class _FakeAsyncClient:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(
            self,
            url: str,
            *,
            params: dict[str, str] | None = None,
        ) -> httpx.Response:
            requests.append(url)
            return httpx.Response(
                200,
                content=_zip_payload(),
                request=httpx.Request("GET", url, params=params),
            )

    monkeypatch.setattr(epost_downloader.httpx, "AsyncClient", _FakeAsyncClient)

    settings = Settings(epost_api_key="secret")
    result = await epost_downloader.download_epost_zip(settings, tmp_path)

    assert result.read_bytes().startswith(b"PK")
    assert requests == [settings.epost_download_url]
