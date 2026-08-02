from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.services.html_extraction import extract_page
from app.services.render_analysis import (
    compare_rendered_page,
    render_issue_signals,
    select_render_candidates,
)


def test_selects_only_bounded_diverse_risk_pages() -> None:
    records = [
        _record("https://example.com/product/101", words=5),
        _record("https://example.com/product/102", words=5),
        _record("https://example.com/contact", words=250, important=True),
        _record("https://example.com/about", words=250),
        _record("https://example.com/file.pdf", words=0, content_type="application/pdf"),
    ]

    selected = select_render_candidates(records, limit=10)

    assert [item.url.normalized_url for item in selected] == [
        "https://example.com/contact",
        "https://example.com/product/101",
    ]
    assert selected[0].reasons == ("important_url",)
    assert "low_static_word_count" in selected[1].reasons


def test_candidate_limit_cannot_exceed_safety_cap() -> None:
    records = [
        _record(f"https://example.com/section-{chr(97 + number)}/page", words=0)
        for number in range(20)
    ]

    assert len(select_render_candidates(records, limit=100)) == 10
    assert select_render_candidates(records, limit=0) == []


def test_compares_content_links_and_seo_instructions() -> None:
    snapshot = _snapshot(words=8)
    snapshot.main_content_hash = "static-main"
    snapshot.metadata_hash = "static-meta"
    snapshot.schema_hash = "static-schema"
    snapshot.canonical = "https://example.com/old"
    rendered = extract_page(
        """
        <html><head>
          <title>Rendered page</title>
          <meta name="robots" content="noindex">
          <link rel="canonical" href="https://example.com/new">
          <script type="application/ld+json">{{"@type": "Article"}}</script>
        </head><body><main>
          <p>{content}</p><a href="/only-after-js">Verder</a>
        </main></body></html>
        """.format(content="woord " * 180),
        "https://example.com/page",
    )

    comparison = compare_rendered_page(
        snapshot,
        rendered,
        static_internal_links={"https://example.com/already-static"},
    )
    signals = render_issue_signals(comparison)

    assert comparison["javascript_dependent_content"] is True
    assert comparison["javascript_only_links"] == ["https://example.com/only-after-js"]
    assert comparison["canonical_changed"] is True
    assert comparison["robots_changed"] is True
    assert {signal.issue_type for signal in signals} == {
        "javascript_dependent_content",
        "javascript_only_links",
        "javascript_metadata_conflict",
    }


def test_detects_content_that_disappears_during_rendering() -> None:
    snapshot = _snapshot(words=400)
    rendered = extract_page("<html><body><main>Leeg</main></body></html>", "https://example.com/")

    comparison = compare_rendered_page(snapshot, rendered)

    assert comparison["rendered_content_missing"] is True
    assert "rendered_content_missing" in {
        signal.issue_type for signal in render_issue_signals(comparison)
    }


def _record(
    url: str,
    *,
    words: int,
    important: bool = False,
    content_type: str = "text/html; charset=utf-8",
) -> tuple[Url, UrlSnapshot]:
    return (
        Url(normalized_url=url, is_active=True, is_important=important),
        _snapshot(words=words, content_type=content_type),
    )


def _snapshot(
    *, words: int, content_type: str = "text/html; charset=utf-8"
) -> UrlSnapshot:
    return UrlSnapshot(
        status_code=200,
        content_type=content_type,
        is_indexable=True,
        word_count=words,
        main_content="woord " * words,
        headings={"h1": ["Kop"]},
        title="Titel",
        meta_robots=None,
        main_content_hash=f"main-{words}",
        metadata_hash="meta",
        schema_hash="schema",
    )
