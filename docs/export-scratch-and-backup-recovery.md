# Export scratch storage and backup pause recovery

## Production evidence, 10 September 2026

The export worker's /tmp tmpfs is full (64 MiB, zero free bytes). The export volume has roughly 13 TiB free. The most recent Schipper export succeeded and the server recorded a download request; that timestamp does not prove the browser saved the file. IO_ENOSPC has not been conclusively traced to this worker: the failed browser action and the successful earlier export are distinct observations.

The crawl deployment pause started on 7 September and was updated at 01:00 UTC on 10 September, with one tracked job. The nightly backup wrapper activates the pause before waiting. Previously it set its cleanup flag only after that wait succeeded, so a timeout could leave the pause active. The production job state and backup logs are still needed to confirm that failure path occurred.

## Changes

- compose.yaml: export-worker uses a dedicated export_tmp_data volume at /tmp instead of the 64 MiB tmpfs. Its other hardening and memory limits remain in place. Docker initializes the volume from the container's /tmp permissions; verify writable access after recreation. Temporary export XML now uses disk capacity. The scratch volume is not application history and needs no backup; it may retain failed-export scratch files. No files are deleted by this change.
- scripts/scheduled-backup.sh: mark the pause and writer-stop operations before executing commands that may partially succeed. Cleanup attempts the normal guarded resume on timeout, retains failure status and reports restoration failures. It does not force unsafe crawl jobs to resume.
- tests/test_config.py: verify the isolated disk scratch mount and retained container hardening.
- tests/test_scheduled_backup_script.py: execute the shell wrapper with simulated pause failure, checking that resume is attempted and the original failure is preserved.

## Verification and rollout

41 targeted tests passed (configuration, scheduled backup and exports). Shell syntax, Ruff and whitespace checks passed. Docker is unavailable locally, so the live volume and end-to-end browser checks remain outstanding.

No database migration is required. Deliver the package using git archive and the agreed streaming upload. Only export-worker needs recreating to replace its tmpfs mount; the backup wrapper is a host file and requires no container rebuild. Check there is no current export job before recreation. Verify /tmp disk capacity, permissions and temporary exports afterward.

Before lifting the existing pause, inspect the active backup lock/process and the tracked crawl job. Use the existing guarded app.maintenance resume-crawls command only once ongoing backup work is excluded and the pause is safe. Do not remove a lock, overwrite crawl statuses, clear Redis or delete temporary files as an exploratory action. The wrapper cannot automatically repair an already abandoned pause or a stale running job.
