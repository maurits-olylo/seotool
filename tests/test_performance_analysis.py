from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.services.performance_analysis import (
    observation_from_pagespeed_response,
    select_performance_candidates,
)


def test_selects_bounded_risk_led_template_sample() -> None:
    important = _record("https://example.com/products/important", important=True)
    product_issue = _record("https://example.com/products/issue")
    article_change = _record("https://example.com/articles/change")
    unrelated = _record("https://example.com/about")

    selected = select_performance_candidates(
        [unrelated, product_issue, article_change, important],
        active_issue_url_ids={product_issue[0].id},
        changed_url_ids={article_change[0].id},
        limit=10,
    )

    assert [item.url.normalized_url for item in selected] == [
        "https://example.com/products/important",
        "https://example.com/articles/change",
        "https://example.com/products/issue",
    ]


def test_candidate_selection_never_exceeds_safety_cap() -> None:
    records = [
        _record(f"https://example.com/template-{index}/page", important=True)
        for index in range(20)
    ]

    assert len(select_performance_candidates(records, limit=100)) == 10
    assert select_performance_candidates(records, limit=0) == []


def test_normalizes_lighthouse_and_crux_evidence_without_full_response() -> None:
    observed = observation_from_pagespeed_response(
        website_id=uuid4(),
        url_id=uuid4(),
        requested_url="https://example.com/page",
        strategy="mobile",
        analyzed_at=datetime(2026, 8, 4, 10, tzinfo=UTC),
        payload={
            "lighthouseResult": {
                "finalDisplayedUrl": "https://example.com/page/",
                "lighthouseVersion": "13.0.0",
                "fetchTime": "2026-08-04T09:59:00Z",
                "categories": {
                    "performance": {"score": 0.72},
                    "accessibility": {"score": 0.95},
                },
                "audits": {
                    "largest-contentful-paint": {
                        "score": 0.4,
                        "numericValue": 3100,
                        "numericUnit": "millisecond",
                        "displayValue": "3.1 s",
                    },
                    "unused-javascript": {
                        "title": "Reduce unused JavaScript",
                        "score": 0.3,
                        "numericValue": 420,
                        "numericUnit": "millisecond",
                        "details": {
                            "items": [
                                {
                                    "url": "https://cdn.example.com/app.js",
                                    "wastedBytes": 120000,
                                    "debugData": "must not be persisted",
                                }
                            ]
                        },
                    },
                    "passed-audit": {"title": "Passed", "score": 1},
                },
            },
            "loadingExperience": {
                "id": "https://example.com/page/",
                "metrics": {
                    "LARGEST_CONTENTFUL_PAINT_MS": {
                        "percentile": 2800,
                        "category": "AVERAGE",
                    }
                },
                "collectionPeriod": {
                    "firstDate": {"year": 2026, "month": 7, "day": 8},
                    "lastDate": {"year": 2026, "month": 8, "day": 4},
                },
            },
        },
    )

    assert observed.category_scores == {"performance": 0.72, "accessibility": 0.95}
    assert observed.lab_metrics["largest-contentful-paint"]["numeric_value"] == 3100.0
    assert observed.field_metrics["LARGEST_CONTENTFUL_PAINT_MS"]["category"] == "AVERAGE"
    assert observed.collection_period_days == 28
    assert [audit["audit_id"] for audit in observed.failed_audits] == [
        "unused-javascript",
        "largest-contentful-paint",
    ]
    assert "debugData" not in observed.failed_audits[0]["items"][0]


def test_rejects_unknown_pagespeed_strategy() -> None:
    with pytest.raises(ValueError, match="mobile or desktop"):
        observation_from_pagespeed_response(
            website_id=uuid4(),
            url_id=uuid4(),
            requested_url="https://example.com/",
            strategy="tablet",
            payload={},
        )


def _record(url: str, *, important: bool = False) -> tuple[Url, UrlSnapshot]:
    return (
        Url(id=uuid4(), normalized_url=url, is_active=True, is_important=important),
        UrlSnapshot(
            status_code=200,
            content_type="text/html; charset=utf-8",
            redirect_chain=[],
        ),
    )
