from app.services.technical_checks import IssueSignal
from app.services.url_filtering import asset_kind

IMAGE_SIZE_LIMIT = 2_000_000
DOCUMENT_SIZE_LIMIT = 5_000_000
ASSET_ISSUE_TYPES = {"oversized_image", "oversized_document"}
HTML_ONLY_ISSUE_TYPES = {
    "canonical_other_url",
    "conflicting_robots",
    "expired_job_posting",
    "job_posting_missing_fields",
    "job_posting_invalid_dates",
    "job_posting_missing_application",
    "job_posting_remote_location_missing",
    "job_posting_location_incomplete",
    "job_posting_not_detail_page",
    "job_posting_missing_recommended_fields",
    "missing_h1",
    "missing_meta_description",
    "missing_title",
    "multiple_h1",
    "thin_content",
    "unexpected_noindex",
}


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
