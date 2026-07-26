import pytest

from app.services.url_filtering import is_excluded_url, query_variant_group
from app.services.url_normalization import InvalidUrlError, NormalizationOptions, normalize_url


def test_normalizes_url_and_tracking_parameters() -> None:
    assert normalize_url("HTTPS://Example.COM:443//a///b/?utm_source=x&b=2&a=1#top") == (
        "https://example.com/a/b?a=1&b=2"
    )


def test_custom_ignored_parameter_and_relative_url() -> None:
    options = NormalizationOptions(ignored_query_parameters=frozenset({"session"}))
    assert (
        normalize_url(
            "../contact/?session=x", base_url="https://example.com/nl/page", options=options
        )
        == "https://example.com/contact"
    )


def test_rejects_unsupported_protocol() -> None:
    with pytest.raises(InvalidUrlError):
        normalize_url("file:///etc/passwd")


def test_rejects_invalid_ipv6_syntax_as_normalization_error() -> None:
    with pytest.raises(InvalidUrlError, match="syntax"):
        normalize_url("https://[invalid/path")


def test_matches_excluded_url_globs_against_url_path_and_query() -> None:
    url = "https://example.com/search?filter=jobs&page=2"
    assert is_excluded_url(url, ["*/search?filter=*"])
    assert is_excluded_url(url, ["/search*"])
    assert not is_excluded_url(url, ["/vacatures/*"])


def test_groups_query_variants_by_origin_and_path() -> None:
    assert query_variant_group("https://example.com/jobs?f=1&page=2") == (
        "https",
        "example.com",
        "/jobs",
    )
    assert query_variant_group("https://example.com/jobs") is None
