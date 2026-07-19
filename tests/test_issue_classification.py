from app.services.issue_classification import issue_scope


def test_issue_scope_separates_non_seo_control_signals() -> None:
    assert issue_scope("http_404") == "seo"
    assert issue_scope("broken_image") == "quality"
    assert issue_scope("multiple_h1") == "quality"
    assert issue_scope("deep_page") == "quality"
    assert issue_scope("oversized_image") == "performance"
    assert issue_scope("oversized_document") == "performance"
    assert issue_scope("possibly_outdated_content") == "editorial"
