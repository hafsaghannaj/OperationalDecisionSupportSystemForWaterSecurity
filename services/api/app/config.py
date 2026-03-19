from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OperationalDecisionSupportSystemForWaterSecurity API"
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("ODSSWS_ENVIRONMENT", "AQUAINTEL_ENVIRONMENT"),
    )
    database_url: str = Field(
        default="postgresql+psycopg://odssws:odssws@localhost:5432/odssws",
        validation_alias=AliasChoices("ODSSWS_DATABASE_URL", "AQUAINTEL_DATABASE_URL"),
    )
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000"],
        validation_alias=AliasChoices("ODSSWS_ALLOWED_ORIGINS", "AQUAINTEL_ALLOWED_ORIGINS"),
    )
    # Set ODSSWS_API_KEY in production to protect write endpoints.
    # AQUAINTEL_API_KEY is still accepted as a backward-compatible fallback.
    api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ODSSWS_API_KEY", "AQUAINTEL_API_KEY"),
    )
    auth_token_secret: str = Field(
        default="",
        validation_alias=AliasChoices("ODSSWS_AUTH_TOKEN_SECRET", "AQUAINTEL_AUTH_TOKEN_SECRET"),
    )
    auth_issuer: str = Field(
        default="odssws",
        validation_alias=AliasChoices("ODSSWS_AUTH_ISSUER", "AQUAINTEL_AUTH_ISSUER"),
    )
    auth_audience: str = Field(
        default="odssws-operators",
        validation_alias=AliasChoices("ODSSWS_AUTH_AUDIENCE", "AQUAINTEL_AUTH_AUDIENCE"),
    )
    allow_legacy_api_key: bool = Field(
        default=False,
        validation_alias=AliasChoices("ODSSWS_ALLOW_LEGACY_API_KEY", "AQUAINTEL_ALLOW_LEGACY_API_KEY"),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
