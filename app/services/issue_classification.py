from typing import Literal

IssueScope = Literal["seo", "seo_ux", "quality", "performance", "editorial"]

ISSUE_SCOPE_BY_TYPE: dict[str, IssueScope] = {
    "broken_image": "quality",
    "deep_page": "quality",
    "multiple_h1": "quality",
    "oversized_document": "performance",
    "oversized_image": "performance",
    "possibly_outdated_content": "editorial",
}


def issue_scope(issue_type: str) -> IssueScope:
    return ISSUE_SCOPE_BY_TYPE.get(issue_type, "seo")
