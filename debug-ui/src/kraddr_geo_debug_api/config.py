"""Backend runtime settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings for the SQLite/SpatiaLite backend."""

    spatialite_path: Path
    vworld_api_key: str | None = None
    vworld_domain: str | None = None


def load_settings() -> Settings:
    """Read settings from local env files and process environment."""

    _load_local_env()
    default_path = Path(__file__).resolve().parents[3] / "data" / "juso" / "kraddr_geo.sqlite"
    path = Path(os.environ.get("KRADDR_GEO_SPATIALITE_PATH") or default_path)
    return Settings(
        spatialite_path=path,
        vworld_api_key=os.environ.get("VWORLD_API_KEY") or os.environ.get("VWORLD_KEY"),
        vworld_domain=os.environ.get("VWORLD_DOMAIN"),
    )


def _load_local_env() -> None:
    root = Path(__file__).resolve().parents[2]
    for path in (root / ".env.local", root / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            text = line.strip()
            if not text or text.startswith("#") or "=" not in text:
                continue
            key, value = text.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
