from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

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


def asset_kind(url: str) -> str | None:
    suffix = PurePosixPath(unquote(urlsplit(url).path).lower()).suffix
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in DOCUMENT_SUFFIXES:
        return "document"
    return None
