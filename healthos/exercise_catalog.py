from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from .domain import Exercise
from .exercise_db import DEFAULT_EXERCISES
from .source_policy import SourceUse, policy_for


class ExerciseReviewStatus(StrEnum):
    CANONICAL = "CANONICAL"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ExerciseProvenance:
    exercise_id: str
    source_id: str
    source_record_id: str
    source_version: str
    license_id: str
    retrieved_at: datetime
    raw_hash: str
    review_status: ExerciseReviewStatus
    reviewer: str
    notes: str = ""


@dataclass(frozen=True)
class ExerciseCandidate:
    exercise: Exercise
    provenance: ExerciseProvenance
    media_uris: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExerciseCatalogFinding:
    severity: str
    code: str
    exercise_id: str
    message: str


def internal_provenance(
    exercises: tuple[Exercise, ...] = DEFAULT_EXERCISES,
) -> dict[str, ExerciseProvenance]:
    timestamp = datetime(2026, 9, 22, tzinfo=UTC)
    return {
        exercise.exercise_id: ExerciseProvenance(
            exercise_id=exercise.exercise_id,
            source_id="healthos_internal",
            source_record_id=exercise.exercise_id,
            source_version="2026-09-22",
            license_id="project-owned-canonical-data",
            retrieved_at=timestamp,
            raw_hash="internal:" + exercise.exercise_id,
            review_status=ExerciseReviewStatus.CANONICAL,
            reviewer="healthos-program-auditor",
            notes="Project-authored canonical exercise record.",
        )
        for exercise in exercises
    }


class ExerciseCatalogGate:
    """Quarantine external exercise records until source policy and human review allow promotion."""

    def validate_candidate(self, candidate: ExerciseCandidate) -> tuple[ExerciseCatalogFinding, ...]:
        findings: list[ExerciseCatalogFinding] = []
        provenance = candidate.provenance
        exercise = candidate.exercise

        if provenance.exercise_id != exercise.exercise_id:
            findings.append(
                ExerciseCatalogFinding(
                    "error",
                    "PROVENANCE_ID_MISMATCH",
                    exercise.exercise_id,
                    "Exercise provenance ID must match the exercise ID",
                )
            )

        try:
            policy = policy_for(provenance.source_id)
        except ValueError:
            findings.append(
                ExerciseCatalogFinding(
                    "error",
                    "UNKNOWN_SOURCE",
                    exercise.exercise_id,
                    "External exercise source is not registered",
                )
            )
            return tuple(findings)

        if provenance.license_id != policy.license_id:
            findings.append(
                ExerciseCatalogFinding(
                    "error",
                    "LICENSE_MISMATCH",
                    exercise.exercise_id,
                    "Candidate license metadata does not match the registered source policy",
                )
            )

        if candidate.media_uris and not policy.redistribution:
            findings.append(
                ExerciseCatalogFinding(
                    "error",
                    "MEDIA_NOT_APPROVED",
                    exercise.exercise_id,
                    "Source policy does not approve media redistribution",
                )
            )

        if provenance.review_status is ExerciseReviewStatus.APPROVED and policy.use is not SourceUse.MACHINE_INTEGRATION:
            findings.append(
                ExerciseCatalogFinding(
                    "error",
                    "SOURCE_NOT_PROMOTABLE",
                    exercise.exercise_id,
                    "Discovery/reference-only sources cannot be promoted into the runtime catalog",
                )
            )

        if not provenance.source_record_id.strip() or not provenance.source_version.strip():
            findings.append(
                ExerciseCatalogFinding(
                    "error",
                    "INCOMPLETE_PROVENANCE",
                    exercise.exercise_id,
                    "Source record ID and source version are mandatory",
                )
            )

        if not provenance.raw_hash.strip():
            findings.append(
                ExerciseCatalogFinding(
                    "error",
                    "MISSING_RAW_HASH",
                    exercise.exercise_id,
                    "Raw source hash is mandatory",
                )
            )

        return tuple(findings)

    def promote(self, candidate: ExerciseCandidate) -> Exercise:
        findings = self.validate_candidate(candidate)
        errors = tuple(item for item in findings if item.severity == "error")
        if errors:
            raise ValueError("; ".join(item.code for item in errors))
        if candidate.provenance.review_status is not ExerciseReviewStatus.APPROVED:
            raise ValueError("exercise candidate must be explicitly APPROVED before promotion")
        return candidate.exercise


class CanonicalExerciseCatalogAuditor:
    """Audit runtime catalog integrity independently from external discovery."""

    def audit(
        self,
        exercises: tuple[Exercise, ...] = DEFAULT_EXERCISES,
        provenance: dict[str, ExerciseProvenance] | None = None,
    ) -> tuple[ExerciseCatalogFinding, ...]:
        provenance = provenance or internal_provenance(exercises)
        findings: list[ExerciseCatalogFinding] = []
        ids = [exercise.exercise_id for exercise in exercises]

        if len(ids) != len(set(ids)):
            duplicates = {item for item in ids if ids.count(item) > 1}
            for exercise_id in sorted(duplicates):
                findings.append(
                    ExerciseCatalogFinding("error", "DUPLICATE_ID", exercise_id, "Duplicate canonical exercise ID")
                )

        id_set = set(ids)
        for exercise in exercises:
            if exercise.exercise_id not in provenance:
                findings.append(
                    ExerciseCatalogFinding(
                        "error",
                        "MISSING_PROVENANCE",
                        exercise.exercise_id,
                        "Canonical exercise is missing provenance",
                    )
                )
            elif provenance[exercise.exercise_id].review_status is not ExerciseReviewStatus.CANONICAL:
                findings.append(
                    ExerciseCatalogFinding(
                        "error",
                        "NON_CANONICAL_PROVENANCE",
                        exercise.exercise_id,
                        "Runtime default exercise must carry CANONICAL provenance",
                    )
                )

            for relation_name, related in (
                ("alternative", exercise.alternatives),
            ):
                for target in related:
                    if target not in id_set:
                        findings.append(
                            ExerciseCatalogFinding(
                                "warning",
                                "UNRESOLVED_RELATION",
                                exercise.exercise_id,
                                f"{relation_name} target {target} is not yet present in the canonical catalog",
                            )
                        )

        return tuple(findings)
