# Export and system status correction

## Problem and behavior

The export dataset queried full users even when no task had an assignee. The export database role deliberately cannot read credentials, so PostgreSQL rejected the query. Exports now skip empty assignee lookups and select only id, display_name and email. Migration 0066 grants SELECT on those three columns to an existing seo_export role. The role bootstrap script grants the same columns for fresh installations and later role refreshes. Passwords, MFA and sessions remain inaccessible under the existing restricted role policy.

The operations UI previously displayed missing status as zero workers and a failed database. It now displays unknown counts explicitly and retains the status request error. The status endpoint catches failures of the actual monitoring-table queries as well as connectivity failures, rolls back the failed transaction and still checks workers independently. Redis failures return unknown worker counts rather than measured zeros. Failed database checks return unknown incident/dead-letter counts.

## Files

- app/services/exports.py
- app/api/routes/system.py
- app/ui/app.js
- scripts/database-roles.sql
- alembic/versions/0066_export_user_labels.py
- tests/test_exports.py
- tests/test_system_status.py
- tests/test_operations_ui.cjs
- docs/operations-export-fix-2026-09-09.md

## Local validation

- 50 tests passed: tests/test_exports.py, tests/test_system_status.py, tests/test_config.py.
- JavaScript syntax check and tests/test_operations_ui.cjs passed.
- Ruff and whitespace checks passed for the changed code.
- Alembic identifies 0066 as the only head; PostgreSQL offline migration SQL generated successfully.
- Local Python is 3.13; production image uses Python 3.12.
- Docker daemon is unavailable locally. A live PostgreSQL role/migration test and production acceptance remain required; SQLite tests do not validate PostgreSQL privileges.

## Next phase: diagnosis and rollout

First inspect production container health, migration revision and the authenticated system/status response in the existing interactive NAS shell. No second NAS login or remote Docker command is needed. Do not infer actual stopped workers from the previous UI screenshot.

Validate migration 0066 on isolated PostgreSQL with an existing seo_export role: those three columns must be readable, password_hash and MFA columns must remain denied, and an export with an assigned task must succeed. Test upgrade, downgrade and re-upgrade; role provisioning after the migration must preserve the restricted access.

Use the agreed local git archive, streaming SSH upload and existing interactive NAS-shell deployment route. Only api and export-worker require rebuilding for this code change. Apply migration 0066 before restarting those services, then wait the required 40 seconds before health checks. Restart other workers only if independent diagnosis shows it is needed.

The migration changes only reversible column privileges and rewrites no data, so this change does not itself require an additional full backup. For rollback, coordinate the application rollback and the 0066 downgrade; the previous export code retains its known defect.

Acceptance: authenticated system status; real worker counts; a small crawl on the selected website; CSV and Excel exports including an assigned task; download and inspect output. Retrying a previously failed export requires a new export request, not just a worker restart. No deployment or production mutation has been performed in this phase.
