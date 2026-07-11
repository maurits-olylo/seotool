import pytest

from app.services.url_filtering import is_probable_html_page


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/file.pdf",
        "https://example.com/photo.JPG?download=1",
        "https://example.com/archive%20file.zip",
        "https://example.com/assets/app.js?v=1",
    ],
)
def test_rejects_non_html_asset_urls(url: str) -> None:
    assert is_probable_html_page(url) is False


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "https://example.com/page",
        "https://example.com/page.html",
        "https://example.com/index.php?id=1",
    ],
)
def test_accepts_html_page_urls(url: str) -> None:
    assert is_probable_html_page(url) is True
