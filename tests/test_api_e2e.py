from __future__ import annotations

from fastapi.testclient import TestClient

from healthos.api import create_app
from healthos.config import Settings


def _client() -> TestClient:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="j" * 40,
        audit_hmac_key="a" * 40,
        test_bearer_token="test-token-strong-enough-for-ci",
    )
    return TestClient(create_app(settings, initialize_schema=True))


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token-strong-enough-for-ci"}


def test_api_sync_and_next_block_are_integrated_and_idempotent() -> None:
    client = _client()
    assert client.get("/healthz").json()["status"] == "ok"

    pushed = client.post(
        "/v1/sync/push",
        headers=_headers(),
        json={
            "changes": [
                {
                    "change_id": "api-change-0001",
                    "entity_type": "observation",
                    "entity_id": "synthetic-weight-001",
                    "logical_clock": 1,
                    "deleted": False,
                    "payload": {"metric": "weight", "value": 82.0, "unit": "kg", "synthetic": True},
                }
            ]
        },
    )
    assert pushed.status_code == 200
    assert pushed.json()["accepted"] == ["api-change-0001"]

    pulled = client.get("/v1/sync/pull?after=0", headers=_headers())
    assert pulled.status_code == 200
    assert pulled.json()["changes"][0]["entity_id"] == "synthetic-weight-001"

    request = {
        "goals": [
            {
                "goal_id": "synthetic-strength",
                "description": "Synthetic strength goal",
                "priority": 5,
                "baseline": None,
                "target": None,
                "target_date": None,
                "metric": "strength",
                "constraints": [],
            },
            {
                "goal_id": "synthetic-endurance",
                "description": "Synthetic endurance event preparation",
                "priority": 4,
                "baseline": 5,
                "target": 18,
                "target_date": "2027-04-18",
                "metric": "walking distance endurance",
                "constraints": [],
            },
        ],
        "environment": {
            "environment": "HOME",
            "equipment": ["dumbbells", "band", "step"],
            "space_m2": 10,
            "fixation_points": [],
            "noise_limit": "moderate",
            "surface": "indoor",
            "available_minutes": 50,
        },
        "readiness": {
            "sleep_hours": 7.5,
            "sleep_quality_1_5": 4,
            "energy_1_5": 4,
            "fatigue_1_5": 2,
            "soreness_1_5": 2,
            "stress_1_5": 2,
            "resting_hr_delta_pct": 1,
            "hrv_delta_pct": -2,
            "pain_flag": False,
        },
        "nutrition_trend": {
            "days": 21,
            "avg_intake_kcal": 2350,
            "weight_start_kg": 82.0,
            "weight_end_kg": 80.5,
            "current_tdee_estimate_kcal": 2900,
        },
        "event": {
            "event_id": "synthetic-endurance",
            "name": "Synthetic endurance event",
            "event_date": "2027-04-18",
            "demands": ["walking", "endurance"],
            "duration_minutes": None,
            "distance_km": 18,
            "priority": 4,
        },
        "today": "2027-03-01",
        "weeks": 4,
    }
    first = client.post("/v1/plans/next-block", headers=_headers(), json=request)
    assert first.status_code == 200, first.text
    assert first.json()["audit"]["passed"] is True
    assert len(first.json()["plan"]["sessions"]) == 12
    second = client.post("/v1/plans/next-block", headers=_headers(), json=request)
    assert second.status_code == 200
    assert second.json()["snapshot_id"] == first.json()["snapshot_id"]

    audit = client.get("/v1/audit/verify", headers=_headers())
    assert audit.status_code == 200
    assert audit.json() == {"valid": True}


def test_api_rejects_unauthorized_mutation() -> None:
    client = _client()
    response = client.post(
        "/v1/sync/push",
        json={
            "changes": [
                {
                    "change_id": "api-change-0002",
                    "entity_type": "goal",
                    "entity_id": "goal-1",
                    "logical_clock": 1,
                    "payload": {},
                }
            ]
        },
    )
    assert response.status_code == 401
