from app.models.issues import Issue
from app.services.issue_guidance import build_issue_guidance


def _issue(issue_type: str, category: str = "onpage", confidence: str = "high") -> Issue:
    return Issue(
        website_id=None,  # type: ignore[arg-type]
        issue_type=issue_type,
        category=category,
        severity="medium",
        confidence=confidence,
        title="Testissue",
        description="Testbeschrijving",
        recommended_action="Pas het betreffende onderdeel aan.",
    )


def test_guidance_uses_stored_diagnosis_without_presenting_it_as_fact() -> None:
    guidance = build_issue_guidance(
        _issue("patterned_404_urls", "internal_links", "medium"),
        {
            "likely_cause": "Het template genereert waarschijnlijk lege paginering.",
            "alternative_explanation": (
                "Verouderde handmatige links kunnen hetzelfde patroon geven."
            ),
            "verification": "geen URL uit het patroon geeft nog een 404",
        },
    )

    assert guidance["likely_cause"] == {
        "text": "Het template genereert waarschijnlijk lege paginering.",
        "basis": "interpretation",
    }
    assert guidance["alternative_explanation"]["basis"] == "hypothesis"  # type: ignore[index]
    assert guidance["verification"] == "geen URL uit het patroon geeft nog een 404"
    assert guidance["confidence"] == "medium"


def test_guidance_falls_back_to_observation_and_safe_verification() -> None:
    guidance = build_issue_guidance(_issue("missing_title"), {})

    assert guidance["likely_cause"] is None
    assert guidance["alternative_explanation"] is None
    assert guidance["steps"] == ["Pas het betreffende onderdeel aan."]
    assert "volgende crawl" in str(guidance["verification"])
    assert guidance["sources"] == [
        {
            "title": "Title links beïnvloeden",
            "url": "https://developers.google.com/search/docs/appearance/title-link",
            "publisher": "Google Search Central",
        }
    ]


def test_guidance_adds_specific_value_and_source_for_job_schema() -> None:
    job_guidance = build_issue_guidance(
        _issue("job_posting_schema_missing", "structured_data"), {}
    )
    assert "Google" in job_guidance["relevance"]["text"]  # type: ignore[index]
    assert job_guidance["sources"][0]["publisher"] == "Google Search Central"  # type: ignore[index]


def test_pagination_guidance_treats_repeated_signals_as_one_template_review() -> None:
    guidance = build_issue_guidance(
        _issue("pagination_series_review", "indexation"),
        {"verification": "geen lege grenspagina's"},
    )

    assert "één technisch geheel" in guidance["relevance"]["text"]  # type: ignore[index]
    assert guidance["verification"] == "geen lege grenspagina's"
    assert {source["publisher"] for source in guidance["sources"]} == {
        "Google Search Central"
    }


def test_grouped_redirect_guidance_focuses_on_the_source_page() -> None:
    guidance = build_issue_guidance(
        _issue("multiple_redirected_internal_links", "internal_links"), {}
    )

    assert "één onderhoudstaak" in guidance["relevance"]["text"]  # type: ignore[index]
    assert "bronpagina" in str(guidance["verification"])


def test_template_cluster_guidance_focuses_on_one_shared_review() -> None:
    guidance = build_issue_guidance(
        _issue("template_signal_clusters"),
        {"verification": "het signaal verdwijnt uit de URL-familie"},
    )

    assert "template" in guidance["relevance"]["text"]  # type: ignore[index]
    assert guidance["verification"] == "het signaal verdwijnt uit de URL-familie"
    assert guidance["sources"]


def test_deep_page_guidance_explains_the_contextual_threshold() -> None:
    guidance = build_issue_guidance(_issue("deep_page", "internal_links"), {})

    assert "alleen relevant" in guidance["relevance"]["text"]  # type: ignore[index]
