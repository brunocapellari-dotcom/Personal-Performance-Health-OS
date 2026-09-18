from __future__ import annotations

from typing import Any

from .domain import Medication


class MedicationSafetyGuard:
    FORBIDDEN_ACTIONS = {"change_dose", "increase_dose", "decrease_dose", "stop", "suspend", "replace"}

    def validate_action(self, action: str) -> None:
        if action.strip().lower() in self.FORBIDDEN_ACTIONS:
            raise PermissionError("AI must not change, stop, suspend or replace prescribed medication doses")

    def interaction_response(self, medication: Medication, signal: str) -> dict[str, str]:
        return {
            "medication": medication.medication,
            "signal": signal,
            "action": "alert_and_refer",
            "referral": "physician_or_pharmacist",
        }


class MinimalExposurePolicy:
    """Projects only the minimum fields needed by an external model/tool."""

    ALLOWED_BY_PURPOSE = {
        "training_explanation": {"goal_summary", "session_summary", "readiness_action"},
        "nutrition_explanation": {"energy_target", "macro_target", "dietary_constraints"},
        "safety_review": {"symptom_signal", "medication_name", "interaction_flag"},
    }

    def project(self, payload: dict[str, Any], purpose: str) -> dict[str, Any]:
        allowed = self.ALLOWED_BY_PURPOSE.get(purpose, set())
        return {k: payload[k] for k in allowed if k in payload}
