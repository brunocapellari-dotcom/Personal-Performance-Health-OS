# Full E2E Acceptance Contract

The canonical command is:

> Monta meu próximo bloco.

A passing production system must, in one execution path:

1. load active goals and priorities;
2. load baseline and recent tests;
3. load planned-vs-performed history;
4. calculate current progress/gaps;
5. load active environment/equipment/space/noise/time constraints;
6. read calendar and physical events;
7. summarize recovery/readiness without letting one metric dominate;
8. calculate nutrition state and adaptive energy estimate;
9. resolve goal conflicts;
10. choose a justified periodization phase;
11. generate block/week/session prescriptions;
12. guarantee all exercises are executable in the selected environment;
13. calculate deterministic progressions;
14. route safety flags before normal training;
15. execute independent audit;
16. present the block and explanations;
17. ingest performed training;
18. prove the next prescription changes when the response data materially changes.

## Complete-project regression rule

A material change is never accepted after testing only the edited component. The same commit must pass all automated gates:

- PostgreSQL migration upgrade plus drift check;
- complete Python suite with branch coverage threshold;
- Ruff formatting/lint, strict mypy, Bandit and dependency audit;
- authenticated OpenAPI fuzzing;
- Android unit tests, lint, debug build and release/R8 build;
- Room schema generation/validation;
- repository secret, vulnerability and misconfiguration scan;
- production container build, non-root check, migration, live `/healthz` smoke test and final image scan;
- CodeQL for Python and Java/Kotlin.

A release additionally requires a real Android device using Health Connect to complete:

`Android local encrypted state → device authentication → sync → PostgreSQL → planner → independent auditor → returned block → performed session → sync → materially responsive next prescription`.

Health Connect consent is independent from backend availability. If health permissions are absent, goals/plans/backend synchronization must continue while health ingestion is skipped explicitly.

No production or personal health data may be used as CI fixture. Real-device acceptance uses the user's authorized runtime data only after the repository and deployment security gates have passed.
