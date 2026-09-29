from datetime import UTC, date, datetime
from types import SimpleNamespace

from healthos.dashboard import DashboardEngine
from healthos.domain import Goal, Observation, PerformedSession, ReadinessInput


def _observation(metric: str, value: float, when: datetime) -> Observation:
    return Observation(
        observation_id=f"{metric}-{when.isoformat()}",
        metric=metric,
        value=value,
        unit=None,
        observed_at=when,
        recorded_at=when,
        source_id="health_connect:synthetic",
        source_type="health_connect",
        confidence=0.9,
    )


def test_dashboard_combines_training_recovery_activity_body_and_goals() -> None:
    today = date(2026, 9, 29)
    observations = SimpleNamespace(
        canonical=(
            _observation("weight_kg", 100.0, datetime(2026, 9, 27, 8, tzinfo=UTC)),
            _observation("weight_kg", 99.5, datetime(2026, 9, 28, 8, tzinfo=UTC)),
            _observation("weight_kg", 99.0, datetime(2026, 9, 29, 8, tzinfo=UTC)),
            _observation("steps", 4500, datetime(2026, 9, 29, 12, tzinfo=UTC)),
            _observation("active_calories_kcal", 320, datetime(2026, 9, 29, 12, tzinfo=UTC)),
        ),
        missing_findings=(),
    )
    performed = (
        PerformedSession(
            planned_session_id="done",
            completed=True,
            duration_minutes=40,
            rpe=7,
            performed_at=datetime(2026, 9, 28, 18, tzinfo=UTC),
        ),
    )
    plan = {
        "sessions": [
            {
                "session_id": "today-session",
                "scheduled_date": "2026-09-29",
                "focus": "strength",
                "phase": "accumulation",
                "duration_minutes": 50,
            }
        ]
    }
    goal = Goal(
        goal_id="g1",
        description="Synthetic target",
        priority=5,
        baseline=100,
        target=90,
        target_date=None,
        metric="weight_kg",
        current=95,
    )
    readiness = ReadinessInput(7.5, 4, 4, 2, 2, 2)

    result = DashboardEngine().build(
        today=today,
        readiness=readiness,
        goals=(goal,),
        observations=observations,
        performed_sessions=performed,
        plan_json=plan,
    )

    assert result.training["session_id"] == "today-session"
    assert result.training["is_today"] is True
    assert result.recovery["readiness_score"] is not None
    assert result.activity["sessions"] == 1
    assert result.activity["steps_today"] == 4500
    assert result.body["latest_weight_kg"] == 99.0
    assert result.body["weight_rolling_average_kg"] == 99.5
    assert result.goals[0].distance_to_target == -5
    assert result.goals[0].progress_fraction == 0.5
    assert result.alerts == ()


def test_dashboard_surfaces_missing_context_without_inventing_values() -> None:
    result = DashboardEngine().build(
        today=date(2026, 9, 29),
        readiness=None,
        goals=(),
        observations=None,
        performed_sessions=(),
        plan_json=None,
    )
    assert result.recovery["readiness_score"] is None
    assert result.activity["steps_today"] is None
    assert result.body["latest_weight_kg"] is None
    assert result.training["session_id"] is None
    assert len(result.alerts) == 3


def test_dashboard_pain_flag_is_a_safety_alert() -> None:
    readiness = ReadinessInput(8, 4, 4, 1, 1, 1, pain_flag=True)
    result = DashboardEngine().build(
        today=date(2026, 9, 29),
        readiness=readiness,
        goals=(),
        observations=None,
        performed_sessions=(),
        plan_json={"sessions": []},
    )
    assert any("Pain flag active" in item for item in result.alerts)


def test_dashboard_chooses_next_future_session() -> None:
    result = DashboardEngine()._training_summary(
        {
            "sessions": [
                {"session_id": "old", "scheduled_date": "2026-09-28"},
                {"session_id": "later", "scheduled_date": "2026-10-01"},
                {"session_id": "next", "scheduled_date": "2026-09-30"},
            ]
        },
        date(2026, 9, 29),
    )
    assert result["session_id"] == "next"
    assert result["is_today"] is False
