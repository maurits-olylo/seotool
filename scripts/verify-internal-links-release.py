"""Read-only production smoke check for the internal link overview."""

import sys
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text  # noqa: E402

import app.models  # noqa: E402, F401
from app.db.session import SessionLocal  # noqa: E402
from app.models.crawl import CrawlRun  # noqa: E402
from app.models.website import Website  # noqa: E402
from app.services.internal_links import ranking, referring_pages  # noqa: E402


def fetch(path: str) -> bytes:
    with urlopen(f"http://localhost:8000{path}", timeout=30) as response:
        assert response.status == 200, "API response is not successful"
        return response.read()


def main() -> None:
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        sites = [
            site.id
            for site in db.scalars(select(Website))
            if (urlsplit(site.base_url).hostname or "").removeprefix("www.").lower()
            == "schipperkozijnen.nl"
        ]
        assert len(sites) == 1, "Expected exactly one Schipper website"
        # Production requires a browser session; technical API keys are disabled.
        # Check the data service under the API database role without bypassing HTTP auth.
        result = ranking(db, sites[0])
        assert result["crawl_run_id"], "No recent completed full crawl available"
        assert result["items"] and result["top"], "No internal link data available"
        top = result["top"][0]
        run = db.get(CrawlRun, result["crawl_run_id"])
        assert run is not None, "Full crawl missing"
        sources = referring_pages(db, run, top["url_id"], 0, 1)
        assert sources["total"] == top["incoming_pages"], "Source count differs from ranking"
        assert len(sources["items"]) == 1, "Source details missing"
    assert (
        "internal-links-summary"
        in (Path(__file__).resolve().parents[1] / "app/ui/index.html").read_text()
    )
    assert b"data-internal-target" in fetch("/ui/assets/internal-links.js?v=20260912")
    assert b"internal-link-bar" in fetch("/ui/assets/internal-links.css?v=20260912")
    print(
        f"Internal link data and assets verified: {len(result['items'])} URLs; "
        f"top page has {sources['total']} referring pages; "
        f"full crawl finished {result['finished_at']}. Database unchanged. "
        "Authenticated HTTP access must be checked in the signed-in interface."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        detail = str(error) if isinstance(error, AssertionError) else type(error).__name__
        print(f"Verification failed: {detail}", file=sys.stderr)
        sys.exit(1)
