from services.api.app.config import DEFAULT_ALLOWED_ORIGINS, Settings, get_settings


def test_settings_support_new_odssws_env_names(monkeypatch) -> None:
    monkeypatch.setenv("ODSSWS_DATABASE_URL", "postgresql+psycopg://example")
    monkeypatch.delenv("AQUAINTEL_DATABASE_URL", raising=False)

    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.database_url == "postgresql+psycopg://example"
    finally:
        get_settings.cache_clear()


def test_settings_fall_back_to_legacy_aquaintel_env_names(monkeypatch) -> None:
    monkeypatch.delenv("ODSSWS_DATABASE_URL", raising=False)
    monkeypatch.setenv("AQUAINTEL_DATABASE_URL", "postgresql+psycopg://legacy")

    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.database_url == "postgresql+psycopg://legacy"
    finally:
        get_settings.cache_clear()


def test_settings_default_allowed_origins_include_github_pages() -> None:
    settings = Settings(_env_file=None)

    assert settings.allowed_origins == DEFAULT_ALLOWED_ORIGINS
    assert "https://hafsaghannaj.github.io" in settings.allowed_origins
