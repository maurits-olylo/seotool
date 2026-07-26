from app.services.issue_classification import issue_nature, issue_scope


def test_issue_scope_separates_non_seo_control_signals() -> None:
    assert issue_scope("http_404") == "seo"
    assert issue_scope("broken_image") == "quality"
    assert issue_scope("multiple_h1") == "quality"
    assert issue_scope("deep_page") == "quality"
    assert issue_scope("job_posting_identifier_collision_risk") == "quality"
    assert issue_scope("image_alt_missing") == "quality"
    assert issue_scope("functional_image_alt_empty") == "quality"
    assert issue_scope("image_alt_missing_clusters") == "quality"
    assert issue_scope("oversized_image") == "performance"
    assert issue_scope("oversized_document") == "performance"
    assert issue_scope("possibly_outdated_content") == "editorial"


def test_issue_nature_marks_contextual_and_optional_signals() -> None:
    assert issue_nature("deep_page") == "review"
    assert issue_nature("template_signal_clusters") == "review"
    assert issue_nature("deep_page_clusters") == "review"
    assert issue_scope("deep_page_clusters") == "quality"
    assert issue_nature("internal_redirect_patterns") == "review"
    assert issue_nature("server_error_incident") == "review"
    assert issue_nature("sitemap_redirect_patterns") == "review"
    assert issue_nature("http_404") == "problem"
    assert issue_nature("http_410") == "review"
    assert issue_nature("near_duplicate_content") == "review"
    assert issue_nature("thin_content") == "review"
    assert issue_nature("robots_txt_blocked") == "review"
    assert issue_nature("important_page_few_internal_links") == "review"
    assert issue_nature("job_posting_identifier_collision_risk") == "optimization"
    assert issue_nature("missing_h1") == "review"
    assert issue_nature("duplicate_meta_description") == "optimization"
    assert issue_nature("missing_meta_description") == "optimization"
    assert issue_nature("missing_breadcrumb_schema") == "optimization"
