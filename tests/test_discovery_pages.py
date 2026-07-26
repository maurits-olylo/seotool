from app.services.discovery_pages import is_discovery_only_page


def test_query_variant_canonicalized_to_same_base_is_discovery_only() -> None:
    assert is_discovery_only_page(
        "https://example.com/jobs?filter=seo&page=2",
        "https://example.com/jobs",
    )


def test_query_variant_with_own_or_different_canonical_is_regular_page() -> None:
    assert not is_discovery_only_page(
        "https://example.com/jobs?filter=seo",
        "https://example.com/jobs?filter=seo",
    )
    assert not is_discovery_only_page(
        "https://example.com/jobs?filter=seo",
        "https://example.com/careers",
    )
    assert not is_discovery_only_page(
        "https://example.com/jobs",
        "https://example.com/jobs",
    )
