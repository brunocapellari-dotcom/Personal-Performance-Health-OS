from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .domain import AuditReport, BlockPlan, Event, Goal, NutritionTrend, ReadinessInput, TrainingEnvironment
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
    ) -> NextBlockResult:
        plan = self.director.build_next_block(
            goals=goals,
            environment=environment,
            readiness=readiness,
            nutrition_trend=nutrition_trend,
            event=event,
            today=today,
            weeks=weeks,
        )
        audit = self.auditor.audit(plan, environment)
        return NextBlockResult(plan=plan, audit=audit)
