from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class Environment(StrEnum):
    HOME = "HOME"
    GYM = "GYM"
    OUTDOOR = "OUTDOOR"
    TRAVEL = "TRAVEL"
    MINIMAL_EQUIPMENT = "MINIMAL_EQUIPMENT"


class GoalStatus(StrEnum):
    DEVELOP = "DEVELOP"
    MAINTAIN = "MAINTAIN"
    REDUCE_TEMPORARILY = "REDUCE_TEMPORARILY"


class Phase(StrEnum):
    BASE = "base"
    ACCUMULATION = "accumulation"
    INTENSIFICATION = "intensification"
    REALIZATION = "realization"
    DELOAD = "deload"
    PEAK = "peak"
    TAPER = "taper"


class EvidenceKind(StrEnum):
    EVIDENCE = "EVIDENCE"
    COACHING_PRACTICE = "COACHING_PRACTICE"
    HYPOTHESIS = "HYPOTHESIS"


@dataclass(frozen=True)
class Goal:
    goal_id: str
    description: str
    priority: int
    baseline: float | None
    target: float | None
    target_date: date | None
    metric: str
    constraints: tuple[str, ...] = ()
    status: GoalStatus = GoalStatus.DEVELOP
    current: float | None = None


@dataclass(frozen=True)
class TrainingEnvironment:
    environment: Environment
    equipment: frozenset[str]
    space_m2: float
    fixation_points: frozenset[str] = frozenset()
    noise_limit: str = "moderate"
    surface: str = "indoor"
    available_minutes: int = 60


@dataclass(frozen=True)
class Exercise:
    exercise_id: str
    name: str
    movement_pattern: str
    muscles: tuple[str, ...]
    equipment: frozenset[str]
    environments: frozenset[Environment]
    space_required_m2: float
    noise: str
    skill: int
    fatigue: int
    impact: int
    strength: int
    power: int
    conditioning: int
    unilateral: bool
    progressions: tuple[str, ...] = ()
    regressions: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    operational_capacities: tuple[str, ...] = ()
    fixation_points_required: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ReadinessInput:
    sleep_hours: float
    sleep_quality_1_5: int
    energy_1_5: int
    fatigue_1_5: int
    soreness_1_5: int
    stress_1_5: int
    resting_hr_delta_pct: float | None = None
    hrv_delta_pct: float | None = None
    pain_flag: bool = False


@dataclass(frozen=True)
class ReadinessDecision:
    score: float
    action: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class TrainingResponse:
    sessions_planned: int
    sessions_completed: int
    avg_rpe: float | None = None
    load_ratio: float | None = None


@dataclass(frozen=True)
class AvailabilityWindow:
    day: date
    available_minutes: int


@dataclass(frozen=True)
class Event:
    event_id: str
    name: str
    event_date: date
    demands: tuple[str, ...]
    duration_minutes: int | None = None
    distance_km: float | None = None
    priority: int = 1


@dataclass(frozen=True)
class StrengthPerformance:
    exercise_id: str
    load_kg: float
    reps_by_set: tuple[int, ...]
    rir_by_set: tuple[float, ...]
    target_rep_range: tuple[int, int]
    target_rir: float
    increment_kg: float


@dataclass(frozen=True)
class StrengthProgression:
    next_load_kg: float
    rationale: str


@dataclass(frozen=True)
class NutritionTrend:
    days: int
    avg_intake_kcal: float
    weight_start_kg: float
    weight_end_kg: float
    current_tdee_estimate_kcal: float


@dataclass(frozen=True)
class NutritionDecision:
    inferred_tdee_kcal: float
    blended_tdee_kcal: float
    confidence: str


@dataclass(frozen=True)
class ExercisePrescription:
    exercise_id: str
    sets: int
    rep_range: tuple[int, int] | None = None
    target_rir: float | None = None
    load_kg: float | None = None
    duration_seconds: int | None = None
    distance_m: float | None = None
    rest_seconds: int | None = None
    tempo: str | None = None


@dataclass(frozen=True)
class ConditioningPrescription:
    modality: str
    duration_minutes: int
    intensity_method: str
    intensity_target: str
    exercise_id: str | None = None
    work_seconds: int | None = None
    rest_seconds: int | None = None
    distance_m: float | None = None


@dataclass(frozen=True)
class SessionPlan:
    session_id: str
    week: int
    day_label: str
    focus: str
    phase: Phase
    duration_minutes: int
    prescriptions: tuple[ExercisePrescription, ...]
    conditioning: ConditioningPrescription | None = None
    notes: tuple[str, ...] = ()
    scheduled_date: date | None = None

    @property
    def exercises(self) -> tuple[str, ...]:
        return tuple(p.exercise_id for p in self.prescriptions)


@dataclass(frozen=True)
class BlockPlan:
    block_id: str
    generated_at: datetime
    weeks: int
    phases: tuple[Phase, ...]
    goal_decisions: dict[str, GoalStatus]
    readiness: ReadinessDecision
    sessions: tuple[SessionPlan, ...]
    nutrition_target_kcal: float | None
    audit_required: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditFinding:
    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class AuditReport:
    passed: bool
    findings: tuple[AuditFinding, ...]


@dataclass(frozen=True)
class Medication:
    medication: str
    prescribed_dose: str
    schedule: str
    prescriber: str
    start: date
    end: date | None = None
    adherence: str = "unknown"
    notes: str = ""


@dataclass(frozen=True)
class Supplement:
    supplement: str
    brand: str | None
    dose: str
    schedule: str
    goal: str
    start_date: date
    evidence_level: str
    cost: float | None = None
    observed_effect: str | None = None
    interaction_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Observation:
    observation_id: str
    metric: str
    value: float | str
    unit: str | None
    observed_at: datetime
    recorded_at: datetime
    source_id: str
    source_type: str
    raw_hash: str | None = None
    quality: str = "unknown"
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PerformedSet:
    set_number: int
    reps: int | None = None
    load_kg: float | None = None
    rir: float | None = None
    rpe: float | None = None
    duration_seconds: int | None = None
    distance_m: float | None = None


@dataclass(frozen=True)
class PerformedExercise:
    exercise_id: str
    sets: tuple[PerformedSet, ...]


@dataclass(frozen=True)
class PerformedSession:
    planned_session_id: str
    completed: bool
    duration_minutes: int
    rpe: float | None
    notes: str = ""
    performed_at: datetime | None = None
    avg_hr_bpm: float | None = None
    max_hr_bpm: float | None = None
    distance_m: float | None = None
    exercises: tuple[PerformedExercise, ...] = ()
