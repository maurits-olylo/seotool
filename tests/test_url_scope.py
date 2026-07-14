from app.services.url_scope import is_url_in_website_scope


def test_website_scope_excludes_other_connected_domain() -> None:
    assert is_url_in_website_scope(
        "https://www.pearle.nl/vacatures",
        base_url="https://www.pearle.nl/",
    )
    assert not is_url_in_website_scope(
        "https://jobsatpearle.be/vacatures",
        base_url="https://www.pearle.nl/",
    )


def test_website_scope_supports_explicit_hosts_and_wildcards() -> None:
    assert is_url_in_website_scope(
        "https://example.nl/contact",
        base_url="https://www.example.nl/",
    )
    assert is_url_in_website_scope(
        "https://jobs.example.nl/vacature",
        base_url="https://www.example.nl/",
        allowed_subdomains=["jobs.example.nl"],
    )
    assert is_url_in_website_scope(
        "https://campaign.example.nl/actie",
        base_url="https://www.example.nl/",
        allowed_subdomains=["*.example.nl"],
    )
