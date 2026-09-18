from dataclasses import asdict
from datetime import date, timedelta

from healthos.domain import Environment, Event, Goal, NutritionTrend, ReadinessInput, TrainingEnvironment
from healthos.orchestrator import HealthOS


def test_full_next_block_e2e_uses_all_required_context_and_passes_audit():
    today = date(2027, 3, 1)
    event = Event(
        "synthetic-endurance",
        "Synthetic endurance event",
        today + timedelta(days=48),
        ("walking", "endurance"),
        distance_km=18,
    )
    goals = (
        Goal("synthetic-strength", "Synthetic strength goal", 5, 80, 95, None, "strength"),
        Goal("synthetic-body", "Synthetic body composition goal", 3, 24, 21, None, "body composition"),
        Goal(
            "synthetic-endurance",
            "Synthetic walking endurance goal",
            4,
            5,
            18,
            event.event_date,
            "walking endurance",
        ),
    )
    env = TrainingEnvironment(
        Environment.HOME,
        frozenset({"dumbbells", "band", "step"}),
        10.0,
        noise_limit="moderate",
        available_minutes=50,
    )
    readiness = ReadinessInput(7.5, 4, 4, 2, 2, 2, resting_hr_delta_pct=1.0, hrv_delta_pct=-2.0)
    nutrition = NutritionTrend(21, 2350, 82.0, 80.5, 2900)

    result = HealthOS().next_block(
        goals=goals,
        environment=env,
        readiness=readiness,
        nutrition_trend=nutrition,
        event=event,
        today=today,
        weeks=4,
    )

    assert result.audit.passed, asdict(result.audit)
    assert result.plan.weeks == 4
    assert len(result.plan.sessions) == 12
    assert result.plan.nutrition_target_kcal is not None
    assert result.plan.metadata["environment"] == "HOME"
    assert result.plan.metadata["event_specificity"] >= 0.7
    assert result.plan.readiness.score > 0
    assert result.plan.goal_decisions["synthetic-endurance"].value == "DEVELOP"
    assert all(s.duration_minutes <= env.available_minutes for s in result.plan.sessions)
    assert all("pullup" not in s.exercises for s in result.plan.sessions)


def test_pain_flag_blocks_normal_training_in_full_plan():
    today = date(2027, 3, 1)
    goals = (Goal("synthetic-strength", "Synthetic strength goal", 5, 1, 2, None, "strength"),)
    env = TrainingEnvironment(Environment.HOME, frozenset({"dumbbells", "band"}), 10.0, available_minutes=50)
    readiness = ReadinessInput(8, 5, 5, 1, 1, 1, pain_flag=True)
    result = HealthOS().next_block(
        goals=goals,
        environment=env,
        readiness=readiness,
        nutrition_trend=None,
        event=None,
        today=today,
        weeks=2,
    )
    assert result.audit.passed
    assert result.plan.readiness.action == "SAFETY_REVIEW"
    assert all(s.duration_minutes <= 20 for s in result.plan.sessions)
    assert all(not s.exercises for s in result.plan.sessions)
    assert all(s.conditioning is None for s in result.plan.sessions)
