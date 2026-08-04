from app.services.robots import RobotsRules


def test_robots_rules_and_sitemaps() -> None:
    rules = RobotsRules(
        "User-agent: *\nDisallow: /private\nAllow: /\nSitemap: https://example.com/sitemap.xml",
        "https://example.com/robots.txt",
    )
    assert rules.allows("https://example.com/public")
    assert not rules.allows("https://example.com/private/page")
    assert rules.sitemaps() == ("https://example.com/sitemap.xml",)


def test_robots_keeps_duplicate_sitemap_declarations_for_quality_analysis() -> None:
    rules = RobotsRules(
        "Sitemap: https://example.com/sitemap.xml\nSitemap: https://example.com/sitemap.xml",
        "https://example.com/robots.txt",
    )

    assert rules.sitemaps() == (
        "https://example.com/sitemap.xml",
        "https://example.com/sitemap.xml",
    )
