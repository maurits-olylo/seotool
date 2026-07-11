from app.services.technical_checks import IssueSignal
from app.services.url_filtering import asset_kind

IMAGE_SIZE_LIMIT = 2_000_000
DOCUMENT_SIZE_LIMIT = 5_000_000
ASSET_ISSUE_TYPES = {"oversized_image", "oversized_document"}


def inspect_asset(url: str, response_size: int | None) -> list[IssueSignal]:
    if response_size is None:
        return []
    kind = asset_kind(url)
    if kind == "image" and response_size > IMAGE_SIZE_LIMIT:
        return [_oversized_signal("image", response_size, IMAGE_SIZE_LIMIT)]
    if kind == "document" and response_size > DOCUMENT_SIZE_LIMIT:
        return [_oversized_signal("document", response_size, DOCUMENT_SIZE_LIMIT)]
    return []


def _oversized_signal(kind: str, size: int, limit: int) -> IssueSignal:
    label = "Afbeelding" if kind == "image" else "Document"
    return IssueSignal(
        issue_type=f"oversized_{kind}",
        category="performance",
        severity="medium",
        title=f"{label} is te groot",
        description=f"{label} is {size / 1_000_000:.1f} MB en overschrijdt de limiet.",
        recommended_action="Comprimeer of vervang het bestand en werk verwijzende links bij.",
        evidence={"response_size": size, "limit": limit},
    )
