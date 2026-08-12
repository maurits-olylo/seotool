#!/usr/bin/env python3
"""Upload, verify and retrieve encrypted backups through an S3-compatible API."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import http.client
import os
import stat
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple  # noqa: UP035


class OffsiteBackupError(RuntimeError):
    pass


def _credentials(path: Path) -> Tuple[str, str]:  # noqa: UP006
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode not in {0o400, 0o600}:
        raise OffsiteBackupError("S3 credentials file must have mode 0400 or 0600")
    values: Dict[str, str] = {}  # noqa: UP006
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}:
            raise OffsiteBackupError("Invalid S3 credentials file")
        values[key] = value.strip()
    try:
        return values["AWS_ACCESS_KEY_ID"], values["AWS_SECRET_ACCESS_KEY"]
    except KeyError as exc:
        raise OffsiteBackupError("Incomplete S3 credentials file") from exc


class S3Client:
    def __init__(self) -> None:
        self.endpoint = os.environ["S3_BACKUP_ENDPOINT"].rstrip("/")
        self.region = os.environ["S3_BACKUP_REGION"]
        self.bucket = os.environ["S3_BACKUP_BUCKET"]
        credentials_file = Path(os.environ["S3_BACKUP_CREDENTIALS_FILE"])
        self.access_key, self.secret_key = _credentials(credentials_file)
        endpoint = urllib.parse.urlsplit(self.endpoint)
        if endpoint.scheme != "https" or not endpoint.hostname:
            raise OffsiteBackupError("S3 endpoint must be an HTTPS origin")
        self.host = endpoint.netloc
        self.base_path = endpoint.path.rstrip("/")

    def _signing_key(self, date: str) -> bytes:
        date_key = hmac.new(
            f"AWS4{self.secret_key}".encode(), date.encode(), hashlib.sha256
        ).digest()
        region_key = hmac.new(date_key, self.region.encode(), hashlib.sha256).digest()
        service_key = hmac.new(region_key, b"s3", hashlib.sha256).digest()
        return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()

    def request(
        self,
        method: str,
        key: str,
        *,
        body: bytes = b"",
        body_path: Optional[Path] = None,  # noqa: UP045
        query: str = "",
        extra_headers: Optional[Dict[str, str]] = None,  # noqa: UP006, UP045
    ) -> Tuple[bytes, Dict[str, str]]:  # noqa: UP006
        now = datetime.now(timezone.utc)  # noqa: UP017
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date = now.strftime("%Y%m%d")
        encoded_key = urllib.parse.quote(key.lstrip("/"), safe="/-_.~")
        canonical_uri = f"{self.base_path}/{self.bucket}/{encoded_key}"
        if body_path:
            payload_hash_builder = hashlib.sha256()
            content_md5_builder = hashlib.md5()  # noqa: S324 - required transport checksum
            with body_path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    payload_hash_builder.update(chunk)
                    content_md5_builder.update(chunk)
            payload_hash = payload_hash_builder.hexdigest()
            content_length = body_path.stat().st_size
            content_md5 = base64.b64encode(content_md5_builder.digest()).decode()
        else:
            payload_hash = hashlib.sha256(body).hexdigest()
            content_length = len(body)
            content_md5 = ""
        headers = {
            "host": self.host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
            **{name.lower(): value for name, value in (extra_headers or {}).items()},
        }
        if body_path:
            headers["content-length"] = str(content_length)
            headers["content-md5"] = content_md5
        signed_headers = ";".join(sorted(headers))
        canonical_headers = "".join(f"{name}:{headers[name].strip()}\n" for name in sorted(headers))
        canonical_request = "\n".join(
            [method, canonical_uri, query, canonical_headers, signed_headers, payload_hash]
        )
        scope = f"{date}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ]
        )
        signature = hmac.new(
            self._signing_key(date), string_to_sign.encode(), hashlib.sha256
        ).hexdigest()
        headers["authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        url = f"{self.endpoint}/{self.bucket}/{encoded_key}"
        if query:
            url = f"{url}?{query}"
        parsed = urllib.parse.urlsplit(url)
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=120)
        request_path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        connection.putrequest(method, request_path, skip_host=True)
        for name, value in headers.items():
            connection.putheader(name, value)
        connection.endheaders()
        if body_path:
            with body_path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    connection.send(chunk)
        elif body:
            connection.send(body)
        response = connection.getresponse()
        response_body = response.read()
        response_headers = {name.lower(): value for name, value in response.getheaders()}
        connection.close()
        if not 200 <= response.status < 300:
            detail = response_body[:500].decode(errors="replace")
            raise OffsiteBackupError(f"S3 request failed ({response.status}): {detail}")
        return response_body, response_headers


def _object_key(path: Path) -> str:
    prefix = os.environ.get("S3_BACKUP_PREFIX", "seo-monitor/production").strip("/")
    return f"{prefix}/{path.name}" if prefix else path.name


def _retention_headers() -> Dict[str, str]:  # noqa: UP006
    days = int(os.environ.get("S3_BACKUP_OBJECT_LOCK_DAYS", "30"))
    if days < 1:
        raise OffsiteBackupError("Object Lock retention must be at least one day")
    retain_until = datetime.now(timezone.utc) + timedelta(days=days)  # noqa: UP017
    return {
        "x-amz-object-lock-mode": "COMPLIANCE",
        "x-amz-object-lock-retain-until-date": retain_until.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def upload(client: S3Client, path: Path) -> None:
    path = path.resolve(strict=True)
    checksum = _sha256(path)
    key = _object_key(path)
    client.request(
        "PUT",
        key,
        body_path=path,
        extra_headers={"x-amz-meta-sha256": checksum, **_retention_headers()},
    )
    verify(client, path)
    print(f"Immutable off-site backup uploaded and verified: {key}")


def verify(client: S3Client, path: Path) -> None:
    path = path.resolve(strict=True)
    key = _object_key(path)
    checksum = _sha256(path)
    _, headers = client.request("HEAD", key)
    if headers.get("x-amz-meta-sha256") != checksum:
        raise OffsiteBackupError("Remote backup checksum metadata does not match")
    if int(headers.get("content-length", "-1")) != path.stat().st_size:
        raise OffsiteBackupError("Remote backup size does not match")
    retention_xml, _ = client.request("GET", key, query="retention=")
    root = ET.fromstring(retention_xml)
    mode = root.findtext("{*}Mode")
    retain_until = root.findtext("{*}RetainUntilDate")
    if mode != "COMPLIANCE" or not retain_until:
        raise OffsiteBackupError("Remote backup has no verified COMPLIANCE retention")


def download(client: S3Client, key: str, destination: Path) -> None:
    body, headers = client.request("GET", key)
    expected = headers.get("x-amz-meta-sha256")
    if not expected or hashlib.sha256(body).hexdigest() != expected:
        raise OffsiteBackupError("Downloaded backup checksum does not match")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.incomplete")
    temporary.write_bytes(body)
    os.chmod(temporary, 0o600)
    temporary.replace(destination)
    destination.with_suffix(f"{destination.suffix}.sha256").write_text(
        f"{expected}  {destination.name}\n"
    )
    print(f"Off-site backup downloaded and verified: {destination}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("upload", "verify"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("path", type=Path)
    download_parser = subparsers.add_parser("download")
    download_parser.add_argument("key")
    download_parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    client = S3Client()
    if args.command == "upload":
        upload(client, args.path)
    elif args.command == "verify":
        verify(client, args.path)
        print(f"Immutable off-site backup verified: {_object_key(args.path)}")
    else:
        download(client, args.key, args.destination)


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, ValueError, OffsiteBackupError, ET.ParseError) as exc:
        print(f"Off-site backup failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
