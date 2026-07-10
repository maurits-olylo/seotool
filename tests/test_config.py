import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_rejects_default_api_key_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", api_key="change-me")


def test_accepts_configured_production_key() -> None:
    settings = Settings(app_env="production", api_key="a-long-production-secret")
    assert settings.app_env == "production"
