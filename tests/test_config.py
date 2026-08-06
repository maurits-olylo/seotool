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
        "migrate",
        "database-roles",
    }
    compose = yaml.safe_load((project_root / "compose.yaml").read_text())

    for service_name in expected_services:
        service = compose["services"][service_name]
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert service["security_opt"] == ["no-new-privileges:true"]
        assert service["pids_limit"] in {64, 256}
        assert service["mem_limit"]
        assert service["cpu_shares"]
        assert any(value.startswith("/tmp:") for value in service["tmpfs"])


def test_staging_application_containers_are_hardened() -> None:
    project_root = Path(__file__).resolve().parents[1]
    compose = yaml.safe_load((project_root / "compose.staging.yaml").read_text())

    for service_name in ("api", "render-worker", "migrate", "database-roles"):
        service = compose["services"][service_name]
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert service["security_opt"] == ["no-new-privileges:true"]
        assert service["pids_limit"] in {64, 256}


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


def test_compose_uses_service_specific_database_urls() -> None:
    project_root = Path(__file__).resolve().parents[1]
    compose = yaml.safe_load((project_root / "compose.yaml").read_text())
    expected = {
        "api": "API_DATABASE_URL",
        "worker": "CRAWLER_DATABASE_URL",
        "crawl-worker-2": "CRAWLER_DATABASE_URL",
        "crawl-worker-3": "CRAWLER_DATABASE_URL",
        "render-worker": "CRAWLER_DATABASE_URL",
        "integration-worker": "INTEGRATION_DATABASE_URL",
        "export-worker": "EXPORT_DATABASE_URL",
        "scheduler": "SCHEDULER_DATABASE_URL",
    }
    for service_name, variable_name in expected.items():
        database_url = compose["services"][service_name]["environment"]["DATABASE_URL"]
        assert variable_name in database_url


def test_database_role_policy_protects_sensitive_tables() -> None:
    project_root = Path(__file__).resolve().parents[1]
    policy = (project_root / "scripts/database-roles.sql").read_text()

    for role in ("seo_crawler", "seo_integration", "seo_export", "seo_scheduler"):
        assert f"TO {role}" in policy
    assert "integration_connections, login_attempts, oauth_states, security_audit_events" in policy
    assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC" in policy
    assert "GRANT SELECT, UPDATE ON TABLE exports TO seo_export" in policy


def test_database_role_configurator_does_not_source_environment_files() -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = (project_root / "scripts/configure-database-roles.sh").read_text()
    compose = yaml.safe_load((project_root / "compose.yaml").read_text())

    assert ". ./.env" not in script
    assert "--profile tools run --rm database-roles" in script
    assert compose["services"]["database-roles"]["read_only"] is True
    assert compose["services"]["database-roles"]["cap_drop"] == ["ALL"]


def test_crawler_network_is_separated_from_other_egress() -> None:
    project_root = Path(__file__).resolve().parents[1]
    compose = yaml.safe_load((project_root / "compose.yaml").read_text())
    services = compose["services"]

    assert compose["networks"]["backend"]["internal"] is True
    assert compose["networks"]["backend"]["enable_ipv6"] is False
    assert compose["networks"]["crawler-egress"]["enable_ipv6"] is False
    for service_name in ("worker", "crawl-worker-2", "crawl-worker-3", "render-worker"):
        assert services[service_name]["networks"] == ["backend", "crawler-egress"]
    for service_name in ("api", "integration-worker"):
        assert services[service_name]["networks"] == ["backend", "app-egress"]
    for service_name in ("export-worker", "scheduler", "postgres", "redis"):
        assert services[service_name]["networks"] == ["backend"]


def test_crawler_firewall_blocks_non_public_ipv4_ranges() -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = (project_root / "scripts/crawler-egress-firewall.sh").read_text()

    for destination in (
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "224.0.0.0/4",
        "240.0.0.0/4",
    ):
        assert destination in script
    assert 'iptables -F "$CHAIN_NAME"' in script
    assert '-j DROP' in script
    assert '--reject-with' not in script
    assert '/etc/resolv.conf' in script
    assert '-p udp --dport 53 -j RETURN' in script
    assert '-p tcp --dport 53 -j RETURN' in script
    assert 'iptables -I DOCKER-USER 1 -j "$CHAIN_NAME"' in script
    assert 'test "$LINK_POSITION" -lt "$RETURN_POSITION"' in script
    assert "iptables -F DOCKER-USER" not in script
    assert 'IPV6_ENABLED" != "false"' in script


def test_crawler_network_bootstrap_is_idempotent_and_validates_isolation() -> None:
    project_root = Path(__file__).resolve().parents[1]
    network_script = (
        project_root / "scripts/ensure-crawler-egress-network.sh"
    ).read_text()
    firewall_script = (
        project_root / "scripts/ensure-crawler-egress-firewall.sh"
    ).read_text()

    assert 'docker network inspect "$NETWORK_NAME"' in network_script
    assert "docker network create" in network_script
    assert 'com.docker.compose.network=crawler-egress' in network_script
    assert 'DRIVER" != "bridge"' in network_script
    assert 'INTERNAL" != "false"' in network_script
    assert 'IPV6_ENABLED" != "false"' in network_script
    assert '"$SCRIPT_DIR/ensure-crawler-egress-network.sh"' in firewall_script
