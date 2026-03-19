from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OperationalDecisionSupportSystemForWaterSecurity API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://aquaintel:aquaintel@localhost:5432/aquaintel"
    allowed_origins: list[str] = ["http://localhost:3000"]
    # Set AQUAINTEL_API_KEY in production to protect write endpoints.
    # Leave empty to disable key enforcement (dev default).
    api_key: str = ""

    model_config = SettingsConfigDict(
        env_prefix="AQUAINTEL_",
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
