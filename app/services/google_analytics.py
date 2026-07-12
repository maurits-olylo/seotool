from datetime import UTC, date, datetime, timedelta
from urllib.parse import urljoin
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovery import Url
from app.models.integrations import (
    GoogleAnalyticsMetric,
    IntegrationConnection,
    WebsiteIntegration,
)
from app.models.website import Website
from app.services.google_integrations import get_google_access_token
from app.services.url_normalization import InvalidUrlError, normalize_url


async def sync_google_analytics(db: Session, website_id: UUID, days: int = 28) -> dict[str, object]:
    website = db.get(Website, website_id)
    mapping = db.scalar(
        select(WebsiteIntegration).where(
            WebsiteIntegration.website_id == website_id,
            WebsiteIntegration.service == "ga4",
            WebsiteIntegration.status.in_(["active", "error"]),
        )
    )
    if not website or not mapping:
        raise ValueError("GA4 property is not mapped")
    connection = db.get(IntegrationConnection, mapping.connection_id)
    if not connection or connection.status != "connected":
        raise ValueError("Google account is not connected")

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)
    token = await get_google_access_token(db, connection)
    property_id = mapping.external_property_id.removeprefix("properties/")
    endpoint = f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"
    response_rows: list[dict[str, object]] = []
    offset = 0
    async with httpx.AsyncClient(timeout=60) as http:
        while True:
            response = await http.post(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "dateRanges": [
                        {"startDate": start_date.isoformat(), "endDate": end_date.isoformat()}
                    ],
                    "dimensions": [{"name": "date"}, {"name": "landingPagePlusQueryString"}],
                    "metrics": [
                        {"name": "sessions"},
                        {"name": "activeUsers"},
                        {"name": "keyEvents"},
                    ],
                    "limit": 100000,
                    "offset": offset,
                },
            )
            if response.status_code != 200:
                mapping.status = "error"
                mapping.settings = {**mapping.settings, "last_error": "GA4 import failed"}
                db.commit()
                raise ValueError("GA4 data could not be loaded")
            payload = response.json()
            batch = payload.get("rows", [])
            response_rows.extend(batch)
            offset += len(batch)
            if offset >= int(payload.get("rowCount", len(response_rows))) or not batch:
                break

    url_map = {
        item.normalized_url: item.id
        for item in db.scalars(select(Url).where(Url.website_id == website_id))
    }
    matched = 0
    imported = 0
    for row in response_rows:
        dimensions = row.get("dimensionValues", [])
        metrics = row.get("metricValues", [])
        if len(dimensions) < 2 or len(metrics) < 3:
            continue
        metric_date = datetime.strptime(dimensions[0]["value"], "%Y%m%d").date()
        landing_page = dimensions[1]["value"]
        if landing_page in {"(not set)", ""}:
            continue
        page_url = urljoin(website.base_url, landing_page)
        try:
            normalized = normalize_url(page_url)
        except InvalidUrlError:
            normalized = page_url
        url_id = url_map.get(normalized)
        matched += int(url_id is not None)
        metric = db.scalar(
            select(GoogleAnalyticsMetric).where(
                GoogleAnalyticsMetric.website_id == website_id,
                GoogleAnalyticsMetric.date == metric_date,
                GoogleAnalyticsMetric.landing_page == landing_page,
            )
        )
        if metric is None:
            metric = GoogleAnalyticsMetric(
                website_id=website_id, date=metric_date, landing_page=landing_page
            )
            db.add(metric)
        metric.url_id = url_id
        metric.sessions = int(float(metrics[0].get("value", 0)))
        metric.active_users = int(float(metrics[1].get("value", 0)))
        metric.key_events = float(metrics[2].get("value", 0))
        imported += 1

    now = datetime.now(UTC)
    mapping.status = "active"
    mapping.last_synced_at = now
    mapping.settings = {
        **mapping.settings,
        "last_import_start": start_date.isoformat(),
        "last_import_end": end_date.isoformat(),
        "last_import_rows": imported,
        "last_import_matched": matched,
    }
    connection.last_synced_at = now
    db.commit()
    return {
        "status": "succeeded",
        "start_date": start_date,
        "end_date": end_date,
        "rows": imported,
        "matched_urls": matched,
        "unmatched_urls": imported - matched,
    }
