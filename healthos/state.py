from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from .analytics import TrainingHistoryEngine
from .domain import (
    AvailabilityWindow,
    Environment,
    Event,
    Goal,
    GoalStatus,
    NutritionTrend,
    PerformedExercise,
    PerformedSession,
    PerformedSet,
    Phase,
    ReadinessInput,
    SessionPlan,
    TrainingEnvironment,
    TrainingResponse,
)
from .entity_payloads import (
    AssessmentResultPayload,
    CalendarAvailabilityPayload,
    EventPayload,
    GoalPayload,
    NutritionTrendPayload,
    PerformedSessionPayload,
    ReadinessPayload,
    TrainingEnvironmentPayload,
    TrainingResponsePayload,
)
from .models import EntityRecordModel, PlanSnapshotModel

T = TypeVar("T")


@dataclass(frozen=True)
class ResolvedPlanningState:
    goals: tuple[Goal, ...]
    environment: TrainingEnvironment
    readiness: ReadinessInput
    nutrition_trend: NutritionTrend | None
    event: Event | None
    training_response: TrainingResponse | None
    availability: tuple[AvailabilityWindow, ...]


class PlanningStateResolver:
    def resolve(self, db: Session, *, today: date, weeks: int) -> ResolvedPlanningState:
        goals = self.goals(db)
        if not goals:
            raise ValueError("no active goals are synchronized")
        environment = self.environment(db)
        if environment is None:
            raise ValueError("no active training environment is synchronized")
        readiness = self.readiness(db)
        if readiness is None:
            raise ValueError("no readiness check-in is synchronized")

        assessments = self._latest_assessments(db)
        goals = tuple(
            replace(goal, current=assessments.get(goal.metric, goal.current))
            if goal.current is None and goal.metric in assessments
            else goal
            for goal in goals
        )
        return ResolvedPlanningState(
            goals=goals,
            environment=environment,
            readiness=readiness,
            nutrition_trend=self.nutrition(db),
            event=self.event(db, today),
            training_response=self.training_response(db),
            availability=self.availability(db, today, weeks),
        )

    def _active(self, db: Session, entity_type: str) -> tuple[EntityRecordModel, ...]:
        return tuple(
            db.scalars(
                select(EntityRecordModel)
                .where(EntityRecordModel.entity_type == entity_type, EntityRecordModel.deleted.is_(False))
                .order_by(EntityRecordModel.updated_at.desc(), EntityRecordModel.entity_id.asc())
            ).all()
        )

    def _latest(self, db: Session, entity_type: str) -> EntityRecordModel | None:
        rows = self._active(db, entity_type)
        return rows[0] if rows else None

    def goals(self, db: Session) -> tuple[Goal, ...]:
        goals: list[Goal] = []
        for row in self._active(db, "goal"):
            payload = GoalPayload.model_validate(row.payload)
            goals.append(
                Goal(
                    goal_id=payload.goal_id,
                    description=payload.description,
                    priority=payload.priority,
                    baseline=payload.baseline,
                    target=payload.target,
                    target_date=payload.target_date,
                    metric=payload.metric,
                    constraints=tuple(payload.constraints),
                    status=GoalStatus(payload.status),
                    current=payload.current,
                )
            )
        return tuple(sorted(goals, key=lambda item: (-item.priority, item.goal_id)))

    def environment(self, db: Session) -> TrainingEnvironment | None:
        row = self._latest(db, "training_environment")
        if row is None:
            return None
        payload = TrainingEnvironmentPayload.model_validate(row.payload)
        return TrainingEnvironment(
            environment=Environment(payload.environment),
            equipment=frozenset(payload.equipment),
            space_m2=payload.space_m2,
            fixation_points=frozenset(payload.fixation_points),
            noise_limit=payload.noise_limit,
            surface=payload.surface,
            available_minutes=payload.available_minutes,
            load_options_kg=tuple(sorted(payload.load_options_kg)),
        )

    def readiness(self, db: Session) -> ReadinessInput | None:
        row = self._latest(db, "readiness")
        if row is None:
            return None
        payload = ReadinessPayload.model_validate(row.payload)
        return ReadinessInput(
            sleep_hours=payload.sleep_hours,
            sleep_quality_1_5=payload.sleep_quality_1_5,
            energy_1_5=payload.energy_1_5,
            fatigue_1_5=payload.fatigue_1_5,
            soreness_1_5=payload.soreness_1_5,
            stress_1_5=payload.stress_1_5,
            resting_hr_delta_pct=payload.resting_hr_delta_pct,
            hrv_delta_pct=payload.hrv_delta_pct,
            pain_flag=payload.pain_flag,
        )

    def nutrition(self, db: Session) -> NutritionTrend | None:
        row = self._latest(db, "nutrition_trend")
        if row is None:
            return None
        payload = NutritionTrendPayload.model_validate(row.payload)
        return NutritionTrend(
            days=payload.days,
            avg_intake_kcal=payload.avg_intake_kcal,
            weight_start_kg=payload.weight_start_kg,
            weight_end_kg=payload.weight_end_kg,
            current_tdee_estimate_kcal=payload.current_tdee_estimate_kcal,
        )

    def event(self, db: Session, today: date) -> Event | None:
        candidates: list[Event] = []
        for row in self._active(db, "event"):
            payload = EventPayload.model_validate(row.payload)
            if payload.event_date < today:
                continue
            candidates.append(
                Event(
                    event_id=payload.event_id,
                    name=payload.name,
                    event_date=payload.event_date,
                    demands=tuple(payload.demands),
                    duration_minutes=payload.duration_minutes,
                    distance_km=payload.distance_km,
                    priority=payload.priority,
                )
            )
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: (-item.priority, item.event_date, item.event_id))[0]

    def availability(self, db: Session, today: date, weeks: int) -> tuple[AvailabilityWindow, ...]:
        end = today + timedelta(days=weeks * 7 - 1)
        by_day: dict[date, AvailabilityWindow] = {}
        for row in self._active(db, "calendar_availability"):
            payload = CalendarAvailabilityPayload.model_validate(row.payload)
            if not today <= payload.day <= end:
                continue
            current = by_day.get(payload.day)
            candidate = AvailabilityWindow(payload.day, payload.available_minutes)
            if current is None or candidate.available_minutes > current.available_minutes:
                by_day[payload.day] = candidate
        return tuple(by_day[day] for day in sorted(by_day))

    def _latest_assessments(self, db: Session) -> dict[str, float]:
        latest: dict[str, tuple[datetime, float]] = {}
        for row in self._active(db, "assessment_result"):
            payload = AssessmentResultPayload.model_validate(row.payload)
            previous = latest.get(payload.metric)
            ordering = payload.observed_at
            if previous is None or ordering > previous[0]:
                latest[payload.metric] = (ordering, payload.value)
        return {metric: value for metric, (_, value) in latest.items()}

    def training_response(self, db: Session) -> TrainingResponse | None:
        derived = self._derive_training_response(db)
        if derived is not None:
            return derived
        row = self._latest(db, "training_response")
        if row is None:
            return None
        payload = TrainingResponsePayload.model_validate(row.payload)
        return TrainingResponse(
            sessions_planned=payload.sessions_planned,
            sessions_completed=payload.sessions_completed,
            avg_rpe=payload.avg_rpe,
            load_ratio=payload.load_ratio,
        )

    def _derive_training_response(self, db: Session) -> TrainingResponse | None:
        snapshot = db.scalar(select(PlanSnapshotModel).order_by(PlanSnapshotModel.created_at.desc()).limit(1))
        if snapshot is None:
            return None
        raw_sessions = snapshot.plan_json.get("sessions")
        if not isinstance(raw_sessions, list) or not raw_sessions:
            return None

        planned: list[SessionPlan] = []
        for raw in raw_sessions:
            if not isinstance(raw, dict):
                continue
            try:
                planned.append(
                    SessionPlan(
                        session_id=str(raw["session_id"]),
                        week=int(raw["week"]),
                        day_label=str(raw["day_label"]),
                        focus=str(raw["focus"]),
                        phase=Phase(str(raw["phase"])),
                        duration_minutes=int(raw["duration_minutes"]),
                        prescriptions=(),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        if not planned:
            return None

        performed: list[PerformedSession] = []
        for row in self._active(db, "performed_session"):
            payload = PerformedSessionPayload.model_validate(row.payload)
            exercises = tuple(
                PerformedExercise(
                    exercise_id=exercise.exercise_id,
                    sets=tuple(
                        PerformedSet(
                            set_number=item.set_number,
                            reps=item.reps,
                            load_kg=item.load_kg,
                            rir=item.rir,
                            rpe=item.rpe,
                            duration_seconds=item.duration_seconds,
                            distance_m=item.distance_m,
                        )
                        for item in exercise.sets
                    ),
                )
                for exercise in payload.exercises
            )
            performed.append(
                PerformedSession(
                    planned_session_id=payload.planned_session_id,
                    completed=payload.completed,
                    duration_minutes=payload.duration_minutes,
                    rpe=payload.rpe,
                    notes=payload.notes,
                    performed_at=payload.performed_at,
                    avg_hr_bpm=payload.avg_hr_bpm,
                    max_hr_bpm=payload.max_hr_bpm,
                    distance_m=payload.distance_m,
                    exercises=exercises,
                )
            )

        if not performed:
            return None
        return TrainingHistoryEngine().summarize(tuple(planned), tuple(performed))
