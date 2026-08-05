from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.core.config import Settings


def test_accepts_production_without_technical_api_key() -> None:
    settings = Settings(
        app_env="production",
        api_key="",
        database_url="postgresql+psycopg://seo:strong@postgres:5432/seo",
        token_encryption_key="01" * 32,
        mfa_enforcement_enabled=True,
    )
    assert settings.app_env == "production"


def test_configured_production_key_does_not_enable_legacy_access() -> None:
    settings = Settings(
        app_env="production",
        api_key="a-long-production-secret",
        database_url="postgresql+psycopg://seo:strong@postgres:5432/seo",
        token_encryption_key="01" * 32,
        mfa_enforcement_enabled=True,
    )
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


def test_application_containers_are_hardened() -> None:
    project_root = Path(__file__).resolve().parents[1]
    expected_services = {
        "api",
        "worker",
        "crawl-worker-2",
        "crawl-worker-3",
        "integration-worker",
        "export-worker",
        "render-worker",
        "scheduler",
    }
    compose = yaml.safe_load((project_root / "compose.yaml").read_text())

    for service_name in expected_services:
        service = compose["services"][service_name]
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert service["security_opt"] == ["no-new-privileges:true"]
        assert service["pids_limit"] == 256
        assert service["mem_limit"]
        assert service["cpu_shares"]
        assert any(value.startswith("/tmp:") for value in service["tmpfs"])


def test_staging_application_containers_are_hardened() -> None:
    project_root = Path(__file__).resolve().parents[1]
    compose = yaml.safe_load((project_root / "compose.staging.yaml").read_text())

    for service_name in ("api", "render-worker"):
        service = compose["services"][service_name]
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert service["security_opt"] == ["no-new-privileges:true"]
        assert service["pids_limit"] == 256


def test_application_image_runs_as_non_root_user() -> None:
    project_root = Path(__file__).resolve().parents[1]
    dockerfile = (project_root / "Dockerfile").read_text().splitlines()

    assert "USER app" in dockerfile


def test_production_rejects_insecure_defaults() -> None:
    with pytest.raises(ValidationError, match="Default database credentials"):
        Settings(
            app_env="production",
            service_role="crawl-worker",
            database_url="postgresql+psycopg://seo:seo@postgres:5432/seo",
        )
    with pytest.raises(ValidationError, match="MFA_ENFORCEMENT_ENABLED"):
        Settings(
            app_env="production",
            database_url="postgresql+psycopg://seo:strong@postgres:5432/seo",
            token_encryption_key="01" * 32,
        )
    with pytest.raises(ValidationError, match="TOKEN_ENCRYPTION_KEY"):
        Settings(
            app_env="production",
            database_url="postgresql+psycopg://seo:strong@postgres:5432/seo",
            mfa_enforcement_enabled=True,
        )


def test_compose_limits_sensitive_environment_by_service() -> None:
    project_root = Path(__file__).resolve().parents[1]
    compose = yaml.safe_load((project_root / "compose.yaml").read_text())
    services = compose["services"]
    sensitive = {
        "API_KEY",
        "GOOGLE_CLIENT_SECRET",
        "BING_CLIENT_SECRET",
        "TOKEN_ENCRYPTION_KEY",
        "INITIAL_SUPERUSER_PASSWORD",
        "PAGESPEED_API_KEY",
    }

    assert "env_file" not in "\n".join(
        (project_root / filename).read_text()
        for filename in ("compose.yaml", "compose.staging.yaml")
    )
    assert sensitive.isdisjoint(services["worker"]["environment"])
    assert sensitive.isdisjoint(services["crawl-worker-2"]["environment"])
    assert sensitive.isdisjoint(services["export-worker"]["environment"])
    assert sensitive.isdisjoint(services["scheduler"]["environment"])
    assert "TOKEN_ENCRYPTION_KEY" in services["integration-worker"]["environment"]
    assert "INITIAL_SUPERUSER_PASSWORD" not in services["integration-worker"]["environment"]
