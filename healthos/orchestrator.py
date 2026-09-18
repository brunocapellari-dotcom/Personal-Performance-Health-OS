from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .domain import (
    AuditReport,
    AvailabilityWindow,
    BlockPlan,
    Event,
    Goal,
    NutritionTrend,
    ReadinessInput,
    TrainingEnvironment,
    TrainingResponse,
    StrengthProgression,
)
from .planner import PerformanceDirector, ProgramAuditor


@dataclass(frozen=True)
class NextBlockResult:
    plan: BlockPlan
    audit: AuditReport


class HealthOS:
    """Single orchestration entry point for the user command: 'Monta meu próximo bloco'."""

    def __init__(self) -> None:
        self.director = PerformanceDirector()
        self.auditor = ProgramAuditor()

    def next_block(
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
    ) -> NextBlockResult:
        plan = self.director.build_next_block(
            goals=goals,
            environment=environment,
            readiness=readiness,
            nutrition_trend=nutrition_trend,
            event=event,
            today=today,
            weeks=weeks,
            training_response=training_response,
            availability=availability,
            strength_progressions=strength_progressions,
        )
        audit = self.auditor.audit(plan, environment)
        return NextBlockResult(plan=plan, audit=audit)
