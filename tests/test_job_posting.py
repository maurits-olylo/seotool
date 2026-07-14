from datetime import date

from app.services.job_posting import inspect_job_posting, recognize_job_listing


def test_expired_job_posting() -> None:
    data = [
        {
            "@type": "JobPosting",
            "title": "Developer",
            "description": "Vacature",
            "datePosted": "2025-01-01",
            "validThrough": "2025-02-01",
            "hiringOrganization": {"name": "Thact"},
            "employmentType": "FULL_TIME",
            "identifier": {"value": "developer-1"},
        }
    ]
    signals = inspect_job_posting(data, today=date(2026, 1, 1), main_content="Solliciteer direct.")
    assert [signal.issue_type for signal in signals] == ["expired_job_posting"]


def test_job_posting_missing_required_fields() -> None:
    signals = inspect_job_posting([{"@type": "JobPosting", "title": "Developer"}])
    assert signals[0].issue_type == "job_posting_missing_fields"
    assert signals[0].evidence["missing_fields"] == [
        "description",
        "datePosted",
        "hiringOrganization",
    ]


def test_recognized_vacancy_without_schema_gets_google_for_jobs_issue() -> None:
    signals = inspect_job_posting(
        [],
        page_url="https://example.com/over/vacatures/seo-specialist",
        main_content="Deze vacature is voor een SEO specialist. Solliciteer direct.",
    )

    assert [signal.issue_type for signal in signals] == ["job_posting_schema_missing"]


def test_google_for_jobs_validation_detects_remote_and_application_problems() -> None:
    signals = inspect_job_posting(
        [
            {
                "@type": "JobPosting",
                "title": "Remote developer",
                "description": "Bouw onze applicatie.",
                "datePosted": "2026-01-10",
                "hiringOrganization": {"name": "Thact"},
                "jobLocationType": "TELECOMMUTE",
            }
        ],
        page_url="https://example.com/vacatures/remote-developer",
        main_content="Een vacature voor een remote developer.",
    )
    assert {signal.issue_type for signal in signals} == {
        "job_posting_missing_application",
        "job_posting_remote_location_missing",
        "job_posting_missing_recommended_fields",
    }
    optimization = next(
        signal
        for signal in signals
        if signal.issue_type == "job_posting_missing_recommended_fields"
    )
    assert optimization.category == "optimization"
    assert optimization.severity == "low"
    assert optimization.confidence == "low"
    assert "niet verplicht" in optimization.recommended_action


def test_google_for_jobs_validation_detects_bad_dates_and_overview_schema() -> None:
    signals = inspect_job_posting(
        [
            {
                "@type": "JobPosting",
                "title": "Developer",
                "description": "Bouw onze applicatie.",
                "datePosted": "2026-02-10",
                "validThrough": "2026-01-10",
                "hiringOrganization": {"name": "Thact"},
                "employmentType": "FULL_TIME",
                "identifier": {"value": "dev-1"},
            }
        ],
        page_url="https://example.com/vacatures",
        main_content="Solliciteer direct.",
        today=date(2025, 1, 1),
    )
    assert {signal.issue_type for signal in signals} == {
        "job_posting_invalid_dates",
        "job_posting_not_detail_page",
    }


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


def test_job_listing_recognition_extracts_schema_fields_and_lifecycle() -> None:
    listing = recognize_job_listing(
        [
            {
                "@type": "JobPosting",
                "title": "SEO specialist",
                "datePosted": "2026-01-01",
                "validThrough": "2026-01-10",
                "hiringOrganization": {"name": "Thact"},
                "jobLocation": {"address": {"addressLocality": "Amsterdam"}},
                "employmentType": ["FULL_TIME"],
                "identifier": {"value": "seo-123"},
            }
        ],
        page_url="https://example.com/vacatures/seo-specialist",
        title="SEO specialist vacature",
        headings={"h1": ["SEO specialist"]},
        main_content="Solliciteer op deze vacature.",
        status_code=200,
        redirect_chain=[],
        application_url="https://example.com/solliciteren",
        today=date(2026, 1, 1),
    )

    assert listing is not None
    assert listing.lifecycle_status == "expiring_soon"
    assert listing.title == "SEO specialist"
    assert listing.employer == "Thact"
    assert listing.locations == ["Amsterdam"]
    assert listing.external_identifier == "seo-123"
    assert listing.application_url == "https://example.com/solliciteren"


def test_job_listing_fallback_requires_a_detail_vacancy_url() -> None:
    listing = recognize_job_listing(
        [],
        page_url="https://example.com/vacatures",
        title="Vacatures",
        headings={"h1": ["Vacatures"]},
        main_content="Bekijk alle vacatures.",
        status_code=200,
        redirect_chain=[],
        application_url=None,
    )

    assert listing is None
