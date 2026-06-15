"""Runtime settings loaded from ``KTG_*`` environment variables."""

from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network, ip_network
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
        env_prefix="KTG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    pg_dsn: str = "postgresql+psycopg://addr:addr@localhost:5432/kor_travel_geo"
    pg_pool_size: int = Field(default=10, ge=1)
    pg_max_overflow: int = Field(default=5, ge=0)
    pg_statement_timeout_ms: int = Field(default=5_000, ge=1)
    pg_pool_recycle_s: int = Field(default=3_600, ge=1)
    pg_query_metrics_enabled: bool = True

    api_title: str = "kor-travel-geo"
    api_cors_origins: tuple[str, ...] = Field(default_factory=tuple)
    api_default_radius_m: int = Field(default=200, ge=1, le=2_000)
    api_max_search_size: int = Field(default=100, ge=1, le=100)
    api_max_upload_bytes: int = Field(default=2 * 1024 * 1024 * 1024, ge=1)
    api_explain_timeout_ms: int = Field(default=3_000, ge=1)
    api_max_concurrency: int | None = Field(default=None, ge=1)
    api_admission_timeout_ms: int = Field(default=30_000, ge=1)
    api_performance_logging_enabled: bool = False
    api_slow_request_ms: int = Field(default=500, ge=1)
    geoip_db_path: Path | None = Path("data/geoip/GeoLite2-Country.mmdb")
    geoip_gate_mode: Literal["strict", "permissive", "off"] = "strict"
    geoip_allow_cidrs: Annotated[tuple[IPv4Network | IPv6Network, ...], NoDecode] = ()
    geoip_deny_cidrs: Annotated[tuple[IPv4Network | IPv6Network, ...], NoDecode] = ()
    geoip_open_paths: Annotated[tuple[str, ...], NoDecode] = ("/v1/healthz", "/metrics")
    geoip_trusted_proxies: Annotated[tuple[IPv4Network | IPv6Network, ...], NoDecode] = ()
    geoip_audit_denials: bool = True

    # T-202: admin role gate trusts X-KTG-Actor / X-KTG-Roles headers only from
    # these reverse-proxy / admin-proxy remote addresses. Empty falls back to
    # geoip_trusted_proxies so a single trusted-proxy config can drive both gates.
    admin_trusted_proxy_cidrs: Annotated[
        tuple[IPv4Network | IPv6Network, ...], NoDecode
    ] = ()

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
    upload_set_ttl_days: int = Field(default=30, ge=1)
    upload_set_active_grace_minutes: int = Field(default=360, ge=1)
    rustfs_enabled: bool = False
    rustfs_endpoint_url: str = "http://127.0.0.1:12101"
    rustfs_bucket: str = "kor-travel-geo"
    rustfs_region: str = "us-east-1"
    rustfs_prefix: str = "kor-travel-geo"
    rustfs_force_path_style: bool = True
    rustfs_access_key: SecretStr | None = None
    rustfs_secret_key: SecretStr | None = None
    rustfs_config_path: Path = Path("data/rustfs/config.json")
    rustfs_materialize_dir: Path = Path("data/rustfs/materialized")
    rustfs_retention_days: int = Field(default=0, ge=0)
    rustfs_local_import_roots: Annotated[tuple[Path, ...], NoDecode] = (Path("data"),)
    ops_table_stats_capture_interval_minutes: int = Field(default=0, ge=0)
    ops_table_stats_capture_limit: int = Field(default=500, ge=1, le=2_000)
    ops_table_stats_capture_on_startup: bool = False
    # T-203c source upload-session janitor (doc 1차 기본값, lines ~519-525).
    source_upload_session_ttl_days: int = Field(default=7, ge=1)
    source_registration_deadline_days: int = Field(default=30, ge=1)
    source_janitor_interval_minutes: int = Field(default=0, ge=0)
    source_janitor_on_startup: bool = False
    source_janitor_session_limit: int = Field(default=500, ge=1, le=5_000)
    # T-204 RustFS reconciliation. Rolling-deep window (force a deep rehash of an
    # otherwise-unchanged object whose last deep verify is older than this) and a
    # soft storage-capacity limit used only for the preflight warning (the
    # retention POLICY itself is T-212).
    source_reconcile_rolling_deep_days: int = Field(default=30, ge=1)
    source_reconcile_object_limit: int = Field(default=50_000, ge=1, le=1_000_000)
    source_storage_capacity_limit_bytes: int | None = Field(default=None, ge=0)
    mvm_res_code_actions: dict[str, LoadCodeAction] = Field(
        default_factory=_default_mvm_res_code_actions
    )
    backup_allowed_dirs: Annotated[tuple[Path, ...], NoDecode] = (Path("data/backups"),)
    backup_temp_dir: Path = Path("/tmp/kor-travel-geo-backup")
    backup_default_jobs: int = Field(default=4, ge=1, le=64)
    backup_default_compression_level: int = Field(default=3, ge=1, le=19)
    backup_artifact_ttl_days: int = Field(default=30, ge=1)
    # T-228: disk-space fail-fast preflight before a backup dump starts.
    backup_space_safety_factor: float = Field(default=1.3, ge=1.0)
    backup_require_free_space_check: bool = True
    backup_callback_allowed_hosts: Annotated[tuple[str, ...], NoDecode] = (
        "localhost",
        "127.0.0.1",
        "::1",
    )
    backup_callback_secret: SecretStr | None = None
    backup_callback_max_attempts: int = Field(default=3, ge=1, le=10)
    backup_callback_backoff_ms: int = Field(default=500, ge=0, le=60_000)
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

    @field_validator("rustfs_local_import_roots", mode="before")
    @classmethod
    def normalize_rustfs_local_import_roots(cls, value: object) -> tuple[Path, ...]:
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

    @field_validator(
        "geoip_allow_cidrs",
        "geoip_deny_cidrs",
        "geoip_trusted_proxies",
        "admin_trusted_proxy_cidrs",
        mode="before",
    )
    @classmethod
    def normalize_geoip_cidrs(cls, value: object) -> tuple[IPv4Network | IPv6Network, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return tuple(
                ip_network(part.strip(), strict=False)
                for part in value.split(",")
                if part.strip()
            )
        if isinstance(value, (list, tuple, set)):
            return tuple(ip_network(str(part), strict=False) for part in value)
        return (ip_network(str(value), strict=False),)

    @field_validator("geoip_open_paths", mode="before")
    @classmethod
    def normalize_geoip_open_paths(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        if isinstance(value, (list, tuple, set)):
            return tuple(str(part) for part in value)
        return (str(value),)

    @field_validator("geoip_db_path", mode="before")
    @classmethod
    def normalize_geoip_db_path(cls, value: object) -> Path | None:
        if value is None:
            return None
        text = str(value).strip()
        return Path(text) if text else None


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
