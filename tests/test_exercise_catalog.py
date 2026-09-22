from __future__ import annotations

from datetime import UTC, datetime

import pytest

from healthos.domain import Environment, Exercise
from healthos.exercise_catalog import (
    CanonicalExerciseCatalogAuditor,
    ExerciseCandidate,
    ExerciseCatalogGate,
    ExerciseProvenance,
    ExerciseReviewStatus,
)
from healthos.exercise_db import DEFAULT_EXERCISES
from healthos.source_policy import policy_for


def _candidate(
    *,
    source_id: str = "kinetic_exercises_db",
    status: ExerciseReviewStatus = ExerciseReviewStatus.PROPOSED,
    media: tuple[str, ...] = (),
) -> ExerciseCandidate:
    exercise = Exercise(
        exercise_id="external_test_squat",
        name="External Test Squat",
        movement_pattern="squat",
        muscles=("quads", "glutes"),
        equipment=frozenset(),
        environments=frozenset({Environment.HOME}),
        space_required_m2=2.0,
        noise="low",
        skill=1,
        fatigue=2,
        impact=1,
        strength=3,
        power=1,
        conditioning=1,
        unilateral=False,
    )
    policy = policy_for(source_id)
    provenance = ExerciseProvenance(
        exercise_id=exercise.exercise_id,
        source_id=source_id,
        source_record_id="record-1",
        source_version="2026-09-22",
        license_id=policy.license_id,
        retrieved_at=datetime(2026, 9, 22, tzinfo=UTC),
        raw_hash="a" * 64,
        review_status=status,
        reviewer="synthetic-reviewer",
    )
    return ExerciseCandidate(exercise=exercise, provenance=provenance, media_uris=media)


def test_default_catalog_has_no_blocking_integrity_errors() -> None:
    findings = CanonicalExerciseCatalogAuditor().audit(DEFAULT_EXERCISES)
    assert not [item for item in findings if item.severity == "error"]


def test_discovery_only_source_cannot_be_promoted_even_when_marked_approved() -> None:
    candidate = _candidate(status=ExerciseReviewStatus.APPROVED)
    findings = ExerciseCatalogGate().validate_candidate(candidate)
    assert "SOURCE_NOT_PROMOTABLE" in {item.code for item in findings}
    with pytest.raises(ValueError, match="SOURCE_NOT_PROMOTABLE"):
        ExerciseCatalogGate().promote(candidate)


def test_unapproved_candidate_cannot_be_promoted() -> None:
    candidate = _candidate(status=ExerciseReviewStatus.PROPOSED)
    with pytest.raises(ValueError, match="explicitly APPROVED"):
        ExerciseCatalogGate().promote(candidate)


def test_media_is_blocked_when_source_policy_does_not_allow_redistribution() -> None:
    candidate = _candidate(media=("https://example.invalid/exercise.gif",))
    findings = ExerciseCatalogGate().validate_candidate(candidate)
    assert "MEDIA_NOT_APPROVED" in {item.code for item in findings}


def test_license_mismatch_fails_closed() -> None:
    candidate = _candidate()
    invalid = ExerciseCandidate(
        exercise=candidate.exercise,
        provenance=ExerciseProvenance(
            **{
                **candidate.provenance.__dict__,
                "license_id": "unexpected-license",
            }
        ),
    )
    findings = ExerciseCatalogGate().validate_candidate(invalid)
    assert "LICENSE_MISMATCH" in {item.code for item in findings}
