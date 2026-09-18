from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite
from statistics import mean

from .domain import (
    Event,
    Goal,
    GoalStatus,
    NutritionDecision,
    NutritionTrend,
    Phase,
    ReadinessDecision,
    ReadinessInput,
    StrengthPerformance,
    StrengthProgression,
)


@dataclass(frozen=True)
class GoalGap:
    goal_id: str
    absolute_gap: float | None
    relative_gap_pct: float | None
    target_reached: bool | None


class GoalGapEngine:
    """Calculate measurable gaps without assuming whether higher or lower is better.

    The caller can set direction per metric in the future. Until then, target_reached is
    intentionally left unknown; the signed gap still supports planning and reporting.
    """

    def calculate(self, goals: tuple[Goal, ...]) -> dict[str, GoalGap]:
        output: dict[str, GoalGap] = {}
        for goal in goals:
            if goal.baseline is None or goal.target is None:
                output[goal.goal_id] = GoalGap(goal.goal_id, None, None, None)
                continue
            gap = goal.target - goal.baseline
            relative = None if goal.baseline == 0 else gap / abs(goal.baseline) * 100.0
            output[goal.goal_id] = GoalGap(
                goal.goal_id,
                round(gap, 4),
                None if relative is None else round(relative, 2),
                None,
            )
        return output


class GoalConflictEngine:
    """Deterministic capacity allocation. LLMs may explain, not override hard decisions."""

    def decide(self, goals: tuple[Goal, ...], event: Event | None, today: date) -> dict[str, GoalStatus]:
        if not goals:
            return {}
        decisions = {g.goal_id: GoalStatus.DEVELOP for g in goals}
        sorted_goals = sorted(goals, key=lambda g: g.priority, reverse=True)
        primary = sorted_goals[0]
        if event:
            days = (event.event_date - today).days
            if 0 <= days <= 42:
                for g in goals:
                    text = (g.description + " " + g.metric).lower()
                    event_related = any(d.lower() in text for d in event.demands)
                    if event_related:
                        decisions[g.goal_id] = GoalStatus.DEVELOP
                    elif g.goal_id != primary.goal_id:
                        decisions[g.goal_id] = GoalStatus.MAINTAIN
                return decisions
        if len(goals) >= 3:
            for g in sorted_goals[2:]:
                decisions[g.goal_id] = GoalStatus.MAINTAIN
        return decisions


class ReadinessEngine:
    def evaluate(self, x: ReadinessInput) -> ReadinessDecision:
        if x.pain_flag:
            return ReadinessDecision(0.0, "SAFETY_REVIEW", ("pain_flag",))
        sleep_duration = max(0.0, min(1.0, (x.sleep_hours - 4.0) / 4.0))
        sleep_quality = (max(1, min(5, x.sleep_quality_1_5)) - 1) / 4
        energy = (max(1, min(5, x.energy_1_5)) - 1) / 4
        fatigue = 1 - ((max(1, min(5, x.fatigue_1_5)) - 1) / 4)
        soreness = 1 - ((max(1, min(5, x.soreness_1_5)) - 1) / 4)
        stress = 1 - ((max(1, min(5, x.stress_1_5)) - 1) / 4)
        subjective = mean([sleep_duration, sleep_quality, energy, fatigue, soreness, stress])

        objective_parts: list[float] = []
        if x.resting_hr_delta_pct is not None:
            objective_parts.append(max(0.0, min(1.0, 1 - max(0.0, x.resting_hr_delta_pct) / 12.0)))
        if x.hrv_delta_pct is not None:
            objective_parts.append(max(0.0, min(1.0, 1 + min(0.0, x.hrv_delta_pct) / 25.0)))
        objective = mean(objective_parts) if objective_parts else subjective
        score = round(100 * (0.75 * subjective + 0.25 * objective), 1)

        if score >= 75:
            return ReadinessDecision(score, "NORMAL", ("multi_signal_ready",))
        if score >= 55:
            return ReadinessDecision(score, "REDUCE_VOLUME_10_20", ("moderate_readiness",))
        if score >= 35:
            return ReadinessDecision(score, "LOW_INTENSITY_OR_TECHNIQUE", ("low_readiness",))
        return ReadinessDecision(score, "RECOVERY_BIASED", ("very_low_readiness",))


class StrengthEngine:
    def next_load(self, p: StrengthPerformance) -> StrengthProgression:
        if not p.reps_by_set or len(p.reps_by_set) != len(p.rir_by_set):
            raise ValueError("reps_by_set and rir_by_set must be non-empty and same length")
        low, high = p.target_rep_range
        if low <= 0 or high < low or p.increment_kg <= 0:
            raise ValueError("invalid progression parameters")
        all_at_top = all(r >= high for r in p.reps_by_set)
        rir_ok = all(r >= p.target_rir for r in p.rir_by_set)
        failed_floor = sum(r < low for r in p.reps_by_set) >= max(1, len(p.reps_by_set) // 2)
        if all_at_top and rir_ok:
            return StrengthProgression(round(p.load_kg + p.increment_kg, 2), "double_progression_increment")
        if failed_floor:
            return StrengthProgression(round(max(0.0, p.load_kg * 0.95), 2), "performance_regression_reduce_5pct")
        return StrengthProgression(round(p.load_kg, 2), "hold_load_accumulate_reps")


class AdaptiveNutritionEngine:
    KCAL_PER_KG = 7700.0

    def infer(self, trend: NutritionTrend) -> NutritionDecision:
        if trend.days < 7:
            return NutritionDecision(trend.current_tdee_estimate_kcal, trend.current_tdee_estimate_kcal, "low")
        delta_kg = trend.weight_end_kg - trend.weight_start_kg
        inferred = trend.avg_intake_kcal - (delta_kg * self.KCAL_PER_KG / trend.days)
        if not isfinite(inferred) or inferred < 1000 or inferred > 7000:
            return NutritionDecision(trend.current_tdee_estimate_kcal, trend.current_tdee_estimate_kcal, "low")
        weight = 0.25 if trend.days < 14 else 0.4 if trend.days < 28 else 0.55
        blended = (1 - weight) * trend.current_tdee_estimate_kcal + weight * inferred
        confidence = "medium" if trend.days < 28 else "high"
        return NutritionDecision(round(inferred, 0), round(blended, 0), confidence)


class PeriodizationEngine:
    def phases(self, weeks: int, event: Event | None, today: date) -> tuple[Phase, ...]:
        if weeks <= 0:
            raise ValueError("weeks must be positive")
        if event:
            days = (event.event_date - today).days
            if 0 <= days <= 28:
                base = [Phase.INTENSIFICATION] * max(1, weeks - 2) + [Phase.REALIZATION, Phase.TAPER]
                return tuple(base[-weeks:])
            if 28 < days <= 70:
                pattern = [Phase.ACCUMULATION, Phase.ACCUMULATION, Phase.INTENSIFICATION, Phase.DELOAD]
                return tuple(pattern[i % len(pattern)] for i in range(weeks))
        if weeks == 1:
            return (Phase.ACCUMULATION,)
        if weeks == 2:
            return (Phase.ACCUMULATION, Phase.DELOAD)
        phases = [Phase.ACCUMULATION] * weeks
        phases[-2] = Phase.INTENSIFICATION
        phases[-1] = Phase.DELOAD
        return tuple(phases)


class MissedWorkoutEngine:
    def decision(self, sessions_remaining: int, weekly_load_ratio: float, fatigue_1_5: int, priority: str) -> str:
        if sessions_remaining <= 0:
            return "REMOVE"
        if fatigue_1_5 >= 4:
            return "MINIMUM_EFFECTIVE_DOSE" if priority == "high" else "REMOVE"
        if weekly_load_ratio < 0.7 and sessions_remaining >= 2:
            return "MOVE"
        if weekly_load_ratio < 0.85 and sessions_remaining == 1:
            return "COMBINE_REDUCED"
        return "REMOVE"


class EventEngine:
    def specificity(self, event: Event | None, today: date) -> float:
        if not event:
            return 0.0
        days = max(0, (event.event_date - today).days)
        if days <= 14:
            return 0.9
        if days <= 42:
            return 0.7
        if days <= 84:
            return 0.45
        return 0.25
