import uuid

from app.models.crawl import ElementLocation
from app.services.element_jumps import build_live_jump_url
from app.services.html_extraction import extract_page


def _location(**overrides: object) -> ElementLocation:
    values: dict[str, object] = {
        "website_id": uuid.uuid4(),
        "source_url_id": uuid.uuid4(),
        "snapshot_id": uuid.uuid4(),
        "crawl_run_id": uuid.uuid4(),
        "issue_types": ["test_issue"],
        "element_type": "a",
        "target_url": "https://example.com/missing",
        "visible_text": "Lees meer",
        "element_id": None,
        "css_selector": "main > a:nth-of-type(1)",
        "xpath": "/html/body/main/a[1]",
        "html_fragment": '<a href="/missing">Lees meer</a>',
        "occurrence_index": 1,
        "text_prefix": None,
        "text_suffix": None,
        "text_is_unique": True,
        "context_is_unique": True,
        "rendered_dynamically": False,
    }
    values.update(overrides)
    return ElementLocation(**values)


def test_jump_prefers_stable_element_id_and_encodes_it() -> None:
    location = _location(element_id="vacature locatie")

    assert build_live_jump_url("https://example.com/page?x=1#old", location) == (
        "https://example.com/page?x=1#vacature%20locatie"
    )


def test_unique_heading_and_anchor_text_get_text_fragment_jumps() -> None:
    heading = _location(element_type="h2", visible_text="Prijzen & voorwaarden")
    anchor = _location(visible_text="Bekijk alle vacatures")

    assert build_live_jump_url("https://example.com/page", heading) == (
        "https://example.com/page#:~:text=Prijzen%20%26%20voorwaarden"
    )
    assert build_live_jump_url("https://example.com/page", anchor) == (
        "https://example.com/page#:~:text=Bekijk%20alle%20vacatures"
    )


def test_duplicate_text_only_jumps_with_unique_prefix_and_suffix() -> None:
    ambiguous = _location(text_is_unique=False, context_is_unique=False)
    contextual = _location(
        text_is_unique=False,
        context_is_unique=True,
        text_prefix="Over onze diensten",
        text_suffix="voor organisaties",
    )

    assert build_live_jump_url("https://example.com/page", ambiguous) is None
    assert build_live_jump_url("https://example.com/page", contextual) == (
        "https://example.com/page#:~:text=Over%20onze%20diensten-,Lees%20meer,-voor%20organisaties"
    )


def test_empty_icon_only_and_unlocatable_elements_have_no_jump() -> None:
    assert build_live_jump_url("https://example.com/page", _location(visible_text=None)) is None
    assert (
        build_live_jump_url(
            "https://example.com/page",
            _location(
                visible_text=None,
                css_selector=None,
                xpath=None,
                html_fragment="<a><svg></svg></a>",
            ),
        )
        is None
    )


def test_extracts_multiple_issue_elements_and_duplicate_context() -> None:
    page = extract_page(
        """
        <html><body><main>
          <p>Eerste sectie</p><h2>Meer informatie</h2>
          <a id="fixed" href="{{ cms.link }}">Lees meer</a>
          <p>Tweede sectie</p><h2>Meer informatie</h2>
          <a href="#">Lees meer</a>
          <button>Solliciteer</button>
          <form action="/solliciteren"><button>Ga naar formulier</button></form>
          <a href="/zonder-tekst"><svg></svg></a>
        </main></body></html>
        """,
        "https://example.com/pagina",
    )

    headings = [item for item in page.elements if item.element_type == "h2"]
    assert len(headings) == 2
    assert all("duplicate_heading_text" in item.issue_types for item in headings)
    assert all(item.text_is_unique is False for item in headings)
    assert all(item.context_is_unique is True for item in headings)
    assert any("cms_link_placeholder" in item.issue_types for item in page.elements)
    assert any("invalid_or_empty_link" in item.issue_types for item in page.elements)
    assert any("broken_application_cta" in item.issue_types for item in page.elements)
    assert any(
        link.target_url == "https://example.com/solliciteren" for link in page.links
    )
    icon_link = next(item for item in page.elements if "zonder-tekst" in (item.target_url or ""))
    assert icon_link.visible_text is None


def test_static_extraction_does_not_claim_dynamically_rendered_element() -> None:
    page = extract_page(
        """
        <html><body><main id="app"></main>
        <script>document.querySelector('#app').innerHTML = '<a href="/later">Later</a>';</script>
        </body></html>
        """,
        "https://example.com/page",
    )

    assert page.elements == []


def test_broken_image_candidate_uses_caption_or_stable_id() -> None:
    page = extract_page(
        """
        <html><body><main>
          <figure><img id="team-photo" src="/missing.jpg"><figcaption>Ons team</figcaption></figure>
        </main></body></html>
        """,
        "https://example.com/about",
    )

    image = next(item for item in page.elements if item.element_type == "img")
    assert image.target_url == "https://example.com/missing.jpg"
    assert image.visible_text == "Ons team"
    assert image.element_id == "team-photo"
