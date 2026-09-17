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
