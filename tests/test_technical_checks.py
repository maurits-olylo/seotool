import uuid

from app.models.crawl import UrlSnapshot
from app.services.technical_checks import inspect_snapshot


def test_detects_404() -> None:
    snapshot = UrlSnapshot(
        url_id=uuid.uuid4(),
        crawl_run_id=uuid.uuid4(),
        requested_url="https://example.com/missing",
        status_code=404,
        headings={},
        redirect_chain=[],
    )
    assert [signal.issue_type for signal in inspect_snapshot(snapshot)] == ["http_404"]


def test_detects_onpage_and_indexation_signals() -> None:
    snapshot = UrlSnapshot(
        url_id=uuid.uuid4(),
        crawl_run_id=uuid.uuid4(),
        requested_url="https://example.com/page",
        final_url="https://example.com/page",
        status_code=200,
        title=None,
        meta_description=None,
        headings={"h1": []},
        word_count=10,
        is_indexable=False,
        canonical="https://example.com/other",
        redirect_chain=[],
    )
    types = {signal.issue_type for signal in inspect_snapshot(snapshot)}
    assert types == {
        "missing_title",
        "missing_meta_description",
        "missing_h1",
        "thin_content",
        "unexpected_noindex",
        "canonical_other_url",
    }


def test_does_not_report_final_page_onpage_issues_on_redirect_source() -> None:
    snapshot = UrlSnapshot(
        url_id=uuid.uuid4(),
        crawl_run_id=uuid.uuid4(),
        requested_url="http://example.com/",
        final_url="https://example.com/",
        status_code=200,
        title=None,
        headings={"h1": ["One", "Two"]},
        word_count=1,
        redirect_chain=[
            {
                "url": "http://example.com/",
                "status_code": 301,
                "target": "https://example.com/",
            }
        ],
    )
    assert inspect_snapshot(snapshot) == []
