"""Exercise native dependencies and API inside the actual offline runtime image."""

import asyncio
import importlib
import os
import runpy
import ssl
from io import BytesIO
from zoneinfo import ZoneInfo

import httpx
from cryptography.fernet import Fernet
from lxml import etree
from openpyxl import Workbook, load_workbook


async def main() -> None:
    assert os.getuid() == 10001, "Application must retain its production non-root UID"
    assert ssl.create_default_context().get_ca_certs(), "Trusted TLS roots are required"
    assert ZoneInfo("Europe/Amsterdam").key == "Europe/Amsterdam"
    for module in ("psycopg", "uvloop", "httptools", "alembic", "app.worker", "app.scheduler"):
        importlib.import_module(module)
    cipher = Fernet(Fernet.generate_key())
    assert cipher.decrypt(cipher.encrypt(b"image-check")) == b"image-check"
    assert etree.fromstring(b"<root><item>ok</item></root>").findtext("item") == "ok"
    workbook = Workbook()
    workbook.active["A1"] = "Export check"
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    assert load_workbook(output).active["A1"].value == "Export check"

    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok"}
    runpy.run_path("scripts/verify-detection-release.py")["verify_rules"]()
    print("Non-root API, SQLite, native modules, TLS roots, timezones and Excel verified offline.")


if __name__ == "__main__":
    asyncio.run(main())
