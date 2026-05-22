from kraddr.geo.settings import Settings, get_settings, reset_settings


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
