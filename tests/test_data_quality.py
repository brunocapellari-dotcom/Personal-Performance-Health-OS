from datetime import UTC, datetime, timedelta

from healthos.data_quality import DataQualityEngine
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
