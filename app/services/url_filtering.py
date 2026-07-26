from fnmatch import fnmatchcase
from pathlib import PurePosixPath
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

MAX_QUERY_VARIANTS_PER_PATH = 100

NON_HTML_SUFFIXES = frozenset(
    {
        ".7z",
        ".avi",
        ".avif",
        ".bmp",
        ".css",
        ".doc",
        ".docx",
        ".eot",
        ".gif",
        ".gz",
        ".ico",
        ".jpeg",
        ".jpg",
        ".js",
        ".json",
        ".map",
        ".mov",
        ".mp3",
        ".mp4",
        ".mpeg",
        ".pdf",
        ".png",
        ".ppt",
        ".pptx",
        ".rar",
        ".svg",
        ".tar",
        ".tif",
        ".tiff",
        ".ttf",
        ".wav",
        ".webm",
        ".webp",
        ".woff",
        ".woff2",
        ".xls",
        ".xlsx",
        ".xml",
        ".zip",
    }
)

IMAGE_SUFFIXES = frozenset(
    {".avif", ".bmp", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".svg", ".tif", ".tiff", ".webp"}
)
DOCUMENT_SUFFIXES = frozenset({".doc", ".docx", ".pdf", ".ppt", ".pptx", ".xls", ".xlsx"})


def is_probable_html_page(url: str) -> bool:
    path = unquote(urlsplit(url).path).lower()
    return PurePosixPath(path).suffix not in NON_HTML_SUFFIXES


def is_excluded_url(url: str, patterns: list[str] | tuple[str, ...]) -> bool:
    """Match configured glob patterns against the full URL and path with query."""
    parts = urlsplit(url)
    path_and_query = urlunsplit(("", "", parts.path or "/", parts.query, ""))
    for raw_pattern in patterns:
        pattern = raw_pattern.strip()
        if pattern and (
            fnmatchcase(url, pattern)
            or fnmatchcase(path_and_query, pattern)
            or fnmatchcase(parts.path or "/", pattern)
        ):
            return True
    return False


def query_variant_group(url: str) -> tuple[str, str, str] | None:
    """Group parameter variants by host and path while leaving plain URLs unlimited."""
    parts = urlsplit(url)
    if not parse_qsl(parts.query, keep_blank_values=True):
        return None
    return (parts.scheme.lower(), parts.netloc.lower(), parts.path or "/")


def asset_kind(url: str) -> str | None:
    suffix = PurePosixPath(unquote(urlsplit(url).path).lower()).suffix
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in DOCUMENT_SUFFIXES:
        return "document"
    return None
