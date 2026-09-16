# Internal link query and website switching correction

## Observed production behaviour

Release 31d0753: HUMAN internal-link ranking returned HTTP 504 in the signed-in
interface. Its partially successful full crawl remains usable. Schipper ranking
loaded successfully. Both stored recalculations completed successfully.

The signal screen retained the previous client's rendered rows while loading the
new selection, despite clearing its JavaScript data. A crawl scheduling message
also survived the selection change.

## Changes

- `app/services/internal_links.py`: replace composite NOT IN with NOT EXISTS over
  the same button-minus-anchor evidence set. PostgreSQL can plan an anti join,
  avoiding the NOT IN materialized-subplan risk when the estimated evidence set
  exceeds work_mem. No planner settings or timeout limits are changed. This is
  a suspected production bottleneck, not a confirmed production EXPLAIN result.
- Do not read previous-run link counts or snapshots when either crawl is partial:
  those results cannot be used for a trustworthy comparison. Keep the previous
  measurement date and existing null changes. Ranking and source lists retain
  identical form-only filtering; a real anchor wins over button evidence.
- `app/ui/app.js`: synchronously redraw cleared signals, clear selections and
  scheduling messages, and show loading text instead of stale counts or a false
  empty crawl history. Ignore stale errors as well as stale successful responses.
  Loading failures show an error instead of an indefinite loading indication.
- `app/ui/index.html`: update the script cache version.

## Validation and limits

Regression coverage: `tests/test_internal_links.py` and
`tests/test_operations_ui.cjs`. Existing fixtures cover duplicate links,
self-links, cross-website isolation, nofollow, historical form evidence, actual
anchors, partial crawls, and source-list consistency. Additional coverage checks
that partial crawls skip unused comparison queries and old rendered signal rows
and counts disappear before the replacement request finishes.

Local tests use SQLite; PostgreSQL production latency and its chosen query plan
still need verification after deployment. Do not claim the 504 is resolved until
one authenticated HUMAN request succeeds in a reasonable time. If it still times
out, inspect the production query plan and database activity read-only before
repeating requests or changing resource limits.

This correction changes no database schema, records, issue statuses, or crawl
scheduling. Only the API service needs deployment for this package; no worker or
scheduler restart, migration, full crawl, or stored recalculation is necessary.

Modified files: the three application files above, both regression-test files, `tests/test_api.py` (asset version),
and this document. Local acceptance reports under outputs remain untracked.
