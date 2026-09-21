from __future__ import annotations

from healthos.analytic_contracts import (
    AnalyticContractValidator,
    OBSERVATION_ANALYTICS_CONTRACT,
    OBSERVATION_BASELINE_CONTRACT,
)


def test_internal_baseline_contract_accepts_valid_rows() -> None:
    rows = (
        {
            "metric": "weight_kg",
            "value": 100.0,
            "sample_count": 7,
            "day_count": 7,
            "confidence": 0.95,
            "method": "median",
        },
    )
    assert AnalyticContractValidator().validate(rows, OBSERVATION_BASELINE_CONTRACT).passed


def test_internal_contract_rejects_duplicate_metric_and_bad_confidence() -> None:
    rows = (
        {
            "metric": "weight_kg",
            "value": 100.0,
            "sample_count": 7,
            "day_count": 7,
            "confidence": 1.2,
            "method": "median",
        },
        {
            "metric": "weight_kg",
            "value": 99.0,
            "sample_count": 8,
            "day_count": 8,
            "confidence": 0.9,
            "method": "median",
        },
    )
    report = AnalyticContractValidator().validate(rows, OBSERVATION_BASELINE_CONTRACT)
    assert not report.passed
    assert {finding.code for finding in report.findings} == {"FIELD_RULE", "DUPLICATE_KEY"}


def test_internal_analytics_contract_rejects_non_numeric_latest_value() -> None:
    rows = (
        {
            "metric": "steps",
            "count": 10,
            "latest_value": "not-a-number",
            "mean_value": 5000.0,
            "median_value": 4900.0,
            "min_value": 1000.0,
            "max_value": 9000.0,
        },
    )
    report = AnalyticContractValidator().validate(rows, OBSERVATION_ANALYTICS_CONTRACT)
    assert not report.passed
    assert report.findings[0].field == "latest_value"
