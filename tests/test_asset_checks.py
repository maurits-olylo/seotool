from app.services.asset_checks import inspect_asset


def test_size_findings_are_grouped_after_the_site_crawl() -> None:
    assert inspect_asset("https://example.com/photo.jpg", 5_500_000) == []
    assert inspect_asset("https://example.com/old.pdf", 7_500_000) == []


def test_recognizes_extensionless_document_by_content_type() -> None:
    signals = inspect_asset(
        "https://example.com/download",
        7_500_000,
        content_type="application/pdf",
    )

    assert signals == []


def test_accepts_small_or_unknown_assets() -> None:
    assert inspect_asset("https://example.com/photo.webp", 500_000) == []
    assert inspect_asset("https://example.com/file.pdf", None) == []


def test_flags_broken_image() -> None:
    signals = inspect_asset("https://example.com/missing.jpg", 100, 404)
    assert [signal.issue_type for signal in signals] == ["broken_image"]
    assert signals[0].evidence["status_code"] == 404
