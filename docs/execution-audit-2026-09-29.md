# Execution Audit — Next 50 — 2026-09-29

This document records the repository-backed disposition of the 50-step execution batch. It distinguishes capability already present from capability added in this batch and from acceptance work that cannot be honestly declared complete without infrastructure or a physical Android device.

## Status vocabulary

- **VERIFIED-IN-TREE** — implementation and tests/contracts exist in the repository.
- **ADDED-IN-BATCH** — capability added by this execution batch; it still requires the complete Cloud Build gate before promotion.
- **EXPANDED-IN-BATCH** — an existing capability was materially extended in this execution batch.
- **ACCEPTANCE-BLOCKED** — code path exists, but final proof requires external infrastructure, signing material, provider credentials, or physical-device evidence.
- **NOT-YET-PROMOTABLE** — deliberately not claimed as production-complete until the exact-SHA full-project gate is green.

## 50-step disposition

1. Repository inventory and audit — **VERIFIED-IN-TREE** via architecture/gap/test documentation and recursive tree audit.
2. Component classification — **VERIFIED-IN-TREE**; current gaps are narrowed to release/physical-device acceptance plus richer execution UX.
3. Dead-code/dependency review — **VERIFIED-IN-TREE** for the current architecture; no new runtime dependency was added in this batch.
4. Android screen/flow inventory — **VERIFIED-IN-TREE**; current client contains setup, Health Connect authorization, sync, nutrition lookup, next-block and performed-session capture.
5. API/client mapping — **VERIFIED-IN-TREE** through authenticated API client, sync and next-block coordinator.
6. Alembic chain and clean database path — **VERIFIED-IN-TREE** and part of the mandatory full gate.
7. Architecture decision record/tooling decisions — **VERIFIED-IN-TREE** in docs/tooling-decisions.md and architecture documentation.
8. Canonical entity model — **VERIFIED-IN-TREE** across domain, entity payload validation and synchronized entity history.
9. Stable IDs/versioning — **VERIFIED-IN-TREE** for sync entities, Health Connect source record/version metadata and deterministic imports.
10. Time/unit normalization — **VERIFIED-IN-TREE** for canonical observations; UTC normalization is explicit.
11. Provenance — **VERIFIED-IN-TREE**.
12. Quality/confidence — **VERIFIED-IN-TREE**.
13. Source catalogue — **VERIFIED-IN-TREE**.
14. Source priority — **VERIFIED-IN-TREE**.
15. Deterministic deduplication — **VERIFIED-IN-TREE**.
16. Incremental idempotent sync — **VERIFIED-IN-TREE**.
17. Interrupted-sync recovery — **VERIFIED-IN-TREE** through persisted cursor/pending queue; full real-device interruption test remains an acceptance gate.
18. Structured exercise catalogue — **VERIFIED-IN-TREE**.
19. Exercise movement/muscle/equipment/environment metadata — **VERIFIED-IN-TREE**.
20. Regressions/progressions/alternatives — **VERIFIED-IN-TREE**.
21. Equipment/environment constraint enforcement — **VERIFIED-IN-TREE**.
22. Structured plan model — **VERIFIED-IN-TREE** as BlockPlan/SessionPlan/ExercisePrescription.
23. Performed session separated from plan — **VERIFIED-IN-TREE**.
24. Set load/reps/duration/distance/RPE/RIR capture — **VERIFIED-IN-TREE**.
25. Advanced set structures — **ADDED-IN-BATCH** with explicit warm-up, working, back-off, drop and AMRAP set semantics plus superset/circuit grouping; old payloads remain backward compatible.
26. Rest prescription/timer — **EXPANDED-IN-BATCH**; prescription already existed and the Android session UI now provides an interactive countdown from the prescribed rest interval.
27. Session autosave — **ADDED-IN-BATCH** using the encrypted local Room/SQLCipher state store.
28. Interrupted-session resume — **ADDED-IN-BATCH** from the latest encrypted workout draft.
29. Volume/tonnage/density analytics — **ADDED-IN-BATCH** in healthos.training_metrics.
30. Personal records — **ADDED-IN-BATCH** with deterministic prior-history comparison.
31. Planned × performed — **VERIFIED-IN-TREE**.
32. Exercise history — **VERIFIED-IN-TREE**; richer Android visualization remains UX work.
33. Deterministic strength progression — **VERIFIED-IN-TREE**.
34. Regression after target failure — **VERIFIED-IN-TREE**.
35. Deload — **VERIFIED-IN-TREE**.
36. Missed-session adaptation — **VERIFIED-IN-TREE**.
37. Environment substitution — **VERIFIED-IN-TREE**.
38. Structured cardio — **VERIFIED-IN-TREE** for prescriptions and Health Connect metrics; **ADDED-IN-BATCH** for deterministic cardio-load summaries.
39. Bike/walk/run compatible metrics — **VERIFIED-IN-TREE** through generic modality plus distance/speed/cadence/power observations.
40. Weekly cardiovascular/training load — **ADDED-IN-BATCH** using observed session minutes, sRPE, distance and volume without inventing physiological zones.
41. Health Connect ingest — **VERIFIED-IN-TREE**.
42. Health Connect record resolution/reconciliation — **EXPANDED-IN-BATCH**; source versions/tombstones/dedup remain deterministic and a one-to-one workout reconciler now matches app sessions to Health Connect exercise observations by timing/duration. Every semantic match is explicitly labeled **INFERRED** and surfaced in the dashboard.
43. Body Engine — **VERIFIED-IN-TREE** for weight trend and assessments; **ADDED-IN-BATCH** generic same-unit rolling body metric trend.
44. Smoothed weight/body trend — **VERIFIED-IN-TREE** and generalized in this batch.
45. Recovery Engine — **VERIFIED-IN-TREE** with objective deltas plus multi-signal readiness.
46. Nutrition Engine — **VERIFIED-IN-TREE** for source-aware food data and adaptive TDEE; **ADDED-IN-BATCH** observed daily macro/fiber/hydration/micronutrient aggregation.
47. TDEE recalibration — **VERIFIED-IN-TREE**.
48. Dashboard — **EXPANDED-IN-BATCH** with a deterministic dashboard engine, authenticated backend endpoint and Android presentation for planned training, recovery, weekly activity, steps, body trend, goal progress, alerts and inferred Health Connect workout reconciliation.
49. Full-system automated E2E — **EXPANDED-IN-BATCH** with dashboard/API, advanced-set and reconciliation tests added to the existing suite; exact current SHA still requires Cloud Build execution.
50. Release Candidate validation — **ACCEPTANCE-BLOCKED** until exact-SHA Cloud Build passes and the physical Android Health Connect/offline/online flow is executed.

## Batch additions

The batch intentionally adds no new third-party runtime dependencies. New deterministic analytics cover:

- completed sets and total reps;
- load-volume/tonnage;
- training density;
- set and session effort summaries;
- deterministic personal-record detection;
- cardio sRPE and optional power-derived external work;
- weekly observed training load;
- generic body-measurement rolling trends;
- daily observed energy/macros/fiber/hydration/micronutrient totals;
- encrypted Android workout draft persistence and resume;
- explicit advanced-set and superset/circuit semantics;
- prescribed-rest countdown in the Android workout flow;
- inferred app-workout ↔ Health Connect exercise reconciliation;
- authenticated daily dashboard from backend to Android.

## Promotion rule

Nothing in this document overrides the repository release policy. New code remains **NOT-YET-PROMOTABLE** until the same commit passes the complete Cloud Build gate. Production-complete status additionally requires the documented physical-device end-to-end acceptance path.


## Current CI evidence

GitHub Actions runs for the branch are currently failing before job execution. The inspected jobs report `runner_id = 0` and an empty `steps` array, so they provide evidence of unavailable GitHub execution capacity rather than a code-test failure. The repository therefore continues to use `cloudbuild.yaml` as the intended complete execution gate. No green claim is made until a Cloud Build run for the exact head SHA is available.

## Remaining external acceptance boundary

The code work in the 50-step batch is implemented or represented by existing repository capabilities. The two release proofs that cannot be manufactured inside the repository are:

1. a successful exact-SHA complete Cloud Build run; and
2. physical Android-device validation of Health Connect permissions, offline autosave/resume, online sync, dashboard refresh and adaptive next-block behavior.

These remain release gates rather than hidden TODOs.
