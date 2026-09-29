from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any

from .domain import Goal, PerformedSession, ReadinessInput
from .engines import ReadinessEngine
from .observation_pipeline import ObservationPipelineResult
from .training_metrics import (
    BodyMeasurementTrendEngine,
    WeeklyTrainingLoadEngine,
    WorkoutReconciliationEngine,
)


@dataclass(frozen=True)
class DashboardGoalProgress:
    goal_id: str
    description: str
    metric: str
    current: float | None
    target: float | None
    distance_to_target: float | None
    progress_fraction: float | None


@dataclass(frozen=True)
class DashboardSnapshot:
    today: date
    training: dict[str, Any]
    recovery: dict[str, Any]
    activity: dict[str, Any]
    body: dict[str, Any]
    reconciliation: dict[str, Any]
    goals: tuple[DashboardGoalProgress, ...]
    alerts: tuple[str, ...]


class DashboardEngine:
    """Build a deterministic, source-aware daily summary without adding medical interpretation."""

    def build(
        self,
        *,
        today: date,
        readiness: ReadinessInput | None,
        goals: tuple[Goal, ...],
        observations: ObservationPipelineResult | None,
        performed_sessions: tuple[PerformedSession, ...],
        plan_json: dict[str, Any] | None,
    ) -> DashboardSnapshot:
        alerts: list[str] = []
        recovery: dict[str, Any] = {
            "readiness_score": None,
            "action": None,
            "reasons": [],
            "sleep_hours": None,
        }
        if readiness is not None:
            decision = ReadinessEngine().evaluate(readiness)
            recovery = {
                "readiness_score": decision.score,
                "action": decision.action,
                "reasons": list(decision.reasons),
                "sleep_hours": readiness.sleep_hours,
            }
            if readiness.pain_flag:
                alerts.append("Pain flag active: normal training remains blocked by safety rules.")
        else:
            alerts.append("No current readiness input is available.")

        weekly = tuple(
            session
            for session in performed_sessions
            if session.performed_at is not None
            and today - timedelta(days=6) <= session.performed_at.date() <= today
        )
        weekly_load = WeeklyTrainingLoadEngine().summarize(weekly)
        activity: dict[str, Any] = asdict(weekly_load)
        activity["steps_today"] = self._daily_sum(observations, "steps", today)
        activity["active_calories_kcal_today"] = self._daily_sum(
            observations,
            "active_calories_kcal",
            today,
        )

        weights: tuple[tuple[datetime, float], ...] = ()
        if observations is not None:
            weights = tuple(
                (item.observed_at, float(item.value))
                for item in observations.canonical
                if item.metric == "weight_kg" and isinstance(item.value, (int, float))
            )
            if observations.missing_findings:
                alerts.append(f"{len(observations.missing_findings)} expected data stream(s) are currently missing.")
        else:
            alerts.append("No canonical Health Connect observations are available.")

        body: dict[str, Any] = {
            "latest_weight_kg": None,
            "weight_rolling_average_kg": None,
            "weight_change_kg": None,
            "weight_observations": 0,
        }
        if weights:
            trend = BodyMeasurementTrendEngine().summarize(weights, window=7)
            body = {
                "latest_weight_kg": trend.latest_value,
                "weight_rolling_average_kg": trend.rolling_average,
                "weight_change_kg": trend.absolute_change,
                "weight_observations": trend.observations,
                "latest_weight_at": trend.latest_at,
            }

        reconciliation: dict[str, Any] = {
            "matches": [],
            "match_count": 0,
            "unmatched_performed_session_ids": [],
            "unmatched_observation_ids": [],
            "evidence_kind": "INFERRED",
        }
        if observations is not None:
            reconciled = WorkoutReconciliationEngine().reconcile(
                performed_sessions,
                observations.canonical,
            )
            reconciliation = {
                "matches": [asdict(item) for item in reconciled.matches],
                "match_count": len(reconciled.matches),
                "unmatched_performed_session_ids": list(reconciled.unmatched_performed_session_ids),
                "unmatched_observation_ids": list(reconciled.unmatched_observation_ids),
                "evidence_kind": "INFERRED",
            }

        training = self._training_summary(plan_json, today)
        if training["session_id"] is None:
            alerts.append("No current planned session is available.")

        return DashboardSnapshot(
            today=today,
            training=training,
            recovery=recovery,
            activity=activity,
            body=body,
            reconciliation=reconciliation,
            goals=tuple(self._goal_progress(goal) for goal in goals),
            alerts=tuple(dict.fromkeys(alerts)),
        )

    @staticmethod
    def _daily_sum(
        observations: ObservationPipelineResult | None,
        metric: str,
        day: date,
    ) -> float | None:
        if observations is None:
            return None
        values = [
            float(item.value)
            for item in observations.canonical
            if item.metric == metric
            and item.observed_at.date() == day
            and isinstance(item.value, (int, float))
        ]
        return None if not values else round(sum(values), 3)

    @staticmethod
    def _goal_progress(goal: Goal) -> DashboardGoalProgress:
        distance = None
        progress = None
        if goal.current is not None and goal.target is not None:
            distance = round(goal.target - goal.current, 4)
        if (
            goal.baseline is not None
            and goal.current is not None
            and goal.target is not None
            and goal.target != goal.baseline
        ):
            raw = (goal.current - goal.baseline) / (goal.target - goal.baseline)
            progress = round(max(0.0, min(1.0, raw)), 4)
        return DashboardGoalProgress(
            goal_id=goal.goal_id,
            description=goal.description,
            metric=goal.metric,
            current=goal.current,
            target=goal.target,
            distance_to_target=distance,
            progress_fraction=progress,
        )

    @staticmethod
    def _training_summary(plan_json: dict[str, Any] | None, today: date) -> dict[str, Any]:
        empty: dict[str, Any] = {
            "session_id": None,
            "scheduled_date": None,
            "focus": None,
            "phase": None,
            "duration_minutes": None,
            "is_today": False,
        }
        if plan_json is None:
            return empty
        raw_sessions = plan_json.get("sessions")
        if not isinstance(raw_sessions, list):
            return empty

        candidates: list[tuple[date, dict[str, Any]]] = []
        unscheduled: list[dict[str, Any]] = []
        for raw in raw_sessions:
            if not isinstance(raw, dict):
                continue
            raw_date = raw.get("scheduled_date")
            if isinstance(raw_date, str):
                try:
                    session_date = date.fromisoformat(raw_date)
                except ValueError:
                    continue
                if session_date >= today:
                    candidates.append((session_date, raw))
            elif raw_date is None:
                unscheduled.append(raw)

        selected: dict[str, Any] | None = None
        selected_date: date | None = None
        if candidates:
            selected_date, selected = min(candidates, key=lambda item: item[0])
        elif unscheduled:
            selected = unscheduled[0]

        if selected is None:
            return empty
        return {
            "session_id": selected.get("session_id"),
            "scheduled_date": selected_date,
            "focus": selected.get("focus"),
            "phase": selected.get("phase"),
            "duration_minutes": selected.get("duration_minutes"),
            "is_today": selected_date == today if selected_date is not None else False,
        }
