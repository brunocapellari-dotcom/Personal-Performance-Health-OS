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


def test_api_next_block_accepts_current_progress_response_and_availability() -> None:
    client = _client()
    request = {
        "goals": [
            {
                "goal_id": "adaptive-goal",
                "description": "Synthetic adaptive goal",
                "priority": 5,
                "baseline": 5,
                "current": 8,
                "target": 15,
                "target_date": "2027-05-01",
                "metric": "distance_km",
                "constraints": [],
            }
        ],
        "environment": {
            "environment": "HOME",
            "equipment": ["dumbbells", "band", "step"],
            "space_m2": 10,
            "fixation_points": [],
            "noise_limit": "moderate",
            "surface": "indoor",
            "available_minutes": 60,
        },
        "readiness": {
            "sleep_hours": 7.5,
            "sleep_quality_1_5": 4,
            "energy_1_5": 4,
            "fatigue_1_5": 2,
            "soreness_1_5": 2,
            "stress_1_5": 2,
            "pain_flag": False,
        },
        "nutrition_trend": None,
        "event": None,
        "training_response": {
            "sessions_planned": 6,
            "sessions_completed": 2,
            "avg_rpe": 7.0,
            "load_ratio": 0.7,
        },
        "availability": [
            {"day": "2027-03-02", "available_minutes": 45},
            {"day": "2027-03-05", "available_minutes": 50},
        ],
        "today": "2027-03-01",
        "weeks": 1,
    }
    response = client.post("/v1/plans/next-block", headers=_headers(), json=request)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["audit"]["passed"] is True
    assert len(payload["plan"]["sessions"]) == 2
    assert payload["plan"]["metadata"]["goal_gaps"]["adaptive-goal"]["absolute_gap"] == 7.0
    assert payload["plan"]["metadata"]["sessions_per_week"] == {"1": 2}


def test_api_rejects_impossible_training_response() -> None:
    client = _client()
    request = {
        "goals": [
            {
                "goal_id": "g",
                "description": "Synthetic goal",
                "priority": 1,
                "baseline": 1,
                "current": 1,
                "target": 2,
                "metric": "strength",
                "constraints": [],
            }
        ],
        "environment": {
            "environment": "HOME",
            "equipment": [],
            "space_m2": 10,
            "fixation_points": [],
            "noise_limit": "low",
            "surface": "indoor",
            "available_minutes": 30,
        },
        "readiness": {
            "sleep_hours": 8,
            "sleep_quality_1_5": 4,
            "energy_1_5": 4,
            "fatigue_1_5": 2,
            "soreness_1_5": 2,
            "stress_1_5": 2,
            "pain_flag": False,
        },
        "training_response": {
            "sessions_planned": 1,
            "sessions_completed": 2,
        },
        "availability": [],
        "today": "2027-03-01",
        "weeks": 1,
    }
    response = client.post("/v1/plans/next-block", headers=_headers(), json=request)
    assert response.status_code == 422


def test_minimal_next_block_reads_synced_state_and_cache_tracks_state_changes() -> None:
    client = _client()
    seed = {
        "changes": [
            {
                "change_id": "canonical-goal-1",
                "entity_type": "goal",
                "entity_id": "canonical-distance",
                "logical_clock": 1,
                "payload": {
                    "goal_id": "canonical-distance",
                    "description": "Synthetic canonical goal",
                    "priority": 5,
                    "baseline": 5.0,
                    "target": 20.0,
                    "metric": "distance_km",
                    "constraints": [],
                },
            },
            {
                "change_id": "canonical-env-1",
                "entity_type": "training_environment",
                "entity_id": "home",
                "logical_clock": 1,
                "payload": {
                    "environment": "HOME",
                    "equipment": ["dumbbells", "band", "step"],
                    "space_m2": 10,
                    "fixation_points": [],
                    "noise_limit": "moderate",
                    "surface": "indoor",
                    "available_minutes": 60,
                },
            },
            {
                "change_id": "canonical-ready-1",
                "entity_type": "readiness",
                "entity_id": "ready-1",
                "logical_clock": 1,
                "payload": {
                    "observed_at": "2027-03-01T07:00:00Z",
                    "sleep_hours": 7.5,
                    "sleep_quality_1_5": 4,
                    "energy_1_5": 4,
                    "fatigue_1_5": 2,
                    "soreness_1_5": 2,
                    "stress_1_5": 2,
                    "pain_flag": False,
                },
            },
            {
                "change_id": "canonical-calendar-1",
                "entity_type": "calendar_availability",
                "entity_id": "2027-03-02",
                "logical_clock": 1,
                "payload": {"day": "2027-03-02", "available_minutes": 45},
            },
            {
                "change_id": "canonical-calendar-2",
                "entity_type": "calendar_availability",
                "entity_id": "2027-03-05",
                "logical_clock": 1,
                "payload": {"day": "2027-03-05", "available_minutes": 50},
            },
        ]
    }
    seeded = client.post("/v1/sync/push", headers=_headers(), json=seed)
    assert seeded.status_code == 200, seeded.text

    command = {"today": "2027-03-01", "weeks": 1}
    first = client.post("/v1/plans/next-block", headers=_headers(), json=command)
    assert first.status_code == 200, first.text
    repeated = client.post("/v1/plans/next-block", headers=_headers(), json=command)
    assert repeated.status_code == 200
    assert repeated.json()["snapshot_id"] == first.json()["snapshot_id"]
    assert first.json()["plan"]["metadata"]["goal_gaps"]["canonical-distance"]["absolute_gap"] == 15.0

    assessment = {
        "changes": [
            {
                "change_id": "canonical-assessment-1",
                "entity_type": "assessment_result",
                "entity_id": "assessment-distance",
                "logical_clock": 1,
                "payload": {
                    "assessment_id": "assessment-distance",
                    "metric": "distance_km",
                    "value": 9.0,
                    "unit": "km",
                    "observed_at": "2027-03-01T12:00:00Z",
                },
            }
        ]
    }
    assessed = client.post("/v1/sync/push", headers=_headers(), json=assessment)
    assert assessed.status_code == 200, assessed.text
    changed = client.post("/v1/plans/next-block", headers=_headers(), json=command)
    assert changed.status_code == 200, changed.text
    assert changed.json()["snapshot_id"] != first.json()["snapshot_id"]
    assert changed.json()["plan"]["metadata"]["goal_gaps"]["canonical-distance"]["absolute_gap"] == 11.0


def test_observation_timeline_and_source_inventory_are_provenance_aware() -> None:
    client = _client()
    payload = {
        "changes": [
            {
                "change_id": "timeline-weight-01",
                "entity_type": "observation",
                "entity_id": "timeline-weight-entity",
                "logical_clock": 1,
                "payload": {
                    "record_type": "weight",
                    "source_record_id": "weight-source-1",
                    "observed_at_epoch_ms": 1789894800000,
                    "data_origin_package": "com.synthetic.scale",
                    "last_modified_at_epoch_ms": 1789894800000,
                    "client_record_id": "client-weight-1",
                    "client_record_version": 1,
                    "recording_method": 2,
                    "device_type": 1,
                    "device_manufacturer": "Synthetic",
                    "device_model": "Scale-X",
                    "health_connect_deleted": False,
                    "data": {
                        "kilograms": 99.5,
                        "time": "2026-09-20T09:00:00+00:00",
                    },
                },
            },
            {
                "change_id": "timeline-hrv-0001",
                "entity_type": "observation",
                "entity_id": "timeline-hrv-entity",
                "logical_clock": 2,
                "payload": {
                    "record_type": "heart_rate_variability_rmssd",
                    "source_record_id": "hrv-source-1",
                    "observed_at_epoch_ms": 1789894800000,
                    "data_origin_package": "com.synthetic.watch",
                    "last_modified_at_epoch_ms": 1789894800000,
                    "client_record_version": 1,
                    "recording_method": 2,
                    "health_connect_deleted": False,
                    "data": {
                        "rmssdMillis": 48.0,
                        "time": "2026-09-20T09:00:00+00:00",
                    },
                },
            },
        ]
    }
    pushed = client.post("/v1/sync/push", headers=_headers(), json=payload)
    assert pushed.status_code == 200, pushed.text

    timeline = client.get("/v1/observations/timeline?metric=weight_kg", headers=_headers())
    assert timeline.status_code == 200, timeline.text
    assert timeline.json()["count"] == 1
    item = timeline.json()["observations"][0]
    assert item["metric"] == "weight_kg"
    assert item["value"] == 99.5
    assert item["source_id"].startswith("health_connect:com.synthetic.scale")
    assert item["metadata"]["source_record_id"] == "weight-source-1"

    sources = client.get("/v1/observations/sources", headers=_headers())
    assert sources.status_code == 200, sources.text
    source_ids = {item["source_id"] for item in sources.json()["sources"]}
    assert any(value.startswith("health_connect:com.synthetic.scale") for value in source_ids)
    assert any(value.startswith("health_connect:com.synthetic.watch") for value in source_ids)


def test_api_responses_are_non_cacheable_and_request_id_is_bounded() -> None:
    client = _client()
    response = client.get("/healthz", headers={"X-Request-ID": "healthos-test-1234"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "healthos-test-1234"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"

    invalid = client.get("/healthz", headers={"X-Request-ID": "bad id with spaces"})
    generated = invalid.headers["x-request-id"]
    assert generated != "bad id with spaces"
    assert len(generated) == 32
