from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

NON_HTML_SUFFIXES = frozenset(
    {
        ".7z", ".avi", ".avif", ".bmp", ".css", ".doc", ".docx", ".eot",
        ".gif", ".gz", ".ico", ".jpeg", ".jpg", ".js", ".json", ".map",
        ".mov", ".mp3", ".mp4", ".mpeg", ".pdf", ".png", ".ppt", ".pptx",
        ".rar", ".svg", ".tar", ".tif", ".tiff", ".ttf", ".wav", ".webm",
        ".webp", ".woff", ".woff2", ".xls", ".xlsx", ".xml", ".zip",
    }
)


def is_probable_html_page(url: str) -> bool:
    path = unquote(urlsplit(url).path).lower()
    return PurePosixPath(path).suffix not in NON_HTML_SUFFIXES
