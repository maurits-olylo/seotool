import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.models.issues import Issue
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal
from app.services.url_normalization import InvalidUrlError, normalize_url

INTERNATIONAL_INDEXATION_ISSUE_TYPES = {
    "multiple_canonicals",
    "canonical_target_redirect",
    "canonical_target_error",
    "canonical_target_noindex",
    "canonical_chain",
    "canonical_loop",
    "hreflang_invalid_language",
    "hreflang_missing_self_reference",
    "hreflang_missing_return",
    "hreflang_target_redirect",
    "hreflang_target_error",
    "hreflang_target_noindex",
    "hreflang_target_canonical_mismatch",
}
LANGUAGE_CODE_RE = re.compile(
    r"^(?:x-default|[a-z]{2,3}(?:-[a-z]{4})?(?:-(?:[a-z]{2}|[0-9]{3}))?)$",
    re.IGNORECASE,
)


def analyze_international_indexation(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
    rows = list(
        db.execute(
            select(Url, UrlSnapshot)
            .join(UrlSnapshot, UrlSnapshot.url_id == Url.id)
            .where(
                Url.website_id == website_id,
                UrlSnapshot.crawl_run_id == crawl_run_id,
            )
            .order_by(Url.normalized_url)
        )
    )
    snapshots = {_normalized(url.normalized_url): (url, snapshot) for url, snapshot in rows}
    signals_by_url: dict[object, list[IssueSignal]] = defaultdict(list)
    for url, snapshot in rows:
        page_url = _normalized(snapshot.final_url or url.normalized_url)
        canonical_urls = snapshot.canonical_urls or []
        if len(canonical_urls) > 1:
            signals_by_url[url.id].append(
                _signal(
                    "multiple_canonicals",
                    "high",
                    "Pagina bevat meerdere canonicals",
                    "Behoud precies één canonical die de primaire indexeerbare URL aanwijst.",
                    canonical_urls=canonical_urls,
                )
            )
        signals_by_url[url.id].extend(
            _canonical_signals(page_url, snapshot, snapshots=snapshots)
        )
        signals_by_url[url.id].extend(
            _hreflang_signals(page_url, snapshot, snapshots=snapshots)
        )

    touched: list[Issue] = []
    for url, snapshot in rows:
        touched.extend(
            reconcile_issues(
                db,
                website_id=website_id,
                url_id=url.id,
                crawl_run_id=crawl_run_id,
                snapshot_id=snapshot.id,
                signals=signals_by_url[url.id],
                checked_issue_types=INTERNATIONAL_INDEXATION_ISSUE_TYPES,
            )
        )
    db.commit()
    return touched


def _canonical_signals(
    page_url: str,
    snapshot: UrlSnapshot,
    *,
    snapshots: dict[str, tuple[Url, UrlSnapshot]],
) -> list[IssueSignal]:
    canonical = _normalized(snapshot.canonical)
    if not canonical or canonical == page_url:
        return []
    target_row = snapshots.get(canonical)
    if target_row is None:
        return []
    _, target = target_row
    signals: list[IssueSignal] = []
    if target.redirect_chain:
        signals.append(
            _signal(
                "canonical_target_redirect",
                "high",
                "Canonicaldoel stuurt door",
                "Wijs de canonical rechtstreeks naar de definitieve indexeerbare URL.",
                canonical=canonical,
                redirect_chain=target.redirect_chain,
            )
        )
    elif target.status_code != 200:
        signals.append(
            _signal(
                "canonical_target_error",
                "high",
                "Canonicaldoel is niet bereikbaar",
                "Herstel het canonicaldoel of wijs naar een bereikbare URL met status 200.",
                canonical=canonical,
                status_code=target.status_code,
            )
        )
    elif target.is_indexable is False:
        signals.append(
            _signal(
                "canonical_target_noindex",
                "high",
                "Canonicaldoel is niet indexeerbaar",
                "Maak het canonicaldoel indexeerbaar of kies een andere primaire URL.",
                canonical=canonical,
            )
        )

    path = [page_url, canonical]
    seen = {page_url}
    current = canonical
    while current in snapshots:
        target_snapshot = snapshots[current][1]
        next_target = _normalized(target_snapshot.canonical)
        if not next_target or next_target == current:
            break
        path.append(next_target)
        if next_target in seen:
            signals.append(
                _signal(
                    "canonical_loop",
                    "high",
                    "Canonical-loop gedetecteerd",
                    "Laat iedere URL rechtstreeks naar één stabiele primaire URL canonicaliseren.",
                    path=path,
                )
            )
            break
        seen.add(current)
        current = next_target
    if len(path) > 2 and not any(signal.issue_type == "canonical_loop" for signal in signals):
        signals.append(
            _signal(
                "canonical_chain",
                "medium",
                "Canonical-keten gedetecteerd",
                "Wijs de eerste pagina rechtstreeks naar de uiteindelijke canonical URL.",
                path=path,
            )
        )
    return signals


def _hreflang_signals(
    page_url: str,
    snapshot: UrlSnapshot,
    *,
    snapshots: dict[str, tuple[Url, UrlSnapshot]],
) -> list[IssueSignal]:
    links = snapshot.hreflang_links or []
    if not links:
        return []
    signals: list[IssueSignal] = []
    invalid = sorted(
        {str(link.get("language") or "") for link in links if not _valid_language(link)}
    )
    if invalid:
        signals.append(
            _signal(
                "hreflang_invalid_language",
                "medium",
                "Ongeldige hreflangcode",
                "Gebruik geldige ISO-taalcodes en optioneel een geldige regio, of x-default.",
                invalid_languages=invalid,
            )
        )
    targets = {_normalized(str(link.get("target_url") or "")) for link in links}
    if page_url not in targets:
        signals.append(
            _signal(
                "hreflang_missing_self_reference",
                "medium",
                "Hreflangcluster mist zelfverwijzing",
                "Voeg op iedere taalvariant een hreflangverwijzing naar zichzelf toe.",
                page_url=page_url,
            )
        )
    for link in links:
        language = str(link.get("language") or "")
        target_url = _normalized(str(link.get("target_url") or ""))
        target_row = snapshots.get(target_url)
        if not target_url or target_row is None:
            continue
        _, target = target_row
        evidence = {"language": language, "target_url": target_url}
        if target.redirect_chain:
            signals.append(
                _signal(
                    "hreflang_target_redirect",
                    "high",
                    "Hreflangdoel stuurt door",
                    "Wijs hreflang rechtstreeks naar de definitieve taalvariant.",
                    **evidence,
                )
            )
        elif target.status_code != 200:
            signals.append(
                _signal(
                    "hreflang_target_error",
                    "high",
                    "Hreflangdoel is niet bereikbaar",
                    "Herstel of verwijder de hreflangverwijzing naar deze taalvariant.",
                    status_code=target.status_code,
                    **evidence,
                )
            )
        elif target.is_indexable is False:
            signals.append(
                _signal(
                    "hreflang_target_noindex",
                    "high",
                    "Hreflangdoel is niet indexeerbaar",
                    "Maak de taalvariant indexeerbaar of verwijder hem uit het hreflangcluster.",
                    **evidence,
                )
            )
        target_canonical = _normalized(target.canonical)
        if target_canonical and target_canonical != target_url:
            signals.append(
                _signal(
                    "hreflang_target_canonical_mismatch",
                    "high",
                    "Hreflangdoel canonicaliseert elders",
                    "Laat hreflang alleen verwijzen naar zelfcanonicaliserende taalvarianten.",
                    canonical=target_canonical,
                    **evidence,
                )
            )
        return_targets = {
            _normalized(str(item.get("target_url") or ""))
            for item in (target.hreflang_links or [])
        }
        if page_url not in return_targets:
            signals.append(
                _signal(
                    "hreflang_missing_return",
                    "medium",
                    "Hreflang-retourverwijzing ontbreekt",
                    "Voeg op de doelvariant een hreflangverwijzing terug naar deze pagina toe.",
                    **evidence,
                )
            )
    return _deduplicate(signals)


def _valid_language(link: dict[str, str]) -> bool:
    language = str(link.get("language") or "")
    return bool(LANGUAGE_CODE_RE.fullmatch(language))


def _normalized(value: str | None) -> str:
    if not value:
        return ""
    try:
        return normalize_url(value)
    except InvalidUrlError:
        return value


def _deduplicate(signals: list[IssueSignal]) -> list[IssueSignal]:
    return list({signal.issue_type: signal for signal in signals}.values())


def _signal(
    issue_type: str,
    severity: str,
    title: str,
    action: str,
    **evidence: object,
) -> IssueSignal:
    return IssueSignal(
        issue_type=issue_type,
        category="indexation",
        severity=severity,
        title=title,
        description=f"{title}. De volledige crawl bevestigt dit met actueel bron- en doelbewijs.",
        recommended_action=action,
        evidence=evidence,
    )
