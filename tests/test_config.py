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


def test_dataforseo_requires_credentials_only_when_enabled() -> None:
    assert Settings(dataforseo_enabled=False).dataforseo_enabled is False
    with pytest.raises(ValidationError, match="DATAFORSEO_LOGIN"):
        Settings(dataforseo_enabled=True)
    assert (
        Settings(
            dataforseo_enabled=True,
            dataforseo_login="fixture-login",
            dataforseo_password="fixture-password",
            external_serp_estimated_cost_micros=1,
            external_ai_citations_estimated_cost_micros=1,
        ).dataforseo_enabled
        is True
    )


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
        "render-artifacts-init",
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

    for service_name in (
        "api",
        "render-artifacts-init",
        "render-worker",
        "migrate",
        "database-roles",
    ):
        service = compose["services"][service_name]
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert service["security_opt"] == ["no-new-privileges:true"]
        assert service["pids_limit"] in {64, 256}


def test_application_image_runs_as_non_root_user() -> None:
    project_root = Path(__file__).resolve().parents[1]
    dockerfile = (project_root / "Dockerfile").read_text().splitlines()

    assert "USER app" in dockerfile


def test_application_images_install_only_hashed_locked_dependencies() -> None:
    project_root = Path(__file__).resolve().parents[1]
    dockerfile = (project_root / "Dockerfile").read_text()
    render_dockerfile = (project_root / "Dockerfile.render").read_text()
    runtime_lock = (project_root / "requirements.lock").read_text()
    render_lock = (project_root / "requirements-render.lock").read_text()

    assert "--require-hashes -r requirements.lock" in dockerfile
    assert "--require-hashes" in render_dockerfile
    assert "-r requirements.lock -r requirements-render.lock" in render_dockerfile
    assert "pip install --no-cache-dir ." not in dockerfile
    assert 'pip install --no-cache-dir ".[render]"' not in render_dockerfile
    assert "--hash=sha256:" in runtime_lock
    assert "--hash=sha256:" in render_lock


def test_application_images_pin_immutable_base_images() -> None:
    project_root = Path(__file__).resolve().parents[1]
    dockerfile = (project_root / "Dockerfile").read_text()
    render_dockerfile = (project_root / "Dockerfile.render").read_text()

    assert dockerfile.startswith("FROM python:3.12.13-slim-trixie@sha256:")
    assert "FROM node:22-bookworm-slim@sha256:" in render_dockerfile
    assert "FROM mcr.microsoft.com/playwright/python:v1.61.0-resolute@sha256:" in (
        render_dockerfile
    )


def test_security_workflow_is_read_only_and_pins_third_party_actions() -> None:
    project_root = Path(__file__).resolve().parents[1]
    workflow = (project_root / ".github/workflows/security-quality.yml").read_text()

    assert "permissions:\n  contents: read" in workflow
    assert "pull_request_target:" not in workflow
    assert "python-version: \"3.12\"" in workflow
    assert "pip install --require-hashes -r requirements-ci.lock" in workflow
    assert "pip-audit -r requirements.lock --strict" in workflow
    assert "cyclonedx-py requirements requirements.lock" in workflow
    assert "bandit -q -r app -ll" in workflow
    assert "detect-secrets scan" in workflow
    assert "severity: CRITICAL,HIGH" in workflow
    assert "continue-on-error: true" in workflow
    assert "Enforce container scan gate" in workflow
    for action_line in (
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405",
        "actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f",
        "aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25",
    ):
        assert action_line in workflow


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
        "DATAFORSEO_LOGIN",
        "DATAFORSEO_PASSWORD",
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
    assert "DATAFORSEO_LOGIN" in services["integration-worker"]["environment"]
    assert "DATAFORSEO_PASSWORD" in services["integration-worker"]["environment"]
    assert "INITIAL_SUPERUSER_PASSWORD" not in services["integration-worker"]["environment"]
    assert "privacy_ledger_data:/app/privacy-ledger" in services["api"]["volumes"]
    assert compose["volumes"]["privacy_ledger_data"]["name"] == (
        "seo-monitor-privacy-ledger-data"
    )
    assert compose["volumes"]["privacy_ledger_data"]["external"] is True


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
    assert (
        "GRANT SELECT ON TABLE google_analytics_metrics, search_console_metrics TO seo_crawler"
        in policy
    )
    assert (
        "GRANT SELECT, INSERT ON TABLE effect_interventions, effect_evaluations TO seo_crawler"
        in policy
    )
    assert "url_content_classifications, url_content_overrides TO seo_crawler" in policy
    assert "GRANT UPDATE (id) ON TABLE crawl_deployment_control TO seo_crawler" in policy
    assert "GRANT UPDATE (id) ON TABLE websites TO seo_scheduler" in policy
    assert "external_intelligence_requests, external_observations, external_usage_records" in policy


def test_database_role_configurator_does_not_source_environment_files() -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = (project_root / "scripts/configure-database-roles.sh").read_text()
    compose = yaml.safe_load((project_root / "compose.yaml").read_text())

    assert ". ./.env" not in script
    assert "--profile tools run --rm database-roles" in script
    assert compose["services"]["database-roles"]["read_only"] is True
    assert compose["services"]["database-roles"]["cap_drop"] == ["ALL"]


def test_release_12_staging_cleanup_does_not_distinct_json_task_rows() -> None:
    project_root = Path(__file__).resolve().parents[1]
    fixture = (project_root / "scripts/accept-release-12-staging.py").read_text()

    assert "select(RecommendationTaskIssue.task_id)" in fixture
    assert ".distinct()" not in fixture


def test_release_12_phase_d_fixture_is_synthetic_and_source_neutral() -> None:
    project_root = Path(__file__).resolve().parents[1]
    fixture = (project_root / "scripts/accept-release-12-phase-d-staging.py").read_text()

    assert "release-12-priority.invalid" in fixture
    assert 'Website.name.like("[STAGING]%")' in fixture
    assert "searchless_candidate" in fixture
    assert 'gsc: "Zoekprestatie"' in fixture
    assert 'crawler_issues: "Paginacontrole"' in fixture


def test_release_12_phase_e_fixture_is_synthetic_and_restores_source() -> None:
    project_root = Path(__file__).resolve().parents[1]
    fixture = (project_root / "scripts/accept-release-12-phase-e-staging.py").read_text()

    assert "release-12-testability.invalid" in fixture
    assert 'Website.name.like("[STAGING]%")' in fixture
    assert "false_device_candidate" in fixture
    assert "settings.primary_analytics_source = original_source" in fixture


def test_release_12_phase_f_fixture_checks_navigation_and_learning_safeguards() -> None:
    project_root = Path(__file__).resolve().parents[1]
    fixture = (project_root / "scripts/accept-release-12-phase-f-staging.py").read_text()

    assert '"primary_navigation": ["Inzichten", "Kansen", "Acties"]' in fixture
    assert '"legacy_routes": True' in fixture
    assert '"learning_minimum": 3' in fixture
    assert '"causal_claim": False' in fixture


def test_render_artifact_volume_is_initialized_before_worker() -> None:
    project_root = Path(__file__).resolve().parents[1]
    for filename, volume_name in (
        ("compose.yaml", "render_artifacts_data"),
        ("compose.staging.yaml", "staging_render_artifacts_data"),
    ):
        compose = yaml.safe_load((project_root / filename).read_text())
        initializer = compose["services"]["render-artifacts-init"]
        worker = compose["services"]["render-worker"]
        assert initializer["user"] == "root"
        assert initializer["cap_drop"] == ["ALL"]
        assert initializer["cap_add"] == ["CHOWN", "FOWNER"]
        assert initializer["restart"] == "no"
        assert initializer["profiles"] == ["rendering"]
        assert initializer["volumes"] == [f"{volume_name}:/app/render-artifacts"]
        assert worker["depends_on"]["render-artifacts-init"] == {
            "condition": "service_completed_successfully"
        }


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


def test_boot_restore_configures_production_and_staging_firewalls() -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = (
        project_root / "scripts/restore-crawler-egress-firewalls.sh"
    ).read_text()

    assert "PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" in script
    assert "CRAWLER_EGRESS_NETWORK_NAME=seo-monitor-crawler-egress" in script
    assert "CRAWLER_EGRESS_CHAIN_NAME=SEO-CRAWLER-EGRESS" in script
    assert "CRAWLER_EGRESS_NETWORK_NAME=seo-monitor-staging-crawler-egress" in script
    assert "CRAWLER_EGRESS_CHAIN_NAME=SEO-CRAWLER-STAGING" in script
    assert script.count('"$SCRIPT_DIR/ensure-crawler-egress-firewall.sh"') == 2
