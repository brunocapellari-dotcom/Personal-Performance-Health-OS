# Research Review — 2026-09-15

This review classifies external projects by capability. The rule is **use/adapt/reference/reject**, never blind fork.

## Production selections

| Capability | Decision | Selected direction | Notes |
|---|---|---|---|
| Android health aggregation | ADOPT | Health Connect | Canonical Android path. Production defaults to the stable SDK; alpha-only features stay behind capability checks/feature gates. |
| Health Connect testing | ADOPT | `androidx.health.connect:connect-testing` | Use fake permission/client support for Android integration tests where appropriate. |
| Local Android DB encryption | ADOPT | `sqlcipher/sqlcipher-android` + Room | Use the current replacement library, not deprecated `android-database-sqlcipher`. Protect the DB key with Android Keystore. |
| FIT import | ADOPT | `fitdecode` adapter | Preferred to `fitparse`; adapter keeps parser replaceable. |
| GPX import | ADOPT CANDIDATE | `gpxpy` | Mature parser/manipulator; current stdlib parser remains a zero-dependency test adapter only. |
| Strength progression UX/DSL | REFERENCE | Liftosaur | Strong design reference for programmable progression/deloads; do not import app architecture wholesale. |
| Exercise taxonomy/API patterns | REFERENCE | wger | Evaluate exercise/media/data licensing per asset before use. |
| Outdoor activity/self-hosting | REFERENCE | FitTrackee | Good activity-file workflow and privacy patterns. |
| Privacy-first GPS/BLE recording | REFERENCE | OpenTracks | Useful optional companion/source; upstream is Codeberg. |
| Bluetooth body scales | REFERENCE / OPTIONAL ADAPTER | openScale | Health Connect first when the vendor already syncs; direct BLE path for uncovered scales. |
| Wearables without vendor cloud | REFERENCE / OPTIONAL | Gadgetbridge | Strong privacy pattern; upstream is Codeberg. |
| Nutrition local-first UX | REFERENCE | OpenNutriTracker | Encrypted local storage/export/source-aware food lookup concepts. |
| Adaptive nutrition/self-hosting | REFERENCE | NutriTrace | Particularly useful reference for adaptive TDEE, data sources and wellness integrations. AGPL requires deliberate license handling. |
| Pose/rep counting | FUTURE ADAPTER | MediaPipe Pose | Technical movement feedback only; no diagnosis. |

## New projects reviewed but not selected as core dependencies

- OpenHealthConnect: relevant local/self-hosted Health Connect-to-agent pattern, but too young to become core infrastructure.
- ALIS-HEALTH: useful private Health Connect cockpit reference, but currently immature.
- PulseBase: interesting self-hosted Garmin/health analytics concepts; not selected because the Health OS should remain source-agnostic and not center the architecture on one wearable vendor.
- Lyftr/SoloForge and other newer trackers: useful UX ideas, but no architectural advantage large enough to replace the selected references.

## Health Connect design update

The final Android adapter must:

1. preserve `DataOrigin`, device and recording-method metadata;
2. maintain Changes Tokens independently per data type where data is consumed independently;
3. handle upserts, deletes, pagination, token expiry and re-sync;
4. use background reads only when the feature is available and the user grants the permission;
5. prefer Health Connect Aggregate API when the intended semantics are the user-prioritized deduplicated activity/sleep totals;
6. retain raw source-specific observations for traceability and analyses where aggregation is not appropriate;
7. account for Android/Health Connect attribution changes rather than assuming a fixed package name for device-generated data.

## Nutrition source hierarchy

No single food database is sufficient. Use a federated source model with provenance:

- **TBCA**: primary Brazilian composition/household-measure reference where a matching food exists.
- **TACO/NEPA-UNICAMP**: canonical Brazilian reference dataset with edition preserved.
- **USDA FoodData Central**: structured reference/branded-food API and fallback coverage.
- **Open Food Facts**: packaged/barcode products, with crowd-sourced quality flags and license attribution.

Never average or silently merge conflicting nutrient values from different sources. The selected record remains linked to its source/version and the UI may expose alternatives.

## Rejected/deferred stack

- Google Fit API: reject for new work.
- `fitparse`: replace with `fitdecode`.
- deprecated `android-database-sqlcipher`: replace with `sqlcipher-android`.
- one service per AI coach: reject.
- feature store: defer until measured need.
- TimescaleDB: defer until PostgreSQL performance data justifies it.
- duplicate vector database/corpus: reject; evidence stays in Research AI/Second Brain.
- direct vendor wearable integrations by default: reject; Health Connect first, direct adapters only for real gaps.

## Health Connect Medical Records / FHIR

A new integration opportunity exists for personal medical context. Health Connect supports experimental Medical Records in HL7 FHIR R4/R4B, including medications, allergies, laboratory results, conditions, procedures, visits and vital signs. This should be a **feature-gated import/organization capability**, not a diagnostic or treatment engine. The project must preserve medical data source provenance and the absolute medication rule remains unchanged: imported prescription information can generate alerts/context, but the AI cannot alter dose, suspend, replace or stop treatment.
