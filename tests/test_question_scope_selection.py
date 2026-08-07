from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.integrations import SearchConsoleQueryMetric
from app.models.website import Website
from app.services.question_scope_selection import select_question_scopes, url_family


def add_site(db):  # type: ignore[no-untyped-def]
    client = Client(name="Question scope client")
    website = Website(
        client=client,
        name="Question scope shop",
        base_url="https://shop.example.com",
    )
    db.add(website)
    db.flush()
    return website


def add_url(
    db,  # type: ignore[no-untyped-def]
    website: Website,
    path: str,
    *,
    page_type: str | None = None,
    important: bool = False,
    indexable: bool = True,
) -> Url:
    url = Url(
        website_id=website.id,
        normalized_url=f"https://shop.example.com{path}",
        current_status_code=200,
        is_active=True,
        is_indexable=indexable,
        is_important=important,
        page_type=page_type,
    )
    db.add(url)
    db.flush()
    return url


def add_query(
    db,  # type: ignore[no-untyped-def]
    website: Website,
    url: Url,
    query: str,
    *,
    impressions: int,
    clicks: float = 0,
    position: float = 8,
) -> None:
    db.add(
        SearchConsoleQueryMetric(
            website_id=website.id,
            url_id=url.id,
            date=date(2026, 8, 1),
            query=query,
            page_url=url.normalized_url,
            impressions=impressions,
            clicks=clicks,
            position=position,
        )
    )


def select(db, website: Website, **limits):  # type: ignore[no-untyped-def]
    return select_question_scopes(
        db,
        website_id=website.id,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        **limits,
    )


def test_shop_selection_caps_pages_per_family() -> None:
    with SessionLocal() as db:
        website = add_site(db)
        for index in range(8):
            product = add_url(db, website, f"/producten/product-{index}", page_type="product")
            add_query(
                db,
                website,
                product,
                f"wat kost product {index}",
                impressions=300 - index * 10,
            )
        for index in range(3):
            category = add_url(
                db,
                website,
                f"/categorie/categorie-{index}",
                page_type="category",
                important=index == 2,
            )
            add_query(
                db,
                website,
                category,
                f"welke producten passen bij categorie {index}",
                impressions=100 + index,
            )
        db.commit()

        result = select(db, website, max_pages=10, max_pages_per_family=2)

    families = [candidate.family for candidate in result.candidates]
    assert families.count("page_type:product") == 2
    assert families.count("page_type:category") == 2
    assert result.eligible_pages == 11
    assert result.selected_pages == 4
    assert result.selected_families == 2


def test_selection_caps_questions_per_page_and_total() -> None:
    with SessionLocal() as db:
        website = add_site(db)
        page = add_url(db, website, "/advies/kozijnen", page_type="guide")
        for index, question in enumerate(
            (
                "wat kosten kunststof kozijnen",
                "hoe lang gaan kunststof kozijnen mee",
                "welke kozijnen isoleren het beste",
                "kan ik kunststof kozijnen schilderen",
            )
        ):
            add_query(db, website, page, question, impressions=200 - index * 10)
        db.commit()

        result = select(db, website, max_questions_per_page=2, max_total=2)

    assert len(result.candidates) == 2
    assert result.eligible_questions == 4
    assert {item.question for item in result.candidates} == {
        "wat kosten kunststof kozijnen",
        "hoe lang gaan kunststof kozijnen mee",
    }


def test_first_party_importance_is_an_explainable_priority_contributor() -> None:
    with SessionLocal() as db:
        website = add_site(db)
        normal = add_url(db, website, "/advies/normaal", page_type="guide")
        important = add_url(
            db,
            website,
            "/advies/belangrijk",
            page_type="guide",
            important=True,
        )
        add_query(db, website, normal, "wat kost normaal advies", impressions=100)
        add_query(db, website, important, "wat kost belangrijk advies", impressions=100)
        db.commit()

        result = select(db, website, max_pages_per_family=2)

    assert result.candidates[0].url_id == important.id
    contributor = next(
        item for item in result.candidates[0].contributors if item["signal"] == "important_page"
    )
    assert contributor == {"signal": "important_page", "value": True, "points": 15.0}


def test_non_questions_and_non_indexable_pages_are_excluded() -> None:
    with SessionLocal() as db:
        website = add_site(db)
        page = add_url(db, website, "/producten/stoel", page_type="product")
        hidden = add_url(
            db,
            website,
            "/producten/verborgen",
            page_type="product",
            indexable=False,
        )
        add_query(db, website, page, "rode stoel", impressions=500)
        add_query(db, website, page, "wat kost een rode stoel", impressions=100)
        add_query(db, website, hidden, "wat kost de verborgen stoel", impressions=1_000)
        db.commit()

        result = select(db, website)

    assert [item.question for item in result.candidates] == ["wat kost een rode stoel"]


def test_url_family_falls_back_to_path_shape() -> None:
    url = Url(normalized_url="https://shop.example.com/producten/12345", page_type=None)

    assert url_family(url) == "path:producten:depth-2"


def test_invalid_limits_are_rejected() -> None:
    with SessionLocal() as db:
        website = add_site(db)

        with pytest.raises(ValueError, match="must be positive"):
            select(db, website, max_total=0)


def test_read_only_api_exposes_bounded_selection(client: TestClient) -> None:
    with SessionLocal() as db:
        website = add_site(db)
        page = add_url(db, website, "/advies/kozijnen", page_type="guide")
        add_query(db, website, page, "wat kosten kunststof kozijnen", impressions=100)
        db.commit()
        website_id = website.id

    response = client.get(
        f"/api/v1/websites/{website_id}/content-analysis/question-scopes",
        params={
            "period_start": "2026-08-01",
            "period_end": "2026-08-31",
            "max_total": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["selected_pages"] == 1
    assert response.json()["candidates"][0]["question"] == "wat kosten kunststof kozijnen"


def test_read_only_api_rejects_unbounded_limits(client: TestClient) -> None:
    with SessionLocal() as db:
        website = add_site(db)
        db.commit()
        website_id = website.id

    response = client.get(
        f"/api/v1/websites/{website_id}/content-analysis/question-scopes",
        params={
            "period_start": "2026-08-01",
            "period_end": "2026-08-31",
            "max_total": 501,
        },
    )

    assert response.status_code == 422
