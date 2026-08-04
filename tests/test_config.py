import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_rejects_default_api_key_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", api_key="change-me")


def test_accepts_configured_production_key() -> None:
    settings = Settings(app_env="production", api_key="a-long-production-secret")
    assert settings.app_env == "production"


def test_pagespeed_requires_key_only_when_enabled() -> None:
    assert Settings(pagespeed_enabled=False, pagespeed_api_key="").pagespeed_enabled is False
    with pytest.raises(ValidationError, match="PAGESPEED_API_KEY"):
        Settings(pagespeed_enabled=True, pagespeed_api_key="")
    assert Settings(pagespeed_enabled=True, pagespeed_api_key="test-key").pagespeed_enabled is True
