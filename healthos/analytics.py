from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import mean, median
from typing import cast

from .data_quality import SourceResolver
from .domain import (
    Observation,
    PerformedSession,
    PerformedSet,
    SessionPlan,
    StrengthPerformance,
    StrengthProgression,
    TrainingResponse,
)
from .engines import StrengthEngine


@dataclass(frozen=True)
class RecoverySignal:
    metric: str
    latest_value: float
    baseline_value: float
    delta_pct: float
    samples_in_baseline: int
    latest_at: datetime


class RecoverySignalEngine:
    """Derive objective recovery deltas without contaminating the baseline with the latest reading."""

    def derive(
        self,
        observations: tuple[Observation, ...],
        metric: str,
        *,
        now: datetime | None = None,
        lookback: timedelta = timedelta(days=28),
        recent_exclusion: timedelta = timedelta(hours=18),
        min_baseline_samples: int = 3,
    ) -> RecoverySignal | None:
        now = now or datetime.now(UTC)
        if lookback.total_seconds() <= 0 or recent_exclusion.total_seconds() < 0:
            raise ValueError("invalid recovery signal windows")
        if min_baseline_samples < 1:
            raise ValueError("min_baseline_samples must be positive")

        eligible = tuple(
            sorted(
                (
                    obs
                    for obs in observations
                    if obs.metric == metric
                    and isinstance(obs.value, (int, float))
                    and obs.observed_at <= now
                    and obs.observed_at >= now - lookback
                ),
                key=lambda item: item.observed_at,
            )
        )
        if not eligible:
            return None

        latest = eligible[-1]
        cutoff = latest.observed_at - recent_exclusion
        baseline_values = tuple(
            float(obs.value)
            for obs in eligible
            if obs.observed_at < cutoff
        )
        if len(baseline_values) < min_baseline_samples:
            return None
        baseline = float(median(baseline_values))
        if baseline == 0:
            return None
        latest_value = float(latest.value)
        delta = (latest_value - baseline) / abs(baseline) * 100.0
        return RecoverySignal(
            metric=metric,
            latest_value=round(latest_value, 4),
            baseline_value=round(baseline, 4),
            delta_pct=round(delta, 2),
            samples_in_baseline=len(baseline_values),
            latest_at=latest.observed_at,
        )


@dataclass(frozen=True)
class BodyTrend:
    latest_kg: float
    rolling_average_kg: float
    change_kg: float
    observations: int


class BodyTrendEngine:
    def summarize(self, weights_kg: tuple[float, ...], *, window: int = 7) -> BodyTrend:
        if not weights_kg:
            raise ValueError("at least one weight is required")
        if window <= 0:
            raise ValueError("window must be positive")
        recent = weights_kg[-window:]
        return BodyTrend(
            latest_kg=round(weights_kg[-1], 3),
            rolling_average_kg=round(mean(recent), 3),
            change_kg=round(weights_kg[-1] - weights_kg[0], 3),
            observations=len(weights_kg),
        )


@dataclass(frozen=True)
class SessionResponse:
    adherence: float
    duration_ratio: float
    session_rpe_load: float | None
    status: str


class PlannedVsPerformedEngine:
    """Convert execution data into deterministic response features for the next prescription."""

    def compare(self, planned: SessionPlan, performed: PerformedSession) -> SessionResponse:
        if planned.session_id != performed.planned_session_id:
            raise ValueError("planned/performed session IDs do not match")
        if planned.duration_minutes <= 0:
            raise ValueError("planned duration must be positive")
        adherence = 1.0 if performed.completed else 0.0
        duration_ratio = max(0.0, performed.duration_minutes / planned.duration_minutes)
        session_load = None
        if performed.rpe is not None:
            if not 0 <= performed.rpe <= 10:
                raise ValueError("RPE must be between 0 and 10")
            session_load = round(performed.duration_minutes * performed.rpe, 1)

        if not performed.completed:
            status = "NOT_COMPLETED"
        elif duration_ratio < 0.75:
            status = "PARTIAL_VOLUME"
        elif duration_ratio > 1.25:
            status = "OVERRUN"
        else:
            status = "AS_PLANNED"
        return SessionResponse(round(adherence, 3), round(duration_ratio, 3), session_load, status)


class StrengthHistoryEngine:
    """Derive the next executable load from performed sets and known equipment loads."""

    def recommend(
        self,
        targets: dict[str, tuple[tuple[int, int], float]],
        performed: tuple[PerformedSession, ...],
        load_options_kg: tuple[float, ...],
    ) -> dict[str, StrengthProgression]:
        latest: dict[str, tuple[datetime, tuple[PerformedSet, ...]]] = {}
        for session in performed:
            if not session.completed:
                continue
            when = self._utc_time(session.performed_at)
            for exercise in session.exercises:
                completed_sets = tuple(item for item in exercise.sets if item.completed)
                if exercise.exercise_id not in targets or not completed_sets:
                    continue
                current = latest.get(exercise.exercise_id)
                if current is None or when >= current[0]:
                    latest[exercise.exercise_id] = (when, completed_sets)

        available = tuple(sorted(set(load_options_kg)))
        output: dict[str, StrengthProgression] = {}
        for exercise_id, (_, sets) in latest.items():
            loaded = tuple(item for item in sets if item.load_kg is not None and item.reps is not None)
            if not loaded:
                continue
            current_load = float(cast(float, loaded[-1].load_kg))
            same_load = tuple(item for item in loaded if float(cast(float, item.load_kg)) == current_load)
            reps = tuple(int(cast(int, item.reps)) for item in same_load)
            rirs = tuple(float(item.rir) for item in same_load if item.rir is not None)
            target_range, target_rir = targets[exercise_id]
            if len(rirs) != len(reps):
                output[exercise_id] = StrengthProgression(current_load, "rir_missing_hold_load")
                continue
            if not available:
                output[exercise_id] = StrengthProgression(current_load, "available_loads_unknown_hold")
                continue

            higher = tuple(value for value in available if value > current_load)
            increment = higher[0] - current_load if higher else 1.0
            raw = StrengthEngine().next_load(
                StrengthPerformance(
                    exercise_id=exercise_id,
                    load_kg=current_load,
                    reps_by_set=reps,
                    rir_by_set=rirs,
                    target_rep_range=target_range,
                    target_rir=target_rir,
                    increment_kg=max(0.001, increment),
                )
            )
            output[exercise_id] = self._snap_to_available(raw, current_load, available)
        return output

    @staticmethod
    def _utc_time(value: datetime | None) -> datetime:
        if value is None:
            return datetime.min.replace(tzinfo=UTC)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _snap_to_available(
        decision: StrengthProgression,
        current_load: float,
        available: tuple[float, ...],
    ) -> StrengthProgression:
        if decision.next_load_kg > current_load:
            candidates = tuple(value for value in available if value >= decision.next_load_kg)
            if not candidates:
                return StrengthProgression(current_load, "no_higher_available_load")
            return StrengthProgression(candidates[0], decision.rationale)
        if decision.next_load_kg < current_load:
            candidates = tuple(value for value in available if value <= decision.next_load_kg)
            if not candidates:
                return StrengthProgression(current_load, "no_lower_available_load")
            return StrengthProgression(candidates[-1], decision.rationale)
        return StrengthProgression(current_load, decision.rationale)


class TrainingHistoryEngine:
    """Summarize raw performed sessions into deterministic planning response features."""

    def summarize(
        self,
        planned: tuple[SessionPlan, ...],
        performed: tuple[PerformedSession, ...],
    ) -> TrainingResponse:
        planned_by_id = {session.session_id: session for session in planned}
        performed_by_id: dict[str, PerformedSession] = {}
        for session in performed:
            if session.planned_session_id not in planned_by_id:
                continue
            existing = performed_by_id.get(session.planned_session_id)
            if existing is None:
                performed_by_id[session.planned_session_id] = session
                continue
            existing_time = self._utc_time(existing.performed_at)
            candidate_time = self._utc_time(session.performed_at)
            if candidate_time >= existing_time:
                performed_by_id[session.planned_session_id] = session

        relevant_planned = tuple(planned_by_id.values())
        relevant_performed = tuple(performed_by_id.values())
        completed = tuple(session for session in relevant_performed if session.completed)
        rpes = tuple(session.rpe for session in completed if session.rpe is not None)

        planned_minutes = sum(session.duration_minutes for session in relevant_planned)
        performed_minutes = sum(max(0, session.duration_minutes) for session in relevant_performed)
        load_ratio = None
        if planned_minutes > 0:
            load_ratio = round(performed_minutes / planned_minutes, 3)

        return TrainingResponse(
            sessions_planned=len(relevant_planned),
            sessions_completed=len(completed),
            avg_rpe=None if not rpes else round(mean(rpes), 2),
            load_ratio=load_ratio,
        )

    @staticmethod
    def _utc_time(value: datetime | None) -> datetime:
        if value is None:
            return datetime.min.replace(tzinfo=UTC)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


@dataclass(frozen=True)
class AssessmentChange:
    metric: str
    baseline: float
    retest: float
    absolute_change: float
    relative_change_pct: float | None


class AssessmentEngine:
    def compare(self, metric: str, baseline: float, retest: float) -> AssessmentChange:
        absolute = retest - baseline
        relative = None if baseline == 0 else (absolute / abs(baseline)) * 100.0
        return AssessmentChange(
            metric=metric,
            baseline=baseline,
            retest=retest,
            absolute_change=round(absolute, 4),
            relative_change_pct=None if relative is None else round(relative, 2),
        )
