from app.services.technical_checks import IssueSignal
from app.services.url_filtering import asset_kind

IMAGE_SIZE_LIMIT = 2_000_000
DOCUMENT_SIZE_LIMIT = 5_000_000
ASSET_ISSUE_TYPES = {"oversized_image", "oversized_document", "broken_image"}
HTML_ONLY_ISSUE_TYPES = {
    "canonical_other_url",
    "conflicting_robots",
    "expired_job_posting",
    "job_posting_schema_missing",
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


def inspect_asset(
    url: str,
    response_size: int | None,
    status_code: int | None = 200,
    *,
    content_type: str | None = None,
) -> list[IssueSignal]:
    kind = asset_kind(url, content_type)
    if kind == "image" and status_code is not None and status_code >= 400:
        return [
            IssueSignal(
                issue_type="broken_image",
                category="content",
                severity="medium",
                title="Afbeelding kan niet worden geladen",
                description=f"De afbeeldings-URL geeft HTTP-status {status_code}.",
                recommended_action="Herstel het afbeeldingsbestand of vervang de bron-URL.",
                evidence={"status_code": status_code},
            )
        ]
    return []
