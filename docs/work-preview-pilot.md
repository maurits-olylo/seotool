# Read-only work preview pilot

## Scope and access

`/app/work-preview` requires a signed-in active user. Its data endpoint is
`GET /api/v1/websites/{website_id}/work-preview`, with website-level administrator
access and the existing superuser/API-key policy. Only Schipper and HUMAN hostnames
are enabled. No write methods, migrations, automatic tasks, notifications or crawls.

## Pilot 2: specific decisions and evidence

Each supported case has a first step, proposed role, completion criterion and an
explicit evidence reason. Duplicate metadata asks for a comparison of page roles;
404/sitemap findings require a status check and a business decision; orphan findings
ask for a route from the homepage; schema comparisons distinguish organizational
identity from page identity. Existing vacancy recommendation steps are retained.

- `verified`, `ignored`, `accepted_risk`: history, with different outcome wording.
- `resolved`: separate verification lane, not research or claimed success.
- Age-only findings: periodic editorial review, unless high severity or due date.
- Unknown types: unassessed; they remain visible.
- Supported uncertain cases: research with separate explanations for missing evidence,
  old evidence, newer analysis, changed destination/status, confidence and review status.
- Supported evidence-backed duplicates/missing-page cases: decision.
- Execute still requires existing assigned, planned/in-progress direct work, matching
  definition/version, no dependencies/input blockers, explicit steps and criteria,
  accepted/planned/in-progress issue, high confidence and current non-partial evidence.
  Zero execute is not evidence that no new work can be proposed.

Evidence compares HTTP findings with the latest page measurement; content findings
with the latest snapshot having a metadata hash (full extraction), not just the newest
light check. A changed HTTP status/destination or failed latest check blocks readiness.
Site-wide comparisons must belong to the latest completed full site crawl. Missing
snapshot references, missing explicit root-route evidence and old schema comparison
versions remain research. Seven days is a transparent pilot freshness assumption.
A partial crawl is not a blanket reason to hide results, but does not prove absence
of routes; the route warning appears only where relevant. No detectors are rerun.

Evidence details are allowlisted and bounded: duplicate values and counterpart URLs,
sitemap observations, root-route marker, schema type/field/value. Raw HTML and arbitrary
JSON are not displayed. Missing details are explicitly named. An observation time alone
does not prove current status, missing content, or full-site completeness.

## Content review candidates

The opportunity lane contains one review proposal per page with at least one stored
GSC query with 75 impressions in the selected 28-day window. The window ends on the
website's latest stored GSC query date, excluding future dates. At most three queries
per page are shown, with their measured clicks/impressions and the period. This is a
pilot selection threshold, not an SEO score, claim of missing answers, or page total.
Older windows require refreshing evidence first. Missing days are not treated as zero;
these are stored observations, not a guarantee of complete GSC coverage.

The SEO manager compares relevant queries with existing answers before deciding on
content changes. Only an actual missing feature requires a builder, followed by editorial
filling and verification. No automatic FAQ/schema instruction or promise of growth.
Existing tasks linked to that page remain visible as potentially related work, not
as evidence that those exact queries have already been addressed. No tasks are created.

## Interface and counting

The default excludes history; users can select all including history or history alone.
`include_history=true` enables history on the API; an explicit history lane also works.
Search and pagination apply to the selection. Counts cover the whole website, including
history and content proposals. `total_signals` and `total_opportunities` are separate;
neither is a count of unique actionable work packages. Shared-cause grouping and automatic
handoffs are still outside this pilot.

## Performance and security

Window queries project newest page/analysis snapshots and occurrences per website.
No page HTML/main content is loaded. Only displayed issue evidence JSON is loaded;
SQL query count does not increase per card. Stored query metrics aggregate within the
28-day window and select at most three qualifying queries per page. All queries and
task lookups are website-scoped. No external HTTP or AI requests occur. UI values are
escaped; links permit HTTP(S) only. Stale website responses cannot replace a newer view.

Local tests use synthetic SQLite data. Production PostgreSQL timings for pilot 2 and
its extra analysis/GSC queries must be checked after deployment; previous timings are
not proof of pilot-2 performance. Recheck the eight real cases and an existing task in
the signed-in interface before adopting the view as the daily work queue.

## Validation and deployment

Run pytest, Ruff, node --check app/ui/work-preview.js,
node tests/test_work_preview_ui.cjs and node tests/test_operations_ui.cjs.
The UI test checks default history selection, evidence rendering and escaping.
Backend regressions cover freshness, changed destination, history/verification,
missing site evidence, schema context, age-only review, GSC periods, existing work,
read-only access and authorization.

Deploy only the API after release checks. No migration or worker restart is needed.
No new database fields, dependencies or production records are introduced.
