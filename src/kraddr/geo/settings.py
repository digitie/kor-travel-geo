"""Runtime settings loaded from ``KRADDR_GEO_*`` environment variables."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LoadCodeAction = Literal["insert", "update", "delete"]


def _default_mvm_res_code_actions() -> dict[str, LoadCodeAction]:
    return {
        "31": "insert",
        "33": "insert",
        "34": "update",
        "35": "update",
        "36": "update",
        "63": "delete",
        "64": "delete",
    }


class Settings(BaseSettings):
    """Application settings shared by library, API, CLI, and loaders."""

    model_config = SettingsConfigDict(
        env_prefix="KRADDR_GEO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    pg_dsn: str = "postgresql+psycopg://addr:addr@localhost:5432/kraddr_geo"
    pg_pool_size: int = Field(default=10, ge=1)
    pg_max_overflow: int = Field(default=5, ge=0)
    pg_statement_timeout_ms: int = Field(default=5_000, ge=1)
    pg_pool_recycle_s: int = Field(default=3_600, ge=1)

    api_title: str = "kraddr-geo"
    api_cors_origins: tuple[str, ...] = Field(default_factory=tuple)
    api_default_radius_m: int = Field(default=200, ge=1, le=2_000)
    api_max_search_size: int = Field(default=100, ge=1, le=100)
    api_max_upload_bytes: int = Field(default=2 * 1024 * 1024 * 1024, ge=1)
    api_explain_timeout_ms: int = Field(default=3_000, ge=1)

    juso_api_key: SecretStr | None = None
    juso_search_url: str = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
    juso_coord_url: str = "https://business.juso.go.kr/addrlink/addrCoordApi.do"
    juso_coord_api_key: SecretStr | None = None
    vworld_api_key: SecretStr | None = None
    vworld_url: str = "https://api.vworld.kr/req/address"
    epost_api_key: SecretStr | None = None
    epost_download_url: str = (
        "http://openapi.epost.go.kr/postal/downloadAreaCodeService/"
        "downloadAreaCodeService/getAreaCodeInfo"
    )

    cache_enabled: bool = True
    cache_ttl_days: int = Field(default=30, ge=1)

    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    loader_data_dir: Path = Path("data")
    loader_batch_size: int = Field(default=5_000, ge=1)
    loader_temp_schema: str = "staging"
    mvm_res_code_actions: dict[str, LoadCodeAction] = Field(
        default_factory=_default_mvm_res_code_actions
    )
    backup_allowed_dirs: Annotated[tuple[Path, ...], NoDecode] = (Path("data/backups"),)
    backup_temp_dir: Path = Path("/tmp/kraddr-geo-backup")
    backup_default_jobs: int = Field(default=4, ge=1, le=64)
    backup_default_compression_level: int = Field(default=3, ge=1, le=19)
    backup_artifact_ttl_days: int = Field(default=30, ge=1)
    backup_callback_allowed_hosts: Annotated[tuple[str, ...], NoDecode] = (
        "localhost",
        "127.0.0.1",
        "::1",
    )
    backup_download_token_secret: SecretStr | None = None

    @field_validator("pg_dsn", mode="before")
    @classmethod
    def normalize_pg_dsn(cls, value: object) -> str:
        text = str(value)
        if text.startswith("postgresql://"):
            return text.replace("postgresql://", "postgresql+psycopg://", 1)
        return text

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> str:
        return str(value).upper()

    @field_validator("backup_allowed_dirs", mode="before")
    @classmethod
    def normalize_backup_allowed_dirs(cls, value: object) -> tuple[Path, ...]:
        if isinstance(value, str):
            return tuple(Path(part.strip()) for part in value.split(",") if part.strip())
        if value is None:
            return ()
        if isinstance(value, (list, tuple, set)):
            return tuple(Path(part) for part in value)
        return (Path(str(value)),)

    @field_validator("backup_callback_allowed_hosts", mode="before")
    @classmethod
    def normalize_backup_callback_allowed_hosts(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            return tuple(part.strip().lower() for part in value.split(",") if part.strip())
        if value is None:
            return ()
        if isinstance(value, (list, tuple, set)):
            return tuple(str(part).lower() for part in value)
        return (str(value).lower(),)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a lazy singleton settings object."""

    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def set_settings(settings: Settings) -> None:
    """Override the settings singleton, primarily for tests."""

    global _settings
    _settings = settings


def reset_settings() -> None:
    """Clear the settings singleton, primarily for tests."""

    global _settings
    _settings = None
