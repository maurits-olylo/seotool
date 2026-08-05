from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    service_role: str = "api"
    app_name: str = "SEO Monitor API"
    api_key: str = "change-me"
    database_url: str = "postgresql+psycopg://seo:seo@postgres:5432/seo"
    redis_url: str = "redis://redis:6379/0"
    log_level: str = "INFO"
    user_agent: str = "SEO-Monitor-Bot/0.1"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    bing_client_id: str = ""
    bing_client_secret: str = ""
    bing_redirect_uri: str = ""
    token_encryption_key: str = ""
    initial_superuser_email: str = ""
    initial_superuser_password: str = ""
    rendering_enabled: bool = False
    pagespeed_enabled: bool = False
    pagespeed_api_key: str = ""
    mfa_enforcement_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.pagespeed_enabled and not self.pagespeed_api_key:
            raise ValueError("PAGESPEED_API_KEY is required when PageSpeed is enabled")
        if self.app_env == "production":
            if "seo:seo@" in self.database_url:
                raise ValueError("Default database credentials are not allowed in production")
            if self.service_role == "api" and not self.mfa_enforcement_enabled:
                raise ValueError("MFA_ENFORCEMENT_ENABLED must be true for the production API")
            if self.service_role in {"api", "integration-worker"}:
                try:
                    key = bytes.fromhex(self.token_encryption_key)
                except ValueError as exc:
                    raise ValueError(
                        "TOKEN_ENCRYPTION_KEY must contain 64 hexadecimal characters"
                    ) from exc
                if len(key) != 32:
                    raise ValueError("TOKEN_ENCRYPTION_KEY must contain 64 hexadecimal characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
