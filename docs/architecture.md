# Canonical Architecture

## Design principles

1. Objectives first; exercises second.
2. Local-first collection; synchronized server is optional infrastructure, not the only copy of the user's data.
3. Append raw/normalized observations, derive analytics separately.
4. Keep `observed_at`, `recorded_at`, source/DataOrigin, device/recording method where available, raw hash and quality for every imported metric.
5. Deterministic engines own load/progression, conflict allocation, missed-workout logic and hard safety gates.
6. LLM roles explain and synthesize; they do not silently change deterministic outputs.
7. Planner and auditor are independent executions.
8. External models receive purpose-specific minimal projections only.
9. Research knowledge lives in Research AI/Segundo Cérebro; Health OS stores references/evidence IDs rather than duplicate corpora.
10. Full-project regression is required after relevant changes.

## Bounded contexts

### Profile & Goals
Profile, constraints, training environments, goals, target dates, metrics, baseline and priority.

### Training
Exercise catalog, progression rules, periodization, blocks, weeks, sessions, planned vs performed, tests and deload/taper.

### Conditioning & Events
Zone 2, tempo, threshold, VO2max, intervals, HIIT, mixed modal, loaded movement and future event preparation.

### Recovery & Readiness
Sleep, resting HR, HRV where available, fatigue, soreness, stress, energy, pain flag and recent performance.

### Nutrition
Foods, recipes, meals, energy, macros, hydration, micronutrients, adaptive TDEE and nutrition × training strategy.

### Body
Weight trends, circumferences, photos and composition estimates with source/uncertainty.

### Supplements & Medication Safety
Evidence/cost/interaction registry; medication dose changes are forbidden actions.

### Integrations
Health Connect, FIT, GPX, CSV, scale/wearable adapters and provenance.

### Knowledge & AI
Research requests, evidence packages, role-based synthesis and independent audit.

## Data model strategy

Use three layers:

1. **Raw evidence**: immutable imported file/record metadata, hashes and source IDs.
2. **Canonical observations/events**: normalized units, timestamps, provenance and quality flags.
3. **Derived state**: rolling averages, readiness features, TDEE estimates, training load and block decisions.

Derived values must be recomputable and must never overwrite raw observations. Duplicate-source resolution suppresses observations only in derived views; it never deletes raw provenance.

## Storage target

- Android: Room backed by current `sqlcipher-android`, database key protected by Android Keystore, plus offline queue.
- Server: PostgreSQL. Start with standard PostgreSQL indexes/partitions; do not add TimescaleDB unless measured query/retention needs justify it.
- Blobs: encrypted object storage with content hash and owner/reference metadata.

## AI runtime

One provider-neutral orchestrator with typed role prompts/tools. Do not deploy one service per named coach. This prevents duplicated memory, duplicated tool calls, conflicting state and operational cost.

Hard order:

`deterministic policy → role synthesis → deterministic validation → independent auditor → user-facing plan`

## Safety

- pain flag can force safety review
- medication dose mutation is technically forbidden
- external AI payloads are minimized by purpose
- imported data is untrusted input and must be validated
- no diagnostic claims from pose or readiness engines
