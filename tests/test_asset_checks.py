from app.services.asset_checks import inspect_asset


def test_flags_oversized_image() -> None:
    signals = inspect_asset("https://example.com/photo.jpg", 5_500_000)
    assert [signal.issue_type for signal in signals] == ["oversized_image"]
    assert signals[0].evidence["response_size"] == 5_500_000


def test_flags_oversized_document() -> None:
    signals = inspect_asset("https://example.com/old.pdf", 7_500_000)
    assert [signal.issue_type for signal in signals] == ["oversized_document"]


def test_accepts_small_or_unknown_assets() -> None:
    assert inspect_asset("https://example.com/photo.webp", 500_000) == []
    assert inspect_asset("https://example.com/file.pdf", None) == []
