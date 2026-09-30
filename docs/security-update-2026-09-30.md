# PyJWT security update — 30 September 2026

## Scope

The release based on `08464cd` was blocked by ten dependency-audit findings and
six findings in each container image for PyJWT 2.13.0. Update only the PyJWT
entry in `requirements.lock` and `requirements-ci.lock` to 2.15.1. Other package
versions, application behavior and database schema remain unchanged.

PyJWT is a transitive Redis dependency. The application has no direct JWT calls.
Version 2.14.0 fixes the reported advisories; 2.15.1 also includes the subsequent
payload handling and decoding compatibility fixes. Use the current patched
version rather than stopping at 2.14.0.

Sources checked on 30 September 2026:

- https://pyjwt.readthedocs.io/en/stable/changelog.html
- https://pypi.org/pypi/PyJWT/2.15.1/json

Both binary-only lockfiles use the official universal wheel SHA-256:
`42d59d631f7768a1028a64c7ff581a9bf7519804daf91fc5b6c56e30eec5e193`.
The targeted lock edit avoids unrelated dependency upgrades. A fresh hashed
installation and dependency resolution in Linux CI remain mandatory.

## Verification and release gate

Install the updated wheel with hash verification before running local tests.
Run the existing Python and JavaScript suites, Ruff, Bandit, secret scanning and
the production-lock vulnerability audit. The local audit uses `--no-deps
--disable-pip --strict` against the fully pinned lock; it does not validate
Linux dependency resolution.

The existing macOS environment has stale installed project metadata and an older
cryptography version than the Linux lockfile. Its `pip check` is not a clean
release-environment result. The existing GitHub workflow must install the full
CI lock in Python 3.12, pass `pip check`, run PostgreSQL tests, build both images,
exercise both offline runtimes and pass both blocking image scans. Keep all
scan severities and blocking policies unchanged. Record results and exact commit
in the release manifest; do not deploy an unverified commit.

## Deployment scope

Both `Dockerfile` and `Dockerfile.render` install `requirements.lock`. Rebuild
and restart all running Python services: `api`, `worker`, `crawl-worker-2`,
`crawl-worker-3`, `integration-worker`, `maintenance-worker`, `export-worker`,
`render-worker` and `scheduler`. Check for active jobs before restarting workers.
Update the images for the on-demand `migrate` and `render-artifacts-init`
services as well; neither requires a separate persistent restart.

PostgreSQL and Redis images and volumes are unaffected. There is no migration
and no data rewrite, so this change does not require an additional release
database backup. Use the existing interactive NAS deployment route, wait the
required 40 seconds after restarts and verify health, worker registrations and
PyJWT 2.15.1 in each running Python service. Include the pending UI fixes from
`08464cd` in the same release archive.

The explicitly blocked `outputs/release-08464cd` deployment drafts must remain
blocked; create new scripts and an archive for the newly validated commit.
