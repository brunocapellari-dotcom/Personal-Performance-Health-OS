from datetime import UTC, datetime, timedelta

from healthos.data_quality import DataQualityEngine, DuplicatePolicy, MissingDataDetector, MissingDataExpectation, SourceResolver
from healthos.domain import Observation


def test_data_quality_rejects_future_and_bad_confidence() -> None:
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    obs = Observation(
        "x",
        "weight",
        100.0,
        "kg",
        now + timedelta(hours=1),
        now,
        "scale",
        "manual",
        confidence=1.2,
    )
    report = DataQualityEngine().validate((obs,), now=now)
    assert not report.passed
    assert {f.code for f in report.findings} == {"FUTURE_TIMESTAMP", "CONFIDENCE_RANGE"}


def test_duplicate_resolution_requires_value_compatibility_not_only_time_proximity() -> None:
    now = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
    first = Observation(
        "a",
        "heart_rate_bpm",
        100.0,
        "bpm",
        now,
        now,
        "watch-a",
        "HEALTH_CONNECT",
        confidence=0.9,
        quality="high",
    )
    second = Observation(
        "b",
        "heart_rate_bpm",
        140.0,
        "bpm",
        now + timedelta(seconds=1),
        now + timedelta(seconds=1),
        "watch-b",
        "HEALTH_CONNECT",
        confidence=0.9,
        quality="high",
    )
    resolver = SourceResolver(
        ("watch-a", "watch-b"),
        {"heart_rate_bpm": DuplicatePolicy(timedelta(seconds=2), 1.0)},
    )
    result = resolver.deduplicate((first, second))
    assert {item.observation_id for item in result.selected} == {"a", "b"}
    assert result.suppressed_ids == ()


def test_missing_data_detector_distinguishes_absent_and_stale_series() -> None:
    now = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
    stale = Observation(
        "old-weight",
        "weight_kg",
        100.0,
        "kg",
        now - timedelta(days=10),
        now - timedelta(days=10),
        "scale",
        "HEALTH_CONNECT",
    )
    findings = MissingDataDetector().detect(
        (stale,),
        (
            MissingDataExpectation("weight_kg", timedelta(days=7)),
            MissingDataExpectation("sleep_duration_min", timedelta(days=2)),
        ),
        now=now,
    )
    assert {(item.metric, item.code) for item in findings} == {
        ("weight_kg", "STALE_SERIES"),
        ("sleep_duration_min", "MISSING_SERIES"),
    }
