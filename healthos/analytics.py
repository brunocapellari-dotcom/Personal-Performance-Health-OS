from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean

from .domain import Observation, PerformedSession, SessionPlan


@dataclass(frozen=True)
class DeduplicationDecision:
    selected: tuple[Observation, ...]
    suppressed_ids: tuple[str, ...]


class SourceResolver:
    """Resolve overlapping wearable observations without deleting provenance.

    The engine chooses one canonical observation for a metric/time bucket and returns
    the suppressed IDs separately. Raw observations remain immutable in storage.
    """

    QUALITY_SCORE = {
        "verified": 4,
        "high": 3,
        "medium": 2,
        "low": 1,
        "unknown": 0,
    }

    def __init__(self, source_priority: tuple[str, ...] = ()) -> None:
        self._priority = {source_id: len(source_priority) - index for index, source_id in enumerate(source_priority)}

    def _score(self, observation: Observation) -> tuple[int, int, float, datetime]:
        return (
            self._priority.get(observation.source_id, 0),
            self.QUALITY_SCORE.get(observation.quality.lower(), 0),
            observation.confidence if observation.confidence is not None else -1.0,
            observation.recorded_at,
        )

    def deduplicate(
        self,
        observations: tuple[Observation, ...],
        *,
        tolerance: timedelta = timedelta(seconds=30),
    ) -> DeduplicationDecision:
        if tolerance.total_seconds() < 0:
            raise ValueError("tolerance cannot be negative")
        if not observations:
            return DeduplicationDecision((), ())

        ordered = sorted(observations, key=lambda x: (x.metric, x.observed_at, x.observation_id))
        groups: list[list[Observation]] = []
        for obs in ordered:
            if not groups:
                groups.append([obs])
                continue
            last_group = groups[-1]
            anchor = last_group[0]
            same_metric = obs.metric == anchor.metric
            close_time = abs((obs.observed_at - anchor.observed_at).total_seconds()) <= tolerance.total_seconds()
            if same_metric and close_time:
                last_group.append(obs)
            else:
                groups.append([obs])

        selected: list[Observation] = []
        suppressed: list[str] = []
        for group in groups:
            winner = max(group, key=self._score)
            selected.append(winner)
            suppressed.extend(obs.observation_id for obs in group if obs.observation_id != winner.observation_id)

        return DeduplicationDecision(tuple(selected), tuple(suppressed))


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
