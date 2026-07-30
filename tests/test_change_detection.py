import uuid

from app.models.crawl import UrlSnapshot
from app.services.change_detection import compare_snapshots


def snapshot(**values: object) -> UrlSnapshot:
    defaults = {
        "url_id": uuid.uuid4(),
        "crawl_run_id": uuid.uuid4(),
        "requested_url": "https://example.com/page",
        "status_code": 200,
        "final_url": "https://example.com/page",
        "headings": {"h1": ["Old"]},
        "main_content_hash": "old",
        "links_hash": "links",
        "schema_hash": "schema",
        "is_indexable": True,
    }
    defaults.update(values)
    return UrlSnapshot(**defaults)


def test_detects_selected_snapshot_changes() -> None:
    previous = snapshot()
    current = snapshot(
        status_code=404,
        headings={"h1": ["New"]},
        main_content_hash="new",
        is_indexable=False,
    )
    types = {change.change_type for change in compare_snapshots(previous, current)}
    assert types == {
        "status_code_changed",
        "h1_changed",
        "main_content_changed",
        "indexability_changed",
    }


def test_ignores_main_content_when_only_the_block_order_changes() -> None:
    previous = snapshot(
        main_content="Product alpha € 10 Product beta € 20",
        main_content_hash="old",
    )
    current = snapshot(
        main_content="Product beta € 20 Product alpha € 10",
        main_content_hash="new",
    )

    changes = compare_snapshots(previous, current)

    assert "main_content_changed" not in {change.change_type for change in changes}


def test_ignores_dynamic_opening_status_in_main_content() -> None:
    previous = snapshot(
        main_content=(
            "Showrooms Amstelveen Geopend vanaf 13:00 uur Meer informatie "
            "Groningen Geopend tot 17:00 uur Maak een afspraak"
        ),
        main_content_hash="old",
    )
    current = snapshot(
        main_content=(
            "Showrooms Amstelveen Geopend vanaf 10:00 uur Meer informatie "
            "Groningen Alleen op afspraak Maak een afspraak"
        ),
        main_content_hash="new",
    )

    changes = compare_snapshots(previous, current)

    assert "main_content_changed" not in {change.change_type for change in changes}


def test_keeps_real_showroom_content_change_beside_opening_status() -> None:
    previous = snapshot(
        main_content="Showroom Amstelveen Binderij 14a Geopend tot 17:00 uur",
        main_content_hash="old",
    )
    current = snapshot(
        main_content="Showroom Amstelveen Nieuw adres 10 Geopend vanaf 10:00 uur",
        main_content_hash="new",
    )

    assert "main_content_changed" in {
        change.change_type for change in compare_snapshots(previous, current)
    }


def test_first_snapshot_is_new_url() -> None:
    assert compare_snapshots(None, snapshot())[0].change_type == "new_url"


def test_ignores_whitespace_only_metadata_changes() -> None:
    previous = snapshot(meta_description="Een duidelijke omschrijving.")
    current = snapshot(meta_description="  Een   duidelijke\nomschrijving. ")

    assert compare_snapshots(previous, current) == []


def test_ignores_whitespace_only_h1_changes() -> None:
    previous = snapshot(headings={"h1": ["SEO monitoring platform"]})
    current = snapshot(headings={"h1": ["  SEO   monitoring\nplatform "]})

    assert compare_snapshots(previous, current) == []


def test_schema_comparison_ignores_script_order_but_detects_values() -> None:
    previous = snapshot(schema_data=[{"@type": "Article", "@id": "/old"}, {"@type": "Person"}])
    reordered = snapshot(schema_data=[{"@type": "Person"}, {"@id": "/old", "@type": "Article"}])
    changed = snapshot(schema_data=[{"@type": "Person"}, {"@id": "/new", "@type": "Article"}])

    assert compare_snapshots(previous, reordered) == []
    assert [item.change_type for item in compare_snapshots(previous, changed)] == [
        "structured_data_changed"
    ]


def test_schema_comparison_ignores_graph_and_type_order() -> None:
    previous = snapshot(
        schema_data=[
            {
                "@context": "https://schema.org",
                "@graph": [
                    {"@id": "/website", "@type": ["WebSite", "Thing"]},
                    {"@id": "/page", "@type": "WebPage"},
                ],
            }
        ]
    )
    reordered = snapshot(
        schema_data=[
            {
                "@context": "https://schema.org",
                "@graph": [
                    {"@type": "WebPage", "@id": "/page"},
                    {"@type": ["Thing", "WebSite"], "@id": "/website"},
                ],
            }
        ]
    )

    assert compare_snapshots(previous, reordered) == []


def test_schema_comparison_keeps_meaningful_list_order() -> None:
    previous = snapshot(schema_data=[{"@type": "ItemList", "itemListElement": ["one", "two"]}])
    reordered = snapshot(schema_data=[{"@type": "ItemList", "itemListElement": ["two", "one"]}])

    assert [item.change_type for item in compare_snapshots(previous, reordered)] == [
        "structured_data_changed"
    ]
