from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import ElementLocation, UrlLink, UrlSnapshot
from app.models.discovery import Url
from app.models.issues import Issue
from app.services.asset_checks import DOCUMENT_SIZE_LIMIT, IMAGE_SIZE_LIMIT
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal
from app.services.url_filtering import asset_kind

DOCUMENT_INVENTORY_ISSUE_TYPE = "downloadable_document_inventory"
IMAGE_DELIVERY_ISSUE_TYPE = "image_delivery_quality"
MEDIA_DELIVERY_ISSUE_TYPE = "media_delivery_quality"
VIDEO_SIZE_LIMIT = 25_000_000
AUDIO_SIZE_LIMIT = 10_000_000
RESPONSIVE_IMAGE_REVIEW_MINIMUM = 200_000


def analyze_asset_quality(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
    snapshots = list(
        db.execute(
            select(Url, UrlSnapshot)
            .join(UrlSnapshot, UrlSnapshot.url_id == Url.id)
            .where(
                Url.website_id == website_id,
                UrlSnapshot.crawl_run_id == crawl_run_id,
                UrlSnapshot.status_code == 200,
            )
            .order_by(Url.normalized_url)
        )
    )
    source_urls = _source_urls_by_target(db, crawl_run_id=crawl_run_id)
    elements = _elements_by_target(db, crawl_run_id=crawl_run_id)
    touched: list[Issue] = []
    touched.extend(
        _reconcile_documents(
            db,
            website_id=website_id,
            crawl_run_id=crawl_run_id,
            snapshots=snapshots,
            source_urls=source_urls,
        )
    )
    touched.extend(
        _reconcile_images(
            db,
            website_id=website_id,
            crawl_run_id=crawl_run_id,
            snapshots=snapshots,
            elements=elements,
        )
    )
    touched.extend(
        _reconcile_media(
            db,
            website_id=website_id,
            crawl_run_id=crawl_run_id,
            snapshots=snapshots,
            elements=elements,
        )
    )
    db.commit()
    return touched


def _reconcile_documents(
    db: Session,
    *,
    website_id: object,
    crawl_run_id: object,
    snapshots: list[tuple[Url, UrlSnapshot]],
    source_urls: dict[object, list[dict[str, str]]],
) -> list[Issue]:
    documents: list[dict[str, object]] = []
    for url, snapshot in snapshots:
        if asset_kind(url.normalized_url, snapshot.content_type) != "document":
            continue
        references = source_urls.get(url.id, [])
        documents.append(
            {
                "url": url.normalized_url,
                "content_type": snapshot.content_type,
                "response_size": snapshot.response_size,
                "response_size_mb": _megabytes(snapshot.response_size),
                "is_oversized": (snapshot.response_size or 0) > DOCUMENT_SIZE_LIMIT,
                "is_indexable": snapshot.is_indexable,
                "source_urls": sorted({item["source_url"] for item in references}),
                "anchor_texts": sorted(
                    {item["anchor_text"] for item in references if item["anchor_text"]}
                ),
            }
        )
    source_pages = sorted(
        {
            source_url
            for document in documents
            for source_url in document["source_urls"]  # type: ignore[union-attr]
        }
    )
    signals = (
        [
            IssueSignal(
                issue_type=DOCUMENT_INVENTORY_ISSUE_TYPE,
                category="content",
                severity="low",
                confidence="high",
                title=f"{len(documents)} downloadbare documenten vragen beoordeling",
                description=(
                    "Downloadbare documenten zijn geldig, maar belangrijke informatie is in "
                    "HTML doorgaans beter vindbaar, bruikbaar op mobiel en onderhoudbaar."
                ),
                recommended_action=(
                    "Bied kerninformatie ook als toegankelijke HTML aan, vermeld bestandstype "
                    "en grootte bij de link, comprimeer grote bestanden en overweeg noindex "
                    "wanneer de HTML-versie in zoekresultaten moet verschijnen."
                ),
                evidence={
                    "document_count": len(documents),
                    "oversized_document_count": sum(
                        bool(document["is_oversized"]) for document in documents
                    ),
                    "source_page_count": len(source_pages),
                    "source_urls": source_pages[:200],
                    "documents": documents[:500],
                },
            )
        ]
        if documents
        else []
    )
    return reconcile_issues(
        db,
        website_id=website_id,
        url_id=None,
        crawl_run_id=crawl_run_id,
        snapshot_id=None,
        signals=signals,
        checked_issue_types={DOCUMENT_INVENTORY_ISSUE_TYPE},
    )


def _reconcile_images(
    db: Session,
    *,
    website_id: object,
    crawl_run_id: object,
    snapshots: list[tuple[Url, UrlSnapshot]],
    elements: dict[str, list[ElementLocation]],
) -> list[Issue]:
    findings: list[dict[str, object]] = []
    for url, snapshot in snapshots:
        if asset_kind(url.normalized_url, snapshot.content_type) != "image":
            continue
        locations = elements.get(url.normalized_url, [])
        issue_types = {
            issue_type
            for location in locations
            for issue_type in location.issue_types
        }
        oversized = (snapshot.response_size or 0) > IMAGE_SIZE_LIMIT
        missing_dimensions = "image_dimensions_missing" in issue_types
        missing_responsive_source = (
            "image_responsive_source_missing" in issue_types
            and (snapshot.response_size or 0) >= RESPONSIVE_IMAGE_REVIEW_MINIMUM
        )
        if not (oversized or missing_dimensions or missing_responsive_source):
            continue
        findings.append(
            {
                "url": url.normalized_url,
                "response_size": snapshot.response_size,
                "response_size_mb": _megabytes(snapshot.response_size),
                "oversized": oversized,
                "missing_dimensions": missing_dimensions,
                "missing_responsive_source": missing_responsive_source,
                "source_urls": sorted(
                    {
                        _element_source_url(location)
                        for location in locations
                        if _element_source_url(location)
                    }
                ),
            }
        )
    signals = (
        [
            IssueSignal(
                issue_type=IMAGE_DELIVERY_ISSUE_TYPE,
                category="performance",
                severity="medium",
                confidence="high",
                title=f"{len(findings)} afbeeldingen kunnen efficiënter worden geleverd",
                description=(
                    "Deze afbeeldingen zijn groot, missen vaste afmetingen of bieden geen "
                    "responsive bron voor verschillende schermformaten."
                ),
                recommended_action=(
                    "Comprimeer grote afbeeldingen, lever passende formaten via srcset/sizes "
                    "en voeg width en height toe om layoutverschuiving te beperken."
                ),
                evidence={
                    "affected_image_count": len(findings),
                    "oversized_image_count": sum(bool(item["oversized"]) for item in findings),
                    "source_urls": sorted(
                        {
                            source_url
                            for item in findings
                            for source_url in item["source_urls"]  # type: ignore[union-attr]
                        }
                    )[:200],
                    "images": findings[:500],
                },
            )
        ]
        if findings
        else []
    )
    return reconcile_issues(
        db,
        website_id=website_id,
        url_id=None,
        crawl_run_id=crawl_run_id,
        snapshot_id=None,
        signals=signals,
        checked_issue_types={IMAGE_DELIVERY_ISSUE_TYPE},
    )


def _reconcile_media(
    db: Session,
    *,
    website_id: object,
    crawl_run_id: object,
    snapshots: list[tuple[Url, UrlSnapshot]],
    elements: dict[str, list[ElementLocation]],
) -> list[Issue]:
    findings: list[dict[str, object]] = []
    for url, snapshot in snapshots:
        kind = asset_kind(url.normalized_url, snapshot.content_type)
        if kind not in {"video", "audio"}:
            continue
        limit = VIDEO_SIZE_LIMIT if kind == "video" else AUDIO_SIZE_LIMIT
        locations = elements.get(url.normalized_url, [])
        issue_types = sorted(
            {
                issue_type
                for location in locations
                for issue_type in location.issue_types
                if issue_type
                in {
                    "media_source_missing",
                    "video_captions_missing",
                    "video_missing_poster",
                    "video_preload_auto",
                }
            }
        )
        if (snapshot.response_size or 0) <= limit and not issue_types:
            continue
        findings.append(
            {
                "url": url.normalized_url,
                "kind": kind,
                "content_type": snapshot.content_type,
                "response_size": snapshot.response_size,
                "response_size_mb": _megabytes(snapshot.response_size),
                "large_self_hosted_file": (snapshot.response_size or 0) > limit,
                "signals": issue_types,
                "source_urls": sorted(
                    {
                        _element_source_url(location)
                        for location in locations
                        if _element_source_url(location)
                    }
                ),
            }
        )
    embed_locations = [
        location
        for locations in elements.values()
        for location in locations
        if location.element_type == "iframe"
        and {"iframe_title_missing", "embed_not_lazy"} & set(location.issue_types)
    ]
    embeds = [
        {
            "source_url": _element_source_url(location),
            "target_url": location.target_url,
            "signals": sorted(
                {"iframe_title_missing", "embed_not_lazy"} & set(location.issue_types)
            ),
        }
        for location in embed_locations
    ]
    media_markup_locations = [
        location
        for locations in elements.values()
        for location in locations
        if location.element_type in {"video", "audio"}
        and {
            "media_source_missing",
            "video_captions_missing",
            "video_missing_poster",
            "video_preload_auto",
        }
        & set(location.issue_types)
    ]
    media_markup = [
        {
            "source_url": _element_source_url(location),
            "target_url": location.target_url,
            "element_type": location.element_type,
            "signals": sorted(
                {
                    "media_source_missing",
                    "video_captions_missing",
                    "video_missing_poster",
                    "video_preload_auto",
                }
                & set(location.issue_types)
            ),
        }
        for location in media_markup_locations
    ]
    all_source_urls = sorted(
        {
            source_url
            for item in [*findings, *embeds, *media_markup]
            for source_url in item.get("source_urls", [item.get("source_url")])
            if isinstance(source_url, str) and source_url
        }
    )
    signals = (
        [
            IssueSignal(
                issue_type=MEDIA_DELIVERY_ISSUE_TYPE,
                category="performance",
                severity="medium",
                confidence="medium",
                title="Video, audio en embeds vragen een leveringscontrole",
                description=(
                    "Grote mediabestanden en onvolledige video- of iframe-opmaak kunnen "
                    "laadtijd, toegankelijkheid en videovindbaarheid beperken."
                ),
                recommended_action=(
                    "Gebruik streaming of compressie voor grote media, voeg poster en captions "
                    "toe, beperk preload en geef embeds een titel en lazy loading."
                ),
                evidence={
                    "media_file_count": len(findings),
                    "large_media_count": sum(
                        bool(finding["large_self_hosted_file"]) for finding in findings
                    ),
                    "embed_count": len(embeds),
                    "media_markup_count": len(media_markup),
                    "source_urls": all_source_urls[:200],
                    "media": findings[:500],
                    "embeds": embeds[:500],
                    "media_markup": media_markup[:500],
                },
            )
        ]
        if findings or embeds or media_markup
        else []
    )
    return reconcile_issues(
        db,
        website_id=website_id,
        url_id=None,
        crawl_run_id=crawl_run_id,
        snapshot_id=None,
        signals=signals,
        checked_issue_types={MEDIA_DELIVERY_ISSUE_TYPE},
    )


def _source_urls_by_target(
    db: Session, *, crawl_run_id: object
) -> dict[object, list[dict[str, str]]]:
    rows = db.execute(
        select(UrlLink.target_url_id, Url.normalized_url, UrlLink.anchor_text)
        .join(Url, Url.id == UrlLink.source_url_id)
        .where(
            UrlLink.crawl_run_id == crawl_run_id,
            UrlLink.is_internal.is_(True),
            UrlLink.target_url_id.is_not(None),
        )
        .order_by(UrlLink.target_url_id, Url.normalized_url)
    )
    result: dict[object, list[dict[str, str]]] = defaultdict(list)
    for target_url_id, source_url, anchor_text in rows:
        result[target_url_id].append(
            {"source_url": source_url, "anchor_text": anchor_text or ""}
        )
    return result


def _elements_by_target(
    db: Session, *, crawl_run_id: object
) -> dict[str, list[ElementLocation]]:
    result: dict[str, list[ElementLocation]] = defaultdict(list)
    for location, source_url in db.execute(
        select(ElementLocation, Url.normalized_url)
        .join(Url, Url.id == ElementLocation.source_url_id)
        .where(ElementLocation.crawl_run_id == crawl_run_id)
        .order_by(ElementLocation.target_url)
    ):
        location._source_url = source_url  # type: ignore[attr-defined]
        if location.target_url:
            result[location.target_url].append(location)
        elif location.element_type == "iframe":
            result["__embeds__"].append(location)
    return result


def _element_source_url(location: ElementLocation) -> str | None:
    return getattr(location, "_source_url", None)


def _megabytes(size: int | None) -> float | None:
    return round(size / 1_000_000, 2) if size is not None else None
