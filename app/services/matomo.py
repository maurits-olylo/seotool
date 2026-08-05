import asyncio
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urljoin, urlsplit, urlunsplit
from uuid import UUID

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.discovery import Url
from app.models.integrations import (
    IntegrationConnection,
    MatomoAggregateMetric,
    MatomoPageMetric,
    WebsiteIntegration,
)
from app.models.website import Website
from app.services.metric_storage import insert_metric_rows
from app.services.oauth import decrypt_token
from app.services.security import validate_public_http_url
from app.services.url_normalization import InvalidUrlError, normalize_url

REPORT_LABELS = {
    "Actions.getPageUrls": "Paginaresultaten",
    "Referrers.getReferrerType": "Verkeersbronnen",
    "Goals.get": "Doelen en conversies",
}


class MatomoReportError(ValueError):
    def __init__(self, method: str, reason: str) -> None:
        self.method = method
        self.report_label = REPORT_LABELS.get(method, method)
        self.reason = reason
        super().__init__(f"{self.report_label}: {reason}")


def _safe_report_error(payload: dict[str, object]) -> str:
    message = str(payload.get("message") or "").lower()
    if "token" in message or "authentication" in message:
        return "het API-token is geweigerd"
    if "access" in message or "permission" in message or "privilege" in message:
        return "het Matomo-account heeft onvoldoende leesrechten"
    if "method" in message or "plugin" in message or "module" in message:
        return "dit rapport is niet beschikbaar in deze Matomo-installatie"
    return "Matomo heeft dit rapport geweigerd"


def normalize_matomo_server_url(value: str) -> str:
    raw = value.strip()
    parts = urlsplit(raw)
    if parts.scheme.lower() != "https" or not parts.hostname:
        raise ValueError("Matomo server URL must use HTTPS")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Matomo server URL must not contain credentials, query, or fragment")
    path = parts.path.rstrip("/")
    if not path.endswith("/index.php"):
        path = f"{path}/index.php"
    endpoint = urlunsplit(("https", parts.netloc, path, "", ""))
    try:
        validate_public_http_url(endpoint)
    except InvalidUrlError as exc:
        raise ValueError(str(exc)) from exc
    return endpoint


async def list_matomo_sites(
    server_url: str, token_auth: str, *, timeout_seconds: float = 20
) -> list[dict[str, str | None]]:
    endpoint = normalize_matomo_server_url(server_url)
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as http:
        try:
            response = await http.post(
                endpoint,
                data={
                    "module": "API",
                    "method": "SitesManager.getSitesWithAtLeastViewAccess",
                    "format": "JSON",
                    "token_auth": token_auth,
                },
            )
        except httpx.RequestError as exc:
            raise ValueError("Matomo server could not be reached") from exc
    if response.is_redirect:
        raise ValueError("Matomo server redirected the API request")
    if response.status_code != 200:
        raise ValueError("Matomo connection was rejected")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("Matomo returned an invalid response") from exc
    if isinstance(payload, dict) and payload.get("result") == "error":
        raise ValueError("Matomo token is invalid or lacks view access")
    if not isinstance(payload, list):
        raise ValueError("Matomo returned an invalid site list")
    sites: list[dict[str, str | None]] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("idsite") is None:
            continue
        sites.append(
            {
                "id": str(item["idsite"]),
                "name": str(item.get("name") or f"Site {item['idsite']}"),
                "main_url": str(item["main_url"]) if item.get("main_url") else None,
            }
        )
    return sites


async def list_connection_sites(connection: IntegrationConnection) -> list[dict[str, str | None]]:
    server_url = str(connection.settings.get("server_url") or "")
    token = decrypt_token(connection.encrypted_access_token)
    if not server_url or not token:
        raise ValueError("Matomo connection is incomplete")
    return await list_matomo_sites(server_url, token)


async def _report(
    http: httpx.AsyncClient,
    endpoint: str,
    token: str,
    method: str,
    site_id: str,
    start_date: date,
    end_date: date,
) -> object:
    request_data = {
        "module": "API",
        "method": method,
        "idSite": site_id,
        "period": "day",
        "date": f"{start_date.isoformat()},{end_date.isoformat()}",
        "format": "JSON",
        "filter_limit": "-1",
        "token_auth": token,
    }
    if method == "Actions.getPageUrls":
        request_data.update({"flat": "1", "expanded": "1"})
    try:
        response = await http.post(endpoint, data=request_data)
    except httpx.RequestError as exc:
        raise MatomoReportError(method, "Matomo kon niet worden bereikt") from exc
    if response.is_redirect or response.status_code != 200:
        raise MatomoReportError(method, "Matomo heeft het verzoek niet geaccepteerd")
    try:
        payload = response.json()
    except ValueError as exc:
        raise MatomoReportError(method, "Matomo gaf geen geldig rapport terug") from exc
    if isinstance(payload, dict) and payload.get("result") == "error":
        raise MatomoReportError(method, _safe_report_error(payload))
    return payload


def _dated_rows(payload: object) -> list[tuple[date, dict[str, object]]]:
    result: list[tuple[date, dict[str, object]]] = []
    if not isinstance(payload, dict):
        return result
    for raw_date, rows in payload.items():
        try:
            metric_date = date.fromisoformat(str(raw_date))
        except ValueError:
            continue
        if isinstance(rows, dict):
            rows = [rows]
        if isinstance(rows, list):
            result.extend((metric_date, row) for row in rows if isinstance(row, dict))
    return result


def _number(row: dict[str, object], key: str) -> float:
    try:
        return float(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0


async def sync_matomo(
    db: Session,
    website_id: UUID,
    days: int | None = None,
    *,
    through: date | None = None,
) -> dict[str, object]:
    website = db.get(Website, website_id)
    mapping = db.scalar(
        select(WebsiteIntegration).where(
            WebsiteIntegration.website_id == website_id,
            WebsiteIntegration.service == "matomo",
            WebsiteIntegration.status.in_(("active", "error")),
        )
    )
    if not website or not mapping:
        raise ValueError("Matomo site is not mapped")
    connection = db.get(IntegrationConnection, mapping.connection_id)
    if not connection or connection.status != "connected":
        raise ValueError("Matomo is not connected")
    endpoint = normalize_matomo_server_url(str(connection.settings.get("server_url") or ""))
    token = decrypt_token(connection.encrypted_access_token)
    if not token:
        raise ValueError("Matomo connection is incomplete")

    days = days or (480 if not mapping.settings.get("last_import_start") else 28)
    end_date = through or date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)
    async with httpx.AsyncClient(timeout=60, follow_redirects=False) as http:
        try:
            pages = await _report(
                http,
                endpoint,
                token,
                "Actions.getPageUrls",
                mapping.external_property_id,
                start_date,
                end_date,
            )
        except MatomoReportError as exc:
            mapping.status = "error"
            mapping.settings = {**mapping.settings, "last_error": str(exc)}
            db.commit()
            raise
        optional_results = await asyncio.gather(
            _report(
                http,
                endpoint,
                token,
                "Referrers.getReferrerType",
                mapping.external_property_id,
                start_date,
                end_date,
            ),
            _report(
                http,
                endpoint,
                token,
                "Goals.get",
                mapping.external_property_id,
                start_date,
                end_date,
            ),
            return_exceptions=True,
        )

    optional_payloads: list[object] = []
    warnings: list[str] = []
    for result in optional_results:
        if isinstance(result, BaseException):
            warnings.append(str(result))
            optional_payloads.append({})
        else:
            optional_payloads.append(result)
    sources, goals = optional_payloads
    sources_unavailable = isinstance(optional_results[0], BaseException)
    goals_unavailable = isinstance(optional_results[1], BaseException)

    for model in (MatomoPageMetric, MatomoAggregateMetric):
        db.execute(
            delete(model).where(
                model.website_id == website_id,
                model.date >= start_date,
                model.date <= end_date,
            )
        )
    url_map = {
        item.normalized_url: item.id
        for item in db.scalars(select(Url).where(Url.website_id == website_id))
    }
    page_rows: list[dict[str, object]] = []
    matched = 0
    unmatched_variants: set[str] = set()
    for metric_date, row in _dated_rows(pages):
        raw_url = str(row.get("url") or row.get("label") or "").strip()
        if not raw_url:
            continue
        page_url = urljoin(website.base_url, raw_url)
        try:
            normalized = normalize_url(page_url)
        except InvalidUrlError:
            normalized = page_url
        url_id = url_map.get(normalized)
        matched += int(url_id is not None)
        if url_id is None and len(unmatched_variants) < 100:
            unmatched_variants.add(page_url)
        page_rows.append(
            {
                "website_id": website_id,
                "url_id": url_id,
                "date": metric_date,
                "page_url": page_url,
                "visits": int(_number(row, "nb_visits")),
                "pageviews": int(_number(row, "nb_hits")),
                "unique_pageviews": int(_number(row, "nb_uniq_pageviews")),
                "conversions": _number(row, "nb_conversions"),
            }
        )
    insert_metric_rows(db, MatomoPageMetric, page_rows)

    aggregate_rows: list[dict[str, object]] = []
    for metric_type, payload in (("traffic_source", sources), ("goal", goals)):
        for metric_date, row in _dated_rows(payload):
            key = str(row.get("idgoal") or row.get("segment") or row.get("label") or "unknown")
            aggregate_rows.append(
                {
                    "website_id": website_id,
                    "date": metric_date,
                    "metric_type": metric_type,
                    "dimension_key": key,
                    "dimension_name": str(row.get("name") or row.get("label") or key),
                    "visits": int(_number(row, "nb_visits")),
                    "actions": int(_number(row, "nb_actions")),
                    "conversions": _number(row, "nb_conversions"),
                    "revenue": _number(row, "revenue"),
                }
            )
    insert_metric_rows(db, MatomoAggregateMetric, aggregate_rows)

    now = datetime.now(UTC)
    total = len(page_rows)
    mapping.status = "active"
    mapping.last_synced_at = now
    mapping.settings = {
        **mapping.settings,
        "last_import_start": start_date.isoformat(),
        "last_import_end": end_date.isoformat(),
        "last_import_rows": total,
        "last_import_matched": matched,
        "url_match_rate": round(matched / total, 4) if total else None,
        "unmatched_url_variants": sorted(unmatched_variants),
        "coverage": {
            "pages": "available",
            "traffic_sources": (
                "unavailable"
                if sources_unavailable
                else "available"
                if _dated_rows(sources)
                else "unknown"
            ),
            "goals": (
                "unavailable"
                if goals_unavailable
                else "available"
                if _dated_rows(goals)
                else "unknown"
            ),
            "transitions": "unknown",
            "downloads": "unknown",
            "outbound_links": "unknown",
            "internal_search": "not_imported",
        },
        "last_error": "; ".join(warnings) if warnings else None,
    }
    connection.last_synced_at = now
    db.commit()
    return {
        "status": "partially_succeeded" if warnings else "succeeded",
        "start_date": start_date,
        "end_date": end_date,
        "page_rows": total,
        "matched_urls": matched,
        "unmatched_urls": total - matched,
        "url_match_rate": mapping.settings["url_match_rate"],
        "aggregate_rows": len(aggregate_rows),
        "coverage": mapping.settings["coverage"],
        "warnings": warnings,
    }
