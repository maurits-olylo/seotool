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


def test_first_snapshot_is_new_url() -> None:
    assert compare_snapshots(None, snapshot())[0].change_type == "new_url"


def test_ignores_whitespace_only_metadata_changes() -> None:
    previous = snapshot(meta_description="Een duidelijke omschrijving.")
    current = snapshot(meta_description="  Een   duidelijke\nomschrijving. ")

    assert compare_snapshots(previous, current) == []


def test_schema_comparison_ignores_script_order_but_detects_values() -> None:
    previous = snapshot(schema_data=[{"@type": "Article", "@id": "/old"}, {"@type": "Person"}])
    reordered = snapshot(schema_data=[{"@type": "Person"}, {"@id": "/old", "@type": "Article"}])
    changed = snapshot(schema_data=[{"@type": "Person"}, {"@id": "/new", "@type": "Article"}])

    assert compare_snapshots(previous, reordered) == []
    assert [item.change_type for item in compare_snapshots(previous, changed)] == [
        "structured_data_changed"
    ]
