# Security dependency update — 14 September 2026

Status: prepared locally; not deployed. Container scans and the full Python 3.12 test suite are pending.

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
- GitHub validation is pending explicit authorization to publish a control branch to the public repository and dispatch the existing security-quality workflow. Automatic approval review rejected that external publication; no push or dispatch was executed.
- Production is unchanged. A green dependency audit alone does not establish that the new OS/browser images are clean. Remaining high/critical findings must be evaluated after Trivy runs; no automatic exception is permitted.

## Sources

- [Cryptography changelog](https://cryptography.io/en/latest/changelog/)
- [Cryptography 50.0.1 release metadata](https://pypi.org/pypi/cryptography/50.0.1/json)
- [Playwright 1.62.0 release metadata](https://pypi.org/pypi/playwright/1.62.0/json)
- [Original failing workflow run](https://github.com/maurits-olylo/seotool/actions/runs/34829868961)

This update does not close the broader security gates documented in `docs/security-remediation-status-2026-08-11.md`.
