from pathlib import Path

from app.services.html_extraction import INVALID_JSON_LD_MARKER, extract_page


def test_extracts_page_data_and_hashes() -> None:
    html = (Path(__file__).parent / "fixtures" / "page.html").read_text()
    page = extract_page(html, "https://example.com/voorbeeld")
    assert page.title == "Voorbeeldpagina"
    assert page.meta_description == "Een duidelijke omschrijving."
    assert page.canonical == "https://example.com/voorbeeld"
    assert page.headings["h1"] == ["Hoofdtitel"]
    assert "Niet meetellen" not in page.main_content
    assert page.schema_types == ["JobPosting"]
    assert page.links[0].target_url == "https://example.com/contact"
    assert page.links[0].is_internal
    assert page.links[1].is_nofollow
    assert all(
        len(value) == 64 for value in [page.html_hash, page.main_content_hash, page.metadata_hash]
    )


def test_content_change_only_changes_relevant_hashes() -> None:
    first = extract_page(
        "<html><head><title>A</title></head><main>One</main></html>", "https://example.com"
    )
    second = extract_page(
        "<html><head><title>A</title></head><main>Two</main></html>", "https://example.com"
    )
    assert first.metadata_hash == second.metadata_hash
    assert first.main_content_hash != second.main_content_hash


def test_uses_complete_body_when_page_contains_multiple_article_cards() -> None:
    html = """
    <html><body>
      <header>Navigation</header>
      <article class="card">First card</article>
      <article class="card">Second card with useful content</article>
      <footer>Footer links</footer>
    </body></html>
    """
    page = extract_page(html, "https://example.com/")
    assert page.main_content == "First card Second card with useful content"
    assert page.word_count == 7


def test_link_and_schema_hashes_ignore_order_and_external_links() -> None:
    first = extract_page(
        '<html><body><a href="/b">B</a><a href="/a">A</a>'
        '<a href="https://external.example/one">Extern</a>'
        '<script type="application/ld+json">{"@type":"Article"}</script>'
        '<script type="application/ld+json">{"@type":"Person"}</script>'
        "</body></html>",
        "https://example.com/page",
    )
    second = extract_page(
        '<html><body><a href="https://external.example/two">Anders</a>'
        '<a href="/a">A</a><a href="/b">B</a>'
        '<script type="application/ld+json">{"@type":"Person"}</script>'
        '<script type="application/ld+json">{"@type":"Article"}</script>'
        "</body></html>",
        "https://example.com/page",
    )

    assert first.links_hash == second.links_hash
    assert first.schema_hash == second.schema_hash


def test_preserves_invalid_json_ld_as_a_validation_marker() -> None:
    page = extract_page(
        '<html><body><script type="application/ld+json">{"@type":}</script></body></html>',
        "https://example.com/page",
    )

    assert page.schema_data == [{INVALID_JSON_LD_MARKER: True}]
    assert page.schema_types == []


def test_skips_malformed_ipv6_link_and_canonical_without_failing_page() -> None:
    page = extract_page(
        """
        <html><head><link rel="canonical" href="https://[invalid/canonical"></head>
        <body><main>
          <a href="https://[invalid/link">Malformed</a>
          <a href="/valid">Valid</a>
        </main></body></html>
        """,
        "https://www.human.nl/medialogica/kijk/afleveringen/2018/aflevering-6.html",
    )

    assert page.canonical is None
    assert [link.target_url for link in page.links] == ["https://www.human.nl/valid"]
