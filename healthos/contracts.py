from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class CalendarWindow:
    start: datetime
    end: datetime
    available_minutes: int
    source_event_ids: tuple[str, ...] = ()


class CalendarProvider(Protocol):
    def availability(self, start: datetime, end: datetime) -> tuple[CalendarWindow, ...]: ...


@dataclass(frozen=True)
class EvidenceReference:
    evidence_id: str
    claim: str
    evidence_kind: str
    source_uri: str | None
    version_or_date: str | None
    confidence: float | None


class KnowledgeProvider(Protocol):
    def evidence_for(self, topic: str) -> tuple[EvidenceReference, ...]: ...


@dataclass(frozen=True)
class FoodRecord:
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
    source_record_id: str | None = None
    license_id: str | None = None
    retrieved_at: datetime | None = None
    raw_hash: str | None = None


class NutritionDataProvider(Protocol):
    def search(self, query: str) -> tuple[FoodRecord, ...]: ...


class PackagedFoodProvider(Protocol):
    def lookup_barcode(self, barcode: str) -> FoodRecord | None: ...
