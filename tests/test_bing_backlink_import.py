from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.integrations import (
    BingInboundLink,
    BingLinkTarget,
    BingReferringAnchor,
    BingReferringDomain,
)
from app.models.website import Website, WebsiteSettings
from app.services.bing_backlink_import import (
    InvalidBingBacklinkExport,
    import_bing_backlink_exports,
)


def test_imports_complete_bing_backlink_exports_idempotently() -> None:
    domains = '\ufeff"Domain","Backlinks Count"\n"https://ref.example","2"\n'
    pages = (
        '"Source Url","Anchor text","Target Url"\n'
        '"https://ref.example/a","Example","https://example.com/page"\n'
        '"https://ref.example/b","More","https://example.com/page"\n'
    )
    anchors = '"Anchor","Backlinks Count"\n"Example","2"\n'
    with SessionLocal() as db:
        client = Client(name="Bing CSV client")
        website = Website(client=client, name="Bing CSV site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        db.add(Url(website_id=website.id, normalized_url="https://example.com/page"))
        db.commit()

        first = import_bing_backlink_exports(
            db,
            website_id=website.id,
            domains_csv=domains,
            pages_csv=pages,
            anchors_csv=anchors,
        )
        second = import_bing_backlink_exports(
            db,
            website_id=website.id,
            domains_csv=domains,
            pages_csv=pages,
            anchors_csv=anchors,
        )

        assert first == second
        assert first == {
            "status": "succeeded",
            "source": "manual_csv",
            "domains": 1,
            "domain_backlinks": 2,
            "pages": 2,
            "anchors": 1,
            "targets": 1,
            "matched_targets": 1,
        }
        assert db.scalar(select(func.count(BingReferringDomain.id))) == 1
        assert db.scalar(select(func.count(BingReferringAnchor.id))) == 1
        assert db.scalar(select(func.count(BingInboundLink.id))) == 2
        target = db.scalar(select(BingLinkTarget))
        assert target and target.inbound_link_count == 2 and target.url_id is not None


def test_rejects_wrong_bing_export_columns() -> None:
    with SessionLocal() as db:
        try:
            import_bing_backlink_exports(
                db,
                website_id=Client().id,
                domains_csv="Wrong,Columns\na,b\n",
                pages_csv="Source Url,Anchor text,Target Url\na,b,c\n",
                anchors_csv="Anchor,Backlinks Count\na,1\n",
            )
            raise AssertionError("Invalid export should fail")
        except InvalidBingBacklinkExport:
            pass
