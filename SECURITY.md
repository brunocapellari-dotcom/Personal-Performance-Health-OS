# Security Policy

Health data is sensitive. Source visibility and health-data visibility are separate concerns: this repository may be public, but personal health records, credentials, backups, exports, photos, FIT/GPX/TCX files and production configuration must never be committed.

## Mandatory controls

- Encryption at rest and in transit is mandatory.
- Android secrets and cryptographic keys use Android Keystore.
- Server secrets use a secret vault/KMS or deployment-secret mechanism, never repository files.
- Raw health data, imports, backups, photos and exports are excluded from Git.
- CI credentials are generated ephemerally for each run and are not reusable production credentials.
- External model calls receive only purpose-specific minimum projections.
- Every import is untrusted input and must be schema, size and type validated.
- Original FIT/GPX/media objects are content-hashed and isolated from execution paths.
- Medication dose mutation is forbidden by deterministic policy.
- Pose estimation is technical feedback and cannot produce diagnosis.
- Audit logs record material plan, safety and data mutations without storing sensitive payloads in the audit record.
- Production backup and blob encryption keys are independent.
- Production containers run as non-root and the database is not exposed publicly by the canonical Compose stack.
- Repository and production-image scans are blocking for high/critical vulnerabilities; repository scans also check secrets and misconfiguration.
- CodeQL analyzes Python and Android/Kotlin code. Bandit, pip-audit and Trivy remain because they cover distinct layers rather than duplicate the same check.

## Public repository rule

Only source code, synthetic fixtures, schemas, documentation and non-sensitive configuration templates belong in Git. Test data that resembles real health data must be demonstrably synthetic. `.env` files, database files and personal imports are denied by repository policy and ignored by Git.

Before a public release or merge to `main`, the complete project gate must pass on the same commit: backend, PostgreSQL migrations, Python quality/security tests, API fuzzing, Android unit/lint/debug/release builds, production container smoke test, repository scan and final image scan.

## Incident response

If a real secret or personal health artifact is ever committed, treat it as compromised even if the commit is later deleted: revoke/rotate the secret, remove the data from active history, review logs, and document the incident. Never rely on a later `.gitignore` change as remediation for already-published material.
