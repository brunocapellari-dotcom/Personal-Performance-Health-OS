from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from .domain import (
    AuditFinding,
    AuditReport,
    BlockPlan,
    ConditioningPrescription,
    Event,
    ExercisePrescription,
    Goal,
    NutritionTrend,
    Phase,
    ReadinessInput,
    SessionPlan,
    TrainingEnvironment,
)
from .engines import (
    AdaptiveNutritionEngine,
    EventEngine,
    GoalConflictEngine,
    GoalGapEngine,
    PeriodizationEngine,
    ReadinessEngine,
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
    ) -> BlockPlan:
        goal_decisions = self.goal_conflicts.decide(goals, event, today)
        goal_gaps = self.goal_gaps.calculate(goals)
        readiness_decision = self.readiness.evaluate(readiness)
        phases = self.periodization.phases(weeks, event, today)
        specificity = self.event_engine.specificity(event, today)
        nutrition_target = None
        if nutrition_trend:
            nutrition_target = self.nutrition.infer(nutrition_trend).blended_tdee_kcal

        def prescribe(exercise_ids: tuple[str, ...], phase: Phase) -> tuple[ExercisePrescription, ...]:
            if phase in {Phase.INTENSIFICATION, Phase.REALIZATION}:
                sets, reps, rir, rest = 4, (4, 8), 2.0, 150
            elif phase in {Phase.DELOAD, Phase.TAPER}:
                sets, reps, rir, rest = 2, (6, 10), 4.0, 120
            else:
                sets, reps, rir, rest = 3, (6, 12), 3.0, 120
            return tuple(
                ExercisePrescription(
                    exercise_id=exercise_id,
                    sets=sets,
                    rep_range=reps,
                    target_rir=rir,
                    load_kg=None,
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

        sessions: list[SessionPlan] = []
        for week, phase in enumerate(phases, start=1):
            readiness_modifier = 0.85 if readiness_decision.action == "REDUCE_VOLUME_10_20" else 1.0
            if readiness_decision.action in {"LOW_INTENSITY_OR_TECHNIQUE", "RECOVERY_BIASED", "SAFETY_REVIEW"}:
                readiness_modifier = 0.65
            strength_duration = max(20, round(environment.available_minutes * readiness_modifier))
            strength_a_exercises = tuple(strength_exercises[0::2])
            strength_b_exercises = tuple(strength_exercises[1::2])
            strength_notes: tuple[str, ...] = ("deterministic_progression", "capacity_based_not_cosmetic")
            if readiness_decision.action == "SAFETY_REVIEW":
                strength_duration = min(20, environment.available_minutes)
                strength_a_exercises = ()
                strength_b_exercises = ()
                strength_notes = ("safety_review_required_before_training",)
            sessions.append(
                SessionPlan(
                    session_id=f"w{week}-strength-a",
                    week=week,
                    day_label="Strength A",
                    focus="strength+operational",
                    phase=phase,
                    duration_minutes=strength_duration,
                    prescriptions=prescribe(strength_a_exercises, phase),
                    conditioning=None,
                    notes=strength_notes,
                )
            )
            conditioning_mode = "zone2"
            if phase in {Phase.INTENSIFICATION, Phase.REALIZATION}:
                conditioning_mode = "threshold_intervals"
            if phase == Phase.TAPER:
                conditioning_mode = "short_easy_specific"
            if event and specificity >= 0.7:
                conditioning_mode += "+event_specific"
            conditioning_duration = (
                min(20, environment.available_minutes)
                if readiness_decision.action == "SAFETY_REVIEW"
                else max(20, min(60, environment.available_minutes))
            )
            sessions.append(
                SessionPlan(
                    session_id=f"w{week}-conditioning",
                    week=week,
                    day_label="Conditioning",
                    focus="aerobic/work_capacity",
                    phase=phase,
                    duration_minutes=conditioning_duration,
                    prescriptions=(),
                    conditioning=None
                    if readiness_decision.action == "SAFETY_REVIEW"
                    else ConditioningPrescription(
                        modality=conditioning_mode,
                        duration_minutes=conditioning_duration,
                        exercise_id=locomotion[0].exercise_id if locomotion else None,
                        intensity_method="HR_or_RPE",
                        intensity_target="individualized_zone_or_session_target",
                    ),
                    notes=("record_hr_or_rpe",)
                    if readiness_decision.action != "SAFETY_REVIEW"
                    else ("safety_review_required_before_training",),
                )
            )
            sessions.append(
                SessionPlan(
                    session_id=f"w{week}-strength-b",
                    week=week,
                    day_label="Strength B",
                    focus="strength+robustness",
                    phase=phase,
                    duration_minutes=strength_duration,
                    prescriptions=prescribe(strength_b_exercises, phase),
                    conditioning=None,
                    notes=("planned_vs_performed_required",)
                    if readiness_decision.action != "SAFETY_REVIEW"
                    else ("safety_review_required_before_training",),
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
            },
        )


class ProgramAuditor:
    """Independent rule-based auditor. Must not mutate the planner output."""

    def audit(self, plan: BlockPlan, env: TrainingEnvironment, selector: ExerciseSelector | None = None) -> AuditReport:
        selector = selector or ExerciseSelector()
        findings: list[AuditFinding] = []
        eligible_ids = {e.exercise_id for e in selector.eligible(env)}

        if len(plan.sessions) != plan.weeks * 3:
            findings.append(
                AuditFinding(
                    "error", "SESSION_COUNT", "Expected exactly 3 planned sessions per week in baseline policy"
                )
            )
        if plan.readiness.action == "SAFETY_REVIEW" and any(s.duration_minutes > 30 for s in plan.sessions):
            findings.append(
                AuditFinding("error", "SAFETY_OVERRIDE", "Pain/safety review must prevent normal-duration training")
            )
        for session in plan.sessions:
            if session.duration_minutes > env.available_minutes:
                findings.append(AuditFinding("error", "TIME", f"{session.session_id} exceeds available time"))
            for ex_id in session.exercises:
                if ex_id not in eligible_ids:
                    findings.append(
                        AuditFinding("error", "ENVIRONMENT", f"{ex_id} violates environment/equipment constraints")
                    )
        if not plan.goal_decisions:
            findings.append(AuditFinding("warning", "NO_GOALS", "No goals were available to drive the program"))
        return AuditReport(passed=not any(f.severity == "error" for f in findings), findings=tuple(findings))
