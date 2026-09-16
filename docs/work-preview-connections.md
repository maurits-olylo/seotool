# Work preview: sources, groups and existing tasks

The preview stays read-only. No issue, task, ownership or workflow status is changed.

## Sources and navigation

Cards can load referring pages from the latest completed full crawl using the existing,
website-authorized sources endpoint. The UI shows the crawl date, warns about partial
coverage, paginates sources, and rejects responses after a website/selection change.
An empty list is not proof of an orphan page. Source URLs and anchor text are escaped.

Signal/task links pass entity IDs and website context to `/app`. The main UI resolves
both through authorized endpoints, verifies that the target belongs to the website,
loads that client/website, then opens the exact issue/task. It never trusts a URL-supplied
client ID. Missing or mismatched targets show an error without opening a different item.

## Duplicate cards

Only duplicate titles and meta descriptions are grouped. Every member must independently
name the same complete URL set and exact shared value from the same crawl. Lane, issue
status, severity, evidence readiness and guidance must agree. Partial or contradictory
groups stay separate. Grouping happens before search and pagination; any member URL finds
the group. Raw lane counters and total_signals remain signal counts; total is card count.
Member IDs, dates, source access and existing tasks are preserved. Stored issues never merge.

## Task readiness

Task detail uses the preview's evidence assessment scoped to all linked issues and the
specific task. It does not query search-performance proposals for this check. One blocking
issue prevents an execution recommendation. Missing assessment falls back to review.
The main task panel shows the same reason and next step. Closed and implemented task
states retain their completion/verification meaning. This is guidance, not a new API
permission or status-transition restriction; existing manual controls remain available.

Historical PostgreSQL evidence is still selected as complete raw JSON text and decoded
in Python; JSON field extraction must not reintroduce escaped-NUL failures.

## Validation

Python regressions cover reciprocal grouping, conflicting evidence/statuses, counts,
search/pagination and task/preview agreement. Node regressions cover website/task routing,
review fallback, source pagination and HTML escaping. Visual checks use synthetic data.
A real PostgreSQL escaped-NUL test remains required in CI before release.
