from app.api.routes.issues import _change_context


def test_change_context_prioritizes_indexation_over_cosmetic_changes() -> None:
    robots = _change_context("robots_changed")
    description = _change_context("description_changed")

    assert robots["importance"] == "high"
    assert "indexatie" in robots["relevance"]
    assert description["importance"] == "low"
    assert "indexatie-effect" in description["relevance"]


def test_unknown_change_gets_cautious_review_context() -> None:
    context = _change_context("future_change_type")

    assert context["importance"] == "low"
    assert "geen duidelijke SEO-impact" in context["relevance"]
