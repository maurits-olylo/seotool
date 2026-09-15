# Security dependency update — 14 September 2026

Status: published and validated on `codex/security-dependencies-20260914`; not deployed. Full tests pass, but the container security gate remains red.

## Changes

- `pyproject.toml`: cryptography >=50.0.1,<51 and Playwright 1.62.0.
- `requirements.lock`, `requirements-ci.lock`: cryptography 50.0.1 with wheel SHA-256 values verified against the PyPI release JSON. Other dependency versions remain unchanged. This targeted refresh was used because the Intel macOS pip-compile environment cannot resolve the new target wheels; CI must verify installation and resolution.
- `requirements-render.lock`: Playwright 1.62.0 wheel hashes from PyPI, matching the renderer image.
- `Dockerfile`: official Python 3.12.14 slim-trixie image pinned to its verified registry digest.
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
- Production is unchanged. A green dependency audit alone does not establish that the new OS/browser images are clean. Remaining high/critical findings must be evaluated after Trivy runs; no automatic exception is permitted.

## Sources

- [Cryptography changelog](https://cryptography.io/en/latest/changelog/)
- [Cryptography 50.0.1 release metadata](https://pypi.org/pypi/cryptography/50.0.1/json)
- [Playwright 1.62.0 release metadata](https://pypi.org/pypi/playwright/1.62.0/json)
- [Original failing workflow run](https://github.com/maurits-olylo/seotool/actions/runs/34829868961)

This update does not close the broader security gates documented in `docs/security-remediation-status-2026-08-11.md`.


## GitHub validation outcome — 15 September 2026

[Validated runtime and scan run](https://github.com/maurits-olylo/seotool/actions/runs/34945401996) at commit `4988de8`:

- 654 tests pass on Python 3.12. Lint, Bandit, secrets scan and pip-audit pass.
- Both container images build successfully.
- Renderer scan succeeds: zero HIGH or CRITICAL findings under the existing policy, including unfixed vulnerabilities.
- The actual renderer runs as its non-root user with no network, a read-only filesystem, dropped capabilities and temporary storage. Chromium launch, JavaScript, PNG screenshots, axe analysis and Fernet encryption/decryption pass.
- Application scan still fails: 44 package/advisory occurrences across eight distinct CVEs: CVE-2025-69720, CVE-2026-16742, CVE-2026-54369, CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410, CVE-2026-9538. No fixed package version is supplied by the scanner for these findings on the selected distribution. This is not proof that they cannot affect the application.
- The overall workflow correctly remains red. No findings have been suppressed, accepted or excluded.

## Final implementation

- `Dockerfile` and `Dockerfile.render` apply available distribution upgrades at build time. Base digests remain pinned, but resulting OS package versions depend on the build date; retain CI evidence for each release.
- `Dockerfile.render` retains the supported Playwright Noble image and removes unused Firefox/WebKit browser bundles and the two GStreamer bad-plugin packages. The application uses Chromium only. Its exercised rendering functionality continues to work; this test is not a guarantee for every website or media format.
- `requirements-render.lock` pins setuptools 84.0.0 with PyPI hashes. The renderer manages its disposable global Python environment with `--break-system-packages` because OS upgrades restore the EXTERNALLY-MANAGED marker.
- `Dockerfile.render` removes build-only pip and virtualenv after dependency installation, along with `/root/.cache/virtualenv`. The diagnostic run located the old package records in the upstream virtualenv pip cache, including its vendored code and inventory. Complete unused tooling/cache was removed, not just security inventory files.
- `scripts/verify-renderer-image.py` performs the offline runtime checks above.
- `.github/workflows/security-quality.yml` runs the actual image smoke test, reports residual package locations and emits JSON-based finding details. Severity and blocking policy are unchanged.

## Follow-up

The next phase should assess the remaining application OS dependencies and a supported minimal base, including runtime compatibility and vulnerability reachability. Do not remove essential libraries blindly or treat missing fixed versions as accepted risk. Do not deploy this as a fully remediated security release while the gate is red.

Changes were published only to `codex/security-dependencies-20260914`. GitHub main and NAS production remain unchanged. The original broader security gates in `docs/security-remediation-status-2026-08-11.md` remain open.
