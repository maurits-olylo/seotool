from pathlib import Path


def test_onboarding_migration_is_linear_and_additive() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (root / "alembic/versions/0062_website_onboarding_foundation.py").read_text()

    assert 'revision: str = "0062"' in migration
    assert 'down_revision: str | None = "0061"' in migration
    assert '"website_onboardings"' in migration
    assert '"website_ownership_verifications"' in migration
    assert 'ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE")' in migration
    assert "op.alter_column" not in migration


def test_first_crawl_migration_follows_onboarding_foundation() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (root / "alembic/versions/0063_onboarding_first_crawl.py").read_text()

    assert 'revision: str = "0063"' in migration
    assert 'down_revision: str | None = "0062"' in migration
    assert '"first_crawl_job_id"' in migration
    assert 'ondelete="SET NULL"' in migration
    assert "op.alter_column" not in migration
