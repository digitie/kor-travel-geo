"""epost zipcode dataset downloader helpers."""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path

import anyio
import httpx

from kraddr.geo.exceptions import ConfigError, LoaderError
from kraddr.geo.settings import Settings


async def download_epost_zip(
    settings: Settings,
    output_dir: Path | str,
    *,
    download_kind: str = "1",
) -> Path:
    """Download the epost dataset ZIP for quarterly offline loading."""

    if settings.epost_api_key is None:
        msg = "KRADDR_GEO_EPOST_API_KEY is required for epost download"
        raise ConfigError(msg)
    root = Path(output_dir)
    await anyio.Path(root).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    zip_path = root / f"epost_downloadKnd_{download_kind}_{timestamp}.zip"
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            settings.epost_download_url,
            params={
                "serviceKey": settings.epost_api_key.get_secret_value(),
                "downloadKnd": download_kind,
            },
        )
        response.raise_for_status()
    if not response.content.startswith(b"PK"):
        msg = "epost download did not return a ZIP payload"
        raise LoaderError(msg)
    await anyio.Path(zip_path).write_bytes(response.content)
    return zip_path


def extract_epost_zip(zip_path: Path | str, output_dir: Path | str | None = None) -> Path:
    source = Path(zip_path)
    target = Path(output_dir) if output_dir is not None else source.with_suffix("")
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive:
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
