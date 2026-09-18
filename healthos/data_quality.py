from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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


class DataQualityEngine:
    """Validate imported observations before they influence planning decisions."""

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
        return DataQualityReport(not any(f.severity == "error" for f in findings), tuple(findings))
