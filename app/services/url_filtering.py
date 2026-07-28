from fnmatch import fnmatchcase
from pathlib import PurePosixPath
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

MAX_QUERY_VARIANTS_PER_PATH = 100

NON_HTML_SUFFIXES = frozenset(
    {
        ".7z",
        ".3g2",
        ".3gp",
        ".aac",
        ".avi",
        ".avif",
        ".bmp",
        ".css",
        ".doc",
        ".docx",
        ".eot",
        ".flac",
        ".gif",
        ".gz",
        ".ico",
        ".jpeg",
        ".jpg",
        ".js",
        ".json",
        ".map",
        ".mov",
        ".m4a",
        ".m4v",
        ".mkv",
        ".mp3",
        ".mp4",
        ".mpeg",
        ".oga",
        ".ogg",
        ".ogv",
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


def asset_kind(url: str, content_type: str | None = None) -> str | None:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type.startswith("image/"):
        return "image"
    if media_type in {
        "application/pdf",
        "application/msword",
        "application/vnd.ms-excel",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }:
        return "document"
    if media_type.startswith("video/"):
        return "video"
    if media_type.startswith("audio/"):
        return "audio"
    suffix = PurePosixPath(unquote(urlsplit(url).path).lower()).suffix
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in DOCUMENT_SUFFIXES:
        return "document"
    if suffix in {".3g2", ".3gp", ".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".ogv", ".webm"}:
        return "video"
    if suffix in {".aac", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".wav"}:
        return "audio"
    return None
