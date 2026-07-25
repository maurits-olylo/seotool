"""Replace large GSC text uniqueness indexes with compact SHA-256 keys.

Revision ID: 0028
Revises: 0027
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "search_console_metrics",
        sa.Column("dedup_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "search_console_query_metrics",
        sa.Column("dedup_key", sa.String(length=64), nullable=True),
    )

    op.execute(
        """
        UPDATE search_console_metrics
        SET dedup_key = encode(sha256(convert_to(page_url, 'UTF8')), 'hex')
        WHERE dedup_key IS NULL
        """
    )
    op.execute(
        """
        UPDATE search_console_query_metrics
        SET dedup_key = encode(
            sha256(
                convert_to(query, 'UTF8')
                || decode('00', 'hex')
                || convert_to(page_url, 'UTF8')
            ),
            'hex'
        )
        WHERE dedup_key IS NULL
        """
    )

    op.alter_column("search_console_metrics", "dedup_key", nullable=False)
    op.alter_column("search_console_query_metrics", "dedup_key", nullable=False)
    op.drop_constraint(
        "search_console_metrics_website_id_date_page_url_key",
        "search_console_metrics",
        type_="unique",
    )
    op.drop_constraint(
        "search_console_query_metrics_website_id_date_query_page_url_key",
        "search_console_query_metrics",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_search_console_metrics_website_date_dedup",
        "search_console_metrics",
        ["website_id", "date", "dedup_key"],
    )
    op.create_unique_constraint(
        "uq_search_console_query_metrics_website_date_dedup",
        "search_console_query_metrics",
        ["website_id", "date", "dedup_key"],
    )
    op.drop_index(
        "ix_search_console_query_metrics_query",
        table_name="search_console_query_metrics",
    )


def downgrade() -> None:
    op.create_index(
        "ix_search_console_query_metrics_query",
        "search_console_query_metrics",
        ["query"],
    )
    op.drop_constraint(
        "uq_search_console_query_metrics_website_date_dedup",
        "search_console_query_metrics",
        type_="unique",
    )
    op.drop_constraint(
        "uq_search_console_metrics_website_date_dedup",
        "search_console_metrics",
        type_="unique",
    )
    op.create_unique_constraint(
        "search_console_query_metrics_website_id_date_query_page_url_key",
        "search_console_query_metrics",
        ["website_id", "date", "query", "page_url"],
    )
    op.create_unique_constraint(
        "search_console_metrics_website_id_date_page_url_key",
        "search_console_metrics",
        ["website_id", "date", "page_url"],
    )
    op.drop_column("search_console_query_metrics", "dedup_key")
    op.drop_column("search_console_metrics", "dedup_key")
