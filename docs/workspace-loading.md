# Workspace loading and recovery instructions

Direct preview links now resolve their authorized website, task and issue before the
ordinary workspace bootstrap. Client/website selectors load once without the complete
signal/URL inventory. Already retrieved task and issue details are reused by the dialog.
Issue detail includes normalized_url, so a direct link need not download every URL just
to label one page. Historical inspection and task detail load concurrently.

Normal startup shows an explicit loading status, then activates the requested view.
Signal/URL inventory reads are deduplicated while in flight and reused within the selected
website. The dashboard, signal, URL and change views request that inventory when needed;
other screens do not block on it. Reports, report archives and vacancies no longer load
as a side effect of every signal refresh. Website switches invalidate the inventory and
reload the current view. No shared/persistent cross-user data cache was introduced.

Loading/error states replace temporary dashboard signal zero counts. The selected issue
is retained independently of the list so task updates also work after a direct opening.
Late notification, inspection and task responses are checked against current selection.

Resolved diagnoses show recovery verification, not another repair instruction. Historical
signals are identified as handled. The task readiness instruction also informs the general
diagnosis step. The verification section does not tell users to mark work implemented when
the signal already awaits verification. Status transitions and automatic verification
behavior are unchanged; this release does not invent proof of work or recovery.

## Boundaries and acceptance

The URL inventory itself remains paginated in batches of 1000; dashboard/signal inventory
queries may still need backend optimization after measuring. This change removes known
unnecessary/duplicate work, not every possible latency source.

Local tests exercise direct startup, reused detail payloads, in-flight deduplication,
website mismatches, late responses and recovery instructions. After deployment measure
Schipper and HUMAN startup and direct task navigation using the same session conditions.
Record time to usable target and errors; do not compare a production timing to a mocked
unit-test duration. Validate reports, URLs, changes and website switching as well.

## Independent dashboard reads

The dashboard now uses a compact authorized `issue-summary` response (counts and at most
five items), sharing the existing list's visibility/grouping rules. It does not download
the URL inventory, impact enrichment, suppressions, coverage, exports or system health.
The selected signal filter no longer changes dashboard totals. The summary still evaluates
visible issues on the server; this is not a constant-time aggregate query.

Each dashboard panel renders as its own request completes and distinguishes loading,
failed and genuinely empty results. In-flight dashboard reads are deduplicated and scoped
to a selection object: late replies cannot overwrite a later selection, including A–B–A.
Crawl overview requests only the latest run. Existing report and vacancy endpoints remain
in use; they may still require further optimization based on production measurements.

Changes retain the full paginated history for correct grouping, including domain swaps.
Their API reads only snapshot IDs, crawl IDs and check dates, not full snapshot content.
Each change includes its authorized URL label so dashboard changes do not need the URL
inventory. Successful task/issue deep links consume their navigation query parameters
while retaining unrelated query parameters and the current view hash.

Regression checks cover summary/list grouping parity, active-only and website isolation,
bounded output, authorization, URL labels and lightweight snapshot queries, independent
panel rendering, failure states, real zeros, deduplication and stale responses.
Production loading times still require a new browser measurement after deployment.
