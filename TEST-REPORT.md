# Verification Report — 2026-09-18

## Evidence status

The repository history has been rewritten for public release safety. The default branch now starts from the clean initialization commit and a sanitized final-production snapshot; subsequent commits contain only public-safe project changes.

Historical CI evidence before the history rewrite proved the executable core on PostgreSQL/Python: compileall, Ruff, Ruff format, strict mypy, Bandit, pip-audit and 24/24 tests passed. That evidence remains useful but **does not certify the current final-production tree** because Android, container, backup/restore, nutrition adapters, release attestations and additional security gates were added afterward.

The current tree therefore remains **IMPLEMENTED / AWAITING COMPLETE POST-PUBLIC REGRESSION**.

## Current mandatory full-project gate

A release candidate is accepted only when the same current commit passes:

- PostgreSQL 18.6 service and Alembic upgrade/check;
- Python compile, Ruff, formatting, strict mypy, Bandit and pip-audit;
- full pytest regression with branch coverage threshold >= 85%;
- authenticated OpenAPI fuzzing;
- Android unit tests, lint, debug build and release/R8 build;
- Room schema/migration validation;
- repository secret/vulnerability/misconfiguration scan;
- non-root production container build and smoke test;
- Trivy HIGH/CRITICAL image scan;
- CodeQL for Python and Java/Kotlin;
- encrypted backup/restore tests and audit-chain verification;
- release subject checksums, SBOM and GitHub/Sigstore artifact attestations.

## Public transition

The current tree contains a `public`-event workflow on the default branch. When repository visibility changes from private to public it:

1. deletes pre-public GitHub Actions runs;
2. dispatches the complete full-project CI on `main`;
3. dispatches CodeQL on `main`.

No current claim of 100% green is made before those dispatched runs finish successfully.

## Final release acceptance

Automated CI is necessary but not sufficient. Final acceptance still requires a physical Android device executing:

Health Connect → encrypted local DB → device authentication → bidirectional sync → PostgreSQL → next-block planner → independent auditor → performed session → next sync → materially changed next prescription.

No production-complete status should be declared before that path passes with real-device evidence.
