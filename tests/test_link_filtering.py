from app.services.link_filtering import is_non_navigational_link_target


def test_recognizes_cloudflare_email_protection_and_cms_placeholders() -> None:
    assert is_non_navigational_link_target(
        "https://example.com/cdn-cgi/l/email-protection"
    )
    assert is_non_navigational_link_target(
        "https://example.com/articles/${link:{uuid:{value}}}"
    )
    assert is_non_navigational_link_target(
        "https://example.com/articles/%24%7Blink.url%7D"
    )
    assert not is_non_navigational_link_target("https://example.com/contact")
