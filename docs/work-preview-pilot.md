# Read-only work preview pilot

## Scope and access

`/app/work-preview` requires a signed-in active user. Its data endpoint is
`GET /api/v1/websites/{website_id}/work-preview`, with website-level administrator
access and the existing superuser/API-key policy. Only the Schipper and HUMAN
hostnames are enabled for this pilot. Static assets contain no customer data.
There are no write methods, migrations, automatic tasks, notifications or crawls.
The signals page links to the separate preview; existing navigation stays intact.

## Classification

The preview returns a lane, reason, first step, proposed role, completion check,
measurement references and all existing linked tasks for each issue. It deliberately
does not bundle identical issue types into a supposed shared cause. Counts represent
issues, including history, not deduplicated work packages. Unknown types remain
visible in `unassessed`. Pagination and search apply after classification; distribution
counts cover the full website, regardless of the active search or lane filter.

- Verified, ignored and accepted-risk records go to history, with distinct wording.
  Resolved records still awaiting verification go to research.
- Age-only findings go to periodic review, unless elevated to high severity or an
  explicit due date has arrived. This does not assert their content is correct.
- Missing/old/superseded measurements, non-high confidence and review status lead
  supported active cases to research. Evidence alignment means the occurrence
  snapshot matches the newest snapshot of that URL, is at most seven days old and
  belongs to a successful or partial run. Seven days is an explicit pilot assumption,
  not a general freshness guarantee. Missing page snapshots cannot establish readiness.
- Supported missing-page/vacancy/duplicate-content cases require a decision.
- Supported link, route and schema cases remain research by default. A 'direct'
  template alone does not authorize work or establish a suitable replacement URL.
- Execute requires existing assigned, planned/in-progress direct work, no listed
  dependency or missing input, matching current recommendation key and version,
  nonempty steps and acceptance criteria, an accepted/planned/in-progress issue,
  high confidence, aligned recent evidence and a non-partial source crawl.
  This is readiness of existing approved work, not automated creation of a new plan.

The model's text dependencies are not converted into a workflow engine. Old tasks
remain visible; they are not overwritten. The preview does not revisit actual pages,
claim repair, re-run detectors or turn newer light checks into full link evidence.

## Performance and security

The service uses batched queries and narrow window projections for newest snapshots
and occurrences. It does not load snapshot HTML or main content. Query count does not
grow per displayed card. Ranking of urgency is independent of lane. No external HTTP
calls or AI services are used. Customer strings in the UI are escaped and only HTTP(S)
links are enabled. Stale client responses cannot replace a newly selected website.

Local validation uses synthetic SQLite fixtures. Production PostgreSQL performance
with full retained histories is not yet measured; check read-only timing after deployment
before broad use. Desktop layout and filtering were inspected in a local browser with
clearly labelled synthetic examples. This is not a production pilot result.

## Changed files

- app/services/work_preview.py
- app/api/routes/recommendations.py
- app/api/routes/ui.py
- app/ui/index.html
- app/ui/work-preview.html
- app/ui/work-preview.css
- app/ui/work-preview.js
- tests/test_work_preview.py
- docs/work-preview-pilot.md

Run pytest, ruff check app tests scripts, and node --check app/ui/work-preview.js.
Deploy only the API after release checks. No worker restart or migration is needed.
Next acceptance: open both sites, inspect category counts and the eight earlier cases,
check existing tasks and missing evidence, and confirm unchanged issue/task counts.
Actual regrouping into work packages and automatic handoffs remain later work.
