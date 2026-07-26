import uuid

from sqlalchemy import event, select

from app.db.session import SessionLocal
from app.models.crawl import ElementLocation
from app.services.element_jumps import build_live_jump_url
from app.services.element_locations import mark_target_elements_for_targets
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
    assert all("duplicate_heading_text" not in item.issue_types for item in headings)
    assert all(item.text_is_unique is False for item in headings)
    assert all(item.context_is_unique is True for item in headings)
    assert any("cms_link_placeholder" in item.issue_types for item in page.elements)
    assert all("invalid_or_empty_link" not in item.issue_types for item in page.elements)
    assert any("broken_application_cta" in item.issue_types for item in page.elements)
    assert any(
        link.target_url == "https://example.com/solliciteren" for link in page.links
    )
    icon_link = next(item for item in page.elements if "zonder-tekst" in (item.target_url or ""))
    assert icon_link.visible_text is None


def test_interactive_controls_are_not_reported_as_broken_seo_links() -> None:
    page = extract_page(
        """
        <html><body>
          <div class="modal">
            <a class="repeat-remove" href="#">Bijlage verwijderen</a>
            <button type="button">Upload nog een bestand</button>
          </div>
          <a class="st-custom-button" data-network="linkedin" href="#">LinkedIn</a>
          <a onclick="openDialog()">Open formulier</a>
        </body></html>
        """,
        "https://example.com/pagina",
    )

    assert page.elements
    assert all("invalid_or_empty_link" not in item.issue_types for item in page.elements)


def test_broken_application_cta_remains_actionable() -> None:
    page = extract_page(
        '<html><body><button type="button">Solliciteer nu</button></body></html>',
        "https://example.com/vacature",
    )

    assert "broken_application_cta" in page.elements[0].issue_types


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


def test_marks_many_targets_with_one_filtered_select() -> None:
    run_id = uuid.uuid4()
    with SessionLocal() as db:
        matching_link = _location(
            crawl_run_id=run_id,
            target_url="https://example.com/one",
            issue_types=[],
        )
        matching_button = _location(
            crawl_run_id=run_id,
            target_url="https://example.com/two",
            element_type="button",
            issue_types=[],
        )
        unrelated = _location(
            crawl_run_id=run_id,
            target_url="https://example.com/other",
            issue_types=[],
        )
        db.add_all([matching_link, matching_button, unrelated])
        db.commit()
        selects: list[str] = []

        def capture_select(
            _conn: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: object,
        ) -> None:
            if statement.lstrip().upper().startswith("SELECT"):
                selects.append(statement)

        bind = db.get_bind()
        event.listen(bind, "before_cursor_execute", capture_select)
        try:
            updated = mark_target_elements_for_targets(
                db,
                crawl_run_id=run_id,
                target_urls={
                    "https://example.com/one",
                    "https://example.com/two",
                },
                issue_type="internally_linked_404",
                element_types={"a", "button"},
            )
        finally:
            event.remove(bind, "before_cursor_execute", capture_select)

        assert updated == 2
        assert len(selects) == 1
        assert "crawl_run_id" in selects[0]
        locations = list(
            db.scalars(
                select(ElementLocation).where(ElementLocation.crawl_run_id == run_id)
            )
        )
        by_target = {location.target_url: location.issue_types for location in locations}
        assert by_target["https://example.com/one"] == ["internally_linked_404"]
        assert by_target["https://example.com/two"] == ["internally_linked_404"]
        assert by_target["https://example.com/other"] == []


def test_bulk_target_matching_preserves_url_normalization() -> None:
    run_id = uuid.uuid4()
    with SessionLocal() as db:
        location = _location(
            crawl_run_id=run_id,
            target_url="https://EXAMPLE.com:443/missing#fragment",
            issue_types=[],
        )
        db.add(location)
        db.commit()

        updated = mark_target_elements_for_targets(
            db,
            crawl_run_id=run_id,
            target_urls={"https://example.com/missing"},
            issue_type="internally_linked_404",
        )

        assert updated == 1
        assert location.issue_types == ["internally_linked_404"]
