from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, ElementLocation, UrlLink, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.asset_quality_analysis import analyze_asset_quality


def test_groups_documents_images_and_media_per_website() -> None:
    with SessionLocal() as db:
        client = Client(name="Asset client")
        website = Website(client=client, name="Asset site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        source = _url(db, website.id, "https://example.com/article")
        document = _url(db, website.id, "https://example.com/download")
        image = _url(db, website.id, "https://example.com/hero.jpg")
        video = _url(db, website.id, "https://example.com/intro.mp4")
        run = _run(db, website.id)
        source_snapshot = _snapshot(source, run, "text/html", 10_000)
        db.add(source_snapshot)
        db.flush()
        db.add_all(
            [
                _snapshot(document, run, "application/pdf", 7_500_000),
                _snapshot(image, run, "image/jpeg", 3_000_000),
                _snapshot(video, run, "video/mp4", 30_000_000),
                UrlLink(
                    crawl_run_id=run.id,
                    source_url_id=source.id,
                    target_url=document.normalized_url,
                    target_url_id=document.id,
                    anchor_text="Download rapport",
                    is_internal=True,
                    is_nofollow=False,
                ),
                _element(
                    website.id,
                    source.id,
                    source_snapshot.id,
                    run.id,
                    image.normalized_url,
                    "img",
                    ["image_dimensions_missing", "image_responsive_source_missing"],
                ),
                _element(
                    website.id,
                    source.id,
                    source_snapshot.id,
                    run.id,
                    video.normalized_url,
                    "video",
                    ["video_missing_poster", "video_captions_missing"],
                ),
                _element(
                    website.id,
                    source.id,
                    source_snapshot.id,
                    run.id,
                    "https://video.example/embed/1",
                    "iframe",
                    ["iframe_title_missing", "embed_not_lazy"],
                ),
            ]
        )
        db.flush()

        found = analyze_asset_quality(db, website_id=website.id, crawl_run_id=run.id)

        assert {issue.issue_type for issue in found} == {
            "downloadable_document_inventory",
            "image_delivery_quality",
            "media_delivery_quality",
        }
        occurrences = {
            issue.issue_type: db.scalar(
                select(IssueOccurrence).where(IssueOccurrence.issue_id == issue.id)
            )
            for issue in found
        }
        assert occurrences["downloadable_document_inventory"].evidence["document_count"] == 1
        assert occurrences["image_delivery_quality"].evidence["affected_image_count"] == 1
        assert occurrences["media_delivery_quality"].evidence["large_media_count"] == 1
        assert occurrences["media_delivery_quality"].evidence["embed_count"] == 1


def _url(db, website_id, value):  # type: ignore[no-untyped-def]
    url = Url(
        website_id=website_id,
        normalized_url=value,
        current_status_code=200,
        current_final_url=value,
        is_active=True,
    )
    db.add(url)
    db.flush()
    return url


def _run(db, website_id):  # type: ignore[no-untyped-def]
    job = CrawlJob(website_id=website_id, job_type="full_site_crawl")
    db.add(job)
    db.flush()
    run = CrawlRun(
        crawl_job_id=job.id,
        website_id=website_id,
        crawl_type="full_site_crawl",
    )
    db.add(run)
    db.flush()
    return run


def _snapshot(url, run, content_type, size):  # type: ignore[no-untyped-def]
    return UrlSnapshot(
        url_id=url.id,
        crawl_run_id=run.id,
        requested_url=url.normalized_url,
        final_url=url.normalized_url,
        status_code=200,
        content_type=content_type,
        response_size=size,
        is_indexable=True,
    )


def _element(  # type: ignore[no-untyped-def]
    website_id,
    source_url_id,
    snapshot_id,
    crawl_run_id,
    target_url,
    element_type,
    issue_types,
):
    return ElementLocation(
        website_id=website_id,
        source_url_id=source_url_id,
        snapshot_id=snapshot_id,
        crawl_run_id=crawl_run_id,
        issue_types=issue_types,
        element_type=element_type,
        target_url=target_url,
        visible_text=None,
        element_id=None,
        css_selector=None,
        xpath=None,
        html_fragment=f"<{element_type}>",
        occurrence_index=1,
        text_prefix=None,
        text_suffix=None,
        text_is_unique=False,
        context_is_unique=False,
        rendered_dynamically=False,
    )
