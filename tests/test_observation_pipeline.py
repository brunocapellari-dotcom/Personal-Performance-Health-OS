from __future__ import annotations

from datetime import UTC, datetime, timedelta

from healthos.data_quality import MissingDataExpectation
from healthos.entity_payloads import HealthObservationPayload
from healthos.observation_pipeline import ObservationPipeline


def _payload(
    *,
    record_type: str,
    source_record_id: str,
    observed_at: datetime,
    package: str,
    data: dict[str, object],
    recording_method: int = 2,
    device_model: str | None = None,
) -> HealthObservationPayload:
    return HealthObservationPayload(
        record_type=record_type,
        source_record_id=source_record_id,
        observed_at_epoch_ms=int(observed_at.timestamp() * 1000),
        data_origin_package=package,
        last_modified_at_epoch_ms=int(observed_at.timestamp() * 1000),
        client_record_id=f"client-{source_record_id}",
        client_record_version=1,
        recording_method=recording_method,
        device_type=1 if device_model else None,
        device_manufacturer="Synthetic" if device_model else None,
        device_model=device_model,
        health_connect_deleted=False,
        data=data,
    )


def test_pipeline_preserves_provenance_and_source_priority_for_duplicates() -> None:
    now = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
    observed = now - timedelta(hours=1)
    phone = _payload(
        record_type="weight",
        source_record_id="weight-phone",
        observed_at=observed,
        package="com.synthetic.phone",
        data={"kilograms": 100.0, "time": observed.isoformat()},
        recording_method=3,
    )
    scale = _payload(
        record_type="weight",
        source_record_id="weight-scale",
        observed_at=observed + timedelta(seconds=20),
        package="com.synthetic.scale",
        data={"kilograms": 100.02, "time": (observed + timedelta(seconds=20)).isoformat()},
        recording_method=2,
        device_model="Scale-X",
    )

    result = ObservationPipeline().run_health_connect(
        (("phone-entity", phone), ("scale-entity", scale)),
        source_priority=("health_connect:com.synthetic.scale:synthetic:scale-x:1",),
        now=now,
    )

    assert result.raw_count == 2
    assert result.normalized_count == 2
    assert len(result.canonical) == 1
    canonical = result.canonical[0]
    assert canonical.source_id.startswith("health_connect:com.synthetic.scale")
    assert canonical.metadata["source_record_id"] == "weight-scale"
    assert canonical.metadata["client_record_version"] == 1
    assert canonical.metadata["device_model"] == "Scale-X"
    assert len(result.suppressed_ids) == 1
    assert result.baseline_contract.passed
    assert result.analytics_contract.passed


def test_pipeline_builds_daily_baseline_and_reports_expected_missing_series() -> None:
    now = datetime(2026, 9, 21, 23, 0, tzinfo=UTC)
    first = now - timedelta(days=1, hours=2)
    second = now - timedelta(hours=2)
    records = (
        (
            "steps-1",
            _payload(
                record_type="steps",
                source_record_id="steps-1",
                observed_at=first,
                package="com.synthetic.watch",
                data={
                    "count": 4000,
                    "startTime": (first - timedelta(hours=1)).isoformat(),
                    "endTime": first.isoformat(),
                },
            ),
        ),
        (
            "steps-2",
            _payload(
                record_type="steps",
                source_record_id="steps-2",
                observed_at=first + timedelta(hours=1),
                package="com.synthetic.watch",
                data={
                    "count": 2000,
                    "startTime": first.isoformat(),
                    "endTime": (first + timedelta(hours=1)).isoformat(),
                },
            ),
        ),
        (
            "steps-3",
            _payload(
                record_type="steps",
                source_record_id="steps-3",
                observed_at=second,
                package="com.synthetic.watch",
                data={
                    "count": 8000,
                    "startTime": (second - timedelta(hours=1)).isoformat(),
                    "endTime": second.isoformat(),
                },
            ),
        ),
    )

    result = ObservationPipeline().run_health_connect(
        records,
        expectations=(MissingDataExpectation("sleep_duration_min", timedelta(days=2)),),
        now=now,
    )

    baseline = result.baselines["steps"]
    assert baseline.method == "mean_daily_sum"
    assert baseline.value == 7000.0
    assert baseline.day_count == 2
    assert result.missing_findings[0].code == "MISSING_SERIES"
    assert result.missing_findings[0].metric == "sleep_duration_min"


def test_series_metrics_are_normalized_into_timeline_points() -> None:
    now = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
    payload = _payload(
        record_type="speed",
        source_record_id="speed-1",
        observed_at=now,
        package="com.synthetic.watch",
        data={
            "startTime": (now - timedelta(minutes=1)).isoformat(),
            "endTime": now.isoformat(),
            "samples": [
                {"time": (now - timedelta(seconds=30)).isoformat(), "metersPerSecond": 2.5},
                {"time": now.isoformat(), "metersPerSecond": 3.0},
            ],
        },
    )

    result = ObservationPipeline().run_health_connect((("speed-entity", payload),), now=now)

    assert [item.metric for item in result.canonical] == ["speed_m_s", "speed_m_s"]
    assert [item.value for item in result.canonical] == [2.5, 3.0]
    assert result.analytics["speed_m_s"].latest_value == 3.0


def test_vo2_max_is_normalized_with_measurement_method() -> None:
    now = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
    payload = _payload(
        record_type="vo2_max",
        source_record_id="vo2-1",
        observed_at=now,
        package="com.synthetic.watch",
        data={
            "millilitersPerMinuteKilogram": 42.5,
            "measurementMethod": 2,
            "time": now.isoformat(),
        },
    )

    result = ObservationPipeline().run_health_connect((("vo2-entity", payload),), now=now)

    assert len(result.canonical) == 1
    observation = result.canonical[0]
    assert observation.metric == "vo2_max_ml_kg_min"
    assert observation.value == 42.5
    assert observation.unit == "ml/kg/min"
    assert observation.metadata["measurement_method"] == 2
    assert result.analytics["vo2_max_ml_kg_min"].latest_value == 42.5


def test_newer_source_record_version_wins_before_normalization() -> None:
    now = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
    older = HealthObservationPayload(
        record_type="weight",
        source_record_id="same-record",
        observed_at_epoch_ms=int(now.timestamp() * 1000),
        data_origin_package="com.synthetic.scale",
        last_modified_at_epoch_ms=int((now - timedelta(minutes=5)).timestamp() * 1000),
        client_record_id="weight-client",
        client_record_version=1,
        recording_method=2,
        health_connect_deleted=False,
        data={"kilograms": 101.0, "time": now.isoformat()},
    )
    newer = HealthObservationPayload(
        record_type="weight",
        source_record_id="same-record",
        observed_at_epoch_ms=int(now.timestamp() * 1000),
        data_origin_package="com.synthetic.scale",
        last_modified_at_epoch_ms=int(now.timestamp() * 1000),
        client_record_id="weight-client",
        client_record_version=2,
        recording_method=2,
        health_connect_deleted=False,
        data={"kilograms": 100.5, "time": now.isoformat()},
    )

    result = ObservationPipeline().run_health_connect(
        (("old-entity", older), ("new-entity", newer)),
        now=now,
    )

    assert result.raw_count == 2
    assert result.normalized_count == 1
    assert result.canonical[0].value == 100.5
    assert result.source_version_suppressed_ids == ("old-entity",)


def test_recovery_body_and_hydration_metrics_normalize_into_canonical_timeline() -> None:
    now = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
    records = (
        (
            "hrv-entity",
            _payload(
                record_type="heart_rate_variability_rmssd",
                source_record_id="hrv-1",
                observed_at=now,
                package="com.synthetic.watch",
                data={"rmssdMillis": 48.0, "time": now.isoformat()},
            ),
        ),
        (
            "fat-entity",
            _payload(
                record_type="body_fat",
                source_record_id="fat-1",
                observed_at=now,
                package="com.synthetic.scale",
                data={"percent": 28.5, "time": now.isoformat()},
            ),
        ),
        (
            "lean-entity",
            _payload(
                record_type="lean_body_mass",
                source_record_id="lean-1",
                observed_at=now,
                package="com.synthetic.scale",
                data={"kilograms": 71.2, "time": now.isoformat()},
            ),
        ),
        (
            "hydration-entity",
            _payload(
                record_type="hydration",
                source_record_id="water-1",
                observed_at=now,
                package="com.synthetic.nutrition",
                data={
                    "liters": 0.5,
                    "startTime": (now - timedelta(minutes=2)).isoformat(),
                    "endTime": now.isoformat(),
                },
            ),
        ),
        (
            "floors-entity",
            _payload(
                record_type="floors_climbed",
                source_record_id="floors-1",
                observed_at=now,
                package="com.synthetic.watch",
                data={
                    "floors": 12.0,
                    "startTime": (now - timedelta(hours=1)).isoformat(),
                    "endTime": now.isoformat(),
                },
            ),
        ),
        (
            "cycling-entity",
            _payload(
                record_type="cycling_pedaling_cadence",
                source_record_id="cadence-1",
                observed_at=now,
                package="com.synthetic.bike",
                data={
                    "startTime": (now - timedelta(minutes=1)).isoformat(),
                    "endTime": now.isoformat(),
                    "samples": [
                        {"time": (now - timedelta(seconds=30)).isoformat(), "revolutionsPerMinute": 82.0},
                        {"time": now.isoformat(), "revolutionsPerMinute": 88.0},
                    ],
                },
            ),
        ),
    )

    result = ObservationPipeline().run_health_connect(records, now=now)

    by_metric = {}
    for observation in result.canonical:
        by_metric.setdefault(observation.metric, []).append(observation.value)

    assert by_metric["hrv_rmssd_ms"] == [48.0]
    assert by_metric["body_fat_pct"] == [28.5]
    assert by_metric["lean_body_mass_kg"] == [71.2]
    assert by_metric["hydration_l"] == [0.5]
    assert by_metric["floors_climbed"] == [12.0]
    assert by_metric["cycling_cadence_rpm"] == [82.0, 88.0]
    assert result.baseline_contract.passed
    assert result.analytics_contract.passed
