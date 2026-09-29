from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from healthos.domain import ExerciseGroupType, PerformedExercise, PerformedSession, PerformedSet, SetType
from healthos.entity_payloads import PerformedSessionPayload
from healthos.training_metrics import SessionMetricsEngine


def test_performed_session_payload_accepts_advanced_set_structures() -> None:
    payload = PerformedSessionPayload.model_validate(
        {
            "planned_session_id": "advanced-session",
            "performed_at": "2026-09-29T12:00:00Z",
            "completed": True,
            "duration_minutes": 45,
            "rpe": 8,
            "exercises": [
                {
                    "exercise_id": "squat",
                    "group_type": "superset",
                    "group_id": "A",
                    "sets": [
                        {"set_number": 1, "reps": 10, "load_kg": 40, "set_type": "warm_up"},
                        {
                            "set_number": 2,
                            "completed": True,
                            "completed_at": "2026-09-29T12:01:00Z",
                            "reps": 8,
                            "load_kg": 60,
                            "set_type": "working",
                        },
                        {"set_number": 3, "reps": 12, "load_kg": 40, "set_type": "drop"},
                        {"set_number": 4, "reps": 15, "load_kg": 30, "set_type": "amrap"},
                    ],
                }
            ],
        }
    )
    assert payload.exercises[0].group_type == "superset"
    assert payload.exercises[0].group_id == "A"
    assert payload.exercises[0].sets[1].completed is True
    assert payload.exercises[0].sets[1].completed_at is not None
    assert [item.set_type for item in payload.exercises[0].sets] == [
        "warm_up",
        "working",
        "drop",
        "amrap",
    ]


def test_advanced_set_payload_rejects_unknown_set_type() -> None:
    with pytest.raises(ValidationError):
        PerformedSessionPayload.model_validate(
            {
                "planned_session_id": "invalid-advanced-session",
                "performed_at": "2026-09-29T12:00:00Z",
                "completed": True,
                "duration_minutes": 30,
                "exercises": [
                    {
                        "exercise_id": "squat",
                        "sets": [{"set_number": 1, "reps": 8, "set_type": "invented"}],
                    }
                ],
            }
        )


def test_training_metrics_keep_advanced_sets_in_normal_volume_math() -> None:
    session = PerformedSession(
        planned_session_id="advanced",
        completed=True,
        duration_minutes=20,
        rpe=8,
        performed_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
        exercises=(
            PerformedExercise(
                exercise_id="press",
                group_type=ExerciseGroupType.CIRCUIT,
                group_id="C1",
                sets=(
                    PerformedSet(set_number=1, reps=10, load_kg=20, set_type=SetType.WARM_UP),
                    PerformedSet(set_number=2, reps=8, load_kg=30, set_type=SetType.WORKING),
                    PerformedSet(set_number=3, reps=12, load_kg=20, set_type=SetType.BACK_OFF),
                ),
            ),
        ),
    )
    result = SessionMetricsEngine().summarize(session)
    assert result.completed_sets == 3
    assert result.total_reps == 30
    assert result.volume_load_kg == 680.0
