from __future__ import annotations

import pytest

from healthos.fhir_compat import FhirCompatibilityAdapter, FhirCompatibilityPolicy, FhirVersion


def test_fhir_adapter_is_disabled_by_default() -> None:
    with pytest.raises(RuntimeError, match="feature-gated"):
        FhirCompatibilityAdapter().envelope(
            {"resourceType": "Observation", "id": "obs-1"},
            fhir_version=FhirVersion.R4,
            source_system="health-connect-medical-records",
        )


def test_fhir_adapter_accepts_r4_and_preserves_provenance_when_enabled() -> None:
    adapter = FhirCompatibilityAdapter(FhirCompatibilityPolicy(enabled=True))
    envelope = adapter.envelope(
        {"resourceType": "Observation", "id": "obs-1", "status": "final"},
        fhir_version=FhirVersion.R4,
        source_system="health-connect-medical-records",
        source_record_id="hc-medical-1",
    )
    assert envelope.fhir_version is FhirVersion.R4
    assert envelope.resource_type == "Observation"
    assert envelope.resource_id == "obs-1"
    assert envelope.source_record_id == "hc-medical-1"
    assert len(envelope.raw_hash) == 64


def test_fhir_adapter_rejects_invalid_resource_shape() -> None:
    adapter = FhirCompatibilityAdapter(FhirCompatibilityPolicy(enabled=True))
    with pytest.raises(ValueError, match="resourceType"):
        adapter.envelope(
            {"id": "obs-1"},
            fhir_version=FhirVersion.R4B,
            source_system="health-connect-medical-records",
        )
