# Security dependency update — 14 September 2026

Status: published and validated on `codex/security-dependencies-20260914`; not deployed. The full security-quality workflow is green for runtime commit `95a166c`.

## Changes

- `pyproject.toml`: cryptography >=50.0.1,<51 and Playwright 1.62.0.
- `requirements.lock`, `requirements-ci.lock`: cryptography 50.0.1 with wheel SHA-256 values verified against the PyPI release JSON. Other dependency versions remain unchanged. This targeted refresh was used because the Intel macOS pip-compile environment cannot resolve the new target wheels; CI must verify installation and resolution.
- `requirements-render.lock`: Playwright 1.62.0 wheel hashes from PyPI, matching the renderer image.
- `Dockerfile`: Ubuntu 24.04 LTS pinned to its verified registry digest, with distribution-maintained Python 3.12 and an isolated `/opt/venv` built in a separate stage.
- `Dockerfile.render`: Playwright 1.62.0 noble and refreshed Node 22 bookworm-slim build-stage digest, verified through registry manifests.
- `tests/test_config.py`: expected image versions updated.

## Evidence and remaining work

- 29 local configuration tests passed; repository Ruff check passed.
- pip-audit against the updated fully pinned production lock reported no known vulnerabilities. The audit used `--no-deps --disable-pip --strict`, scanning the packages explicitly present in the complete lock; Linux resolution is a separate check.
- Hashed dry-run resolution for the combined production and renderer locks passed for Linux x86_64 / Python 3.12; no packages were installed.
- No vulnerability exclusions or scan-policy relaxations were added.
- Docker is not running locally. Local Python tests with the old installed cryptography package would not validate the upgrade.
- Cryptography 49+ no longer ships Intel macOS wheels. Linux/Python 3.12 remains the production and CI validation target; no unsupported local wheel is substituted.
- The user subsequently explicitly authorized publication and workflow execution on the control branch. That authorization was used; production and GitHub main were not updated.
- Production is unchanged. The dependency audit and both container scans pass for the final tested build; no scan exceptions were introduced.

## Sources

- [Cryptography changelog](https://cryptography.io/en/latest/changelog/)
- [Cryptography 50.0.1 release metadata](https://pypi.org/pypi/cryptography/50.0.1/json)
- [Playwright 1.62.0 release metadata](https://pypi.org/pypi/playwright/1.62.0/json)
- [Original failing workflow run](https://github.com/maurits-olylo/seotool/actions/runs/34829868961)

This update does not close the broader security gates documented in `docs/security-remediation-status-2026-08-11.md`.


## Intermediate renderer validation — 15 September 2026

[Validated runtime and scan run](https://github.com/maurits-olylo/seotool/actions/runs/34945401996) at commit `4988de8`:

- 654 tests pass on Python 3.12. Lint, Bandit, secrets scan and pip-audit pass.
- Both container images build successfully.
- Renderer scan succeeds: zero HIGH or CRITICAL findings under the existing policy, including unfixed vulnerabilities.
- The actual renderer runs as its non-root user with no network, a read-only filesystem, dropped capabilities and temporary storage. Chromium launch, JavaScript, PNG screenshots, axe analysis and Fernet encryption/decryption pass.
- Application scan still fails: 44 package/advisory occurrences across eight distinct CVEs: CVE-2025-69720, CVE-2026-16742, CVE-2026-54369, CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410, CVE-2026-9538. No fixed package version is supplied by the scanner for these findings on the selected distribution. This is not proof that they cannot affect the application.
- The overall workflow correctly remains red. No findings have been suppressed, accepted or excluded.

## Renderer implementation

- `Dockerfile` and `Dockerfile.render` apply available distribution upgrades at build time. Base digests remain pinned, but resulting OS package versions depend on the build date; retain CI evidence for each release.
- `Dockerfile.render` retains the supported Playwright Noble image and removes unused Firefox/WebKit browser bundles and the two GStreamer bad-plugin packages. The application uses Chromium only. Its exercised rendering functionality continues to work; this test is not a guarantee for every website or media format.
- `requirements-render.lock` pins setuptools 84.0.0 with PyPI hashes. The renderer manages its disposable global Python environment with `--break-system-packages` because OS upgrades restore the EXTERNALLY-MANAGED marker.
- `Dockerfile.render` removes build-only pip and virtualenv after dependency installation, along with `/root/.cache/virtualenv`. The diagnostic run located the old package records in the upstream virtualenv pip cache, including its vendored code and inventory. Complete unused tooling/cache was removed, not just security inventory files.
- `scripts/verify-renderer-image.py` performs the offline runtime checks above.
- `.github/workflows/security-quality.yml` runs the actual image smoke test, reports residual package locations and emits JSON-based finding details. Severity and blocking policy are unchanged.

## Final application correction and validation

The application now uses official Ubuntu 24.04 LTS, digest
`sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254`,
with Ubuntu-maintained Python 3.12. Security fixes are backported by the distribution;
the upstream Python patch number alone is not an indicator of its patch status.
See [Ubuntu release notes](https://documentation.ubuntu.com/release-notes/24.04/).

A separate build stage installs the hashed lockfile into `/opt/venv`. The final image
contains the runtime and installed dependencies, without pip or the venv installation
packages from the build stage. UID/GID 10001, service commands and export directory
permissions are preserved. No database migration or application behavior change is included.

[Successful full workflow](https://github.com/maurits-olylo/seotool/actions/runs/34955863726)
at runtime commit `95a166c`:

- 654 tests pass; Ruff, Bandit, secrets scan and locked dependency audit pass.
- Both container images build and both Trivy scan gates succeed: zero HIGH/CRITICAL
  findings under the existing policy, including unfixed findings. No suppression or
  severity-policy change was made.
- Actual application image: non-root UID, native Python module imports, TLS trust roots,
  timezones, Fernet encryption, lxml parsing, Excel write/read and the API health endpoint
  with SQLite pass without network, with a read-only filesystem and dropped capabilities.
- Actual renderer image: non-root Chromium, JavaScript, PNG screenshots, axe and Fernet pass
  under the same restricted runtime conditions.
- 29 local configuration tests and local Ruff validation also passed.

Additional changed files in this phase: `Dockerfile`, `tests/test_config.py`,
`scripts/verify-application-image.py`, `.github/workflows/security-quality.yml`,
`docs/architecture.md`, and this report.

## Release boundary

The new runtime has not been exercised against the NAS PostgreSQL/Redis services or live
crawl workloads. Those require deployment-specific checks. The image smoke test is a
compatibility check, not an end-to-end production validation. Rebuilds pull current OS
updates and therefore require renewed scan evidence.

Changes were published only to `codex/security-dependencies-20260914`. GitHub main and NAS
production remain unchanged. Next phase: prepare the approved NAS release and its health,
worker and export checks through the existing deployment route. This green workflow closes
these dependency/container findings for the tested build; it does not automatically close
unrelated gates in `docs/security-remediation-status-2026-08-11.md`.
