from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from .domain import (
    AuditFinding,
    AuditReport,
    AvailabilityWindow,
    BlockPlan,
    ConditioningPrescription,
    Event,
    ExercisePrescription,
    Goal,
    NutritionTrend,
    Phase,
    ReadinessInput,
    SessionPlan,
    StrengthProgression,
    TrainingEnvironment,
    TrainingResponse,
)
from .engines import (
    AdaptiveNutritionEngine,
    EventEngine,
    GoalConflictEngine,
    GoalGapEngine,
    PeriodizationEngine,
    ReadinessEngine,
    TrainingResponseEngine,
)
from .exercise_db import ExerciseSelector


class PerformanceDirector:
    def __init__(self) -> None:
        self.goal_conflicts = GoalConflictEngine()
        self.goal_gaps = GoalGapEngine()
        self.readiness = ReadinessEngine()
        self.periodization = PeriodizationEngine()
        self.event_engine = EventEngine()
        self.exercise_selector = ExerciseSelector()
        self.nutrition = AdaptiveNutritionEngine()
        self.training_response = TrainingResponseEngine()

    def build_next_block(
        self,
        *,
        goals: tuple[Goal, ...],
        environment: TrainingEnvironment,
        readiness: ReadinessInput,
        nutrition_trend: NutritionTrend | None,
        event: Event | None,
        today: date,
        weeks: int = 4,
        training_response: TrainingResponse | None = None,
        availability: tuple[AvailabilityWindow, ...] = (),
        strength_progressions: dict[str, StrengthProgression] | None = None,
    ) -> BlockPlan:
        goal_decisions = self.goal_conflicts.decide(goals, event, today)
        goal_gaps = self.goal_gaps.calculate(goals)
        readiness_decision = self.readiness.evaluate(readiness)
        response_decision = self.training_response.evaluate(training_response)
        phases = self.periodization.phases(weeks, event, today)
        specificity = self.event_engine.specificity(event, today)
        nutrition_target = None
        if nutrition_trend:
            nutrition_target = self.nutrition.infer(nutrition_trend).blended_tdee_kcal

        readiness_modifier = 0.85 if readiness_decision.action == "REDUCE_VOLUME_10_20" else 1.0
        if readiness_decision.action in {"LOW_INTENSITY_OR_TECHNIQUE", "RECOVERY_BIASED", "SAFETY_REVIEW"}:
            readiness_modifier = 0.65
        volume_modifier = min(readiness_modifier, response_decision.volume_modifier)
        strength_progressions = strength_progressions or {}

        def prescribe(exercise_ids: tuple[str, ...], phase: Phase) -> tuple[ExercisePrescription, ...]:
            if phase in {Phase.INTENSIFICATION, Phase.REALIZATION}:
                base_sets, reps, rir, rest = 4, (4, 8), 2.0, 150
            elif phase in {Phase.DELOAD, Phase.TAPER}:
                base_sets, reps, rir, rest = 2, (6, 10), 4.0, 120
            else:
                base_sets, reps, rir, rest = 3, (6, 12), 3.0, 120
            sets = max(1, round(base_sets * volume_modifier))
            adjusted_rir = min(5.0, rir + (1.0 if volume_modifier < 0.8 else 0.0))
            return tuple(
                ExercisePrescription(
                    exercise_id=exercise_id,
                    sets=sets,
                    rep_range=reps,
                    target_rir=adjusted_rir,
                    load_kg=(
                        strength_progressions[exercise_id].next_load_kg
                        if exercise_id in strength_progressions
                        else None
                    ),
                    rest_seconds=rest,
                )
                for exercise_id in exercise_ids
            )

        patterns = ("push", "pull", "squat", "hinge", "lunge", "core")
        strength_exercises: list[str] = []
        for pattern in patterns:
            try:
                strength_exercises.append(self.exercise_selector.choose_one(environment, pattern).exercise_id)
            except ValueError:
                continue

        carries = self.exercise_selector.eligible(environment, "carry")
        locomotion = self.exercise_selector.eligible(environment, "locomotion")
        if carries:
            strength_exercises.append(carries[0].exercise_id)

        strength_a = tuple(strength_exercises[0::2])
        strength_b = tuple(strength_exercises[1::2])
        full_body = tuple(strength_exercises[:5])
        sessions: list[SessionPlan] = []
        sessions_per_week: dict[str, int] = {}
        availability_limits = {window.day.isoformat(): window.available_minutes for window in availability}

        for week, phase in enumerate(phases, start=1):
            week_start = today + timedelta(days=(week - 1) * 7)
            week_end = week_start + timedelta(days=6)
            week_windows = tuple(
                sorted(
                    (
                        window
                        for window in availability
                        if week_start <= window.day <= week_end and window.available_minutes >= 15
                    ),
                    key=lambda item: item.day,
                )
            )

            target_sessions = 1 if readiness_decision.action == "SAFETY_REVIEW" else response_decision.target_sessions_per_week
            slots: tuple[AvailabilityWindow | None, ...]
            if availability:
                slots = tuple(self._select_windows(week_windows, min(target_sessions, len(week_windows))))
            else:
                slots = tuple(None for _ in range(target_sessions))
            sessions_per_week[str(week)] = len(slots)

            if readiness_decision.action == "SAFETY_REVIEW":
                for slot_index, slot in enumerate(slots, start=1):
                    duration = min(20, self._slot_limit(slot, environment))
                    sessions.append(
                        SessionPlan(
                            session_id=f"w{week}-safety-{slot_index}",
                            week=week,
                            day_label="Safety Review",
                            focus="safety/recovery",
                            phase=phase,
                            duration_minutes=duration,
                            prescriptions=(),
                            conditioning=None,
                            notes=("safety_review_required_before_training",),
                            scheduled_date=slot.day if slot else None,
                        )
                    )
                continue

            conditioning_mode = self._conditioning_mode(phase, event is not None and specificity >= 0.7)
            if len(slots) == 1:
                slot = slots[0]
                limit = self._slot_limit(slot, environment)
                conditioning_minutes = min(15, max(10, limit // 3))
                sessions.append(
                    SessionPlan(
                        session_id=f"w{week}-combined",
                        week=week,
                        day_label="Full Body + Conditioning",
                        focus="strength+work_capacity",
                        phase=phase,
                        duration_minutes=max(15, round(limit * volume_modifier)),
                        prescriptions=prescribe(full_body, phase),
                        conditioning=self._conditioning(
                            conditioning_mode,
                            conditioning_minutes,
                            locomotion[0].exercise_id if locomotion else None,
                        ),
                        notes=("minimum_effective_week", "planned_vs_performed_required"),
                        scheduled_date=slot.day if slot else None,
                    )
                )
                continue

            if len(slots) == 2:
                first, second = slots
                first_limit = self._slot_limit(first, environment)
                second_limit = self._slot_limit(second, environment)
                sessions.append(
                    SessionPlan(
                        session_id=f"w{week}-strength-a",
                        week=week,
                        day_label="Strength A",
                        focus="strength+operational",
                        phase=phase,
                        duration_minutes=max(15, round(first_limit * volume_modifier)),
                        prescriptions=prescribe(strength_a, phase),
                        conditioning=None,
                        notes=("deterministic_progression", "capacity_based_not_cosmetic"),
                        scheduled_date=first.day if first else None,
                    )
                )
                conditioning_minutes = min(20, max(10, second_limit // 3))
                sessions.append(
                    SessionPlan(
                        session_id=f"w{week}-strength-b-mixed",
                        week=week,
                        day_label="Strength B + Conditioning",
                        focus="strength+robustness+aerobic",
                        phase=phase,
                        duration_minutes=max(15, round(second_limit * volume_modifier)),
                        prescriptions=prescribe(strength_b, phase),
                        conditioning=self._conditioning(
                            conditioning_mode,
                            conditioning_minutes,
                            locomotion[0].exercise_id if locomotion else None,
                        ),
                        notes=("planned_vs_performed_required", "reduced_frequency_week"),
                        scheduled_date=second.day if second else None,
                    )
                )
                continue

            if len(slots) >= 3:
                first, second, third = slots[:3]
                first_limit = self._slot_limit(first, environment)
                second_limit = self._slot_limit(second, environment)
                third_limit = self._slot_limit(third, environment)
                sessions.extend(
                    (
                        SessionPlan(
                            session_id=f"w{week}-strength-a",
                            week=week,
                            day_label="Strength A",
                            focus="strength+operational",
                            phase=phase,
                            duration_minutes=max(15, round(first_limit * volume_modifier)),
                            prescriptions=prescribe(strength_a, phase),
                            conditioning=None,
                            notes=("deterministic_progression", "capacity_based_not_cosmetic"),
                            scheduled_date=first.day if first else None,
                        ),
                        SessionPlan(
                            session_id=f"w{week}-conditioning",
                            week=week,
                            day_label="Conditioning",
                            focus="aerobic/work_capacity",
                            phase=phase,
                            duration_minutes=max(15, round(second_limit * volume_modifier)),
                            prescriptions=(),
                            conditioning=self._conditioning(
                                conditioning_mode,
                                max(15, round(second_limit * volume_modifier)),
                                locomotion[0].exercise_id if locomotion else None,
                            ),
                            notes=("record_hr_or_rpe",),
                            scheduled_date=second.day if second else None,
                        ),
                        SessionPlan(
                            session_id=f"w{week}-strength-b",
                            week=week,
                            day_label="Strength B",
                            focus="strength+robustness",
                            phase=phase,
                            duration_minutes=max(15, round(third_limit * volume_modifier)),
                            prescriptions=prescribe(strength_b, phase),
                            conditioning=None,
                            notes=("planned_vs_performed_required",),
                            scheduled_date=third.day if third else None,
                        ),
                    )
                )

        return BlockPlan(
            block_id=str(uuid4()),
            generated_at=datetime.now(UTC),
            weeks=weeks,
            phases=phases,
            goal_decisions=goal_decisions,
            readiness=readiness_decision,
            sessions=tuple(sessions),
            nutrition_target_kcal=nutrition_target,
            metadata={
                "event_specificity": specificity,
                "environment": environment.environment.value,
                "equipment": sorted(environment.equipment),
                "goal_gaps": {
                    goal_id: {
                        "absolute_gap": gap.absolute_gap,
                        "relative_gap_pct": gap.relative_gap_pct,
                    }
                    for goal_id, gap in goal_gaps.items()
                },
                "recent_adherence": response_decision.adherence,
                "training_response_reasons": response_decision.reasons,
                "volume_modifier": volume_modifier,
                "sessions_per_week": sessions_per_week,
                "availability_enforced": bool(availability),
                "availability_limits": availability_limits,
                "strength_progressions": {
                    exercise_id: {
                        "next_load_kg": decision.next_load_kg,
                        "rationale": decision.rationale,
                    }
                    for exercise_id, decision in sorted(strength_progressions.items())
                },
            },
        )

    @staticmethod
    def _select_windows(
        windows: tuple[AvailabilityWindow, ...],
        count: int,
    ) -> tuple[AvailabilityWindow, ...]:
        if count <= 0 or not windows:
            return ()
        if count >= len(windows):
            return windows
        if count == 1:
            return (windows[len(windows) // 2],)
        indexes = tuple(round(i * (len(windows) - 1) / (count - 1)) for i in range(count))
        return tuple(windows[index] for index in indexes)

    @staticmethod
    def _slot_limit(slot: AvailabilityWindow | None, environment: TrainingEnvironment) -> int:
        if slot is None:
            return environment.available_minutes
        return min(environment.available_minutes, slot.available_minutes)

    @staticmethod
    def _conditioning_mode(phase: Phase, event_specific: bool) -> str:
        mode = "zone2"
        if phase in {Phase.INTENSIFICATION, Phase.REALIZATION}:
            mode = "threshold_intervals"
        elif phase == Phase.TAPER:
            mode = "short_easy_specific"
        if event_specific:
            mode += "+event_specific"
        return mode

    @staticmethod
    def _conditioning(
        mode: str,
        duration_minutes: int,
        exercise_id: str | None,
    ) -> ConditioningPrescription:
        return ConditioningPrescription(
            modality=mode,
            duration_minutes=duration_minutes,
            exercise_id=exercise_id,
            intensity_method="HR_or_RPE",
            intensity_target="individualized_zone_or_session_target",
        )


class ProgramAuditor:
    """Independent rule-based auditor. Must not mutate the planner output."""

    def audit(self, plan: BlockPlan, env: TrainingEnvironment, selector: ExerciseSelector | None = None) -> AuditReport:
        selector = selector or ExerciseSelector()
        findings: list[AuditFinding] = []
        eligible_ids = {e.exercise_id for e in selector.eligible(env)}
        expected_counts = {int(key): int(value) for key, value in plan.metadata.get("sessions_per_week", {}).items()}
        actual_counts = Counter(session.week for session in plan.sessions)

        for week in range(1, plan.weeks + 1):
            expected = expected_counts.get(week)
            if expected is not None and actual_counts.get(week, 0) != expected:
                findings.append(
                    AuditFinding(
                        "error",
                        "SESSION_COUNT",
                        f"Week {week} has {actual_counts.get(week, 0)} sessions but planner declared {expected}",
                    )
                )
            if expected == 0:
                findings.append(
                    AuditFinding("warning", "NO_AVAILABILITY", f"Week {week} has no valid training availability")
                )

        scheduled_dates = [session.scheduled_date for session in plan.sessions if session.scheduled_date is not None]
        if len(scheduled_dates) != len(set(scheduled_dates)):
            findings.append(AuditFinding("error", "DUPLICATE_DATE", "Multiple sessions were scheduled on the same date"))

        availability_limits = {
            date.fromisoformat(key): int(value) for key, value in plan.metadata.get("availability_limits", {}).items()
        }
        availability_enforced = bool(plan.metadata.get("availability_enforced"))

        if plan.readiness.action == "SAFETY_REVIEW":
            if any(s.duration_minutes > 20 for s in plan.sessions):
                findings.append(
                    AuditFinding("error", "SAFETY_OVERRIDE", "Safety review must prevent normal-duration training")
                )
            if any(s.exercises or s.conditioning is not None for s in plan.sessions):
                findings.append(
                    AuditFinding("error", "SAFETY_CONTENT", "Safety review sessions cannot contain normal training")
                )

        for session in plan.sessions:
            if session.duration_minutes > env.available_minutes:
                findings.append(AuditFinding("error", "TIME", f"{session.session_id} exceeds environment time limit"))
            if availability_enforced:
                if session.scheduled_date is None or session.scheduled_date not in availability_limits:
                    findings.append(
                        AuditFinding("error", "CALENDAR", f"{session.session_id} is outside declared availability")
                    )
                elif session.duration_minutes > availability_limits[session.scheduled_date]:
                    findings.append(
                        AuditFinding("error", "CALENDAR_TIME", f"{session.session_id} exceeds calendar availability")
                    )
            for ex_id in session.exercises:
                if ex_id not in eligible_ids:
                    findings.append(
                        AuditFinding("error", "ENVIRONMENT", f"{ex_id} violates environment/equipment constraints")
                    )
            if session.conditioning is not None:
                if session.conditioning.duration_minutes > session.duration_minutes:
                    findings.append(
                        AuditFinding("error", "CONDITIONING_TIME", f"{session.session_id} conditioning exceeds session")
                    )
                if session.conditioning.exercise_id and session.conditioning.exercise_id not in eligible_ids:
                    findings.append(
                        AuditFinding(
                            "error",
                            "CONDITIONING_ENVIRONMENT",
                            f"{session.conditioning.exercise_id} violates environment/equipment constraints",
                        )
                    )

        if not plan.goal_decisions:
            findings.append(AuditFinding("warning", "NO_GOALS", "No goals were available to drive the program"))
        return AuditReport(passed=not any(f.severity == "error" for f in findings), findings=tuple(findings))
