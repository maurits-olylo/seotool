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
