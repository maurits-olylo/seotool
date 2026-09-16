"""Check deployed rules and query production evidence without reclassifying issues."""

import argparse
import json
import sys
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text  # noqa: E402

import app.models  # noqa: E402, F401
from app.db.session import SessionLocal  # noqa: E402
from app.models.crawl import CrawlRun, UrlSnapshot  # noqa: E402
from app.models.website import Website  # noqa: E402
from app.services.crawl_reachability import crawl_reachability  # noqa: E402
from app.services.html_extraction import extract_page  # noqa: E402
from app.services.recommendation_library import recommendation_for_issue_type  # noqa: E402
from app.services.structured_data_analysis import _headline_variant_matches  # noqa: E402


def verify_rules() -> None:
    page = extract_page(
        '<main><form action="/save"><button>Send</button></form><a href="/page">Page</a></main>',
        "https://example.com/",
    )
    assert [link.target_url for link in page.links] == ["https://example.com/page"]
    assert any(element.target_url == "https://example.com/save" for element in page.elements)
    snapshot = UrlSnapshot(title="It will rain | HUMAN", headings={"h1": ["It will rain"]})
    assert _headline_variant_matches(snapshot, "Kijk It will rain bij HUMAN")
    assert not _headline_variant_matches(snapshot, "Kijk It will rain morgen")
    definition = recommendation_for_issue_type("expired_job_posting_404")
    assert definition and definition.key == "decide_vacancy_disposition"
    assert definition.feasibility == "needs_decision"
    print("Form evidence, navigation links, headline variants and vacancy decisions verified.")


def verify_database() -> None:
    assert sys.version_info[:2] == (3, 12), "Unexpected Python runtime"
    assert version("cryptography") == "50.0.1", "Unexpected cryptography version"
    with SessionLocal(autoflush=False) as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        db.execute(text("SET LOCAL statement_timeout = '30s'"))
        assert db.scalar(text("SHOW transaction_read_only")) == "on"
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0066"
        sites = [
            site
            for site in db.scalars(select(Website))
            if (urlsplit(site.base_url).hostname or "").lower().removeprefix("www.")
            in {"schipperkozijnen.nl", "human.nl"}
        ]
        assert len(sites) == 2, "Expected two pilot websites"
        for site in sites:
            run = db.scalar(
                select(CrawlRun)
                .where(
                    CrawlRun.website_id == site.id,
                    CrawlRun.crawl_type == "full_site_crawl",
                    CrawlRun.status.in_(["succeeded", "partially_succeeded"]),
                )
                .order_by(CrawlRun.started_at.desc())
                .limit(1)
            )
            assert run, "Pilot full crawl missing"
            graph = crawl_reachability(db, website_id=site.id, crawl_run_id=run.id)
            assert graph.depths, "No positive routes found in pilot crawl"
            print(
                json.dumps(
                    {
                        "website_id": str(site.id),
                        "crawl_run_id": str(run.id),
                        "reachable_urls": len(graph.depths),
                        "complete": graph.complete,
                        "blocking_sources": len(graph.blockers),
                    }
                )
            )
        assert not db.new and not db.dirty and not db.deleted
        db.rollback()
    print("Release runtime and pilot data verified; no issues or tasks changed.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules-only", action="store_true")
    args = parser.parse_args()
    try:
        verify_rules()
        if not args.rules_only:
            verify_database()
    except Exception as error:
        # Do not disclose SQL parameters, connection strings or stored page content.
        print(f"Release verification failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
