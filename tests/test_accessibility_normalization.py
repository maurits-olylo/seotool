from app.services.accessibility.normalization import (
    accessibility_issue_signals,
    normalize_axe_result,
)


def test_normalizes_only_pilot_rules_and_bounds_node_evidence() -> None:
    result = normalize_axe_result(
        {
            "testEngine": {"version": "4.12.1"},
            "violations": [
                {
                    "id": "button-name",
                    "impact": "critical",
                    "help": "Buttons must have discernible text",
                    "helpUrl": "https://example.test/button-name",
                    "tags": ["wcag2a", "wcag412"],
                    "nodes": [
                        {
                            "target": [f"#button-{number}"],
                            "html": "<button></button>",
                            "failureSummary": "Fix the button",
                        }
                        for number in range(12)
                    ],
                },
                {"id": "color-contrast", "impact": "serious", "nodes": [{}]},
            ],
            "incomplete": [{"id": "label", "impact": "serious", "nodes": [{}]}],
        }
    )

    violations = result["violations"]
    assert isinstance(violations, list)
    assert len(violations) == 1
    assert violations[0]["node_count"] == 12
    assert len(violations[0]["nodes"]) == 10
    assert len(result["incomplete"]) == 1


def test_creates_issues_only_for_certain_violations() -> None:
    evidence = normalize_axe_result(
        {
            "violations": [
                {"id": "button-name", "impact": "critical", "nodes": [{"target": ["#buy"]}]}
            ],
            "incomplete": [
                {"id": "label", "impact": "serious", "nodes": [{"target": ["#email"]}]}
            ],
        }
    )

    signals = accessibility_issue_signals(evidence)

    assert [signal.issue_type for signal in signals] == ["accessibility_button_name"]
    assert signals[0].category == "accessibility"
    assert signals[0].severity == "high"
    assert signals[0].evidence["accessibility"]["node_count"] == 1
    assert signals[0].evidence["accessibility"]["component_signature"].startswith(
        "axe:button-name:"
    )
