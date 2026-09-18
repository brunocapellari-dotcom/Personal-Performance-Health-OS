# Personal Performance & Health OS

Canonical repository for a local-first personal performance system.

## Mission

Turn goals into measurable training, nutrition and recovery decisions through the invariant flow:

`goals → baseline → gaps → priorities → periodization → sessions → execution → response → adaptation → independent audit`

The deterministic core owns progression, safety and policy. AI may interpret context, plan within policy, explain decisions and synthesize evidence; it cannot invent arbitrary loads, alter prescribed medication, bypass environment constraints or override safety gates.

## Production architecture

The repository is one product, not a collection of disconnected prototypes:

- **Android native client** — Kotlin/Compose, Health Connect read integration, Room 3, SQLCipher, Android Keystore, offline queue and device-bound signing key.
- **Core API** — Python/FastAPI with deterministic engines and logical AI roles.
- **PostgreSQL 18** — canonical synchronized entity history, append-only health/training events and audit trail.
- **Encrypted object storage** — photos/FIT/GPX/media blobs, with a key independent from encrypted backups.
- **Research AI + Segundo Cérebro** — evidence packages and validated knowledge through explicit contracts; no duplicate research corpus inside Health OS.
- **Production image** — non-root multi-stage container; canonical Compose stack keeps PostgreSQL on an internal network.

The named AIs are logical roles inside one orchestration runtime, not always-on microservices. `Performance Director` plans and `Program Auditor` evaluates independently. Safety policies sit below both.

## Implemented capabilities

- goal-gap calculation and conflict allocation (`DEVELOP`, `MAINTAIN`, `REDUCE_TEMPORARILY`);
- multi-signal readiness with pain safety gate;
- deterministic strength progression;
- adaptive TDEE inference from intake and weight trend;
- environment/equipment/noise/space/fixation-aware exercise selection;
- event-specific periodization and missed-workout recalculation;
- structured strength/conditioning prescriptions and Planned × Performed features;
- body trend and assessment engines;
- medication dose-change hard guard;
- next-block orchestration plus independent audit;
- PostgreSQL/Alembic persistence and idempotent bidirectional sync;
- device enrollment and ECDSA P-256 challenge-response authentication;
- HMAC-chained audit trail;
- AES-GCM encrypted blobs and independently encrypted database backups;
- operational `healthos-ops backup`, `restore --destructive`, and `audit-verify` commands;
- Android Health Connect differential ingestion with per-record-type tokens, backfill and tombstones;
- backend sync that remains available when Health Connect permission is absent;
- USDA FoodData Central search and Open Food Facts v3 barcode adapters with provenance/licence metadata;
- GPX/CSV/FIT adapter contracts and source-quality policies;
- full-system CI gate for backend, Android and the production container.

## Data-source hierarchy

Nutrition and activity data are federated rather than pretending one database is universally authoritative:

- USDA FoodData Central: canonical open nutrient reference (CC0);
- TACO/NEPA-Unicamp: Brazilian composition reference with source citation;
- Open Food Facts v3: packaged/barcode complement, retaining ODbL provenance and community-data quality;
- TBCA/USP-FoRC: controlled reference only under its current noncommercial/no-derivatives terms unless separate permission is obtained;
- Health Connect: canonical Android interchange layer for user-authorized personal records;
- `fitdecode`: default permissive FIT parser; official Garmin FIT SDK only as optional interoperability validator after licence review;
- wger: exercise discovery/API reference, not an AGPL code fork.

See `docs/DATA-SOURCES.md`, `docs/source-registry.md` and `healthos/source_policy.py`.

## Security and public-source boundary

This repository can be public without making personal health data public. Real `.env` files, databases, health imports, photos, FIT/GPX/TCX files, backups and private exports are excluded from Git. CI fixtures are synthetic.

Production requires PostgreSQL, independent high-entropy secrets, independent blob/backup keys, encrypted local Android storage and TLS at the deployment edge. Repository scans block secrets, high/critical vulnerabilities and material misconfiguration.

## Complete-project verification

No change is promoted after testing only the edited module. The same commit must pass:

`PostgreSQL migrations + full Python suite + static/security checks + API fuzzing + Android tests/lint/debug/release + Room schema + repository scan + production container smoke test + image scan + CodeQL`

The final release gate additionally requires a physical Android device completing:

`Health Connect/local encrypted state → device auth → sync → PostgreSQL → planner → auditor → returned block → performed session → next adapted prescription`.

See `docs/e2e-acceptance.md`.

## Operations

The production container never embeds secrets. Deployment injects them externally. Migrations run explicitly before the API is started. Backups are encrypted and restore verifies the audit chain before completion.

## Non-negotiable medical rule

The system must never change, suspend, replace, increase or decrease a prescribed medication dose. Interaction signals produce an alert and referral to a physician or pharmacist.
