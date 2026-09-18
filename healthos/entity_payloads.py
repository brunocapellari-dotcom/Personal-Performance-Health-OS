from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

MAX_SYNC_PAYLOAD_BYTES = 256 * 1024


class EntityPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoalPayload(EntityPayload):
    goal_id: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1000)
    priority: int = Field(ge=1, le=5)
    baseline: float | None = None
    current: float | None = None
    target: float | None = None
    target_date: date | None = None
    metric: str = Field(min_length=1, max_length=128)
    constraints: list[str] = Field(default_factory=list, max_length=50)
    status: Literal["DEVELOP", "MAINTAIN", "REDUCE_TEMPORARILY"] = "DEVELOP"


class TrainingEnvironmentPayload(EntityPayload):
    environment: Literal["HOME", "GYM", "OUTDOOR", "TRAVEL", "MINIMAL_EQUIPMENT"]
    equipment: list[str] = Field(default_factory=list, max_length=100)
    space_m2: float = Field(gt=0, le=100000)
    fixation_points: list[str] = Field(default_factory=list, max_length=50)
    noise_limit: Literal["low", "moderate", "high"] = "moderate"
    surface: str = Field(default="indoor", min_length=1, max_length=128)
    available_minutes: int = Field(ge=15, le=240)
    load_options_kg: list[float] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_load_options(self) -> "TrainingEnvironmentPayload":
        if any(value <= 0 or value > 5000 for value in self.load_options_kg):
            raise ValueError("load_options_kg must contain positive realistic loads")
        if len(set(self.load_options_kg)) != len(self.load_options_kg):
            raise ValueError("load_options_kg cannot contain duplicates")
        return self


class ReadinessPayload(EntityPayload):
    observed_at: datetime | None = None
    sleep_hours: float = Field(ge=0, le=24)
    sleep_quality_1_5: int = Field(ge=1, le=5)
    energy_1_5: int = Field(ge=1, le=5)
    fatigue_1_5: int = Field(ge=1, le=5)
    soreness_1_5: int = Field(ge=1, le=5)
    stress_1_5: int = Field(ge=1, le=5)
    resting_hr_delta_pct: float | None = Field(default=None, ge=-100, le=300)
    hrv_delta_pct: float | None = Field(default=None, ge=-100, le=500)
    pain_flag: bool = False


class NutritionTrendPayload(EntityPayload):
    observed_at: datetime | None = None
    days: int = Field(ge=7, le=180)
    avg_intake_kcal: float = Field(gt=0, le=15000)
    weight_start_kg: float = Field(gt=0, le=1000)
    weight_end_kg: float = Field(gt=0, le=1000)
    current_tdee_estimate_kcal: float = Field(gt=0, le=15000)


class EventPayload(EntityPayload):
    event_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=500)
    event_date: date
    demands: list[str] = Field(default_factory=list, max_length=50)
    duration_minutes: int | None = Field(default=None, gt=0, le=100000)
    distance_km: float | None = Field(default=None, gt=0, le=10000)
    priority: int = Field(default=1, ge=1, le=5)


class TrainingResponsePayload(EntityPayload):
    sessions_planned: int = Field(ge=0, le=100)
    sessions_completed: int = Field(ge=0, le=100)
    avg_rpe: float | None = Field(default=None, ge=0, le=10)
    load_ratio: float | None = Field(default=None, ge=0, le=5)

    @model_validator(mode="after")
    def completed_not_above_planned(self) -> "TrainingResponsePayload":
        if self.sessions_completed > self.sessions_planned:
            raise ValueError("sessions_completed cannot exceed sessions_planned")
        return self


class CalendarAvailabilityPayload(EntityPayload):
    day: date
    available_minutes: int = Field(ge=15, le=240)


class PerformedSetPayload(EntityPayload):
    set_number: int = Field(ge=1, le=100)
    reps: int | None = Field(default=None, ge=0, le=10000)
    load_kg: float | None = Field(default=None, ge=0, le=5000)
    rir: float | None = Field(default=None, ge=0, le=10)
    rpe: float | None = Field(default=None, ge=0, le=10)
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    distance_m: float | None = Field(default=None, ge=0, le=1000000)


class PerformedExercisePayload(EntityPayload):
    exercise_id: str = Field(min_length=1, max_length=128)
    sets: list[PerformedSetPayload] = Field(default_factory=list, max_length=100)


class PerformedSessionPayload(EntityPayload):
    planned_session_id: str = Field(min_length=1, max_length=128)
    performed_at: datetime
    completed: bool
    duration_minutes: int = Field(ge=0, le=1440)
    rpe: float | None = Field(default=None, ge=0, le=10)
    avg_hr_bpm: float | None = Field(default=None, ge=20, le=300)
    max_hr_bpm: float | None = Field(default=None, ge=20, le=300)
    distance_m: float | None = Field(default=None, ge=0, le=1000000)
    notes: str = Field(default="", max_length=5000)
    exercises: list[PerformedExercisePayload] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def heart_rate_order(self) -> "PerformedSessionPayload":
        if self.avg_hr_bpm is not None and self.max_hr_bpm is not None and self.avg_hr_bpm > self.max_hr_bpm:
            raise ValueError("avg_hr_bpm cannot exceed max_hr_bpm")
        return self


class AssessmentResultPayload(EntityPayload):
    assessment_id: str = Field(min_length=1, max_length=128)
    metric: str = Field(min_length=1, max_length=128)
    value: float
    unit: str = Field(min_length=1, max_length=64)
    observed_at: datetime
    context: str | None = Field(default=None, max_length=1000)


class CheckinPayload(EntityPayload):
    observed_at: datetime
    weight_kg: float | None = Field(default=None, gt=0, le=1000)
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    energy_1_5: int | None = Field(default=None, ge=1, le=5)
    fatigue_1_5: int | None = Field(default=None, ge=1, le=5)
    soreness_1_5: int | None = Field(default=None, ge=1, le=5)
    stress_1_5: int | None = Field(default=None, ge=1, le=5)
    pain_flag: bool = False
    notes: str = Field(default="", max_length=5000)


class MedicationEventPayload(EntityPayload):
    medication_id: str = Field(min_length=1, max_length=128)
    observed_at: datetime
    action: Literal["taken", "missed", "note", "interaction_flag", "adherence_update"]
    notes: str = Field(default="", max_length=5000)


class SupplementEventPayload(EntityPayload):
    supplement_id: str = Field(min_length=1, max_length=128)
    observed_at: datetime
    action: Literal["taken", "missed", "note", "effect", "interaction_flag"]
    notes: str = Field(default="", max_length=5000)


class BodyMeasurementPayload(EntityPayload):
    metric: Literal["weight", "waist", "abdomen", "chest", "arm", "thigh", "hip", "neck", "other"]
    value: float = Field(gt=0, le=1000)
    unit: str = Field(min_length=1, max_length=32)
    observed_at: datetime
    label: str | None = Field(default=None, max_length=128)


class HealthObservationPayload(EntityPayload):
    record_type: str = Field(min_length=1, max_length=128)
    source_record_id: str = Field(min_length=1, max_length=256)
    observed_at_epoch_ms: int = Field(ge=1)
    data_origin_package: str = Field(min_length=1, max_length=512)
    health_connect_deleted: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class GenericObservationPayload(EntityPayload):
    metric: str = Field(min_length=1, max_length=128)
    value: float | str
    unit: str | None = Field(default=None, max_length=64)
    observed_at: datetime | None = None
    synthetic: bool | None = None


ENTITY_MODELS: dict[str, type[EntityPayload]] = {
    "goal": GoalPayload,
    "training_environment": TrainingEnvironmentPayload,
    "readiness": ReadinessPayload,
    "nutrition_trend": NutritionTrendPayload,
    "event": EventPayload,
    "training_response": TrainingResponsePayload,
    "calendar_availability": CalendarAvailabilityPayload,
    "performed_session": PerformedSessionPayload,
    "assessment_result": AssessmentResultPayload,
    "checkin": CheckinPayload,
    "medication_event": MedicationEventPayload,
    "supplement_event": SupplementEventPayload,
    "body_measurement": BodyMeasurementPayload,
    "health_connect_tombstone": HealthObservationPayload,
}


def validate_entity_payload(entity_type: str, entity_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    size = len(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))
    if size > MAX_SYNC_PAYLOAD_BYTES:
        raise ValueError(f"sync payload exceeds {MAX_SYNC_PAYLOAD_BYTES} bytes")

    try:
        if entity_type == "observation":
            model: EntityPayload
            if "record_type" in payload:
                model = HealthObservationPayload.model_validate(payload)
            else:
                model = GenericObservationPayload.model_validate(payload)
        else:
            model_type = ENTITY_MODELS.get(entity_type)
            if model_type is None:
                raise ValueError(f"unsupported entity_type: {entity_type}")
            model = model_type.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid {entity_type} payload: {exc.errors(include_url=False)}") from exc

    normalized = model.model_dump(mode="json", exclude_none=True)

    id_field_by_type = {
        "goal": "goal_id",
        "event": "event_id",
        "assessment_result": "assessment_id",
    }
    id_field = id_field_by_type.get(entity_type)
    if id_field is not None and str(normalized[id_field]) != entity_id:
        raise ValueError(f"{entity_type} entity_id must match payload {id_field}")

    return normalized
