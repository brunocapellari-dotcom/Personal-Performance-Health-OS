from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Literal

from .domain import Observation, PerformedExercise, PerformedSession


@dataclass(frozen=True)
class ExerciseMetrics:
    exercise_id: str
    completed_sets: int
    total_reps: int
    volume_load_kg: float
    work_seconds: int
    distance_m: float
    max_load_kg: float | None
    max_reps_single_set: int | None
    average_rpe: float | None
    average_rir: float | None


@dataclass(frozen=True)
class SessionMetrics:
    planned_session_id: str
    completed_sets: int
    total_reps: int
    volume_load_kg: float
    duration_minutes: int
    density_kg_per_min: float | None
    work_seconds: int
    distance_m: float
    session_rpe_load: float | None
    exercises: tuple[ExerciseMetrics, ...]


@dataclass(frozen=True)
class PersonalRecord:
    exercise_id: str
    metric: Literal["max_load_kg", "max_reps_single_set", "volume_load_kg", "distance_m", "work_seconds"]
    value: float
    unit: str
    previous_best: float | None
    baseline: bool


@dataclass(frozen=True)
class CardioLoad:
    modality: str
    duration_minutes: int
    distance_m: float
    average_hr_bpm: float | None
    max_hr_bpm: float | None
    average_power_w: float | None
    session_rpe_load: float | None
    external_work_kj: float | None


@dataclass(frozen=True)
class WeeklyTrainingLoad:
    sessions: int
    completed_sessions: int
    total_minutes: int
    total_session_rpe_load: float
    total_volume_load_kg: float
    total_distance_m: float


@dataclass(frozen=True)
class BodyMetricTrend:
    latest_value: float
    rolling_average: float
    absolute_change: float
    relative_change_pct: float | None
    observations: int
    latest_at: datetime


@dataclass(frozen=True)
class NutritionEntry:
    energy_kcal: float = 0.0
    protein_g: float = 0.0
    carbohydrate_g: float = 0.0
    fat_g: float = 0.0
    fiber_g: float = 0.0
    hydration_l: float = 0.0
    micronutrients: dict[str, float] | None = None


@dataclass(frozen=True)
class NutritionTotals:
    energy_kcal: float
    protein_g: float
    carbohydrate_g: float
    fat_g: float
    fiber_g: float
    hydration_l: float
    micronutrients: dict[str, float]


class SessionMetricsEngine:
    """Derive reproducible training metrics from performed-session facts."""

    def summarize(self, session: PerformedSession) -> SessionMetrics:
        if session.duration_minutes < 0:
            raise ValueError("duration_minutes cannot be negative")
        exercise_metrics = tuple(self._exercise_metrics(item) for item in session.exercises)
        completed_sets = sum(item.completed_sets for item in exercise_metrics)
        total_reps = sum(item.total_reps for item in exercise_metrics)
        volume_load = sum(item.volume_load_kg for item in exercise_metrics)
        work_seconds = sum(item.work_seconds for item in exercise_metrics)
        set_distance = sum(item.distance_m for item in exercise_metrics)
        distance = float(session.distance_m) if session.distance_m is not None else set_distance
        density = None
        if session.duration_minutes > 0 and volume_load > 0:
            density = round(volume_load / session.duration_minutes, 3)
        session_rpe_load = None
        if session.rpe is not None:
            if not 0 <= session.rpe <= 10:
                raise ValueError("RPE must be between 0 and 10")
            session_rpe_load = round(session.duration_minutes * session.rpe, 1)
        return SessionMetrics(
            planned_session_id=session.planned_session_id,
            completed_sets=completed_sets,
            total_reps=total_reps,
            volume_load_kg=round(volume_load, 3),
            duration_minutes=session.duration_minutes,
            density_kg_per_min=density,
            work_seconds=work_seconds,
            distance_m=round(distance, 3),
            session_rpe_load=session_rpe_load,
            exercises=exercise_metrics,
        )

    @staticmethod
    def _exercise_metrics(exercise: PerformedExercise) -> ExerciseMetrics:
        completed = tuple(item for item in exercise.sets if item.completed)
        reps = tuple(item.reps for item in completed if item.reps is not None)
        loads = tuple(item.load_kg for item in completed if item.load_kg is not None)
        rpes = tuple(item.rpe for item in completed if item.rpe is not None)
        rirs = tuple(item.rir for item in completed if item.rir is not None)
        volume = sum(
            float(item.load_kg) * int(item.reps)
            for item in completed
            if item.load_kg is not None and item.reps is not None
        )
        return ExerciseMetrics(
            exercise_id=exercise.exercise_id,
            completed_sets=len(completed),
            total_reps=sum(int(value) for value in reps),
            volume_load_kg=round(volume, 3),
            work_seconds=sum(item.duration_seconds or 0 for item in completed),
            distance_m=round(sum(item.distance_m or 0.0 for item in completed), 3),
            max_load_kg=None if not loads else max(float(value) for value in loads),
            max_reps_single_set=None if not reps else max(int(value) for value in reps),
            average_rpe=None if not rpes else round(mean(float(value) for value in rpes), 2),
            average_rir=None if not rirs else round(mean(float(value) for value in rirs), 2),
        )


class PersonalRecordEngine:
    """Detect new exercise records against completed historical sessions only."""

    _UNITS = {
        "max_load_kg": "kg",
        "max_reps_single_set": "reps",
        "volume_load_kg": "kg",
        "distance_m": "m",
        "work_seconds": "s",
    }

    def detect(
        self,
        history: tuple[PerformedSession, ...],
        current: PerformedSession,
    ) -> tuple[PersonalRecord, ...]:
        current_metrics = SessionMetricsEngine().summarize(current)
        previous_best: dict[tuple[str, str], float] = {}
        for session in history:
            if not session.completed:
                continue
            metrics = SessionMetricsEngine().summarize(session)
            for exercise in metrics.exercises:
                for metric, value in self._values(exercise).items():
                    key = (exercise.exercise_id, metric)
                    previous_best[key] = max(previous_best.get(key, value), value)

        records: list[PersonalRecord] = []
        for exercise in current_metrics.exercises:
            for metric, value in self._values(exercise).items():
                if value <= 0:
                    continue
                key = (exercise.exercise_id, metric)
                previous = previous_best.get(key)
                if previous is None or value > previous:
                    records.append(
                        PersonalRecord(
                            exercise_id=exercise.exercise_id,
                            metric=metric,
                            value=round(value, 3),
                            unit=self._UNITS[metric],
                            previous_best=None if previous is None else round(previous, 3),
                            baseline=previous is None,
                        )
                    )
        return tuple(records)

    @staticmethod
    def _values(exercise: ExerciseMetrics) -> dict[
        Literal["max_load_kg", "max_reps_single_set", "volume_load_kg", "distance_m", "work_seconds"],
        float,
    ]:
        values: dict[
            Literal["max_load_kg", "max_reps_single_set", "volume_load_kg", "distance_m", "work_seconds"],
            float,
        ] = {
            "volume_load_kg": exercise.volume_load_kg,
            "distance_m": exercise.distance_m,
            "work_seconds": float(exercise.work_seconds),
        }
        if exercise.max_load_kg is not None:
            values["max_load_kg"] = exercise.max_load_kg
        if exercise.max_reps_single_set is not None:
            values["max_reps_single_set"] = float(exercise.max_reps_single_set)
        return values


class CardioLoadEngine:
    """Summarize cardio without inventing heart-rate zones or physiological thresholds."""

    def summarize(
        self,
        session: PerformedSession,
        *,
        modality: str,
        average_power_w: float | None = None,
    ) -> CardioLoad:
        if not modality.strip():
            raise ValueError("modality is required")
        if average_power_w is not None and average_power_w < 0:
            raise ValueError("average_power_w cannot be negative")
        metrics = SessionMetricsEngine().summarize(session)
        work_kj = None
        if average_power_w is not None and session.duration_minutes > 0:
            work_kj = round(average_power_w * session.duration_minutes * 60 / 1000.0, 2)
        return CardioLoad(
            modality=modality.strip().lower(),
            duration_minutes=session.duration_minutes,
            distance_m=metrics.distance_m,
            average_hr_bpm=session.avg_hr_bpm,
            max_hr_bpm=session.max_hr_bpm,
            average_power_w=average_power_w,
            session_rpe_load=metrics.session_rpe_load,
            external_work_kj=work_kj,
        )


class WeeklyTrainingLoadEngine:
    def summarize(self, sessions: tuple[PerformedSession, ...]) -> WeeklyTrainingLoad:
        metrics = tuple(SessionMetricsEngine().summarize(session) for session in sessions)
        return WeeklyTrainingLoad(
            sessions=len(sessions),
            completed_sessions=sum(1 for session in sessions if session.completed),
            total_minutes=sum(max(0, item.duration_minutes) for item in metrics),
            total_session_rpe_load=round(sum(item.session_rpe_load or 0.0 for item in metrics), 1),
            total_volume_load_kg=round(sum(item.volume_load_kg for item in metrics), 3),
            total_distance_m=round(sum(item.distance_m for item in metrics), 3),
        )


class BodyMeasurementTrendEngine:
    """Generic rolling trend for weight, circumference or other same-unit body metrics."""

    def summarize(
        self,
        observations: tuple[tuple[datetime, float], ...],
        *,
        window: int = 7,
    ) -> BodyMetricTrend:
        if not observations:
            raise ValueError("at least one observation is required")
        if window <= 0:
            raise ValueError("window must be positive")
        ordered = tuple(sorted(observations, key=lambda item: item[0]))
        latest_at, latest = ordered[-1]
        recent = tuple(value for _, value in ordered[-window:])
        first = ordered[0][1]
        relative = None if first == 0 else (latest - first) / abs(first) * 100.0
        return BodyMetricTrend(
            latest_value=round(latest, 3),
            rolling_average=round(mean(recent), 3),
            absolute_change=round(latest - first, 3),
            relative_change_pct=None if relative is None else round(relative, 2),
            observations=len(ordered),
            latest_at=latest_at,
        )


class NutritionTotalsEngine:
    """Aggregate observed intake. Targets remain a separate planning concern."""

    def summarize(self, entries: tuple[NutritionEntry, ...]) -> NutritionTotals:
        micros: dict[str, float] = {}
        for entry in entries:
            if min(
                entry.energy_kcal,
                entry.protein_g,
                entry.carbohydrate_g,
                entry.fat_g,
                entry.fiber_g,
                entry.hydration_l,
            ) < 0:
                raise ValueError("nutrition values cannot be negative")
            for name, value in (entry.micronutrients or {}).items():
                if value < 0:
                    raise ValueError("micronutrient values cannot be negative")
                micros[name] = micros.get(name, 0.0) + value
        return NutritionTotals(
            energy_kcal=round(sum(item.energy_kcal for item in entries), 2),
            protein_g=round(sum(item.protein_g for item in entries), 2),
            carbohydrate_g=round(sum(item.carbohydrate_g for item in entries), 2),
            fat_g=round(sum(item.fat_g for item in entries), 2),
            fiber_g=round(sum(item.fiber_g for item in entries), 2),
            hydration_l=round(sum(item.hydration_l for item in entries), 3),
            micronutrients={key: round(value, 4) for key, value in sorted(micros.items())},
        )


@dataclass(frozen=True)
class WorkoutMatch:
    planned_session_id: str
    observation_id: str
    source_id: str
    end_delta_minutes: float
    duration_delta_minutes: float
    confidence: float
    evidence_kind: Literal["INFERRED"] = "INFERRED"


@dataclass(frozen=True)
class WorkoutReconciliationResult:
    matches: tuple[WorkoutMatch, ...]
    unmatched_performed_session_ids: tuple[str, ...]
    unmatched_observation_ids: tuple[str, ...]


class WorkoutReconciliationEngine:
    """One-to-one heuristic reconciliation of app sessions and Health Connect exercise observations.

    A match is explicitly INFERRED: source metadata remains authoritative and the engine never
    turns an inferred match into a claim that both records are the same underlying event.
    """

    def reconcile(
        self,
        sessions: tuple[PerformedSession, ...],
        observations: tuple[Observation, ...],
        *,
        end_tolerance_minutes: float = 90.0,
    ) -> WorkoutReconciliationResult:
        if end_tolerance_minutes <= 0:
            raise ValueError("end_tolerance_minutes must be positive")

        exercise_observations = tuple(
            item
            for item in observations
            if item.metric == "exercise_duration_min" and isinstance(item.value, (int, float))
        )
        candidates: list[tuple[float, int, int, float, float]] = []
        for session_index, session in enumerate(sessions):
            if session.performed_at is None:
                continue
            duration_tolerance = max(15.0, session.duration_minutes * 0.75)
            for observation_index, observation in enumerate(exercise_observations):
                try:
                    end_delta = abs((observation.observed_at - session.performed_at).total_seconds()) / 60.0
                except TypeError:
                    continue
                duration_delta = abs(float(observation.value) - session.duration_minutes)
                if end_delta > end_tolerance_minutes or duration_delta > duration_tolerance:
                    continue
                score = (end_delta / end_tolerance_minutes) + (duration_delta / duration_tolerance)
                candidates.append((score, session_index, observation_index, end_delta, duration_delta))

        matched_sessions: set[int] = set()
        matched_observations: set[int] = set()
        matches: list[WorkoutMatch] = []
        for score, session_index, observation_index, end_delta, duration_delta in sorted(candidates):
            if session_index in matched_sessions or observation_index in matched_observations:
                continue
            session = sessions[session_index]
            observation = exercise_observations[observation_index]
            confidence = round(max(0.0, min(1.0, 1.0 - (score / 2.0))), 3)
            matches.append(
                WorkoutMatch(
                    planned_session_id=session.planned_session_id,
                    observation_id=observation.observation_id,
                    source_id=observation.source_id,
                    end_delta_minutes=round(end_delta, 2),
                    duration_delta_minutes=round(duration_delta, 2),
                    confidence=confidence,
                )
            )
            matched_sessions.add(session_index)
            matched_observations.add(observation_index)

        return WorkoutReconciliationResult(
            matches=tuple(matches),
            unmatched_performed_session_ids=tuple(
                session.planned_session_id
                for index, session in enumerate(sessions)
                if index not in matched_sessions
            ),
            unmatched_observation_ids=tuple(
                observation.observation_id
                for index, observation in enumerate(exercise_observations)
                if index not in matched_observations
            ),
        )
