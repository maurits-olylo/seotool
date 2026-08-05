from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_accepts_production_without_technical_api_key() -> None:
    settings = Settings(app_env="production", api_key="")
    assert settings.app_env == "production"


def test_configured_production_key_does_not_enable_legacy_access() -> None:
    settings = Settings(app_env="production", api_key="a-long-production-secret")
    assert settings.app_env == "production"


def test_pagespeed_requires_key_only_when_enabled() -> None:
    assert Settings(pagespeed_enabled=False, pagespeed_api_key="").pagespeed_enabled is False
    with pytest.raises(ValidationError, match="PAGESPEED_API_KEY"):
        Settings(pagespeed_enabled=True, pagespeed_api_key="")
    assert Settings(pagespeed_enabled=True, pagespeed_api_key="test-key").pagespeed_enabled is True


def test_api_ports_are_bound_to_loopback() -> None:
    project_root = Path(__file__).resolve().parents[1]
    for compose_file in ("compose.yaml", "compose.prod.yaml", "compose.staging.yaml"):
        content = (project_root / compose_file).read_text()
        assert "127.0.0.1:" in content
        assert 'ports: ["8000:8000"]' not in content
        assert 'ports: ["${API_PORT:-8000}:8000"]' not in content
