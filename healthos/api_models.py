from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .domain import Environment


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceEnrollRequest(StrictModel):
    device_id: str = Field(min_length=3, max_length=128)
    public_key_pem: str = Field(min_length=120, max_length=4096)
    role: Literal["owner_device", "readonly"] = "owner_device"


class DeviceEnrollResponse(StrictModel):
    device_id: str
    role: str
    fingerprint: str


class ChallengeRequest(StrictModel):
    device_id: str = Field(min_length=3, max_length=128)


class ChallengeResponse(StrictModel):
    challenge_id: str
    nonce: str
    expires_at: datetime


class VerifyRequest(StrictModel):
    challenge_id: str = Field(min_length=16, max_length=64)
    signature_b64: str = Field(min_length=16, max_length=2048)


class TokenResponse(StrictModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class SyncChangeIn(StrictModel):
    change_id: str = Field(min_length=8, max_length=64)
    entity_type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    entity_id: str = Field(min_length=1, max_length=128)
    logical_clock: int = Field(ge=1)
    deleted: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


class SyncPushRequest(StrictModel):
    changes: list[SyncChangeIn] = Field(min_length=1, max_length=250)


class SyncPushResponse(StrictModel):
    accepted: list[str]
    duplicates: list[str]
    conflicts: list[str]
    cursor: int


class SyncChangeOut(StrictModel):
    server_seq: int
    change_id: str
    entity_type: str
    entity_id: str
    logical_clock: int
    origin_device_id: str
    deleted: bool
    payload: dict[str, Any]
    created_at: datetime


class SyncPullResponse(StrictModel):
    changes: list[SyncChangeOut]
    cursor: int


class FoodRecordOut(StrictModel):
    food_id: str
    name: str
    source: str
    source_version: str | None
    energy_kcal_per_100g: float | None
    protein_g_per_100g: float | None
    carbohydrate_g_per_100g: float | None
    fat_g_per_100g: float | None
    micronutrients: dict[str, float]
    source_quality: str
    source_record_id: str | None
    license_id: str | None
    retrieved_at: datetime | None
    raw_hash: str | None


class NutritionSearchResponse(StrictModel):
    foods: list[FoodRecordOut]


class GoalIn(StrictModel):
    goal_id: str
    description: str
    priority: int = Field(ge=1, le=5)
    baseline: float | None = None
    current: float | None = None
    target: float | None = None
    target_date: date | None = None
    metric: str
    constraints: list[str] = Field(default_factory=list)


class TrainingEnvironmentIn(StrictModel):
    environment: Environment
    equipment: list[str] = Field(default_factory=list)
    space_m2: float = Field(gt=0)
    fixation_points: list[str] = Field(default_factory=list)
    noise_limit: str = "moderate"
    surface: str = "indoor"
    available_minutes: int = Field(ge=15, le=240)


class ReadinessIn(StrictModel):
    sleep_hours: float = Field(ge=0, le=24)
    sleep_quality_1_5: int = Field(ge=1, le=5)
    energy_1_5: int = Field(ge=1, le=5)
    fatigue_1_5: int = Field(ge=1, le=5)
    soreness_1_5: int = Field(ge=1, le=5)
    stress_1_5: int = Field(ge=1, le=5)
    resting_hr_delta_pct: float | None = None
    hrv_delta_pct: float | None = None
    pain_flag: bool = False


class NutritionTrendIn(StrictModel):
    days: int = Field(ge=7, le=180)
    avg_intake_kcal: float = Field(gt=0)
    weight_start_kg: float = Field(gt=0)
    weight_end_kg: float = Field(gt=0)
    current_tdee_estimate_kcal: float = Field(gt=0)


class TrainingResponseIn(StrictModel):
    sessions_planned: int = Field(ge=0, le=100)
    sessions_completed: int = Field(ge=0, le=100)
    avg_rpe: float | None = Field(default=None, ge=0, le=10)
    load_ratio: float | None = Field(default=None, ge=0, le=5)

    @model_validator(mode="after")
    def completed_cannot_exceed_planned(self) -> "TrainingResponseIn":
        if self.sessions_completed > self.sessions_planned:
            raise ValueError("sessions_completed cannot exceed sessions_planned")
        return self


class AvailabilityWindowIn(StrictModel):
    day: date
    available_minutes: int = Field(ge=15, le=240)


class EventIn(StrictModel):
    event_id: str
    name: str
    event_date: date
    demands: list[str] = Field(default_factory=list)
    duration_minutes: int | None = Field(default=None, gt=0)
    distance_km: float | None = Field(default=None, gt=0)
    priority: int = Field(default=1, ge=1, le=5)


class NextBlockRequest(StrictModel):
    goals: list[GoalIn] = Field(min_length=1, max_length=20)
    environment: TrainingEnvironmentIn
    readiness: ReadinessIn
    nutrition_trend: NutritionTrendIn | None = None
    event: EventIn | None = None
    training_response: TrainingResponseIn | None = None
    availability: list[AvailabilityWindowIn] = Field(default_factory=list, max_length=84)
    today: date
    weeks: int = Field(default=4, ge=1, le=12)


class NextBlockResponse(StrictModel):
    snapshot_id: str
    plan: dict[str, Any]
    audit: dict[str, Any]
