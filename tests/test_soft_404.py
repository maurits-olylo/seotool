from app.models.crawl import UrlSnapshot
from app.services.soft_404 import inspect_soft_404


def test_detects_strong_soft_404_from_independent_signals() -> None:
    snapshot = _snapshot(
        title="404 - Pagina niet gevonden",
        main_content="Deze pagina bestaat niet. Ga terug naar de homepage.",
        word_count=9,
        canonical="https://example.com/",
    )

    signals = inspect_soft_404(snapshot)

    assert [signal.issue_type for signal in signals] == ["soft_404"]
    assert signals[0].confidence == "high"
    assert signals[0].evidence["strong_evidence_count"] >= 2


def test_marks_empty_search_page_for_review_instead_of_hard_error() -> None:
    snapshot = _snapshot(
        url="https://example.com/zoeken?q=onbekend",
        title="Zoeken",
        main_content="Geen zoekresultaten gevonden.",
        word_count=3,
    )

    signals = inspect_soft_404(snapshot)

    assert [signal.issue_type for signal in signals] == ["possible_soft_404"]
    assert signals[0].confidence == "low"
    assert signals[0].severity == "low"


def test_does_not_treat_short_valid_page_as_soft_404() -> None:
    snapshot = _snapshot(
        title="Contact",
        main_content="Bel ons voor een afspraak.",
        word_count=5,
    )

    assert inspect_soft_404(snapshot) == []


def test_uses_previous_missing_status_as_supporting_evidence() -> None:
    previous = _snapshot(status_code=404, title=None, main_content=None, word_count=None)
    current = _snapshot(
        title="Pagina niet gevonden",
        main_content="Ga terug naar het overzicht.",
        word_count=6,
    )

    signals = inspect_soft_404(current, previous=previous)

    assert [signal.issue_type for signal in signals] == ["soft_404"]
    assert signals[0].evidence["previous_status_code"] == 404


def test_skips_redirects_non_html_and_noindex_pages() -> None:
    redirect = _snapshot(redirect_chain=[{"status_code": 301}])
    asset = _snapshot(content_type="image/png")
    noindex = _snapshot(is_indexable=False)

    assert inspect_soft_404(redirect) == []
    assert inspect_soft_404(asset) == []
    assert inspect_soft_404(noindex) == []


def _snapshot(
    *,
    url="https://example.com/missing",
    status_code=200,
    title="Page",
    main_content="Content",
    word_count=1,
    canonical=None,
    redirect_chain=None,
    content_type="text/html",
    is_indexable=True,
):  # type: ignore[no-untyped-def]
    return UrlSnapshot(
        requested_url=url,
        final_url=url,
        status_code=status_code,
        title=title,
        main_content=main_content,
        word_count=word_count,
        canonical=canonical,
        redirect_chain=redirect_chain or [],
        content_type=content_type,
        is_indexable=is_indexable,
    )
