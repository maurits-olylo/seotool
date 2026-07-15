import pytest

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
