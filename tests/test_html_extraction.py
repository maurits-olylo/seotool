from pathlib import Path

from app.services.html_extraction import extract_page


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
