from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote
from uuid import UUID

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.discovery import Url
from app.models.integrations import (
    IntegrationConnection,
    SearchConsoleMetric,
    SearchConsoleQueryMetric,
    WebsiteIntegration,
)
from app.services.google_integrations import get_google_access_token
from app.services.url_normalization import InvalidUrlError, normalize_url


async def sync_search_console(
    db: Session, website_id: UUID, days: int | None = None
) -> dict[str, object]:
    mapping = db.scalar(
        select(WebsiteIntegration).where(
            WebsiteIntegration.website_id == website_id,
            WebsiteIntegration.service == "search_console",
            WebsiteIntegration.status.in_(["active", "error"]),
        )
    )
    if not mapping:
        raise ValueError("Search Console property is not mapped")
    connection = db.get(IntegrationConnection, mapping.connection_id)
    if not connection or connection.status != "connected":
        raise ValueError("Google account is not connected")

    if days is None:
        target_start = date.today() - timedelta(days=480)
        imported_start = mapping.settings.get("last_import_start")
        days = (
            480
            if not imported_start or date.fromisoformat(str(imported_start)) > target_start
            else 28
        )

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)
    token = await get_google_access_token(db, connection)
    endpoint = (
        "https://www.googleapis.com/webmasters/v3/sites/"
        f"{quote(mapping.external_property_id, safe='')}/searchAnalytics/query"
    )

    async def fetch_rows(dimensions: list[str]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        start_row = 0
        while True:
            response = await http.post(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                    "dimensions": dimensions,
                    "rowLimit": 25000,
                    "startRow": start_row,
                    "dataState": "final",
                },
            )
            if response.status_code != 200:
                raise ValueError("Search Console data could not be loaded")
            batch = response.json().get("rows", [])
            rows.extend(batch)
            if len(batch) < 25000:
                return rows
            start_row += len(batch)

    async with httpx.AsyncClient(timeout=60) as http:
        try:
            rows = await fetch_rows(["date", "page"])
            query_rows = await fetch_rows(["date", "query", "page"])
        except ValueError:
            mapping.status = "error"
            mapping.settings = {
                **mapping.settings,
                "last_error": "Search Console import failed",
            }
            db.commit()
            raise

    url_map = {
        item.normalized_url: item.id
        for item in db.scalars(select(Url).where(Url.website_id == website_id))
    }
    matched = 0
    for row in rows:
        keys = row.get("keys", [])
        if len(keys) < 2:
            continue
        metric_date = date.fromisoformat(str(keys[0]))
        page_url = str(keys[1])
        try:
            normalized = normalize_url(page_url)
        except InvalidUrlError:
            normalized = page_url
        url_id = url_map.get(normalized)
        matched += int(url_id is not None)
        metric = db.scalar(
            select(SearchConsoleMetric).where(
                SearchConsoleMetric.website_id == website_id,
                SearchConsoleMetric.date == metric_date,
                SearchConsoleMetric.page_url == page_url,
            )
        )
        if metric is None:
            metric = SearchConsoleMetric(website_id=website_id, date=metric_date, page_url=page_url)
            db.add(metric)
        metric.url_id = url_id
        metric.clicks = float(row.get("clicks", 0))
        metric.impressions = int(row.get("impressions", 0))
        metric.ctr = float(row.get("ctr", 0))
        metric.position = float(row.get("position", 0))

    # Query-level data is replaced only for the imported date range. This keeps
    # retries idempotent while avoiding a database lookup for every query row.
    db.execute(
        delete(SearchConsoleQueryMetric).where(
            SearchConsoleQueryMetric.website_id == website_id,
            SearchConsoleQueryMetric.date >= start_date,
            SearchConsoleQueryMetric.date <= end_date,
        )
    )
    query_matched = 0
    metrics: list[SearchConsoleQueryMetric] = []
    for row in query_rows:
        keys = row.get("keys", [])
        if len(keys) < 3:
            continue
        metric_date = date.fromisoformat(str(keys[0]))
        query = str(keys[1])
        page_url = str(keys[2])
        try:
            normalized = normalize_url(page_url)
        except InvalidUrlError:
            normalized = page_url
        url_id = url_map.get(normalized)
        query_matched += int(url_id is not None)
        metrics.append(
            SearchConsoleQueryMetric(
                website_id=website_id,
                url_id=url_id,
                date=metric_date,
                query=query,
                page_url=page_url,
                clicks=float(row.get("clicks", 0)),
                impressions=int(row.get("impressions", 0)),
                ctr=float(row.get("ctr", 0)),
                position=float(row.get("position", 0)),
            )
        )
    db.add_all(metrics)

    now = datetime.now(UTC)
    mapping.status = "active"
    mapping.last_synced_at = now
    mapping.settings = {
        **mapping.settings,
        "last_import_start": start_date.isoformat(),
        "last_import_end": end_date.isoformat(),
        "last_import_rows": len(rows),
        "last_import_matched": matched,
        "last_query_import_rows": len(metrics),
        "last_query_import_matched": query_matched,
    }
    connection.last_synced_at = now
    db.commit()
    return {
        "status": "succeeded",
        "start_date": start_date,
        "end_date": end_date,
        "rows": len(rows),
        "matched_urls": matched,
        "unmatched_urls": len(rows) - matched,
        "query_rows": len(metrics),
        "query_matched_urls": query_matched,
        "query_unmatched_urls": len(metrics) - query_matched,
    }
