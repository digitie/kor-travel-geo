import pytest

from kraddr.geo.settings import Settings, get_settings, reset_settings, set_settings


def test_settings_normalize_postgresql_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_settings()
    monkeypatch.setenv("KRADDR_GEO_PG_DSN", "postgresql://u:p@localhost:5432/kraddr_geo")

    settings = get_settings()

    assert settings.pg_dsn == "postgresql+psycopg://u:p@localhost:5432/kraddr_geo"
    reset_settings()


def test_settings_default_mvm_res_code_actions() -> None:
    settings = Settings()

    assert settings.mvm_res_code_actions["31"] == "insert"
    assert settings.mvm_res_code_actions["34"] == "update"
    assert settings.mvm_res_code_actions["63"] == "delete"


def test_set_settings_overrides_singleton() -> None:
    settings = Settings(api_title="custom")

    set_settings(settings)

    assert get_settings() is settings
    reset_settings()


def test_settings_defaults_match_backend_spec() -> None:
    settings = Settings()

    assert settings.pg_statement_timeout_ms == 5_000
    assert settings.api_cors_origins == ()
    assert settings.api_default_radius_m == 200
    assert settings.api_max_upload_bytes == 2 * 1024 * 1024 * 1024
    assert settings.api_explain_timeout_ms == 3_000
    assert settings.api_max_concurrency is None
    assert settings.api_admission_timeout_ms == 30_000
    assert settings.upload_set_ttl_days == 30
    assert settings.upload_set_active_grace_minutes == 360
    assert settings.ops_table_stats_capture_interval_minutes == 0
    assert settings.ops_table_stats_capture_limit == 500
    assert settings.ops_table_stats_capture_on_startup is False
    assert settings.epost_download_url == (
        "http://openapi.epost.go.kr/postal/downloadAreaCodeService/"
        "downloadAreaCodeService/getAreaCodeInfo"
    )
    assert settings.backup_allowed_dirs == (settings.loader_data_dir / "backups",)
    assert settings.backup_default_jobs == 4
    assert settings.backup_default_compression_level == 3
    assert "localhost" in settings.backup_callback_allowed_hosts
    assert settings.backup_callback_secret is None
    assert settings.backup_callback_max_attempts == 3
    assert settings.backup_callback_backoff_ms == 500


def test_settings_normalize_backup_csv_values() -> None:
    settings = Settings(
        backup_allowed_dirs="/tmp/a,/tmp/b",
        backup_callback_allowed_hosts="localhost,internal.example",
    )

    assert tuple(path.as_posix() for path in settings.backup_allowed_dirs) == ("/tmp/a", "/tmp/b")
    assert settings.backup_callback_allowed_hosts == ("localhost", "internal.example")
