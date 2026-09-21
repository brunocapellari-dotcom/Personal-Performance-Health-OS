from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from .analytics import RecoverySignalEngine, StrengthHistoryEngine, TrainingHistoryEngine
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
    StrengthProgression,
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
from .observation_pipeline import (
    ADDITIVE_DAILY_METRICS,
    ObservationPipeline,
    ObservationPipelineResult,
    load_health_connect_records,
    load_health_quality_config,
)


@dataclass(frozen=True)
class ResolvedPlanningState:
    goals: tuple[Goal, ...]
    environment: TrainingEnvironment
    readiness: ReadinessInput
    nutrition_trend: NutritionTrend | None
    event: Event | None
    training_response: TrainingResponse | None
    availability: tuple[AvailabilityWindow, ...]
    strength_progressions: dict[str, StrengthProgression]


class PlanningStateResolver:
    def resolve(self, db: Session, *, today: date, weeks: int) -> ResolvedPlanningState:
        planning_now = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=UTC)
        health_pipeline = self.health_pipeline(db, now=planning_now)
        goals = self.goals(db, now=planning_now, pipeline=health_pipeline)
        if not goals:
            raise ValueError("no active goals are synchronized")
        environment = self.environment(db)
        if environment is None:
            raise ValueError("no active training environment is synchronized")
        readiness = self.readiness(db, now=planning_now, pipeline=health_pipeline)
        if readiness is None:
            raise ValueError("no readiness check-in is synchronized")

        return ResolvedPlanningState(
            goals=goals,
            environment=environment,
            readiness=readiness,
            nutrition_trend=self.nutrition(db),
            event=self.event(db, today),
            training_response=self.training_response(db),
            availability=self.availability(db, today, weeks),
            strength_progressions=self.strength_progressions(db, environment),
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

    def goals(
        self,
        db: Session,
        *,
        now: datetime | None = None,
        pipeline: ObservationPipelineResult | None = None,
    ) -> tuple[Goal, ...]:
        assessments = self._latest_assessments(db)
        resolved_pipeline = pipeline if pipeline is not None else self.health_pipeline(db, now=now)
        baselines = resolved_pipeline.baselines if resolved_pipeline is not None else {}
        latest_by_metric: dict[str, float] = {}
        if resolved_pipeline is not None:
            for observation in resolved_pipeline.canonical:
                if isinstance(observation.value, (int, float)):
                    latest_by_metric[observation.metric] = float(observation.value)

        goals: list[Goal] = []
        for row in self._active(db, "goal"):
            payload = GoalPayload.model_validate(row.payload)
            current = payload.current
            if current is None and payload.metric in assessments:
                current = assessments[payload.metric]
            if (
                current is None
                and payload.metric not in ADDITIVE_DAILY_METRICS
                and payload.metric in latest_by_metric
            ):
                current = latest_by_metric[payload.metric]
            if current is None and payload.metric in baselines:
                baseline = baselines[payload.metric]
                if payload.metric not in ADDITIVE_DAILY_METRICS or baseline.day_count >= 3:
                    current = baseline.value
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
                    current=current,
                )
            )
        return tuple(sorted(goals, key=lambda item: (-item.priority, item.goal_id)))

    def health_pipeline(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> ObservationPipelineResult | None:
        records = load_health_connect_records(db)
        if not records:
            return None
        source_priority, expectations = load_health_quality_config(db)
        return ObservationPipeline().run_health_connect(
            records,
            source_priority=source_priority,
            expectations=expectations,
            now=now,
        )

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

    def readiness(
        self,
        db: Session,
        *,
        now: datetime | None = None,
        pipeline: ObservationPipelineResult | None = None,
    ) -> ReadinessInput | None:
        row = self._latest(db, "readiness")
        if row is None:
            return None
        payload = ReadinessPayload.model_validate(row.payload)
        resolved_pipeline = pipeline if pipeline is not None else self.health_pipeline(db, now=now)
        resting_hr_delta_pct = payload.resting_hr_delta_pct
        hrv_delta_pct = payload.hrv_delta_pct
        if resolved_pipeline is not None:
            engine = RecoverySignalEngine()
            if resting_hr_delta_pct is None:
                signal = engine.derive(
                    resolved_pipeline.canonical,
                    "resting_heart_rate_bpm",
                    now=now,
                )
                if signal is not None:
                    resting_hr_delta_pct = signal.delta_pct
            if hrv_delta_pct is None:
                signal = engine.derive(
                    resolved_pipeline.canonical,
                    "hrv_rmssd_ms",
                    now=now,
                )
                if signal is not None:
                    hrv_delta_pct = signal.delta_pct
        return ReadinessInput(
            sleep_hours=payload.sleep_hours,
            sleep_quality_1_5=payload.sleep_quality_1_5,
            energy_1_5=payload.energy_1_5,
            fatigue_1_5=payload.fatigue_1_5,
            soreness_1_5=payload.soreness_1_5,
            stress_1_5=payload.stress_1_5,
            resting_hr_delta_pct=resting_hr_delta_pct,
            hrv_delta_pct=hrv_delta_pct,
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

    def strength_progressions(
        self,
        db: Session,
        environment: TrainingEnvironment,
    ) -> dict[str, StrengthProgression]:
        snapshot = self._latest_plan_snapshot(db)
        if snapshot is None:
            return {}
        raw_sessions = snapshot.plan_json.get("sessions")
        if not isinstance(raw_sessions, list):
            return {}

        targets: dict[str, tuple[tuple[int, int], float]] = {}
        for raw_session in raw_sessions:
            if not isinstance(raw_session, dict):
                continue
            prescriptions = raw_session.get("prescriptions", [])
            if not isinstance(prescriptions, list):
                continue
            for prescription in prescriptions:
                if not isinstance(prescription, dict):
                    continue
                exercise_id = prescription.get("exercise_id")
                rep_range = prescription.get("rep_range")
                target_rir = prescription.get("target_rir")
                if (
                    isinstance(exercise_id, str)
                    and isinstance(rep_range, list)
                    and len(rep_range) == 2
                    and all(isinstance(value, int) for value in rep_range)
                    and isinstance(target_rir, (int, float))
                ):
                    targets[exercise_id] = ((int(rep_range[0]), int(rep_range[1])), float(target_rir))
        if not targets:
            return {}
        return StrengthHistoryEngine().recommend(
            targets,
            self._performed_sessions(db),
            environment.load_options_kg,
        )

    def _derive_training_response(self, db: Session) -> TrainingResponse | None:
        planned = self._planned_sessions(db)
        if not planned:
            return None
        performed = self._performed_sessions(db)
        if not performed:
            return None
        return TrainingHistoryEngine().summarize(planned, performed)

    def _latest_plan_snapshot(self, db: Session) -> PlanSnapshotModel | None:
        return db.scalar(select(PlanSnapshotModel).order_by(PlanSnapshotModel.created_at.desc()).limit(1))

    def _planned_sessions(self, db: Session) -> tuple[SessionPlan, ...]:
        snapshot = self._latest_plan_snapshot(db)
        if snapshot is None:
            return ()
        raw_sessions = snapshot.plan_json.get("sessions")
        if not isinstance(raw_sessions, list):
            return ()

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
        return tuple(planned)

    def _performed_sessions(self, db: Session) -> tuple[PerformedSession, ...]:
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
        return tuple(performed)

