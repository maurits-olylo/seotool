"""Correct orphan diagnoses and active recommendation tasks.

Revision ID: 0033
Revises: 0032
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE_TASK_STATUSES = "'open', 'planned', 'in_progress', 'waiting_for_input', 'implemented'"


def upgrade() -> None:
    op.execute(
        """
        UPDATE issues
        SET title = 'Indexeerbare pagina staat buiten de interne sitestructuur',
            description = 'De URL staat in de sitemap en is indexeerbaar, maar de volledige '
                'crawl vond geen interne route naar deze pagina. Dit bewijst nog niet of de '
                'pagina moet blijven bestaan.',
            recommended_action = 'Bepaal eerst of de pagina zelfstandig moet blijven. Geef haar '
                'daarna een logische plek in de sitestructuur, of voeg haar samen of redirect '
                'haar naar de bedoelde bestemming en werk de sitemap bij.'
        WHERE issue_type = 'orphan_page'
          AND status NOT IN ('resolved', 'verified', 'ignored', 'accepted_risk')
        """
    )
    op.execute(
        """
        UPDATE issues
        SET recommended_action = 'Beoordeel per URL-familie eerst of de pagina''s zelfstandig '
                'moeten blijven. Geef bedoelde pagina''s een logische plek in de sitestructuur; '
                'voeg overbodige pagina''s samen of redirect ze en werk daarna de sitemap bij.'
        WHERE issue_type = 'orphan_page_clusters'
          AND status NOT IN ('resolved', 'verified', 'ignored', 'accepted_risk')
        """
    )
    op.execute(
        f"""
        UPDATE recommendation_tasks AS task
        SET recommendation_type = 'resolve_orphan_structure',
            definition_version = '1',
            title = 'Bepaal de juiste plek of bestemming van deze pagina',
            primary_role = 'seo_analytics',
            supporting_roles = '["content", "development"]'::json,
            effort_min_minutes = 30,
            effort_max_minutes = 120,
            effort_confidence = 'medium',
            feasibility = 'needs_decision',
            action = 'Bepaal eerst of de pagina zelfstandig moet blijven. Geef haar daarna een '
                'logische plek in de sitestructuur, of voeg haar samen of redirect haar naar de '
                'bedoelde bestemming en werk de sitemap bij.',
            rationale = 'De indexeerbare sitemap-URL staat buiten de interne sitestructuur. '
                'Dat bewijst niet dat extra links de juiste oplossing zijn.',
            steps = json_build_array(
                'Beslis eerst of deze pagina zelfstandig moet blijven bestaan.',
                'Blijft de pagina? Geef haar een logische plek in de interne sitestructuur.',
                'Is de pagina niet nodig? Voeg haar samen of redirect haar en werk de sitemap bij.'
            ),
            required_input = json_build_array(
                'Moet deze pagina zelfstandig blijven bestaan?'
            ),
            acceptance_criteria = json_build_array(
                'De pagina heeft een bewuste, crawlbare plek in de sitestructuur, of is '
                'samengevoegd of doorgestuurd naar de bedoelde bestemming.'
            ),
            verification_spec = json_build_object('scope', json_build_array()),
            verification_status = 'not_requested',
            updated_at = CURRENT_TIMESTAMP
        WHERE task.recommendation_type = 'connect_orphan_page'
          AND task.status IN ({ACTIVE_TASK_STATUSES})
          AND EXISTS (
              SELECT 1
              FROM recommendation_task_issues AS task_issue
              JOIN issues AS issue ON issue.id = task_issue.issue_id
              WHERE task_issue.task_id = task.id
                AND issue.issue_type IN ('orphan_page', 'orphan_page_clusters')
          )
        """
    )
    op.execute(
        f"""
        DELETE FROM recommendation_task_urls AS old_scope
        USING recommendation_tasks AS task
        WHERE old_scope.task_id = task.id
          AND old_scope.role = 'source'
          AND task.recommendation_type = 'resolve_orphan_structure'
          AND task.status IN ({ACTIVE_TASK_STATUSES})
          AND EXISTS (
              SELECT 1
              FROM recommendation_task_urls AS current_scope
              WHERE current_scope.task_id = old_scope.task_id
                AND current_scope.url_id = old_scope.url_id
                AND current_scope.role = 'changed'
          )
        """
    )
    op.execute(
        f"""
        UPDATE recommendation_task_urls AS task_url
        SET role = 'changed'
        FROM recommendation_tasks AS task
        WHERE task_url.task_id = task.id
          AND task_url.role = 'source'
          AND task.recommendation_type = 'resolve_orphan_structure'
          AND task.status IN ({ACTIVE_TASK_STATUSES})
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE recommendation_tasks
        SET recommendation_type = 'connect_orphan_page',
            definition_version = '1',
            title = 'Verbind de pagina met relevante interne links',
            primary_role = 'seo_analytics',
            supporting_roles = '["content"]'::json,
            effort_min_minutes = 20,
            effort_max_minutes = 90,
            effort_confidence = 'medium',
            feasibility = 'needs_manual_review',
            steps = json_build_array(
                'Selecteer relevante bronpagina''s.',
                'Voeg contextuele links naar de doelpagina toe.'
            ),
            required_input = json_build_array(),
            acceptance_criteria = json_build_array(
                'De doelpagina heeft relevante crawlbare inkomende links.'
            ),
            verification_spec = json_build_object(
                'scope',
                json_build_array('source', 'target')
            ),
            updated_at = CURRENT_TIMESTAMP
        WHERE recommendation_type = 'resolve_orphan_structure'
        """
    )
    op.execute(
        """
        UPDATE recommendation_task_urls AS task_url
        SET role = 'source'
        FROM recommendation_tasks AS task
        WHERE task_url.task_id = task.id
          AND task_url.role = 'changed'
          AND task.recommendation_type = 'connect_orphan_page'
        """
    )
