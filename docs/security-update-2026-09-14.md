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


## GitHub validation outcome

[Final diagnostic run](https://github.com/maurits-olylo/seotool/actions/runs/34846326439) at commit `a688328`:

- 654 tests pass on Python 3.12. Lint, Bandit, secrets scan and pip-audit pass.
- Both container images build successfully.
- Application scan: 44 HIGH package/advisory occurrences, 0 CRITICAL. Eight distinct CVEs remain: CVE-2025-69720, CVE-2026-16742, CVE-2026-54369, CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410, CVE-2026-9538. The scanner supplies no fixed package version for these on the selected distribution.
- Renderer scan: 2 HIGH OS occurrences of CVE-2025-3887, plus 2 HIGH Python findings (msgpack 1.1.2 / GHSA-6v7p-g79w-8964 and setuptools 70.3.0 / CVE-2025-47273). No CRITICAL findings.
- Setuptools 84.0.0 installs successfully; the older copy still reported by the scanner is not the newly installed top-level package. Pip upstream vendors setuptools 70.3.0, but exact image-level provenance and affected code still require verification; no risk exception is asserted.
- Ubuntu lists the Noble GStreamer fix as ESM Apps / Ubuntu Pro only: https://ubuntu.com/security/CVE-2025-3887 . No subscription was purchased and no packages were silently excluded.

Additional files changed during validation: `Dockerfile` and `Dockerfile.render` apply available distribution upgrades at build time. Their base digests stay pinned, but resulting OS package versions depend on the build date; retain CI evidence for each release. `requirements-render.lock` pins setuptools 84.0.0 with PyPI hashes. The renderer explicitly manages its disposable global Python environment with `--break-system-packages` because OS upgrades restore the EXTERNALLY-MANAGED marker. `.github/workflows/security-quality.yml` now emits JSON-based finding details; severity and blocking policy are unchanged.

Next work: assess/remove unnecessary runtime tooling or choose a supported alternative base, establish actual reachability of remaining findings, then rebuild and re-scan. Do not call this release security-approved or deploy it as a fully remediated security release while the gate remains red.
