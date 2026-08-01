from pydantic import AnyHttpUrl, BaseModel


class PublicWebsiteEstimateRequest(BaseModel):
    url: AnyHttpUrl


class PublicWebsiteEstimateRead(BaseModel):
    normalized_url: str
    estimated_pages: int
    package: str
    method: str
    confidence: str
    sitemap_documents: int
    capped: bool
    explanation: str
