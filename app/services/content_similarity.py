import re
from collections import Counter, defaultdict
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.models.issues import Issue
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal
from app.services.url_normalization import InvalidUrlError, normalize_url

CONTENT_SIMILARITY_ISSUE_TYPES = {
    "duplicate_content",
    "duplicate_meta_description",
    "duplicate_title",
    "near_duplicate_content",
}
MINIMUM_WORDS = 100
SHINGLE_SIZE = 5
NEAR_DUPLICATE_CONTAINMENT = 0.85
TOKEN_RE = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)


def detect_duplicate_content(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
    """Detect exact and highly similar content within one complete site crawl."""
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
    by_hash: dict[str, list[int]] = defaultdict(list)
    for index, (_, snapshot) in enumerate(rows):
        if _is_comparable(snapshot) and snapshot.main_content_hash:
            by_hash[snapshot.main_content_hash].append(index)

    exact_groups = [indices for indices in by_hash.values() if len(indices) > 1]
    exact_members = {index for group in exact_groups for index in group}
    near_groups = near_duplicate_groups(rows, excluded_indices=exact_members)

    signals_by_index: dict[int, list[IssueSignal]] = defaultdict(list)
    _add_duplicate_metadata_signals(rows, signals_by_index)
    for group in exact_groups:
        urls = [rows[index][0].normalized_url for index in group]
        for index in group:
            related = [url for url in urls if url != rows[index][0].normalized_url]
            signals_by_index[index].append(
                IssueSignal(
                    issue_type="duplicate_content",
                    category="content",
                    severity="medium",
                    confidence="high",
                    title="Dezelfde hoofdcontent op meerdere URL's",
                    description=(
                        f"De hoofdcontent is gelijk aan die van {len(related)} andere "
                        "indexeerbare URL(s)."
                    ),
                    recommended_action=(
                        "Kies één primaire pagina en onderscheid, consolideer, redirect of "
                        "canonicaliseer de overige URL's."
                    ),
                    evidence={"related_urls": related, "group_size": len(group)},
                )
            )

    for group, scores in near_groups:
        urls = [rows[index][0].normalized_url for index in group]
        for index in group:
            related = [url for url in urls if url != rows[index][0].normalized_url]
            signals_by_index[index].append(
                IssueSignal(
                    issue_type="near_duplicate_content",
                    category="content",
                    severity="low",
                    confidence="medium",
                    title="Sterk gelijkende hoofdcontent",
                    description=(
                        f"Minimaal {min(scores) * 100:.0f}% van de inhoud overlapt met "
                        f"{len(related)} andere indexeerbare URL(s)."
                    ),
                    recommended_action=(
                        "Controleer of iedere pagina een eigen zoekintentie en voldoende unieke "
                        "inhoud heeft; consolideer pagina's die hetzelfde doel bedienen."
                    ),
                    evidence={
                        "related_urls": related,
                        "minimum_overlap_percent": round(min(scores) * 100, 1),
                        "group_size": len(group),
                    },
                )
            )

    touched: list[Issue] = []
    for index, (url, snapshot) in enumerate(rows):
        touched.extend(
            reconcile_issues(
                db,
                website_id=website_id,
                url_id=url.id,
                crawl_run_id=crawl_run_id,
                snapshot_id=snapshot.id,
                signals=signals_by_index.get(index, []),
                checked_issue_types=CONTENT_SIMILARITY_ISSUE_TYPES,
            )
        )
    return touched


def _add_duplicate_metadata_signals(
    rows: list[tuple[Url, UrlSnapshot]],
    signals_by_index: dict[int, list[IssueSignal]],
) -> None:
    definitions = (
        (
            "title",
            "duplicate_title",
            "Dezelfde title op meerdere pagina's",
            "medium",
            "Schrijf voor iedere indexeerbare pagina een unieke title die het eigen onderwerp "
            "en de zoekintentie beschrijft.",
        ),
        (
            "meta_description",
            "duplicate_meta_description",
            "Dezelfde meta description op meerdere pagina's",
            "low",
            "Schrijf een unieke meta description die de inhoud en propositie van deze pagina "
            "onderscheidt.",
        ),
    )
    for field_name, issue_type, title, severity, action in definitions:
        groups: dict[str, list[int]] = defaultdict(list)
        for index, (_, snapshot) in enumerate(rows):
            if not _is_indexable_page(snapshot):
                continue
            value = _normalize_metadata(getattr(snapshot, field_name))
            if value:
                groups[value].append(index)
        for indices in groups.values():
            if len(indices) < 2:
                continue
            urls = [rows[index][0].normalized_url for index in indices]
            for index in indices:
                related = [url for url in urls if url != rows[index][0].normalized_url]
                signals_by_index[index].append(
                    IssueSignal(
                        issue_type=issue_type,
                        category="onpage",
                        severity=severity,
                        confidence="high",
                        title=title,
                        description=(
                            f"Deze waarde wordt ook gebruikt op {len(related)} andere "
                            "indexeerbare URL(s)."
                        ),
                        recommended_action=action,
                        evidence={
                            "field": field_name,
                            "value": getattr(rows[index][1], field_name),
                            "related_urls": related,
                            "group_size": len(indices),
                        },
                    )
                )


def near_duplicate_groups(
    rows: list[tuple[Url, UrlSnapshot]], *, excluded_indices: set[int]
) -> list[tuple[list[int], list[float]]]:
    """Return groups whose main content has at least 85% shingle containment."""
    shingles: dict[int, set[tuple[str, ...]]] = {}
    postings: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for index, (_, snapshot) in enumerate(rows):
        if index in excluded_indices or not _is_comparable(snapshot):
            continue
        tokens = TOKEN_RE.findall((snapshot.main_content or "").lower())
        document_shingles = {
            tuple(tokens[offset : offset + SHINGLE_SIZE])
            for offset in range(max(0, len(tokens) - SHINGLE_SIZE + 1))
        }
        if document_shingles:
            shingles[index] = document_shingles
            for shingle in document_shingles:
                postings[shingle].append(index)

    overlap_counts: Counter[tuple[int, int]] = Counter()
    common_limit = max(10, len(shingles) // 10)
    for document_indices in postings.values():
        if len(document_indices) > common_limit:
            continue
        for left, right in combinations(document_indices, 2):
            overlap_counts[(left, right)] += 1

    edges: list[tuple[int, int, float]] = []
    for (left, right), overlap in overlap_counts.items():
        left_size = len(shingles[left])
        right_size = len(shingles[right])
        if min(left_size, right_size) / max(left_size, right_size) < 0.75:
            continue
        containment = overlap / min(left_size, right_size)
        if containment >= NEAR_DUPLICATE_CONTAINMENT:
            edges.append((left, right, containment))

    return _connected_groups(edges)


def _is_comparable(snapshot: UrlSnapshot) -> bool:
    return bool(
        _is_indexable_page(snapshot)
        and (snapshot.word_count or 0) >= MINIMUM_WORDS
        and snapshot.main_content
    )


def _is_indexable_page(snapshot: UrlSnapshot) -> bool:
    if snapshot.status_code != 200 or snapshot.is_indexable is not True or snapshot.redirect_chain:
        return False
    if not snapshot.canonical:
        return True
    page_url = snapshot.final_url or snapshot.requested_url
    try:
        return normalize_url(snapshot.canonical) == normalize_url(page_url)
    except InvalidUrlError:
        return True


def _normalize_metadata(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _connected_groups(
    edges: list[tuple[int, int, float]],
) -> list[tuple[list[int], list[float]]]:
    adjacency: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for left, right, score in edges:
        adjacency[left].append((right, score))
        adjacency[right].append((left, score))
    groups: list[tuple[list[int], list[float]]] = []
    visited: set[int] = set()
    for start in sorted(adjacency):
        if start in visited:
            continue
        pending = [start]
        members: list[int] = []
        scores: list[float] = []
        visited.add(start)
        while pending:
            current = pending.pop()
            members.append(current)
            for neighbour, score in adjacency[current]:
                scores.append(score)
                if neighbour not in visited:
                    visited.add(neighbour)
                    pending.append(neighbour)
        groups.append((sorted(members), scores))
    return groups
