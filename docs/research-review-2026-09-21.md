# Research Review — 2026-09-21

## Scope

This review updates the Personal Performance & Health OS after a second comparison round focused on:

- Android Health Connect implementation patterns;
- stable performance metrics;
- provenance and source identity;
- duplicate/source-resolution policy;
- missing-data and confidence;
- baseline/analytics contracts;
- future FHIR compatibility;
- data-quality tooling choices.

The project rule remains **use/adapt/reference/reject**. External projects are not forked merely because they already implement a related feature.

## Android Health Connect — ADOPT as primary Android layer

### Reference reviewed

Official Android `android/health-samples`, especially the Health Connect sample manager.

Patterns adopted:

- permission inspection before requests;
- Changes API with expiration handling;
- per-record-type differential tokens;
- exercise-session reads;
- source-filtered `AggregateRequest` tied to the exercise session's `DataOrigin`;
- sleep-session handling;
- weight handling;
- raw-series handling for heart rate and speed;
- explicit feature/version gating rather than assuming every new API is stable.

The application remains on the stable Health Connect client. Alpha-only capabilities are not promoted into the production path solely for broader metric coverage.

### Stable metric coverage selected

Core metrics:

- exercise;
- steps;
- distance;
- total calories;
- sleep;
- heart rate;
- resting heart rate;
- weight.

Optional performance metrics:

- active calories;
- step cadence;
- speed;
- elevation gained;
- power;
- VO2 max.

The optional tier prevents denial of a specialist permission such as power or speed from blocking ingestion of already-authorized core metrics.

## Canonical health-data pipeline

The canonical path is:

`Health Connect → source identification → normalization → quality/confidence → duplicate resolution → timeline → missing-data detection → baseline → analytics`

### Raw evidence

Raw Health Connect records preserve:

- record type;
- Health Connect record ID;
- DataOrigin/application package;
- last-modified timestamp;
- client record ID/version;
- recording method;
- device type/manufacturer/model when present;
- observed timestamp;
- raw payload;
- tombstones.

Raw evidence is never deleted merely because another source wins duplicate resolution.

### Source identity and priority

A canonical source ID is built from the originating package and device metadata where available.

Source priority is explicit synchronized configuration. There is no built-in preference for a specific watch, scale, vendor or app.

### Duplicate resolution

Duplicate suppression belongs to the derived canonical view.

A candidate is not treated as duplicate merely because timestamps are close. Metric, time tolerance and value compatibility must all satisfy the metric-specific duplicate policy.

### Missing-data detection

Missing/stale-data warnings are generated only for explicitly configured expected metrics. A metric the user never intended to collect must not produce permanent false warnings.

### Confidence/data quality

Recording method, device metadata and engineering-quality findings feed confidence. Plausibility ranges produce quality warnings, not medical diagnoses.

## Raw versus Aggregate API

Raw source records remain the provenance/audit layer.

The Health Connect Aggregate API is used for derived totals when aggregate semantics are preferable. For an exercise session, aggregates are filtered to the session's own `DataOrigin`, matching the official sample pattern. This avoids silently mixing unrelated providers.

Aggregates are projections and must not be written back as competing raw observations.

## Analytical dataset contracts

### Internal contracts — ADOPT now

Small deterministic contracts validate the derived baseline and analytics datasets:

- required fields;
- finite numeric values;
- confidence range;
- row/key uniqueness;
- row-count expectations.

This is sufficient for the present Health OS and introduces no separate data-quality platform.

### Soda Core — EVALUATE / EXTERNAL ADAPTER LATER

Soda is relevant if aggregated PostgreSQL/BigQuery analytical datasets grow enough to justify an external contract runner. It is not embedded in the Health OS runtime now.

It must never replace:

- medical review;
- medication safety;
- health-specific deterministic validation;
- provenance rules.

### Pandera — RESERVE

Pandera is a strong candidate if Health OS later standardizes substantial analytics on pandas/Polars DataFrames. Adding it now would duplicate the current typed contracts.

### Great Expectations / GX — DEFER

Useful for a broader enterprise analytical platform, but broader than the current Health OS requirement.

## FHIR — COMPATIBILITY BOUNDARY ONLY

Health Connect Medical Records supports HL7 FHIR R4/R4B resources. Health OS now has a disabled-by-default compatibility adapter capable of:

- identifying FHIR version;
- preserving source system and source record ID;
- preserving the resource;
- hashing the raw resource;
- validating basic transport shape.

It deliberately does not implement:

- EHR/hospital infrastructure;
- clinical terminology services;
- diagnostic logic;
- medical validation;
- prescription mutation.

FHIR compatibility does not imply clinical interpretation.

## Redundancy review

Removed/avoided:

- duplicate `SourceResolver` implementations;
- a second data-quality runtime;
- hard-coded vendor source rankings;
- a separate timeline database;
- a separate feature store;
- Soda/GX/Pandera runtime duplication before measured need;
- a separate FHIR service;
- copying the Android Health sample as an application fork;
- alpha Health Connect APIs in the stable production path;
- aggregate records duplicated as raw observations.

Canonical ownership after review:

- Health Connect gateway: Android transport and platform normalization;
- observation pipeline: source identity, normalization, quality, dedup, timeline, baseline, analytics;
- internal analytic contracts: derived-dataset integrity;
- deterministic planner: prescriptions and adaptation;
- FHIR adapter: future interoperability boundary only.

## Release implications

The current source tree contains material changes and therefore historical green CI results do not certify it.

Before release, the same commit must pass:

- Python compile/lint/type/tests/security;
- PostgreSQL migration/concurrency tests;
- Android compile/lint/unit/instrumentation tests;
- Health Connect fake tests;
- physical-device Health Connect consent/read/sync tests;
- container/security/SBOM gates;
- complete planned → performed → next-prescription E2E.
