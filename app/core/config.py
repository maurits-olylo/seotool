from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "SEO Monitor API"
    api_key: str = "change-me"
    database_url: str = "postgresql+psycopg://seo:seo@postgres:5432/seo"
    redis_url: str = "redis://redis:6379/0"
    log_level: str = "INFO"
    user_agent: str = "SEO-Monitor-Bot/0.1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env == "production" and self.api_key in {"", "change-me"}:
            raise ValueError("API_KEY must be changed in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
