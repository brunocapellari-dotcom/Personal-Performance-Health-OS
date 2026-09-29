from datetime import UTC, datetime

import pytest

from healthos.domain import PerformedExercise, PerformedSession, PerformedSet
from healthos.training_metrics import (
    BodyMeasurementTrendEngine,
    CardioLoadEngine,
    NutritionEntry,
    NutritionTotalsEngine,
    PersonalRecordEngine,
    SessionMetricsEngine,
    WeeklyTrainingLoadEngine,
)


def _session(
    *,
    load: float = 40.0,
    reps: tuple[int, ...] = (10, 8),
    rpe: float | None = 7.0,
    distance_m: float | None = None,
    duration_minutes: int = 30,
    completed: bool = True,
) -> PerformedSession:
    sets = tuple(
        PerformedSet(set_number=index + 1, reps=value, load_kg=load, rir=2.0, rpe=8.0)
        for index, value in enumerate(reps)
    )
    return PerformedSession(
        planned_session_id="session-1",
        completed=completed,
        duration_minutes=duration_minutes,
        rpe=rpe,
        performed_at=datetime(2026, 9, 29, 8, 0, tzinfo=UTC),
        distance_m=distance_m,
        exercises=(PerformedExercise("squat", sets),),
    )


def test_session_metrics_include_volume_density_and_set_effort() -> None:
    result = SessionMetricsEngine().summarize(_session())
    assert result.completed_sets == 2
    assert result.total_reps == 18
    assert result.volume_load_kg == 720.0
    assert result.density_kg_per_min == 24.0
    assert result.session_rpe_load == 210.0
    assert result.exercises[0].average_rir == 2.0
    assert result.exercises[0].average_rpe == 8.0


def test_session_metrics_fall_back_to_set_distance() -> None:
    session = PerformedSession(
        planned_session_id="cardio",
        completed=True,
        duration_minutes=20,
        rpe=6.0,
        exercises=(
            PerformedExercise(
                "carry",
                (
                    PerformedSet(set_number=1, distance_m=100.0, duration_seconds=60),
                    PerformedSet(set_number=2, distance_m=120.0, duration_seconds=70),
                ),
            ),
        ),
    )
    result = SessionMetricsEngine().summarize(session)
    assert result.distance_m == 220.0
    assert result.work_seconds == 130


def test_personal_record_engine_compares_only_completed_history() -> None:
    history = (
        _session(load=35.0, reps=(10, 10)),
        _session(load=100.0, reps=(1,), completed=False),
    )
    records = PersonalRecordEngine().detect(history, _session(load=40.0, reps=(10, 10)))
    metrics = {(record.exercise_id, record.metric): record for record in records}
    assert metrics[("squat", "max_load_kg")].previous_best == 35.0
    assert metrics[("squat", "volume_load_kg")].previous_best == 700.0


def test_personal_record_engine_marks_first_observation_as_baseline() -> None:
    records = PersonalRecordEngine().detect((), _session())
    assert records
    assert all(record.baseline for record in records)


def test_cardio_load_uses_session_rpe_and_optional_power() -> None:
    result = CardioLoadEngine().summarize(
        _session(distance_m=5000.0, duration_minutes=25, rpe=8.0),
        modality="bike",
        average_power_w=200.0,
    )
    assert result.distance_m == 5000.0
    assert result.session_rpe_load == 200.0
    assert result.external_work_kj == 300.0


def test_weekly_training_load_aggregates_observed_sessions() -> None:
    result = WeeklyTrainingLoadEngine().summarize(
        (
            _session(duration_minutes=30, rpe=7.0),
            _session(duration_minutes=20, rpe=6.0, completed=False),
        )
    )
    assert result.sessions == 2
    assert result.completed_sessions == 1
    assert result.total_minutes == 50
    assert result.total_session_rpe_load == 330.0


def test_body_measurement_trend_is_chronological_and_rolling() -> None:
    points = (
        (datetime(2026, 9, 29, tzinfo=UTC), 99.0),
        (datetime(2026, 9, 27, tzinfo=UTC), 100.0),
        (datetime(2026, 9, 28, tzinfo=UTC), 99.5),
    )
    result = BodyMeasurementTrendEngine().summarize(points, window=2)
    assert result.latest_value == 99.0
    assert result.rolling_average == 99.25
    assert result.absolute_change == -1.0
    assert result.relative_change_pct == -1.0


def test_nutrition_totals_preserve_micronutrient_names() -> None:
    result = NutritionTotalsEngine().summarize(
        (
            NutritionEntry(
                energy_kcal=500,
                protein_g=40,
                carbohydrate_g=50,
                fat_g=15,
                fiber_g=8,
                hydration_l=0.5,
                micronutrients={"iron_mg": 2.0},
            ),
            NutritionEntry(
                energy_kcal=300,
                protein_g=20,
                carbohydrate_g=30,
                fat_g=10,
                fiber_g=4,
                hydration_l=0.75,
                micronutrients={"iron_mg": 1.5, "sodium_mg": 300},
            ),
        )
    )
    assert result.energy_kcal == 800
    assert result.protein_g == 60
    assert result.fiber_g == 12
    assert result.hydration_l == 1.25
    assert result.micronutrients == {"iron_mg": 3.5, "sodium_mg": 300.0}


def test_invalid_values_are_rejected() -> None:
    with pytest.raises(ValueError):
        NutritionTotalsEngine().summarize((NutritionEntry(energy_kcal=-1),))
    with pytest.raises(ValueError):
        CardioLoadEngine().summarize(_session(), modality="bike", average_power_w=-1)
