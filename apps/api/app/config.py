"""Central app configuration, loaded from environment variables.

Model API keys are intentionally allowed to be empty — see Fase 0 in the
README. The gateway checks at call time whether a given provider is
configured and returns a clear error instead of failing silently.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_secret_key: str = "change-me-in-production"
    cors_origins: str = "http://localhost:3000"

    database_url: str = "postgresql://milo:milo@localhost:5432/milo"
    redis_url: str = "redis://localhost:6379/0"

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None
    deepseek_api_key: str | None = None

    ntfy_topic: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
