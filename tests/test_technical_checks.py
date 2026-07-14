import uuid
from datetime import date

from app.models.crawl import UrlSnapshot
from app.services.http_crawler import CrawlError
from app.services.technical_checks import inspect_crawl_error, inspect_snapshot


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


def test_maps_only_actionable_crawl_errors_to_issues() -> None:
    timeout = inspect_crawl_error(CrawlError("Timed out", error_type="timeout"))
    redirect_loop = inspect_crawl_error(
        CrawlError("Redirect loop detected", error_type="redirect_loop")
    )
    generic = inspect_crawl_error(CrawlError("Connection reset"))

    assert [signal.issue_type for signal in timeout] == ["crawl_timeout"]
    assert [signal.issue_type for signal in redirect_loop] == ["redirect_loop"]
    assert generic == []


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
    assert types == {"canonical_other_url"}


def test_ignores_onpage_signals_for_intentionally_non_indexable_page() -> None:
    snapshot = UrlSnapshot(
        requested_url="https://example.com/account/login",
        final_url="https://example.com/account/login",
        status_code=200,
        title=None,
        meta_description=None,
        headings={"h1": ["Login", "Account"]},
        word_count=20,
        is_indexable=False,
        meta_robots="noindex,follow",
        redirect_chain=[],
    )

    types = {signal.issue_type for signal in inspect_snapshot(snapshot)}

    assert types == set()


def test_keeps_onpage_signals_for_indexable_page() -> None:
    snapshot = UrlSnapshot(
        requested_url="https://example.com/services/seo",
        final_url="https://example.com/services/seo",
        status_code=200,
        title=None,
        meta_description=None,
        headings={"h1": []},
        word_count=200,
        is_indexable=True,
        redirect_chain=[],
    )

    types = {signal.issue_type for signal in inspect_snapshot(snapshot)}

    assert types == {"missing_title", "missing_meta_description", "missing_h1"}


def test_reports_limited_content_only_for_indexable_content_pages() -> None:
    snapshot = UrlSnapshot(
        requested_url="https://example.com/diensten/seo",
        final_url="https://example.com/diensten/seo",
        status_code=200,
        title="SEO",
        meta_description="SEO-diensten",
        headings={"h1": ["SEO"]},
        word_count=100,
        is_indexable=True,
        redirect_chain=[],
    )

    signal = next(item for item in inspect_snapshot(snapshot) if item.issue_type == "thin_content")

    assert signal.title == "Beperkte hoofdcontent"
    assert signal.severity == "low"
    assert signal.evidence == {
        "word_count": 100,
        "threshold": 150,
        "content_level": "limited",
    }


def test_reports_nearly_empty_indexable_page_with_more_urgency() -> None:
    snapshot = UrlSnapshot(
        requested_url="https://example.com/diensten/seo",
        final_url="https://example.com/diensten/seo",
        status_code=200,
        title="SEO",
        headings={"h1": ["SEO"]},
        word_count=12,
        is_indexable=True,
        redirect_chain=[],
    )

    signal = next(item for item in inspect_snapshot(snapshot) if item.issue_type == "thin_content")

    assert signal.title == "Nagenoeg lege pagina"
    assert signal.severity == "medium"
    assert signal.evidence["content_level"] == "nearly_empty"


def test_ignores_thin_confirmation_and_filter_pages() -> None:
    snapshots = [
        UrlSnapshot(
            requested_url="https://example.com/bevestiging-aanvraag",
            final_url="https://example.com/bevestiging-aanvraag",
            status_code=200,
            word_count=10,
            is_indexable=True,
            redirect_chain=[],
        ),
        UrlSnapshot(
            requested_url="https://example.com/nieuws?page=2",
            final_url="https://example.com/nieuws?page=2",
            status_code=200,
            word_count=10,
            is_indexable=True,
            redirect_chain=[],
        ),
    ]

    for snapshot in snapshots:
        assert "thin_content" not in {signal.issue_type for signal in inspect_snapshot(snapshot)}


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


def test_ignores_query_filter_canonical_to_same_path() -> None:
    snapshot = UrlSnapshot(
        requested_url="https://example.com/articles?c=doors",
        final_url="https://example.com/articles?c=doors",
        status_code=200,
        canonical="https://example.com/articles",
        title="Articles",
        meta_description="Articles description",
        headings={"h1": ["Articles"]},
        word_count=100,
        is_indexable=True,
        redirect_chain=[],
    )
    types = {signal.issue_type for signal in inspect_snapshot(snapshot)}
    assert "canonical_other_url" not in types


def test_reports_paginated_canonical_to_first_page() -> None:
    snapshot = UrlSnapshot(
        requested_url="https://example.com/news?page=2&sort=date",
        final_url="https://example.com/news?page=2&sort=date",
        status_code=200,
        canonical="https://example.com/news",
        title="News page 2",
        meta_description="Older news",
        headings={"h1": ["News"]},
        word_count=100,
        is_indexable=True,
        redirect_chain=[],
    )
    types = {signal.issue_type for signal in inspect_snapshot(snapshot)}
    assert "canonical_other_url" in types


def test_reports_invalid_json_ld_blocks() -> None:
    snapshot = UrlSnapshot(
        requested_url="https://example.com/page",
        final_url="https://example.com/page",
        status_code=200,
        title="Page",
        headings={"h1": ["Page"]},
        word_count=200,
        is_indexable=True,
        redirect_chain=[],
        schema_data=[{"_seo_monitor_invalid_json_ld": True}],
    )

    signal = next(
        item for item in inspect_snapshot(snapshot) if item.issue_type == "invalid_json_ld"
    )

    assert signal.severity == "medium"
    assert signal.evidence["invalid_blocks"] == 1


def test_flags_explicitly_dated_old_editorial_content_for_review() -> None:
    snapshot = UrlSnapshot(
        requested_url="https://example.com/kennisbank/seo",
        final_url="https://example.com/kennisbank/seo",
        status_code=200,
        title="SEO handleiding",
        headings={"h1": ["SEO handleiding"]},
        word_count=900,
        is_indexable=True,
        redirect_chain=[],
        schema_data=[
            {
                "@type": "Article",
                "datePublished": "2019-02-01",
                "dateModified": "2022-06-15T10:00:00+02:00",
            }
        ],
    )

    signal = next(
        item
        for item in inspect_snapshot(snapshot, today=date(2026, 7, 14))
        if item.issue_type == "possibly_outdated_content"
    )

    assert signal.severity == "low"
    assert signal.confidence == "low"
    assert signal.evidence["content_date"] == "2022-06-15"
    assert signal.evidence["date_source"] == "dateModified"


def test_does_not_flag_recent_or_non_editorial_content_as_outdated() -> None:
    snapshots = [
        UrlSnapshot(
            requested_url="https://example.com/recent",
            final_url="https://example.com/recent",
            status_code=200,
            word_count=500,
            is_indexable=True,
            redirect_chain=[],
            schema_data=[
                {
                    "@type": "BlogPosting",
                    "datePublished": "2018-01-01",
                    "dateModified": "2026-06-01",
                }
            ],
        ),
        UrlSnapshot(
            requested_url="https://example.com/organisatie",
            final_url="https://example.com/organisatie",
            status_code=200,
            word_count=500,
            is_indexable=True,
            redirect_chain=[],
            schema_data=[{"@type": "Organization", "dateModified": "2018-01-01"}],
        ),
    ]

    for snapshot in snapshots:
        types = {
            signal.issue_type for signal in inspect_snapshot(snapshot, today=date(2026, 7, 14))
        }
        assert "possibly_outdated_content" not in types
