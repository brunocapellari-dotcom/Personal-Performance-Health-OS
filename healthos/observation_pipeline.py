from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from statistics import mean, median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .analytic_contracts import (
    AnalyticContractValidator,
    ContractReport,
    OBSERVATION_ANALYTICS_CONTRACT,
    OBSERVATION_BASELINE_CONTRACT,
)
from .data_quality import (
    DataQualityEngine,
    DataQualityFinding,
    DuplicatePolicy,
    MissingDataDetector,
    MissingDataExpectation,
    MissingDataFinding,
    SourceResolver,
)
from .domain import Observation
from .entity_payloads import HealthObservationPayload, HealthSourcePriorityPayload, MetricExpectationPayload
from .models import EntityRecordModel


@dataclass(frozen=True)
class BaselineMetric:
    metric: str
    value: float
    unit: str | None
    method: str
    sample_count: int
    day_count: int
    window_start: datetime
    window_end: datetime
    confidence: float


@dataclass(frozen=True)
class MetricAnalytics:
    metric: str
    unit: str | None
    count: int
    latest_value: float
    latest_at: datetime
    mean_value: float
    median_value: float
    min_value: float
    max_value: float
    change_from_first: float


@dataclass(frozen=True)
class ObservationPipelineResult:
    raw_count: int
    normalized_count: int
    canonical: tuple[Observation, ...]
    source_version_suppressed_ids: tuple[str, ...]
    suppressed_ids: tuple[str, ...]
    quality_findings: tuple[DataQualityFinding, ...]
    missing_findings: tuple[MissingDataFinding, ...]
    baselines: dict[str, BaselineMetric]
    analytics: dict[str, MetricAnalytics]
    baseline_contract: ContractReport
    analytics_contract: ContractReport


PLAUSIBLE_RANGES: dict[str, tuple[float, float]] = {
    "steps": (0.0, 250_000.0),
    "steps_cadence_spm": (0.0, 400.0),
    "heart_rate_bpm": (20.0, 300.0),
    "resting_heart_rate_bpm": (20.0, 300.0),
    "hrv_rmssd_ms": (1.0, 200.0),
    "weight_kg": (1.0, 1000.0),
    "sleep_duration_min": (0.0, 2880.0),
    "exercise_duration_min": (0.0, 2880.0),
    "distance_m": (0.0, 1_000_000.0),
    "speed_m_s": (0.0, 100.0),
    "elevation_gained_m": (-10_000.0, 100_000.0),
    "power_w": (0.0, 5000.0),
    "vo2_max_ml_kg_min": (5.0, 100.0),
    "cycling_cadence_rpm": (0.0, 300.0),
    "floors_climbed": (0.0, 10000.0),
    "body_fat_pct": (0.0, 100.0),
    "lean_body_mass_kg": (0.0, 1000.0),
    "hydration_l": (0.0, 100.0),
    "active_calories_kcal": (0.0, 20_000.0),
    "total_calories_kcal": (0.0, 30_000.0),
}

DUPLICATE_POLICIES: dict[str, DuplicatePolicy] = {
    "steps": DuplicatePolicy(timedelta(seconds=60), 1.0),
    "steps_cadence_spm": DuplicatePolicy(timedelta(seconds=5), 0.5),
    "heart_rate_bpm": DuplicatePolicy(timedelta(seconds=2), 1.0),
    "resting_heart_rate_bpm": DuplicatePolicy(timedelta(minutes=5), 1.0),
    "hrv_rmssd_ms": DuplicatePolicy(timedelta(minutes=5), 1.0),
    "weight_kg": DuplicatePolicy(timedelta(minutes=5), 0.05),
    "sleep_duration_min": DuplicatePolicy(timedelta(minutes=5), 2.0),
    "exercise_duration_min": DuplicatePolicy(timedelta(minutes=5), 1.0),
    "distance_m": DuplicatePolicy(timedelta(seconds=60), 2.0),
    "speed_m_s": DuplicatePolicy(timedelta(seconds=2), 0.05),
    "elevation_gained_m": DuplicatePolicy(timedelta(seconds=60), 0.5),
    "power_w": DuplicatePolicy(timedelta(seconds=2), 2.0),
    "vo2_max_ml_kg_min": DuplicatePolicy(timedelta(minutes=5), 0.2),
    "cycling_cadence_rpm": DuplicatePolicy(timedelta(seconds=2), 1.0),
    "floors_climbed": DuplicatePolicy(timedelta(seconds=60), 0.1),
    "body_fat_pct": DuplicatePolicy(timedelta(minutes=5), 0.2),
    "lean_body_mass_kg": DuplicatePolicy(timedelta(minutes=5), 0.1),
    "hydration_l": DuplicatePolicy(timedelta(minutes=5), 0.05),
    "active_calories_kcal": DuplicatePolicy(timedelta(seconds=60), 1.0),
    "total_calories_kcal": DuplicatePolicy(timedelta(seconds=60), 1.0),
}

ADDITIVE_DAILY_METRICS = frozenset(
    {
        "steps",
        "sleep_duration_min",
        "exercise_duration_min",
        "distance_m",
        "elevation_gained_m",
        "active_calories_kcal",
        "total_calories_kcal",
        "floors_climbed",
        "hydration_l",
    }
)


class HealthConnectNormalizer:
    """Convert Health Connect transport payloads into source-aware canonical observations."""

    def normalize(self, entity_id: str, payload: HealthObservationPayload) -> tuple[Observation, ...]:
        if payload.health_connect_deleted:
            return ()

        data = payload.data
        provenance = self._provenance(payload)
        source_id = self._source_id(payload)
        quality, confidence = self._source_quality(payload)
        recorded_at = (
            datetime.fromtimestamp(payload.last_modified_at_epoch_ms / 1000, tz=UTC)
            if payload.last_modified_at_epoch_ms is not None
            else datetime.fromtimestamp(payload.observed_at_epoch_ms / 1000, tz=UTC)
        )
        raw_hash = hashlib.sha256(
            json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        def observation(
            metric: str,
            value: float | str,
            unit: str | None,
            observed_at: datetime,
            *,
            suffix: str = "",
            extra_metadata: dict[str, Any] | None = None,
        ) -> Observation:
            stable = f"{payload.source_record_id}|{metric}|{observed_at.isoformat()}|{suffix}"
            obs_id = "hc:" + hashlib.sha256(stable.encode("utf-8")).hexdigest()
            metadata = dict(provenance)
            metadata["transport_entity_id"] = entity_id
            metadata["record_type"] = payload.record_type
            if extra_metadata:
                metadata.update(extra_metadata)
            return Observation(
                observation_id=obs_id,
                metric=metric,
                value=value,
                unit=unit,
                observed_at=observed_at,
                recorded_at=recorded_at,
                source_id=source_id,
                source_type="HEALTH_CONNECT",
                raw_hash=raw_hash,
                quality=quality,
                confidence=confidence,
                metadata=metadata,
            )

        record_type = payload.record_type
        fallback_time = datetime.fromtimestamp(payload.observed_at_epoch_ms / 1000, tz=UTC)
        if record_type == "steps":
            return (observation("steps", float(data["count"]), "steps", self._time(data.get("endTime"), fallback_time)),)
        if record_type == "steps_cadence":
            return self._series(
                data,
                observation,
                value_key="stepsPerMinute",
                metric="steps_cadence_spm",
                unit="steps/min",
                fallback_time=fallback_time,
            )
        if record_type == "heart_rate":
            return self._series(
                data,
                observation,
                value_key="bpm",
                metric="heart_rate_bpm",
                unit="bpm",
                fallback_time=fallback_time,
            )
        if record_type == "resting_heart_rate":
            return (
                observation(
                    "resting_heart_rate_bpm",
                    float(data["bpm"]),
                    "bpm",
                    self._time(data.get("time"), fallback_time),
                ),
            )
        if record_type == "weight":
            return (
                observation(
                    "weight_kg",
                    float(data["kilograms"]),
                    "kg",
                    self._time(data.get("time"), fallback_time),
                ),
            )
        if record_type == "sleep":
            start = self._time(data.get("startTime"), fallback_time)
            end = self._time(data.get("endTime"), fallback_time)
            duration = max(0.0, (end - start).total_seconds() / 60.0)
            return (
                observation(
                    "sleep_duration_min",
                    duration,
                    "min",
                    end,
                    extra_metadata={"start_at": start.isoformat(), "sleep_stages": data.get("stages", [])},
                ),
            )
        if record_type == "exercise":
            start = self._time(data.get("startTime"), fallback_time)
            end = self._time(data.get("endTime"), fallback_time)
            duration = max(0.0, (end - start).total_seconds() / 60.0)
            return (
                observation(
                    "exercise_duration_min",
                    duration,
                    "min",
                    end,
                    extra_metadata={
                        "start_at": start.isoformat(),
                        "exercise_type": data.get("exerciseType"),
                        "title": data.get("title"),
                    },
                ),
            )
        if record_type == "distance":
            return (
                observation(
                    "distance_m",
                    float(data["meters"]),
                    "m",
                    self._time(data.get("endTime"), fallback_time),
                ),
            )
        if record_type == "speed":
            return self._series(
                data,
                observation,
                value_key="metersPerSecond",
                metric="speed_m_s",
                unit="m/s",
                fallback_time=fallback_time,
            )
        if record_type == "elevation_gained":
            return (
                observation(
                    "elevation_gained_m",
                    float(data["meters"]),
                    "m",
                    self._time(data.get("endTime"), fallback_time),
                ),
            )
        if record_type == "power":
            return self._series(
                data,
                observation,
                value_key="watts",
                metric="power_w",
                unit="W",
                fallback_time=fallback_time,
            )
        if record_type == "vo2_max":
            return (
                observation(
                    "vo2_max_ml_kg_min",
                    float(data["millilitersPerMinuteKilogram"]),
                    "ml/kg/min",
                    self._time(data.get("time"), fallback_time),
                    extra_metadata={"measurement_method": data.get("measurementMethod")},
                ),
            )
        if record_type == "heart_rate_variability_rmssd":
            return (
                observation(
                    "hrv_rmssd_ms",
                    float(data["rmssdMillis"]),
                    "ms",
                    self._time(data.get("time"), fallback_time),
                ),
            )
        if record_type == "cycling_pedaling_cadence":
            return self._series(
                data,
                observation,
                value_key="revolutionsPerMinute",
                metric="cycling_cadence_rpm",
                unit="rpm",
                fallback_time=fallback_time,
            )
        if record_type == "floors_climbed":
            return (
                observation(
                    "floors_climbed",
                    float(data["floors"]),
                    "floors",
                    self._time(data.get("endTime"), fallback_time),
                ),
            )
        if record_type == "body_fat":
            return (
                observation(
                    "body_fat_pct",
                    float(data["percent"]),
                    "%",
                    self._time(data.get("time"), fallback_time),
                ),
            )
        if record_type == "lean_body_mass":
            return (
                observation(
                    "lean_body_mass_kg",
                    float(data["kilograms"]),
                    "kg",
                    self._time(data.get("time"), fallback_time),
                ),
            )
        if record_type == "hydration":
            return (
                observation(
                    "hydration_l",
                    float(data["liters"]),
                    "L",
                    self._time(data.get("endTime"), fallback_time),
                ),
            )
        if record_type == "active_calories":
            return (
                observation(
                    "active_calories_kcal",
                    float(data["kilocalories"]),
                    "kcal",
                    self._time(data.get("endTime"), fallback_time),
                ),
            )
        if record_type == "total_calories":
            return (
                observation(
                    "total_calories_kcal",
                    float(data["kilocalories"]),
                    "kcal",
                    self._time(data.get("endTime"), fallback_time),
                ),
            )
        return ()

    @staticmethod
    def _series(
        data: dict[str, Any],
        factory: Any,
        *,
        value_key: str,
        metric: str,
        unit: str,
        fallback_time: datetime,
    ) -> tuple[Observation, ...]:
        output: list[Observation] = []
        raw_samples = data.get("samples", [])
        if not isinstance(raw_samples, list):
            return ()
        for index, sample in enumerate(raw_samples):
            if not isinstance(sample, dict) or value_key not in sample:
                continue
            observed_at = HealthConnectNormalizer._time(sample.get("time"), fallback_time)
            output.append(
                factory(
                    metric,
                    float(sample[value_key]),
                    unit,
                    observed_at,
                    suffix=str(index),
                )
            )
        return tuple(output)

    @staticmethod
    def _time(value: object, fallback: datetime) -> datetime:
        if not isinstance(value, str) or not value:
            return fallback
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _source_quality(payload: HealthObservationPayload) -> tuple[str, float]:
        mapping = {
            1: ("high", 0.95),  # actively recorded
            2: ("high", 0.92),  # automatically recorded
            3: ("medium", 0.80),  # manual entry
            0: ("unknown", 0.65),
        }
        quality, confidence = mapping.get(payload.recording_method, ("unknown", 0.60))
        if payload.device_type is not None:
            confidence = min(0.99, confidence + 0.02)
        return quality, confidence

    @staticmethod
    def _source_id(payload: HealthObservationPayload) -> str:
        parts = ["health_connect", payload.data_origin_package]
        if payload.device_manufacturer:
            parts.append(payload.device_manufacturer.strip().lower().replace(" ", "_"))
        if payload.device_model:
            parts.append(payload.device_model.strip().lower().replace(" ", "_"))
        if payload.device_type is not None:
            parts.append(str(payload.device_type))
        return ":".join(parts)

    @staticmethod
    def _provenance(payload: HealthObservationPayload) -> dict[str, Any]:
        return {
            "source_record_id": payload.source_record_id,
            "data_origin_package": payload.data_origin_package,
            "last_modified_at_epoch_ms": payload.last_modified_at_epoch_ms,
            "client_record_id": payload.client_record_id,
            "client_record_version": payload.client_record_version,
            "recording_method": payload.recording_method,
            "device_type": payload.device_type,
            "device_manufacturer": payload.device_manufacturer,
            "device_model": payload.device_model,
        }


class BaselineEngine:
    def calculate(
        self,
        observations: tuple[Observation, ...],
        *,
        now: datetime | None = None,
        window: timedelta = timedelta(days=28),
    ) -> dict[str, BaselineMetric]:
        now = now or datetime.now(UTC)
        start = now - window
        grouped: dict[str, list[Observation]] = {}
        for obs in observations:
            if start <= obs.observed_at <= now and isinstance(obs.value, (int, float)):
                grouped.setdefault(obs.metric, []).append(obs)

        result: dict[str, BaselineMetric] = {}
        for metric, items in grouped.items():
            ordered = sorted(items, key=lambda item: item.observed_at)
            if metric in ADDITIVE_DAILY_METRICS:
                daily: dict[date, float] = {}
                for item in ordered:
                    daily[item.observed_at.date()] = daily.get(item.observed_at.date(), 0.0) + float(item.value)
                values = tuple(daily.values())
                value = mean(values)
                method = "mean_daily_sum"
                day_count = len(daily)
            else:
                values = tuple(float(item.value) for item in ordered)
                value = median(values)
                method = "median"
                day_count = len({item.observed_at.date() for item in ordered})
            confidences = tuple(item.confidence for item in ordered if item.confidence is not None)
            confidence = mean(confidences) if confidences else 0.5
            result[metric] = BaselineMetric(
                metric=metric,
                value=round(value, 4),
                unit=ordered[-1].unit,
                method=method,
                sample_count=len(ordered),
                day_count=day_count,
                window_start=start,
                window_end=now,
                confidence=round(confidence, 3),
            )
        return result


class AnalyticsEngine:
    def summarize(self, observations: tuple[Observation, ...]) -> dict[str, MetricAnalytics]:
        grouped: dict[str, list[Observation]] = {}
        for obs in observations:
            if isinstance(obs.value, (int, float)):
                grouped.setdefault(obs.metric, []).append(obs)
        output: dict[str, MetricAnalytics] = {}
        for metric, items in grouped.items():
            ordered = sorted(items, key=lambda item: item.observed_at)
            values = tuple(float(item.value) for item in ordered)
            output[metric] = MetricAnalytics(
                metric=metric,
                unit=ordered[-1].unit,
                count=len(values),
                latest_value=values[-1],
                latest_at=ordered[-1].observed_at,
                mean_value=round(mean(values), 4),
                median_value=round(median(values), 4),
                min_value=min(values),
                max_value=max(values),
                change_from_first=round(values[-1] - values[0], 4),
            )
        return output


class ObservationPipeline:
    def __init__(self) -> None:
        self.normalizer = HealthConnectNormalizer()
        self.quality = DataQualityEngine(PLAUSIBLE_RANGES)
        self.baselines = BaselineEngine()
        self.analytics = AnalyticsEngine()
        self.missing = MissingDataDetector()

    def run_health_connect(
        self,
        records: tuple[tuple[str, HealthObservationPayload], ...],
        *,
        source_priority: tuple[str, ...] = (),
        expectations: tuple[MissingDataExpectation, ...] = (),
        now: datetime | None = None,
    ) -> ObservationPipelineResult:
        selected_records, version_suppressed = self._latest_source_versions(records)
        normalized = tuple(
            obs
            for entity_id, payload in selected_records
            for obs in self.normalizer.normalize(entity_id, payload)
        )
        result = self.run_observations(
            normalized,
            raw_count=len(records),
            source_priority=source_priority,
            expectations=expectations,
            now=now,
        )
        return replace(result, source_version_suppressed_ids=version_suppressed)

    @staticmethod
    def _latest_source_versions(
        records: tuple[tuple[str, HealthObservationPayload], ...],
    ) -> tuple[tuple[tuple[str, HealthObservationPayload], ...], tuple[str, ...]]:
        winners: dict[tuple[str, str, str], tuple[str, HealthObservationPayload]] = {}
        suppressed: list[str] = []
        for entity_id, payload in sorted(records, key=lambda item: item[0]):
            key = (payload.data_origin_package, payload.record_type, payload.source_record_id)
            current = winners.get(key)
            if current is None:
                winners[key] = (entity_id, payload)
                continue
            current_id, current_payload = current
            incoming_order = (
                payload.client_record_version,
                payload.last_modified_at_epoch_ms or 0,
                payload.observed_at_epoch_ms,
                entity_id,
            )
            current_order = (
                current_payload.client_record_version,
                current_payload.last_modified_at_epoch_ms or 0,
                current_payload.observed_at_epoch_ms,
                current_id,
            )
            if incoming_order > current_order:
                suppressed.append(current_id)
                winners[key] = (entity_id, payload)
            else:
                suppressed.append(entity_id)
        selected = tuple(sorted(winners.values(), key=lambda item: item[0]))
        return selected, tuple(sorted(suppressed))

    def run_observations(
        self,
        observations: tuple[Observation, ...],
        *,
        raw_count: int | None = None,
        source_priority: tuple[str, ...] = (),
        expectations: tuple[MissingDataExpectation, ...] = (),
        now: datetime | None = None,
    ) -> ObservationPipelineResult:
        now = now or datetime.now(UTC)
        report = self.quality.validate(observations, now=now)
        errors_by_id = {finding.observation_id for finding in report.findings if finding.severity == "error"}
        warnings_by_id: dict[str, int] = {}
        for finding in report.findings:
            if finding.severity == "warning":
                warnings_by_id[finding.observation_id] = warnings_by_id.get(finding.observation_id, 0) + 1

        accepted: list[Observation] = []
        for obs in observations:
            if obs.observation_id in errors_by_id:
                continue
            penalty = 0.10 * warnings_by_id.get(obs.observation_id, 0)
            confidence = max(0.0, min(1.0, (obs.confidence if obs.confidence is not None else 0.5) - penalty))
            quality = "verified" if confidence >= 0.95 else "high" if confidence >= 0.85 else "medium" if confidence >= 0.7 else "low"
            accepted.append(replace(obs, confidence=round(confidence, 3), quality=quality))

        resolver = SourceResolver(source_priority, DUPLICATE_POLICIES)
        dedup = resolver.deduplicate(tuple(accepted))
        canonical = tuple(sorted(dedup.selected, key=lambda item: (item.observed_at, item.metric, item.observation_id)))
        missing = self.missing.detect(canonical, expectations, now=now)
        baselines = self.baselines.calculate(canonical, now=now)
        analytics = self.analytics.summarize(canonical)
        contract_validator = AnalyticContractValidator()
        baseline_rows = tuple(
            {
                "metric": metric,
                "value": item.value,
                "sample_count": item.sample_count,
                "day_count": item.day_count,
                "confidence": item.confidence,
                "method": item.method,
            }
            for metric, item in sorted(baselines.items())
        )
        analytics_rows = tuple(
            {
                "metric": metric,
                "count": item.count,
                "latest_value": item.latest_value,
                "mean_value": item.mean_value,
                "median_value": item.median_value,
                "min_value": item.min_value,
                "max_value": item.max_value,
            }
            for metric, item in sorted(analytics.items())
        )
        return ObservationPipelineResult(
            raw_count=len(observations) if raw_count is None else raw_count,
            normalized_count=len(observations),
            canonical=canonical,
            source_version_suppressed_ids=(),
            suppressed_ids=dedup.suppressed_ids,
            quality_findings=report.findings,
            missing_findings=missing,
            baselines=baselines,
            analytics=analytics,
            baseline_contract=contract_validator.validate(baseline_rows, OBSERVATION_BASELINE_CONTRACT),
            analytics_contract=contract_validator.validate(analytics_rows, OBSERVATION_ANALYTICS_CONTRACT),
        )


def load_health_connect_records(db: Session) -> tuple[tuple[str, HealthObservationPayload], ...]:
    tombstoned: set[tuple[str, str]] = set()
    for row in db.scalars(
        select(EntityRecordModel).where(
            EntityRecordModel.entity_type == "health_connect_tombstone",
            EntityRecordModel.deleted.is_(False),
        )
    ).all():
        try:
            payload = HealthObservationPayload.model_validate(row.payload)
        except ValueError:
            continue
        tombstoned.add((payload.record_type, payload.source_record_id))

    records: list[tuple[str, HealthObservationPayload]] = []
    for row in db.scalars(
        select(EntityRecordModel).where(
            EntityRecordModel.entity_type == "observation",
            EntityRecordModel.deleted.is_(False),
        )
    ).all():
        if "record_type" not in row.payload:
            continue
        try:
            payload = HealthObservationPayload.model_validate(row.payload)
        except ValueError:
            continue
        if (payload.record_type, payload.source_record_id) in tombstoned:
            continue
        records.append((row.entity_id, payload))
    return tuple(records)


def load_health_quality_config(
    db: Session,
) -> tuple[tuple[str, ...], tuple[MissingDataExpectation, ...]]:
    priority_row = db.scalar(
        select(EntityRecordModel)
        .where(
            EntityRecordModel.entity_type == "health_source_priority",
            EntityRecordModel.deleted.is_(False),
        )
        .order_by(EntityRecordModel.updated_at.desc(), EntityRecordModel.entity_id.asc())
        .limit(1)
    )
    source_priority: tuple[str, ...] = ()
    if priority_row is not None:
        try:
            source_priority = tuple(
                HealthSourcePriorityPayload.model_validate(priority_row.payload).ordered_source_ids
            )
        except ValueError:
            source_priority = ()

    expectations: list[MissingDataExpectation] = []
    rows = db.scalars(
        select(EntityRecordModel)
        .where(
            EntityRecordModel.entity_type == "metric_expectation",
            EntityRecordModel.deleted.is_(False),
        )
        .order_by(EntityRecordModel.updated_at.desc(), EntityRecordModel.entity_id.asc())
    ).all()
    seen_metrics: set[str] = set()
    for row in rows:
        try:
            payload = MetricExpectationPayload.model_validate(row.payload)
        except ValueError:
            continue
        if payload.metric in seen_metrics or not payload.enabled:
            continue
        seen_metrics.add(payload.metric)
        expectations.append(
            MissingDataExpectation(
                metric=payload.metric,
                max_age=timedelta(hours=payload.max_age_hours),
            )
        )
    return source_priority, tuple(expectations)
