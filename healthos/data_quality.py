from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite

from .domain import Observation


@dataclass(frozen=True)
class DataQualityFinding:
    severity: str
    code: str
    observation_id: str
    message: str


@dataclass(frozen=True)
class DataQualityReport:
    passed: bool
    findings: tuple[DataQualityFinding, ...]


@dataclass(frozen=True)
class DeduplicationDecision:
    selected: tuple[Observation, ...]
    suppressed_ids: tuple[str, ...]


@dataclass(frozen=True)
class DuplicatePolicy:
    time_tolerance: timedelta = timedelta(seconds=30)
    absolute_value_tolerance: float = 0.0


@dataclass(frozen=True)
class MissingDataExpectation:
    metric: str
    max_age: timedelta


@dataclass(frozen=True)
class MissingDataFinding:
    metric: str
    severity: str
    code: str
    message: str
    latest_observed_at: datetime | None


class DataQualityEngine:
    """Validate observations before they influence canonical timelines or planning.

    These are engineering/data-quality checks, not medical validity rules.
    """

    def __init__(self, plausible_ranges: dict[str, tuple[float, float]] | None = None) -> None:
        self.plausible_ranges = plausible_ranges or {}

    def validate(
        self,
        observations: tuple[Observation, ...],
        *,
        now: datetime | None = None,
        future_tolerance: timedelta = timedelta(minutes=5),
    ) -> DataQualityReport:
        now = now or datetime.now(UTC)
        findings: list[DataQualityFinding] = []
        seen_ids: set[str] = set()
        for obs in observations:
            if obs.observation_id in seen_ids:
                findings.append(
                    DataQualityFinding("error", "DUPLICATE_ID", obs.observation_id, "Duplicate observation ID")
                )
            seen_ids.add(obs.observation_id)
            if obs.observed_at > now + future_tolerance:
                findings.append(
                    DataQualityFinding("error", "FUTURE_TIMESTAMP", obs.observation_id, "Observation is in the future")
                )
            if obs.recorded_at < obs.observed_at - timedelta(days=3650):
                findings.append(
                    DataQualityFinding(
                        "warning",
                        "CLOCK_INCONSISTENCY",
                        obs.observation_id,
                        "Recorded timestamp is implausibly older than observation",
                    )
                )
            if obs.confidence is not None and not 0.0 <= obs.confidence <= 1.0:
                findings.append(
                    DataQualityFinding(
                        "error", "CONFIDENCE_RANGE", obs.observation_id, "Confidence must be between 0 and 1"
                    )
                )
            if not obs.source_id.strip() or not obs.source_type.strip():
                findings.append(
                    DataQualityFinding(
                        "error", "MISSING_PROVENANCE", obs.observation_id, "Source provenance is required"
                    )
                )
            if isinstance(obs.value, float) and not isfinite(obs.value):
                findings.append(
                    DataQualityFinding("error", "NON_FINITE_VALUE", obs.observation_id, "Numeric value must be finite")
                )
            bounds = self.plausible_ranges.get(obs.metric)
            if bounds is not None and isinstance(obs.value, (int, float)):
                low, high = bounds
                value = float(obs.value)
                if value < low or value > high:
                    findings.append(
                        DataQualityFinding(
                            "warning",
                            "PLAUSIBILITY_RANGE",
                            obs.observation_id,
                            f"{obs.metric} is outside the configured engineering plausibility range",
                        )
                    )
        return DataQualityReport(not any(f.severity == "error" for f in findings), tuple(findings))


class SourceResolver:
    """Choose a canonical observation while preserving every raw source record.

    Source priority is explicit/configurable; no vendor receives an implicit hard-coded preference.
    """

    QUALITY_SCORE = {
        "verified": 4,
        "high": 3,
        "medium": 2,
        "low": 1,
        "unknown": 0,
    }

    def __init__(
        self,
        source_priority: tuple[str, ...] = (),
        policies: dict[str, DuplicatePolicy] | None = None,
    ) -> None:
        self._priority = {source_id: len(source_priority) - index for index, source_id in enumerate(source_priority)}
        self._policies = policies or {}

    def _score(self, observation: Observation) -> tuple[int, int, float, datetime]:
        return (
            self._priority.get(observation.source_id, 0),
            self.QUALITY_SCORE.get(observation.quality.lower(), 0),
            observation.confidence if observation.confidence is not None else -1.0,
            observation.recorded_at,
        )

    def _policy(self, metric: str) -> DuplicatePolicy:
        return self._policies.get(metric, DuplicatePolicy())

    @staticmethod
    def _values_match(left: float | str, right: float | str, tolerance: float) -> bool:
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return abs(float(left) - float(right)) <= tolerance
        return str(left) == str(right)

    def deduplicate(
        self,
        observations: tuple[Observation, ...],
        *,
        tolerance: timedelta | None = None,
    ) -> DeduplicationDecision:
        if not observations:
            return DeduplicationDecision((), ())

        ordered = sorted(observations, key=lambda x: (x.metric, x.observed_at, x.observation_id))
        groups: list[list[Observation]] = []
        for obs in ordered:
            matching_group: list[Observation] | None = None
            policy = self._policy(obs.metric)
            if tolerance is not None:
                policy = DuplicatePolicy(tolerance, policy.absolute_value_tolerance)
            if policy.time_tolerance.total_seconds() < 0 or policy.absolute_value_tolerance < 0:
                raise ValueError("duplicate policy tolerances cannot be negative")
            for group in reversed(groups):
                anchor = group[0]
                if anchor.metric != obs.metric:
                    continue
                delta = abs((obs.observed_at - anchor.observed_at).total_seconds())
                if delta > policy.time_tolerance.total_seconds():
                    break
                if self._values_match(obs.value, anchor.value, policy.absolute_value_tolerance):
                    matching_group = group
                    break
            if matching_group is None:
                groups.append([obs])
            else:
                matching_group.append(obs)

        selected: list[Observation] = []
        suppressed: list[str] = []
        for group in groups:
            winner = max(group, key=self._score)
            selected.append(winner)
            suppressed.extend(obs.observation_id for obs in group if obs.observation_id != winner.observation_id)

        return DeduplicationDecision(tuple(selected), tuple(sorted(suppressed)))


class MissingDataDetector:
    def detect(
        self,
        observations: tuple[Observation, ...],
        expectations: tuple[MissingDataExpectation, ...],
        *,
        now: datetime | None = None,
    ) -> tuple[MissingDataFinding, ...]:
        now = now or datetime.now(UTC)
        latest: dict[str, datetime] = {}
        for obs in observations:
            previous = latest.get(obs.metric)
            if previous is None or obs.observed_at > previous:
                latest[obs.metric] = obs.observed_at

        findings: list[MissingDataFinding] = []
        for expectation in expectations:
            if expectation.max_age.total_seconds() <= 0:
                raise ValueError("missing-data max_age must be positive")
            last = latest.get(expectation.metric)
            if last is None:
                findings.append(
                    MissingDataFinding(
                        metric=expectation.metric,
                        severity="warning",
                        code="MISSING_SERIES",
                        message=f"No data is available for expected metric {expectation.metric}",
                        latest_observed_at=None,
                    )
                )
                continue
            if now - last > expectation.max_age:
                findings.append(
                    MissingDataFinding(
                        metric=expectation.metric,
                        severity="warning",
                        code="STALE_SERIES",
                        message=f"Expected metric {expectation.metric} is stale",
                        latest_observed_at=last,
                    )
                )
        return tuple(findings)
