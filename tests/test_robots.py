from app.services.robots import RobotsRules


def test_robots_rules_and_sitemaps() -> None:
    rules = RobotsRules(
        "User-agent: *\nDisallow: /private\nAllow: /\nSitemap: https://example.com/sitemap.xml",
        "https://example.com/robots.txt",
    )
    assert rules.allows("https://example.com/public")
    assert not rules.allows("https://example.com/private/page")
    assert rules.sitemaps() == ("https://example.com/sitemap.xml",)
