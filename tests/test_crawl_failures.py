from app.api.routes.crawls import _failure_guidance


def test_current_redirect_loop_requires_action() -> None:
    assessment, explanation, action = _failure_guidance(
        "Redirect loop detected",
        source_types=["internal_link"],
        incoming_links=2,
    )

    assert assessment == "action_required"
    assert "geen eindpagina" in explanation
    assert "redirectregels" in action


def test_historical_failure_is_informational() -> None:
    assessment, explanation, action = _failure_guidance(
        "Hostname could not be resolved",
        source_types=["known"],
        incoming_links=0,
    )

    assert assessment == "informational"
    assert "historisch bekend" in explanation
    assert "Geen directe actie" in action


def test_current_timeout_should_be_retried() -> None:
    assessment, explanation, action = _failure_guidance(
        "Request timed out",
        source_types=["sitemap"],
        incoming_links=0,
    )

    assert assessment == "retry"
    assert "tijdelijk" in explanation
    assert "Probeer" in action
