from app.services.question_coverage import assess_question_coverage


def assess(content: str, *, headings: dict[str, list[str]] | None = None):  # type: ignore[no-untyped-def]
    return assess_question_coverage(
        "wat kosten kunststof kozijnen",
        title="Kunststof kozijnen",
        headings=headings or {"h1": ["Kunststof kozijnen"]},
        meta_description=None,
        main_content=content,
    )


def test_marks_direct_substantial_answer_as_answered() -> None:
    result = assess(
        "Wat kosten kunststof kozijnen? De prijs hangt af van formaat, glas en montage.",
        headings={"h1": ["Kunststof kozijnen"], "h2": ["Wat kosten kunststof kozijnen?"]},
    )

    assert result.status == "answered"
    assert result.confidence == "high"
    assert result.passage_coverage == 1
    assert result.best_passage == "Wat kosten kunststof kozijnen?"


def test_marks_related_page_without_price_answer_as_missing() -> None:
    result = assess(
        "Kunststof kozijnen isoleren goed en zijn verkrijgbaar in verschillende kleuren."
    )

    assert result.status == "missing"
    assert result.confidence == "high"
    assert result.intent == "price"
    assert "prijsopbouw" in result.recommended_action


def test_marks_scattered_answer_as_implicit() -> None:
    result = assess(
        "Wij leveren kunststof kozijnen. Elke situatie is anders. "
        "Een exacte prijs volgt na het inmeten."
    )

    assert result.status == "implicit"
    assert result.confidence == "medium"
    assert "Maak het bestaande antwoord expliciet" in result.recommended_action


def test_marks_short_incomplete_answer_as_partial() -> None:
    result = assess(
        "Kunststof kozijnen kosten geld. Bekijk ook onze uitgebreide uitleg over isolatie."
    )

    assert result.status == "partial"
    assert result.confidence == "low"
    assert result.subject_coverage == 1


def test_normalizes_accents_and_simple_plural_forms() -> None:
    result = assess_question_coverage(
        "Welke cafés zijn geschikt voor gezinnen?",
        title="Cafés voor gezinnen",
        headings={"h2": ["Geschikt voor gezinnen"]},
        meta_description=None,
        main_content="Deze cafés zijn geschikt voor gezinnen met jonge kinderen en kinderwagens.",
    )

    assert result.status == "answered"
