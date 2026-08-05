from urllib.parse import urlsplit, urlunsplit

import httpx

from app.models.integrations import IntegrationConnection
from app.services.oauth import decrypt_token
from app.services.security import validate_public_http_url
from app.services.url_normalization import InvalidUrlError


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
