from datetime import date

from app.services.job_posting import inspect_job_posting


def test_expired_job_posting() -> None:
    data = [
        {
            "@type": "JobPosting",
            "title": "Developer",
            "description": "Vacature",
            "datePosted": "2025-01-01",
            "validThrough": "2025-02-01",
        }
    ]
    signals = inspect_job_posting(data, today=date(2026, 1, 1))
    assert [signal.issue_type for signal in signals] == ["expired_job_posting"]


def test_job_posting_missing_required_fields() -> None:
    signals = inspect_job_posting([{"@type": "JobPosting", "title": "Developer"}])
    assert signals[0].issue_type == "job_posting_missing_fields"
    assert signals[0].evidence["missing_fields"] == ["description", "datePosted"]


def test_visible_expired_deadline_requires_an_active_application_cta() -> None:
    signals = inspect_job_posting(
        [],
        today=date(2026, 1, 1),
        status_code=200,
        main_content="Solliciteren tot 1 december 2025 voor deze functie.",
        has_application_cta=True,
        inbound_internal_links=3,
    )

    assert [signal.issue_type for signal in signals] == [
        "expired_job_posting",
        "expired_job_posting_linked",
    ]
    assert signals[0].evidence["visible_closing_date"] == "2025-12-01"
    assert signals[1].evidence["inbound_internal_links"] == 3


def test_expired_deadline_without_application_cta_is_not_a_hard_issue() -> None:
    signals = inspect_job_posting(
        [],
        today=date(2026, 1, 1),
        main_content="Sluitingsdatum: 1 december 2025.",
    )

    assert signals == []


def test_missing_job_url_is_reported_when_previously_a_job_posting() -> None:
    signals = inspect_job_posting(
        [],
        status_code=404,
        page_url="https://example.com/over/vacatures/developer",
        was_job_posting=True,
    )

    assert [signal.issue_type for signal in signals] == ["expired_job_posting_404"]
