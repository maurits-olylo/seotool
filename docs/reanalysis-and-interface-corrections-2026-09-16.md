# Stored reanalysis and interface corrections

## Problem and resulting behavior

The signed-in acceptance check found that recalculation replays the latest full crawl
even when later light checks exist. A repeated interpretation must not reopen a repaired
issue, resolve a newer error, or count as a second measurement proving a repair.

Recalculation now runs with a scoped session policy. Latest snapshot identities are
selected per URL with a database window query. Superseded page snapshots are skipped,
including job-listing updates and direct legacy schema reclassification. General
reconciliation also enforces this boundary for contextual checks. Unproven site-wide
aggregates are deferred when the latest observations belong to mixed runs. Checks with
no page snapshot cannot override a current page diagnosis during this operation.

On eligible stored evidence, a disappearing active finding becomes `review`, never
`resolved` or `verified`. Previously resolved, verified, ignored and accepted-risk
findings remain untouched. Repeating the operation does not advance verification or
refresh an existing finding's measurement timestamp. Normal new-crawl reconciliation
keeps its existing lifecycle. The policy is cleared even when analysis fails.

Positive graph routes still support the existing evidence-based orphan review; this
does not claim current website repair. Consequently recalculation is deliberately not
a substitute for a fresh full crawl. A superseded schema measurement may remain deferred
instead of receiving an apparent clean bill of health. Job settings record the source
run, candidate snapshot count and skipped superseded snapshot count. Existing history,
changes, tasks and customer agreements are not deleted or rewritten by a bulk cleanup.

## Link reports

Counts and paginated source lists both exclude same-crawl source/target pairs proven
to be form actions without a real anchor. SQL set difference avoids per-row evidence
queries and large parameter lists. A real anchor to the same destination takes precedence;
without historical element evidence, the link remains. Previous and current rankings
use the same rule. Raw historical links remain stored. A form URL can still appear as
a known URL or technical URL, but form-only submissions no longer make it a linked error.

## Interface and advice

Both client and website selection clear cached operation, report and vacancy data and
refresh the selected view. Late issue responses are discarded when their request or
selected website/client no longer matches. Client website-list responses also check
the selected client before updating the selector.

Vacancy issue detail uses the current `decide_vacancy_disposition` recommendation for
steps and completion criteria. The vacancy owner first chooses active, closed-but-kept,
or removed; the content and development roles act on that decision. This is read-time
guidance, not an edit to existing execution tasks or stored customer instructions.

## Changed files

- `app/services/reanalysis.py` (new)
- `app/jobs.py`
- `app/services/analysis.py`
- `app/services/issue_engine.py`
- `app/services/structured_data_analysis.py`
- `app/services/internal_links.py`
- `app/services/issue_guidance.py`
- `app/ui/app.js`
- `app/ui/index.html`
- `tests/test_issue_recalculation.py`
- `tests/test_issue_engine.py`
- `tests/test_internal_links.py`
- `tests/test_issue_guidance.py`
- `tests/test_operations_ui.cjs`
- `docs/reanalysis-and-interface-corrections-2026-09-16.md` (new)

## Validation and release boundary

Regression tests cover a newer 404, older schema evidence, repeated same-measurement
assessment, preserved terminal statuses, exception cleanup, form-vs-anchor ranking and
source consistency, live guidance without record mutation, both selection handlers and
late issue responses. Run `pytest`, `ruff check app tests scripts`, `node --check app/ui/app.js`
and `node tests/test_operations_ui.cjs`.

No new dependency, migration or production operation is included in this phase. A release
must still validate its exact revision and perform signed-in acceptance after deployment.
Expired Google authorization and historical dead letters are separate diagnostic work;
this patch does not claim to repair those operational findings.
