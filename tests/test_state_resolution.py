from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


def test_goal_current_falls_back_to_health_connect_baseline() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)
    observed = datetime(2026, 9, 20, 7, 0, tzinfo=UTC)

    with database.session() as db:
        push_changes(
            db,
            settings,
            device_id="synthetic-device",
            changes=(
                IncomingChange(
                    "goal-weight-change",
                    "goal",
                    "goal-weight",
                    1,
                    False,
                    {
                        "goal_id": "goal-weight",
                        "description": "Synthetic weight goal",
                        "priority": 3,
                        "baseline": 110.0,
                        "target": 95.0,
                        "metric": "weight_kg",
                        "constraints": [],
                    },
                ),
                IncomingChange(
                    "weight-observation-change",
                    "observation",
                    "weight-observation-entity",
                    1,
                    False,
                    {
                        "record_type": "weight",
                        "source_record_id": "weight-1",
                        "observed_at_epoch_ms": int(observed.timestamp() * 1000),
                        "data_origin_package": "com.synthetic.scale",
                        "last_modified_at_epoch_ms": int(observed.timestamp() * 1000),
                        "client_record_id": "scale-weight-1",
                        "client_record_version": 1,
                        "recording_method": 2,
                        "device_type": 1,
                        "device_manufacturer": "Synthetic",
                        "device_model": "Scale-X",
                        "health_connect_deleted": False,
                        "data": {
                            "kilograms": 101.5,
                            "time": observed.isoformat(),
                        },
                    },
                ),
            ),
        )

    with database.session() as db:
        goals = PlanningStateResolver().goals(
            db,
            now=datetime(2026, 9, 21, 23, 59, tzinfo=UTC),
        )

    assert goals[0].current == 101.5


def test_persisted_source_priority_and_missing_expectations_drive_health_pipeline() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)
    observed = datetime(2026, 9, 21, 8, 0, tzinfo=UTC)
    scale_source = "health_connect:com.synthetic.scale:synthetic:scale-x:1"

    with database.session() as db:
        push_changes(
            db,
            settings,
            device_id="synthetic-device",
            changes=(
                IncomingChange(
                    "quality-priority-1",
                    "health_source_priority",
                    "default",
                    1,
                    False,
                    {"ordered_source_ids": [scale_source]},
                ),
                IncomingChange(
                    "quality-expectation-1",
                    "metric_expectation",
                    "sleep-duration",
                    1,
                    False,
                    {"metric": "sleep_duration_min", "max_age_hours": 48, "enabled": True},
                ),
                IncomingChange(
                    "quality-weight-phone",
                    "observation",
                    "weight-phone",
                    1,
                    False,
                    {
                        "record_type": "weight",
                        "source_record_id": "weight-phone",
                        "observed_at_epoch_ms": int(observed.timestamp() * 1000),
                        "data_origin_package": "com.synthetic.phone",
                        "last_modified_at_epoch_ms": int(observed.timestamp() * 1000),
                        "client_record_version": 1,
                        "recording_method": 3,
                        "health_connect_deleted": False,
                        "data": {"kilograms": 100.0, "time": observed.isoformat()},
                    },
                ),
                IncomingChange(
                    "quality-weight-scale",
                    "observation",
                    "weight-scale",
                    1,
                    False,
                    {
                        "record_type": "weight",
                        "source_record_id": "weight-scale",
                        "observed_at_epoch_ms": int((observed + timedelta(seconds=20)).timestamp() * 1000),
                        "data_origin_package": "com.synthetic.scale",
                        "last_modified_at_epoch_ms": int((observed + timedelta(seconds=20)).timestamp() * 1000),
                        "client_record_version": 1,
                        "recording_method": 2,
                        "device_type": 1,
                        "device_manufacturer": "Synthetic",
                        "device_model": "Scale-X",
                        "health_connect_deleted": False,
                        "data": {
                            "kilograms": 100.02,
                            "time": (observed + timedelta(seconds=20)).isoformat(),
                        },
                    },
                ),
            ),
        )

    with database.session() as db:
        pipeline = PlanningStateResolver().health_pipeline(
            db,
            now=datetime(2026, 9, 21, 12, 0, tzinfo=UTC),
        )

    assert pipeline is not None
    assert len(pipeline.canonical) == 1
    assert pipeline.canonical[0].source_id == scale_source
    assert len(pipeline.suppressed_ids) == 1
    assert {finding.metric for finding in pipeline.missing_findings} == {"sleep_duration_min"}
