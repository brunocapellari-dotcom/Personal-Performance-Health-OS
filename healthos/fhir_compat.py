from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class FhirVersion(StrEnum):
    R4 = "4.0.1"
    R4B = "4.3.0"


@dataclass(frozen=True)
class FhirResourceEnvelope:
    fhir_version: FhirVersion
    resource_type: str
    resource_id: str | None
    source_system: str
    source_record_id: str | None
    imported_at: datetime
    raw_hash: str
    resource: dict[str, Any]


@dataclass(frozen=True)
class FhirCompatibilityPolicy:
    enabled: bool = False
    accepted_versions: tuple[FhirVersion, ...] = (FhirVersion.R4, FhirVersion.R4B)


class FhirCompatibilityAdapter:
    """Compatibility boundary for future Health Connect Medical Records.

    It validates transport/provenance shape only. It intentionally does not
    implement clinical validation, diagnosis logic, or hospital infrastructure.
    """

    def __init__(self, policy: FhirCompatibilityPolicy | None = None) -> None:
        self.policy = policy or FhirCompatibilityPolicy()

    def envelope(
        self,
        resource: dict[str, Any],
        *,
        fhir_version: FhirVersion,
        source_system: str,
        source_record_id: str | None = None,
        imported_at: datetime | None = None,
    ) -> FhirResourceEnvelope:
        if not self.policy.enabled:
            raise RuntimeError("FHIR compatibility adapter is feature-gated and disabled")
        if fhir_version not in self.policy.accepted_versions:
            raise ValueError(f"unsupported FHIR version: {fhir_version}")
        resource_type = resource.get("resourceType")
        if not isinstance(resource_type, str) or not resource_type.strip():
            raise ValueError("FHIR resourceType is required")
        resource_id = resource.get("id")
        if resource_id is not None and not isinstance(resource_id, str):
            raise ValueError("FHIR id must be a string when present")
        if not source_system.strip():
            raise ValueError("FHIR source_system is required")

        canonical = json.dumps(resource, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return FhirResourceEnvelope(
            fhir_version=fhir_version,
            resource_type=resource_type,
            resource_id=resource_id,
            source_system=source_system,
            source_record_id=source_record_id,
            imported_at=imported_at or datetime.now(UTC),
            raw_hash=hashlib.sha256(canonical).hexdigest(),
            resource=dict(resource),
        )
