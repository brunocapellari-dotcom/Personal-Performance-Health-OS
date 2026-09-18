# Gap Analysis — 2026-09-18

## Implemented

- standalone canonical repository referenced by the Holding;
- deterministic goal, conflict, readiness, progression, event, missed-workout, nutrition and audit engines;
- FastAPI backend with PostgreSQL/Alembic contracts;
- ECDSA device enrollment/challenge authentication;
- idempotent bidirectional sync and explicit conflict storage;
- append-only health-event semantics;
- HMAC-chained audit log;
- encrypted blob storage;
- encrypted backup/restore with separate key and restore verification;
- Android Kotlin/Compose client;
- Room 3 + SQLCipher + Android Keystore local storage;
- Health Connect differential sync by record type and bounded background worker;
- sync independent from Health Connect consent;
- USDA FoodData Central and Open Food Facts normalized adapters;
- source-license/use policy enforcement;
- Docker production artifact and isolated database network with controlled API egress;
- Ruff, mypy, Bandit, pip-audit, Schemathesis, Trivy, CodeQL and Dependabot gates;
- release APK/container checksums, SBOM and artifact-attestation workflow;
- sanitized branch history and post-public Actions-history cleanup workflow.

## Remaining acceptance gates

These are release gates, not future modules:

1. change repository visibility to public so GitHub-hosted runners are available;
2. complete current-tree full-project CI and CodeQL successfully on the same sanitized source state;
3. fix every real CI/build/security failure without weakening gates;
4. deploy backend behind real TLS with managed secrets/KMS and production PostgreSQL;
5. configure production Android API endpoint and signing identity;
6. execute Android instrumentation/fake Health Connect tests where supported;
7. execute physical-device Health Connect and offline/online sync validation;
8. connect Calendar, Research AI and Segundo Cérebro through scoped contracts;
9. expand exercise catalogue and performed-session persistence while preserving provenance/license rules;
10. run the final real-device E2E and prove adaptive next prescription.

## Explicitly rejected shortcuts

- copying unit code into AI-Holding;
- Google Fit API;
- one microservice per coach;
- blind forks of GPL/AGPL fitness applications;
- PowerSync before measured need;
- external analytics/telemetry for health data;
- merging nutrition sources without provenance/license metadata;
- claiming green status from historical tests after material architecture changes.
