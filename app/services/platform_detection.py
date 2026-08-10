import re
from dataclasses import dataclass

from app.services.http_crawler import FetchResult


@dataclass(frozen=True)
class PlatformDetection:
    platform: str | None
    confidence: str | None


PLATFORM_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("wordpress", (r"wp-content/", r"wp-includes/", r'name=["\']generator["\'][^>]+wordpress')),
    ("shopify", (r"cdn\.shopify\.com", r"shopify\.theme", r"shopify-section")),
    ("webflow", (r"data-wf-page=", r"website-files\.com", r"webflow\.js")),
    ("wix", (r"wixstatic\.com", r"x-wix-", r"wix-code-sdk")),
    ("squarespace", (r"static1\.squarespace\.com", r"squarespace-cdn\.com", r"squarespace\.com")),
)


def detect_platform(result: FetchResult) -> PlatformDetection:
    html = result.content.decode("utf-8", errors="ignore").lower()
    headers = "\n".join(f"{key}:{value}" for key, value in result.headers.items()).lower()
    source = f"{headers}\n{html}"
    matches = [
        (platform, sum(bool(re.search(pattern, source, re.I)) for pattern in patterns))
        for platform, patterns in PLATFORM_SIGNALS
    ]
    platform, count = max(matches, key=lambda item: item[1])
    if count == 0:
        return PlatformDetection(platform=None, confidence=None)
    return PlatformDetection(platform=platform, confidence="high" if count >= 2 else "medium")
