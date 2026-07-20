from typing import Literal

IssueScope = Literal["seo", "seo_ux", "quality", "performance", "editorial"]
IssueNature = Literal["problem", "review", "optimization"]

ISSUE_SCOPE_BY_TYPE: dict[str, IssueScope] = {
    "broken_image": "quality",
    "deep_page": "quality",
    "job_posting_identifier_collision_risk": "quality",
    "multiple_h1": "quality",
    "oversized_document": "performance",
    "oversized_image": "performance",
    "possibly_outdated_content": "editorial",
}

ISSUE_NATURE_BY_TYPE: dict[str, IssueNature] = {
    "duplicate_meta_description": "optimization",
    "deep_page": "review",
    "http_410": "review",
    "important_page_few_internal_links": "review",
    "job_posting_identifier_collision_risk": "optimization",
    "missing_breadcrumb_schema": "optimization",
    "missing_h1": "review",
    "missing_meta_description": "optimization",
    "near_duplicate_content": "review",
    "pagination_series_review": "review",
    "robots_txt_blocked": "review",
    "thin_content": "review",
}


def issue_scope(issue_type: str) -> IssueScope:
    return ISSUE_SCOPE_BY_TYPE.get(issue_type, "seo")


def issue_nature(issue_type: str) -> IssueNature:
    return ISSUE_NATURE_BY_TYPE.get(issue_type, "problem")
