# Detection and advice corrections — 16 September 2026

Status: implemented locally; no production reclassification or deployment. No migration or new dependency is required.

## Crawl depth and reachability

A previously seeded URL could retain `None` in the crawler's pending queue after its database depth had been discovered. Children then inherited the stale empty value. Queue entries now receive the improved depth before sorting. At resume and at the end of a completed frontier, depth is reconstructed from the selected full crawl's snapshots and links.

`app/services/crawl_reachability.py` supplies the same reconstruction to orphan detection and can be called without changing records for the forthcoming production comparison. It does not use historical `UrlSource` records as navigation evidence. Navigation links, including nofollow links, count towards visitor reachability; self-links do not create a route. Excluded, non-HTML and technical placeholder targets do not enter the graph. Discovery-only pages can be traversed but remain excluded as orphan candidates. Redirected destinations have the same navigation depth as their source. A redirected HTML response can cover a destination not fetched separately.

A missing, failed or unusable reachable source makes negative reachability inconclusive. This does not discard the positive routes or the rest of a partial crawl. It prevents new orphan claims and automatic resolution based on absence. A failed root cannot prove a disconnected page. Current asset observations still trigger asset checks; the navigation change must not disable image/PDF auditing.

Orphan eligibility uses a successful indexable snapshot and sitemap membership observed within that crawl's time window. `UrlSource` stores the latest observation rather than a historical membership ledger: a later sitemap import may make old membership unprovable. Such cases are skipped rather than guessed. Website scope/settings still come from the configured website; an old-run comparison after settings changes requires explicit review.

Reachability evidence is versioned. A legacy orphan that now has a route is marked for review rather than credited as website repair. Version-2 findings can follow the ordinary resolution lifecycle after another crawl confirms a route. Same-run reclassification requires review. Historical occurrences and existing task agreements are retained.

## Structured data

Publisher/Organization and LocalBusiness names are not tested against the page's title/main content. Their missing-field and image checks remain. Other recognized entity names/headlines are compared after Unicode, punctuation and whitespace normalization. No extracted comparison text means no mismatch finding. A mismatch is low-confidence evidence requiring an entity/content review, not an instruction to copy the title into schema.

Legacy mismatches that disappear under these rules are retained for review, without claiming a repair. Findings created with comparison version 2 retain ordinary verification behavior. Failed snapshots cannot resolve schema findings. This change is deliberately not a semantic schema validator or a guarantee that every remaining mismatch is actionable.

## Vacancy decisions

`decide_vacancy_disposition` handles expired/linked-expired/missing-expired vacancies. Content ownership makes the initial decision: active, closed but retained, or removed. Steps name the later editorial and development responsibilities. Acceptance criteria are conditional on the selected outcome. Removal does not require valid JobPosting markup on the removed page, and redirects require a relevant replacement.

Markup defects retain the technical recommendation. Existing tasks are not rewritten. An active task attached to the same issue prevents duplication even when its old recommendation type differs from the new definition. No dependency engine, automatic handoff or automatic verification of vacancy decisions is introduced in this package.

## Verification and next phase

Local fixtures cover a seeded chain in adversarial ordering, resume, isolated groups, self-links, stale sources, other-run links, root redirects, absent snapshots, publisher metadata, typography, conditional vacancy criteria and existing-task protection. The complete existing suite plus the first regressions passed (664 tests). After the final redirect fallback and three additional cases, the affected set passed again (37 tests; 667 tests are now collected in total). Ruff and diff whitespace checks passed. One pre-existing test-client deprecation warning remains.

Next: compare old and new classifications against the stored production data in a read-only run. Do not bulk-close legacy findings based on the synthetic proof. After that comparison, decide which historical alerts should be withdrawn and which require website work. UI simplification and role dependency workflows remain separate phases.

## Files

- `app/jobs.py`
- `app/services/crawl_reachability.py` (new)
- `app/services/internal_link_analysis.py`
- `app/services/structured_data_analysis.py`
- `app/services/recommendation_library.py`
- `app/services/recommendation_tasks.py`
- `tests/test_crawl_depth.py`
- `tests/test_orphan_pages.py`
- `tests/test_structured_data_analysis.py`
- `tests/test_recommendations.py`
- `docs/detection-advice-corrections-2026-09-16.md` (new)
