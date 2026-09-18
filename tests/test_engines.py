from datetime import date, timedelta

from healthos.domain import (
    Environment,
    Event,
    Goal,
    GoalStatus,
    NutritionTrend,
    ReadinessInput,
    StrengthPerformance,
    TrainingEnvironment,
)
from healthos.engines import (
    AdaptiveNutritionEngine,
    GoalConflictEngine,
    MissedWorkoutEngine,
    ReadinessEngine,
    StrengthEngine,
)
from healthos.exercise_db import ExerciseSelector


def test_strength_double_progression_is_deterministic():
    p = StrengthPerformance("goblet_squat", 30, (12, 12, 12), (3, 2, 2), (8, 12), 2, 2)
    out = StrengthEngine().next_load(p)
    assert out.next_load_kg == 32
    assert out.rationale == "double_progression_increment"


def test_strength_holds_when_not_ready_to_increment():
    p = StrengthPerformance("goblet_squat", 30, (12, 11, 10), (2, 2, 2), (8, 12), 2, 2)
    assert StrengthEngine().next_load(p).next_load_kg == 30


def test_readiness_is_multisignal_and_pain_is_hard_gate():
    ready = ReadinessEngine().evaluate(ReadinessInput(7.5, 4, 4, 2, 2, 2, 2, -5))
    assert ready.score > 60
    pain = ReadinessEngine().evaluate(ReadinessInput(8, 5, 5, 1, 1, 1, -2, 10, pain_flag=True))
    assert pain.action == "SAFETY_REVIEW"
    assert pain.score == 0


def test_adaptive_tdee_uses_observed_weight_trend():
    trend = NutritionTrend(
        days=28,
        avg_intake_kcal=2300,
        weight_start_kg=82,
        weight_end_kg=80.5,
        current_tdee_estimate_kcal=2750,
    )
    out = AdaptiveNutritionEngine().infer(trend)
    assert out.inferred_tdee_kcal > 2750
    assert out.confidence == "high"


def test_goal_conflicts_shift_non_event_goals_to_maintenance_near_event():
    today = date(2027, 3, 1)
    event = Event("synthetic-event", "Synthetic endurance event", today + timedelta(days=20), ("walking", "endurance"))
    goals = (
        Goal("endurance", "synthetic walking endurance", 5, 5, 18, event.event_date, "walking endurance"),
        Goal("strength", "synthetic max strength", 4, 1, 2, None, "strength"),
        Goal("hypertrophy", "synthetic hypertrophy", 2, 1, 2, None, "muscle size"),
    )
    out = GoalConflictEngine().decide(goals, event, today)
    assert out["endurance"] == GoalStatus.DEVELOP
    assert out["hypertrophy"] == GoalStatus.MAINTAIN


def test_exercise_selector_never_uses_missing_equipment_or_excess_noise():
    env = TrainingEnvironment(Environment.HOME, frozenset({"band"}), 4.0, noise_limit="low")
    eligible = ExerciseSelector().eligible(env)
    assert eligible
    for exercise in eligible:
        assert exercise.equipment.issubset(env.equipment)
        assert exercise.noise == "low"
        assert exercise.space_required_m2 <= env.space_m2


def test_missed_workout_is_recalculated_not_blindly_shifted():
    engine = MissedWorkoutEngine()
    assert engine.decision(2, 0.6, 2, "high") == "MOVE"
    assert engine.decision(1, 0.8, 2, "high") == "COMBINE_REDUCED"
    assert engine.decision(2, 0.8, 5, "low") == "REMOVE"


def test_goal_gap_engine_reports_measurable_gap() -> None:
    from healthos.engines import GoalGapEngine

    goal = Goal("synthetic-distance", "Synthetic distance event", 5, 8.0, 20.0, None, "distance_km")
    gap = GoalGapEngine().calculate((goal,))["synthetic-distance"]
    assert gap.absolute_gap == 12.0
    assert gap.relative_gap_pct == 150.0


def test_exercise_selector_respects_fixation_points() -> None:
    without_anchor = TrainingEnvironment(Environment.HOME, frozenset({"band"}), 10.0)
    with_anchor = TrainingEnvironment(
        Environment.HOME,
        frozenset({"band"}),
        10.0,
        fixation_points=frozenset({"anchor"}),
    )
    selector = ExerciseSelector()
    assert not selector.eligible(without_anchor, "anti-rotation")
    assert selector.eligible(with_anchor, "anti-rotation")[0].exercise_id == "band_pallof_press"
