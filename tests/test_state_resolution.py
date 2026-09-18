from __future__ import annotations

from datetime import UTC, datetime

from healthos.config import Settings
from healthos.db import Database
from healthos.models import PlanSnapshotModel
from healthos.state import PlanningStateResolver
from healthos.sync import IncomingChange, push_changes


def _settings() -> Settings:
    return Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="j" * 40,
        audit_hmac_key="a" * 40,
    )


def test_canonical_state_resolves_assessment_calendar_and_performed_history() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)

    changes = (
        IncomingChange(
            "state-goal-1",
            "goal",
            "distance",
            1,
            False,
            {
                "goal_id": "distance",
                "description": "Synthetic distance goal",
                "priority": 5,
                "baseline": 5.0,
                "target": 20.0,
                "metric": "distance_km",
                "constraints": [],
            },
        ),
        IncomingChange(
            "state-env-1",
            "training_environment",
            "home",
            1,
            False,
            {
                "environment": "HOME",
                "equipment": ["dumbbells", "band", "step"],
                "space_m2": 10,
                "fixation_points": [],
                "noise_limit": "moderate",
                "surface": "indoor",
                "available_minutes": 60,
                "load_options_kg": [16.0, 20.0, 22.0, 24.0],
            },
        ),
        IncomingChange(
            "state-ready-1",
            "readiness",
            "ready-1",
            1,
            False,
            {
                "observed_at": "2027-03-01T07:00:00Z",
                "sleep_hours": 7.5,
                "sleep_quality_1_5": 4,
                "energy_1_5": 4,
                "fatigue_1_5": 2,
                "soreness_1_5": 2,
                "stress_1_5": 2,
                "pain_flag": False,
            },
        ),
        IncomingChange(
            "state-assessment-1",
            "assessment_result",
            "assessment-distance-1",
            1,
            False,
            {
                "assessment_id": "assessment-distance-1",
                "metric": "distance_km",
                "value": 9.0,
                "unit": "km",
                "observed_at": "2027-02-28T10:00:00Z",
            },
        ),
        IncomingChange(
            "state-calendar-1",
            "calendar_availability",
            "2027-03-02",
            1,
            False,
            {"day": "2027-03-02", "available_minutes": 45},
        ),
        IncomingChange(
            "state-calendar-old",
            "calendar_availability",
            "2027-01-01",
            1,
            False,
            {"day": "2027-01-01", "available_minutes": 60},
        ),
        IncomingChange(
            "state-performed-1",
            "performed_session",
            "performed-1",
            1,
            False,
            {
                "planned_session_id": "w1-strength-a",
                "performed_at": "2027-02-28T18:00:00Z",
                "completed": True,
                "duration_minutes": 50,
                "rpe": 7.0,
                "avg_hr_bpm": 120,
                "max_hr_bpm": 150,
                "notes": "synthetic",
                "exercises": [
                    {
                        "exercise_id": "goblet_squat",
                        "sets": [
                            {"set_number": 1, "reps": 12, "load_kg": 20, "rir": 3},
                            {"set_number": 2, "reps": 12, "load_kg": 20, "rir": 2},
                            {"set_number": 3, "reps": 12, "load_kg": 20, "rir": 2},
                        ],
                    }
                ],
            },
        ),
    )

    with database.session() as db:
        push_changes(db, settings, device_id="synthetic-device", changes=changes)
        db.add(
            PlanSnapshotModel(
                snapshot_id="previous-plan",
                device_id="synthetic-device",
                request_hash="a" * 64,
                request_json={"synthetic": True},
                plan_json={
                    "sessions": [
                        {
                            "session_id": "w1-strength-a",
                            "week": 1,
                            "day_label": "Strength A",
                            "focus": "strength",
                            "phase": "accumulation",
                            "duration_minutes": 60,
                            "prescriptions": [
                                {
                                    "exercise_id": "goblet_squat",
                                    "sets": 3,
                                    "rep_range": [8, 12],
                                    "target_rir": 2.0,
                                    "load_kg": 20.0,
                                    "rest_seconds": 120,
                                }
                            ],
                        },
                        {
                            "session_id": "w1-conditioning",
                            "week": 1,
                            "day_label": "Conditioning",
                            "focus": "conditioning",
                            "phase": "accumulation",
                            "duration_minutes": 40,
                        },
                    ]
                },
                audit_json={"passed": True},
                created_at=datetime(2027, 2, 25, tzinfo=UTC),
            )
        )

    with database.session() as db:
        state = PlanningStateResolver().resolve(db, today=datetime(2027, 3, 1, tzinfo=UTC).date(), weeks=1)

    assert state.goals[0].current == 9.0
    assert state.availability == (state.availability[0],)
    assert state.availability[0].day.isoformat() == "2027-03-02"
    assert state.training_response is not None
    assert state.training_response.sessions_planned == 2
    assert state.training_response.sessions_completed == 1
    assert state.training_response.avg_rpe == 7.0
    assert state.training_response.load_ratio == 0.5
    assert state.strength_progressions["goblet_squat"].next_load_kg == 22.0
    assert state.strength_progressions["goblet_squat"].rationale == "double_progression_increment"
