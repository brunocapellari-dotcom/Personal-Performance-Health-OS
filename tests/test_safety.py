from datetime import date

import pytest

from healthos.domain import Medication
from healthos.safety import MedicationSafetyGuard, MinimalExposurePolicy


def test_medication_dose_change_is_forbidden():
    guard = MedicationSafetyGuard()
    for action in ("change_dose", "increase_dose", "decrease_dose", "stop", "suspend", "replace"):
        with pytest.raises(PermissionError):
            guard.validate_action(action)


def test_medication_interaction_routes_to_professional():
    med = Medication("example", "10 mg", "daily", "doctor", date(2026, 1, 1))
    response = MedicationSafetyGuard().interaction_response(med, "possible interaction")
    assert response["action"] == "alert_and_refer"
    assert response["referral"] == "physician_or_pharmacist"


def test_minimal_exposure_strips_unneeded_sensitive_fields():
    payload = {
        "goal_summary": "improve conditioning",
        "session_summary": "zone 2",
        "readiness_action": "NORMAL",
        "full_medication_history": "secret",
        "address": "secret",
    }
    projected = MinimalExposurePolicy().project(payload, "training_explanation")
    assert set(projected) == {"goal_summary", "session_summary", "readiness_action"}
