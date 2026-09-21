from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable


@dataclass(frozen=True)
class ContractFinding:
    severity: str
    code: str
    dataset: str
    row_index: int | None
    field: str | None
    message: str


@dataclass(frozen=True)
class FieldRule:
    name: str
    required: bool = True
    predicate: Callable[[Any], bool] | None = None
    description: str = ""


@dataclass(frozen=True)
class DatasetContract:
    name: str
    fields: tuple[FieldRule, ...]
    unique_fields: tuple[str, ...] = ()
    min_rows: int = 0
    allow_extra_fields: bool = True


@dataclass(frozen=True)
class ContractReport:
    passed: bool
    findings: tuple[ContractFinding, ...]


class AnalyticContractValidator:
    """Small runtime-independent contracts for aggregated analytical datasets.

    This deliberately validates data engineering invariants only. It is not a
    medical validator and must not be used to approve diagnoses or treatment.
    """

    def validate(self, rows: tuple[dict[str, Any], ...], contract: DatasetContract) -> ContractReport:
        findings: list[ContractFinding] = []
        if len(rows) < contract.min_rows:
            findings.append(
                ContractFinding(
                    "error",
                    "ROW_COUNT",
                    contract.name,
                    None,
                    None,
                    f"Expected at least {contract.min_rows} rows",
                )
            )

        field_rules = {rule.name: rule for rule in contract.fields}
        seen_unique: set[tuple[object, ...]] = set()
        for index, row in enumerate(rows):
            for rule in contract.fields:
                if rule.required and rule.name not in row:
                    findings.append(
                        ContractFinding(
                            "error",
                            "MISSING_FIELD",
                            contract.name,
                            index,
                            rule.name,
                            f"Missing required field {rule.name}",
                        )
                    )
                    continue
                if rule.name not in row:
                    continue
                value = row[rule.name]
                if rule.predicate is not None and not rule.predicate(value):
                    findings.append(
                        ContractFinding(
                            "error",
                            "FIELD_RULE",
                            contract.name,
                            index,
                            rule.name,
                            rule.description or f"Field {rule.name} failed its contract",
                        )
                    )
            if not contract.allow_extra_fields:
                extras = set(row) - set(field_rules)
                for extra in sorted(extras):
                    findings.append(
                        ContractFinding(
                            "error",
                            "EXTRA_FIELD",
                            contract.name,
                            index,
                            extra,
                            f"Unexpected field {extra}",
                        )
                    )
            if contract.unique_fields:
                key = tuple(row.get(name) for name in contract.unique_fields)
                if key in seen_unique:
                    findings.append(
                        ContractFinding(
                            "error",
                            "DUPLICATE_KEY",
                            contract.name,
                            index,
                            ",".join(contract.unique_fields),
                            "Duplicate analytical contract key",
                        )
                    )
                seen_unique.add(key)

        return ContractReport(
            passed=not any(item.severity == "error" for item in findings),
            findings=tuple(findings),
        )


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(float(value))


def _confidence(value: object) -> bool:
    return _finite_number(value) and 0.0 <= float(value) <= 1.0


OBSERVATION_BASELINE_CONTRACT = DatasetContract(
    name="observation_baselines",
    fields=(
        FieldRule("metric", predicate=_non_empty_string, description="metric must be non-empty"),
        FieldRule("value", predicate=_finite_number, description="value must be finite"),
        FieldRule("sample_count", predicate=_non_negative_int, description="sample_count must be non-negative"),
        FieldRule("day_count", predicate=_non_negative_int, description="day_count must be non-negative"),
        FieldRule("confidence", predicate=_confidence, description="confidence must be between 0 and 1"),
        FieldRule("method", predicate=_non_empty_string, description="method must be non-empty"),
    ),
    unique_fields=("metric",),
)


OBSERVATION_ANALYTICS_CONTRACT = DatasetContract(
    name="observation_analytics",
    fields=(
        FieldRule("metric", predicate=_non_empty_string, description="metric must be non-empty"),
        FieldRule("count", predicate=_non_negative_int, description="count must be non-negative"),
        FieldRule("latest_value", predicate=_finite_number, description="latest_value must be finite"),
        FieldRule("mean_value", predicate=_finite_number, description="mean_value must be finite"),
        FieldRule("median_value", predicate=_finite_number, description="median_value must be finite"),
        FieldRule("min_value", predicate=_finite_number, description="min_value must be finite"),
        FieldRule("max_value", predicate=_finite_number, description="max_value must be finite"),
    ),
    unique_fields=("metric",),
)
