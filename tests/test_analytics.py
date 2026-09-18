from datetime import UTC, datetime, timedelta

from healthos.analytics import AssessmentEngine, BodyTrendEngine, PlannedVsPerformedEngine, SourceResolver, StrengthHistoryEngine
from healthos.domain import ExercisePrescription, Observation, PerformedExercise, PerformedSession, PerformedSet, Phase, SessionPlan


def _obs(obs_id: str, source: str, quality: str, confidence: float, second: int = 0) -> Observation:
    t = datetime(2026, 9, 15, 12, 0, second, tzinfo=UTC)
    return Observation(
        observation_id=obs_id,
        metric="steps",
        value=100,
        unit="count",
        observed_at=t,
        recorded_at=t,
        source_id=source,
        source_type="health_connect",
        quality=quality,
        confidence=confidence,
    )


def test_source_resolver_preserves_provenance_and_suppresses_duplicate() -> None:
    resolver = SourceResolver(("garmin", "phone"))
    result = resolver.deduplicate(
        (_obs("a", "phone", "high", 0.9), _obs("b", "garmin", "medium", 0.8, 5)),
        tolerance=timedelta(seconds=30),
    )
    assert [o.observation_id for o in result.selected] == ["b"]
    assert result.suppressed_ids == ("a",)


def test_body_trend_rolling_average() -> None:
    trend = BodyTrendEngine().summarize((100.0, 99.8, 99.5, 99.4), window=3)
    assert trend.latest_kg == 99.4
    assert trend.rolling_average_kg == 99.567
    assert trend.change_kg == -0.6


def test_planned_vs_performed_generates_session_load() -> None:
    planned = SessionPlan(
        "s1",
        1,
        "A",
        "strength",
        Phase.ACCUMULATION,
        60,
        (ExercisePrescription("goblet_squat", 3, (6, 12), 3.0),),
    )
    performed = PerformedSession("s1", True, 55, 7.0)
    response = PlannedVsPerformedEngine().compare(planned, performed)
    assert response.status == "AS_PLANNED"
    assert response.session_rpe_load == 385.0


def test_assessment_change() -> None:
    change = AssessmentEngine().compare("6min_walk_m", 500.0, 550.0)
    assert change.absolute_change == 50.0
    assert change.relative_change_pct == 10.0


def _performed_strength_session(reps: tuple[int, ...], rirs: tuple[float, ...]) -> PerformedSession:
    sets = tuple(
        PerformedSet(set_number=index + 1, reps=reps[index], load_kg=20.0, rir=rirs[index])
        for index in range(len(reps))
    )
    return PerformedSession(
        planned_session_id="strength-a",
        completed=True,
        duration_minutes=50,
        rpe=7.0,
        exercises=(PerformedExercise("goblet_squat", sets),),
    )


def test_strength_history_uses_next_available_load_only() -> None:
    recommendations = StrengthHistoryEngine().recommend(
        {"goblet_squat": ((8, 12), 2.0)},
        (_performed_strength_session((12, 12, 12), (3, 2, 2)),),
        (10.0, 16.0, 20.0, 22.0, 24.0),
    )
    assert recommendations["goblet_squat"].next_load_kg == 22.0
    assert recommendations["goblet_squat"].rationale == "double_progression_increment"


def test_strength_history_holds_when_available_loads_are_unknown() -> None:
    recommendations = StrengthHistoryEngine().recommend(
        {"goblet_squat": ((8, 12), 2.0)},
        (_performed_strength_session((12, 12, 12), (3, 2, 2)),),
        (),
    )
    assert recommendations["goblet_squat"].next_load_kg == 20.0
    assert recommendations["goblet_squat"].rationale == "available_loads_unknown_hold"


def test_strength_history_reduction_snaps_to_available_load() -> None:
    recommendations = StrengthHistoryEngine().recommend(
        {"goblet_squat": ((8, 12), 2.0)},
        (_performed_strength_session((6, 6, 6), (0, 0, 0)),),
        (10.0, 16.0, 18.0, 20.0, 22.0),
    )
    assert recommendations["goblet_squat"].next_load_kg == 18.0
    assert recommendations["goblet_squat"].rationale == "performance_regression_reduce_5pct"
