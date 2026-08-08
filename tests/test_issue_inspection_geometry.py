from app.services.issue_inspection import _matching_box


def test_matching_box_requires_one_positive_exact_match() -> None:
    target = {
        "kind": "located",
        "element_type": "a",
        "target_url": "https://example.com/contact",
        "visible_text": "Contact",
        "occurrence_index": 1,
        "locator": {"strategy": "id", "value": "cta", "reliable": True},
    }
    box = {
        "element_type": "a",
        "element_id": "cta",
        "target_url": "https://example.com/contact",
        "visible_text": "Contact",
        "occurrence_index": 1,
        "x": 10,
        "y": 20,
        "width": 100,
        "height": 40,
    }

    assert _matching_box(target, [box]) == {
        "x": 10.0,
        "y": 20.0,
        "width": 100.0,
        "height": 40.0,
    }
    assert _matching_box(target, [box, box]) is None
    assert _matching_box(target, [{**box, "width": -1}]) is None


def test_matching_box_uses_full_signature_without_stable_id() -> None:
    target = {
        "kind": "located",
        "element_type": "button",
        "target_url": None,
        "visible_text": "Aanvragen",
        "occurrence_index": 2,
        "locator": {"strategy": "text", "value": "Aanvragen", "reliable": True},
    }
    matching = {
        "element_type": "button",
        "element_id": None,
        "target_url": None,
        "visible_text": "Aanvragen",
        "occurrence_index": 2,
        "x": 30,
        "y": 40,
        "width": 90,
        "height": 35,
    }

    assert _matching_box(target, [matching]) is not None
    assert _matching_box(target, [{**matching, "occurrence_index": 1}]) is None
