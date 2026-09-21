# Tooling Decisions

## Adopt

### Android Health Connect
Canonical Android health/wellness integration. Use the stable SDK in production; newer alpha-only capabilities must be detected and feature-gated. Use Changes Tokens, DataOrigin metadata, permission-aware background reads and Aggregate API semantics deliberately.

### `androidx.health.connect:connect-testing`
Use Android's Health Connect test support for integration tests of permissions/client behavior as the API matures.

### `sqlcipher/sqlcipher-android` + Room
Selected encrypted Android relational store. It is the long-term replacement for the deprecated `android-database-sqlcipher`. Protect/generated database credentials with Android Keystore; never hard-code passphrases.

### `fitdecode`
Preferred FIT parser behind an adapter.

### `gpxpy`
Selected production GPX parser behind a hardened adapter. GPX input is pre-validated with `defusedxml`, size/point limits are enforced, and import IDs are deterministic.

## Reference / adapt by capability

### android/health-samples
Primary reference for Health Connect/Health Services integration patterns. Do not fork the whole repository.

### Liftosaur
Reference for programmable progression/deload logic. Reimplement only concepts needed by the deterministic Strength Engine.

### wger
Reference for exercise taxonomy, workout/nutrition API patterns and potentially reusable data. Review license/provenance per imported asset.

### FitTrackee
Reference for outdoor activity import and self-hosted privacy patterns.

### OpenTracks
Optional privacy-first Android GPS/BLE source and GPX exporter. Canonical upstream has moved to Codeberg.

### openScale
Reference/optional integration for Bluetooth body scales. Prefer Health Connect where supported; direct BLE is a gap-filler.

### Gadgetbridge
Reference for privacy-first local wearable access without vendor cloud. Optional integration only if required by a specific device.

### OpenNutriTracker
Reference for encrypted local nutrition storage, export and multi-source food concepts.

### NutriTrace
Reference for adaptive TDEE, source-aware food lookup and wellness integration. Its AGPL license is a reason to avoid copying code unless compatibility is chosen intentionally.

### MediaPipe Pose
Future adapter for pose landmarks, rep counting and movement comparison only; no diagnostic use.

## Reject / replace

### Google Fit API — REJECT
Do not build a new dependency on the retired/deprecated Google Fit platform path. Health Connect is the Android integration layer.

### `fitparse` — REPLACE
Use `fitdecode`.

### `android-database-sqlcipher` — REPLACE
The old Android SQLCipher binding is deprecated. Use `sqlcipher-android`.

### One microservice per coach — REJECT
Named coaches are logical roles in one orchestration runtime with shared deterministic engines and typed contracts.

### TimescaleDB by default — DEFER
Plain PostgreSQL is sufficient for a personal system until measurements prove otherwise.

### Separate feature store — DEFER
Derived state can remain reproducible SQL/Python projections until scale requires a dedicated feature platform.

### Separate vector DB / copied research corpus — REJECT
Research AI/Second Brain owns validated knowledge. Health OS stores evidence references and retrieves what it needs.

### Health Connect Medical Records / FHIR — FUTURE FEATURE-GATED ADAPTER
Health Connect Medical Records uses HL7 FHIR R4 (4.0.1) and R4B (4.3.0). Keep the compatibility boundary disabled by default while the production app stays on the stable Health Connect client and only enable it with explicit product/privacy approval. Preserve resource/source provenance and raw hashes, request minimum permissions, and route medication data through the existing non-mutation safety rule. Do not add hospital/EHR infrastructure merely to be FHIR-compatible.

### Soda Core v4 — EVALUATE AS EXTERNAL ANALYTICS ADAPTER
Do not embed Soda in the Health OS runtime. The current project only needs small contracts for derived analytical datasets, which are implemented internally and deterministically. Re-evaluate Soda when PostgreSQL/BigQuery analytical tables become numerous enough to justify an external data-contract engine. Soda must never replace health-safety or medical validation.

### Pandera — RESERVE
MIT-licensed and a better fit than a large data-quality platform if Health OS later standardizes on pandas/Polars DataFrames. Do not add it until dataframe-scale validation appears in the actual architecture.

### Great Expectations / GX Core — DEFER
Capable and mature, but broader than the current need. Revisit for a larger shared analytical platform; do not add it solely to validate a handful of Health OS aggregate tables.
