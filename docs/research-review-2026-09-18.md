# Research Review — 2026-09-18

## Decision rule

Adopt capabilities, not projects. External repositories are classified as **USE**, **ADAPT**, **REFERENCE**, or **REJECT**. GPL/AGPL/proprietary code is not copied into the Health OS unless a later license decision explicitly permits it. Data licenses are evaluated separately from code licenses.

## Current canonical stack

| Capability | Decision | Current choice | Rationale |
|---|---|---|---|
| Android health store | USE | Health Connect 1.1.0 | Official Android path; no Google Fit API dependency. |
| Android local database | USE | Room 3.0.3 | Stable current release; exported schemas and migrations remain mandatory. |
| Android DB encryption | USE | sqlcipher-android 4.19.0 | Current supported SQLCipher Android integration; works with androidx.sqlite driver model. |
| Android build | USE | AGP 9.4 + Gradle 9.6.1 + Java 17 | Reproducible current toolchain; Gradle action updated to 9.6.1. |
| Background work | USE | WorkManager | Native Android scheduling and constraints; no extra scheduler. |
| Backend | USE | FastAPI + PostgreSQL 18.6 | Small operational surface and strong migration/audit support. |
| Sync | USE | Health OS deterministic sync | Keeps local-first semantics, explicit conflict policy and audit without another licensed service. |
| Nutrition primary | USE | USDA FoodData Central | CC0 and structured API; API key remains server-side. |
| Packaged food lookup | USE | Open Food Facts v3 | ODbL source with barcode coverage; provenance remains attached. |
| FIT parser | USE | fitdecode | Permissive adapter; official Garmin FIT SDK remains validation/reference only. |
| Build security | USE | Ruff, mypy, Bandit, pip-audit, Trivy, CodeQL | Complementary rather than duplicate gates. |
| Release provenance | USE | actions/attest / SLSA provenance | Public-repository Sigstore-backed attestations for APK/container release subjects. |

## New repositories reviewed

### Train Libre — REFERENCE

Useful patterns:
- offline-first workout/nutrition ownership;
- no mandatory account;
- opt-in AI;
- recovery, measurements and nutrition in one UX;
- explicit data/license attribution.

Reason not to copy: GPL-3.0 code; exercise catalogue has CC BY-SA 4.0 obligations. Concepts may be reimplemented independently.

### Skulpt — REFERENCE

Useful patterns:
- SQLite is the mobile source of truth;
- sync is optional and layered over local writes;
- workout logging works without server availability;
- health-store imports are scoped instead of copying the entire health store.

Reason not to copy: GPL-3.0 client. The Health OS already has a native Kotlin architecture, so a React Native migration would add cost without demonstrated benefit.

### NutriTrace — REFERENCE

Useful patterns:
- adaptive TDEE;
- USDA + Open Food Facts quality signals;
- explicit self-hosted privacy model;
- read-only MCP/federation concepts;
- migration tooling from other nutrition trackers.

Reason not to copy: AGPL-3.0. The Health OS may reproduce ideas and contracts independently but should not incorporate NutriTrace implementation code.

### ALIS Health — REFERENCE

Useful patterns:
- self-hosted Health Connect cockpit;
- health/nutrition/AI separation;
- pairing workflow;
- security preflight before publication.

Reason not to copy: AGPL-3.0 and a young project. Security/publication ideas can be reimplemented independently.

## Public-repository hardening

The canonical repository now includes:
- rewritten branch history based on the clean initialization commit plus sanitized current snapshot;
- synthetic fixtures only in the current tree;
- repository, container and secret scans;
- CodeQL for Python and Java/Kotlin;
- Dependabot for Python, Gradle and GitHub Actions;
- non-root production container;
- build provenance workflow using GitHub artifact attestations;
- a one-time `public` event workflow that deletes pre-public Actions runs and dispatches the complete CI and CodeQL gates.

## Rejected additions

- PowerSync: technically strong but adds a server/runtime and licensing/operational surface that is not justified by current single-user local-first requirements.
- Firebase/analytics SDKs: no requirement justifies sending health telemetry to another platform.
- one microservice per coaching role: agent roles remain logical roles sharing deterministic engines.
- another nutrition engine: all providers normalize into the existing provenance-aware nutrition contract.
- GPL/AGPL workout apps as forks: use as design/architecture references only.

## Next research targets

1. Health Connect fake/test APIs and real-device automation coverage.
2. Wear OS Health Services only if a wearable workflow is actually required.
3. Android Credential Manager / hardware-backed attestation for stronger future device enrollment.
4. Google Cloud Run + managed PostgreSQL/KMS deployment only after the local/container full gate is green.
5. Read-only MCP contract for Research AI / Segundo Cérebro after the core API permissions model is stable.
