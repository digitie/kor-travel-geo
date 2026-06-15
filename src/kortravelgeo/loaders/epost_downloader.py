"""epost zipcode dataset downloader helpers."""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

import anyio
import httpx

from kortravelgeo.exceptions import ConfigError, LoaderError
from kortravelgeo.settings import Settings


async def download_epost_zip(
    settings: Settings,
    output_dir: Path | str,
    *,
    download_kind: str = "1",
) -> Path:
    """Download the epost dataset ZIP for quarterly offline loading.

    The response body is read with a streamed byte cap (``api_max_upload_bytes``)
    so a malicious/compromised upstream or an unexpectedly huge payload cannot
    exhaust memory/disk — the server-fetch path (T-207) exposes this over HTTP.
    """

    if settings.epost_api_key is None:
        msg = "KTG_EPOST_API_KEY is required for epost download"
        raise ConfigError(msg)
    root = Path(output_dir)
    await anyio.Path(root).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    zip_path = root / f"epost_downloadKnd_{download_kind}_{timestamp}.zip"
    max_bytes = settings.api_max_upload_bytes
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        final_url, content = await _get_capped(
            client,
            settings.epost_download_url,
            params={
                "serviceKey": settings.epost_api_key.get_secret_value(),
                "downloadKnd": download_kind,
            },
            max_bytes=max_bytes,
        )
        if not content.startswith(b"PK"):
            zip_url = _extract_epost_zip_url(content)
            if zip_url is not None:
                _, content = await _get_capped(
                    client, str(final_url.join(zip_url)), max_bytes=max_bytes
                )
    if not content.startswith(b"PK"):
        msg = "epost download did not return a ZIP payload"
        raise LoaderError(msg)
    await anyio.Path(zip_path).write_bytes(content)
    return zip_path


async def _get_capped(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str] | None = None,
    max_bytes: int,
) -> tuple[httpx.URL, bytes]:
    """Streamed GET that aborts once the body exceeds ``max_bytes``."""

    buffer = bytearray()
    async with client.stream("GET", url, params=params) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            buffer += chunk
            if len(buffer) > max_bytes:
                msg = f"epost download exceeds max bytes ({max_bytes})"
                raise LoaderError(msg)
        return response.url, bytes(buffer)


def _extract_epost_zip_url(content: bytes) -> str | None:
    try:
        root = ElementTree.fromstring(content.decode("utf-8", errors="replace"))
    except ElementTree.ParseError:
        return None
    for element in root.iter():
        tag = element.tag.rsplit("}", maxsplit=1)[-1]
        if tag == "fileLocplc" and element.text and element.text.strip():
            return element.text.strip()
    return None


def extract_epost_zip(
    zip_path: Path | str,
    output_dir: Path | str | None = None,
    *,
    max_total_bytes: int | None = None,
) -> Path:
    """Extract an epost ZIP with zip-slip path checks and an optional size budget.

    Member paths that escape ``target`` (absolute or ``..`` traversal) are
    rejected, and when ``max_total_bytes`` is set the summed uncompressed size is
    checked before extraction (decompression-bomb guard).
    """

    source = Path(zip_path)
    target = Path(output_dir) if output_dir is not None else source.with_suffix("")
    target.mkdir(parents=True, exist_ok=True)
    resolved_target = target.resolve()
    with zipfile.ZipFile(source) as archive:
        total = 0
        for info in archive.infolist():
            dest = (target / info.filename).resolve()
            if dest != resolved_target and not dest.is_relative_to(resolved_target):
                msg = f"unsafe path in epost ZIP: {info.filename!r}"
                raise LoaderError(msg)
            total += info.file_size
            if max_total_bytes is not None and total > max_total_bytes:
                msg = f"epost ZIP uncompressed size exceeds limit ({max_total_bytes})"
                raise LoaderError(msg)
        archive.extractall(target)
    return target


def discover_epost_files(path: Path | str) -> tuple[Path | None, Path | None]:
    """Return likely ``(pobox_file, bulk_delivery_file)`` from an extracted dataset."""

    root = Path(path)
    files = [root] if root.is_file() else [file for file in root.rglob("*") if file.is_file()]
    pobox: Path | None = None
    bulk: Path | None = None
    for file in sorted(files):
        name = file.name.lower()
        if pobox is None and ("사서함" in file.name or "pobox" in name):
            pobox = file
        if bulk is None and (
            "다량" in file.name
            or "대량" in file.name
            or "bulk" in name
            or "delivery" in name
        ):
            bulk = file
    return pobox, bulk
