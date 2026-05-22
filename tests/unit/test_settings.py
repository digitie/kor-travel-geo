from kraddr.geo.settings import Settings, get_settings, reset_settings, set_settings


def test_settings_normalize_postgresql_dsn(monkeypatch) -> None:
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
    assert settings.epost_download_url == (
        "http://openapi.epost.go.kr/postal/downloadAreaCodeService/"
        "downloadAreaCodeService/getAreaCodeInfo"
    )
