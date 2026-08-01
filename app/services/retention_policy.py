from __future__ import annotations

from dataclasses import asdict, dataclass

POLICY_VERSION = "2026-08-02-v1"


@dataclass(frozen=True)
class RetentionPolicy:
    dataset: str
    retain_days: int | None
    automatic_cleanup: bool
    rationale: str


POLICIES = {
    policy.dataset: policy
    for policy in (
        RetentionPolicy(
            "element_locations",
            None,
            True,
            "Bewaar actuele crawls, nieuwste URL-locaties en issuebewijs.",
        ),
        RetentionPolicy(
            "url_links",
            180,
            True,
            "Bewaar zes maanden linkdetail plus actuele crawls en diagnosebewijs.",
        ),
        RetentionPolicy(
            "search_console_metrics",
            1098,
            True,
            "Bewaar minimaal drie jaar dagelijkse paginatrends.",
        ),
        RetentionPolicy(
            "search_console_query_metrics",
            1098,
            True,
            "Bewaar minimaal drie jaar dagelijkse querydetails voor jaarvergelijkingen.",
        ),
        RetentionPolicy(
            "google_analytics_metrics",
            1098,
            True,
            "Bewaar minimaal drie jaar organische landingspaginatrends.",
        ),
        RetentionPolicy(
            "google_analytics_event_metrics",
            1098,
            True,
            "Bewaar minimaal drie jaar gekwalificeerde eventtrends.",
        ),
        RetentionPolicy(
            "google_analytics_landing_page_event_metrics",
            1098,
            True,
            "Bewaar minimaal drie jaar eventdetail per landingspagina.",
        ),
        RetentionPolicy(
            "bing_page_metrics",
            1098,
            True,
            "Bewaar minimaal drie jaar dagelijkse Bing-paginatrends.",
        ),
        RetentionPolicy(
            "bing_query_metrics",
            1098,
            True,
            "Bewaar minimaal drie jaar dagelijkse Bing-querytrends.",
        ),
        RetentionPolicy(
            "crawl_runs",
            None,
            False,
            "Crawlrunhistorie blijft beschikbaar voor lifecycle, bewijs en operationele audit.",
        ),
        RetentionPolicy(
            "url_snapshots",
            None,
            False,
            "Alleen auditen totdat aggregaties en bewijsreferenties volledig zijn beschermd.",
        ),
        RetentionPolicy(
            "changes",
            None,
            False,
            "Wijzigingshistorie blijft behouden totdat een afzonderlijk detailbeleid is bewezen.",
        ),
        RetentionPolicy(
            "issues_tasks_verifications_audit",
            None,
            False,
            "Lifecycle-, taak-, verificatie- en auditgeschiedenis blijft permanent bewaard.",
        ),
    )
}

AUTOMATIC_DATASETS = tuple(
    dataset for dataset, policy in POLICIES.items() if policy.automatic_cleanup
)


def serialized_policies() -> dict[str, dict[str, object]]:
    return {dataset: asdict(policy) for dataset, policy in POLICIES.items()}
