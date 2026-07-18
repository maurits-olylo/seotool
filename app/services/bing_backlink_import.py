import csv
import re
from datetime import UTC, datetime
from hashlib import sha256
from io import StringIO
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.discovery import Url
from app.models.integrations import (
    BingInboundLink,
    BingLinkTarget,
    BingReferringAnchor,
    BingReferringDomain,
    WebsiteIntegration,
)
from app.services.url_normalization import InvalidUrlError, normalize_url


class InvalidBingBacklinkExport(ValueError):
    pass


def import_bing_backlink_exports(
    db: Session,
    *,
    website_id: UUID,
    domains_csv: str,
    pages_csv: str,
    anchors_csv: str,
) -> dict[str, int | str]:
    domains = _read_rows(domains_csv, ("Domain", "Backlinks Count"), 50_000)
    pages = _read_rows(pages_csv, ("Source Url", "Anchor text", "Target Url"), 100_000)
    anchors = _read_rows(anchors_csv, ("Anchor", "Backlinks Count"), 50_000)
    observed_at = datetime.now(UTC)

    db.execute(
        update(BingReferringDomain)
        .where(BingReferringDomain.website_id == website_id)
        .values(is_active=False)
    )
    db.execute(
        update(BingReferringAnchor)
        .where(BingReferringAnchor.website_id == website_id)
        .values(is_active=False)
    )
    db.execute(
        update(BingInboundLink)
        .where(BingInboundLink.website_id == website_id)
        .values(is_active=False)
    )
    db.execute(
        update(BingLinkTarget)
        .where(BingLinkTarget.website_id == website_id)
        .values(is_active=False)
    )

    for row in domains:
        domain = row["Domain"].strip()
        count = _positive_count(row["Backlinks Count"], "Backlinks Count")
        if not domain:
            continue
        record = db.scalar(
            select(BingReferringDomain).where(
                BingReferringDomain.website_id == website_id,
                BingReferringDomain.domain == domain,
            )
        )
        if record is None:
            record = BingReferringDomain(website_id=website_id, domain=domain)
            db.add(record)
        record.backlink_count = count
        record.observed_at = observed_at
        record.is_active = True

    for row in anchors:
        anchor_text = row["Anchor"].strip()
        count = _positive_count(row["Backlinks Count"], "Backlinks Count")
        key = sha256(anchor_text.encode()).hexdigest()
        record = db.scalar(
            select(BingReferringAnchor).where(
                BingReferringAnchor.website_id == website_id,
                BingReferringAnchor.anchor_key == key,
            )
        )
        if record is None:
            record = BingReferringAnchor(
                website_id=website_id, anchor_key=key, anchor_text=anchor_text
            )
            db.add(record)
        record.anchor_text = anchor_text
        record.backlink_count = count
        record.observed_at = observed_at
        record.is_active = True

    url_map = {
        item.normalized_url: item.id
        for item in db.scalars(select(Url).where(Url.website_id == website_id))
    }
    target_counts: dict[str, int] = {}
    imported_links = 0
    for row in pages:
        source_url = row["Source Url"].strip()
        target_url = row["Target Url"].strip()
        anchor_text = row["Anchor text"].strip()
        if not source_url or not target_url:
            continue
        link_key = sha256(f"{target_url}\n{source_url}\n{anchor_text}".encode()).hexdigest()
        record = db.scalar(
            select(BingInboundLink).where(
                BingInboundLink.website_id == website_id,
                BingInboundLink.link_key == link_key,
            )
        )
        if record is None:
            record = BingInboundLink(
                website_id=website_id,
                link_key=link_key,
                target_url=target_url,
                source_url=source_url,
                anchor_text=anchor_text,
                first_seen_at=observed_at,
            )
            db.add(record)
        record.last_seen_at = observed_at
        record.is_active = True
        target_counts[target_url] = target_counts.get(target_url, 0) + 1
        imported_links += 1

    matched_targets = 0
    for target_url, count in target_counts.items():
        record = db.scalar(
            select(BingLinkTarget).where(
                BingLinkTarget.website_id == website_id,
                BingLinkTarget.target_url == target_url,
            )
        )
        if record is None:
            record = BingLinkTarget(
                website_id=website_id,
                target_url=target_url,
                first_seen_at=observed_at,
            )
            db.add(record)
        try:
            record.url_id = url_map.get(normalize_url(target_url))
        except InvalidUrlError:
            record.url_id = None
        matched_targets += int(record.url_id is not None)
        record.inbound_link_count = count
        record.last_seen_at = observed_at
        record.is_active = True

    mapping = db.scalar(
        select(WebsiteIntegration).where(
            WebsiteIntegration.website_id == website_id,
            WebsiteIntegration.service == "bing_webmaster",
        )
    )
    if mapping:
        mapping.settings = {
            **mapping.settings,
            "backlink_source": "manual_csv",
            "backlink_imported_at": observed_at.isoformat(),
            "backlink_domain_rows": len(domains),
            "backlink_page_rows": imported_links,
            "backlink_anchor_rows": len(anchors),
        }
    db.commit()
    return {
        "status": "succeeded",
        "source": "manual_csv",
        "domains": len(domains),
        "domain_backlinks": sum(
            _positive_count(row["Backlinks Count"], "Backlinks Count") for row in domains
        ),
        "pages": imported_links,
        "anchors": len(anchors),
        "targets": len(target_counts),
        "matched_targets": matched_targets,
    }


def _read_rows(content: str, headers: tuple[str, ...], maximum: int) -> list[dict[str, str]]:
    reader = csv.DictReader(StringIO(_repair_bing_csv(content.lstrip("\ufeff"))))
    if tuple(reader.fieldnames or ()) != headers:
        raise InvalidBingBacklinkExport(
            f"Ongeldige Bing-export; verwacht kolommen: {', '.join(headers)}"
        )
    rows = list(reader)
    if not rows or len(rows) > maximum:
        raise InvalidBingBacklinkExport("Bing-export is leeg of overschrijdt de veilige limiet")
    return rows


def _repair_bing_csv(content: str) -> str:
    """Repair Bing's invalid encoding for an anchor consisting of one quote."""
    return "\n".join(
        re.sub(r'^""","([0-9]+)"$', r'"""","\1"', line) for line in content.splitlines()
    )


def _positive_count(value: str | None, field: str) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidBingBacklinkExport(f"{field} bevat geen geldig aantal") from exc
    if count < 0:
        raise InvalidBingBacklinkExport(f"{field} mag niet negatief zijn")
    return count
