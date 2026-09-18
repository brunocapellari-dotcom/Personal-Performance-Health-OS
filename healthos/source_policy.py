from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SourceUse(StrEnum):
    MACHINE_INTEGRATION = "machine_integration"
    REFERENCE_ONLY = "reference_only"
    DISCOVERY_ONLY = "discovery_only"


@dataclass(frozen=True)
class SourcePolicy:
    source_id: str
    name: str
    license_id: str
    use: SourceUse
    commercial_use: bool
    redistribution: bool
    attribution_required: bool
    notes: str


POLICIES: dict[str, SourcePolicy] = {
    "health_connect": SourcePolicy(
        source_id="health_connect",
        name="Android Health Connect",
        license_id="platform-user-authorized-data",
        use=SourceUse.MACHINE_INTEGRATION,
        commercial_use=True,
        redistribution=False,
        attribution_required=True,
        notes="User-authorized personal records; preserve data origin and permissions.",
    ),
    "usda_fdc": SourcePolicy(
        source_id="usda_fdc",
        name="USDA FoodData Central",
        license_id="CC0-1.0",
        use=SourceUse.MACHINE_INTEGRATION,
        commercial_use=True,
        redistribution=True,
        attribution_required=False,
        notes="Public-domain nutrient reference; citation is still preferred.",
    ),
    "open_food_facts": SourcePolicy(
        source_id="open_food_facts",
        name="Open Food Facts",
        license_id="ODbL-1.0/DbCL",
        use=SourceUse.MACHINE_INTEGRATION,
        commercial_use=True,
        redistribution=True,
        attribution_required=True,
        notes="Preserve ODbL obligations and source-quality metadata.",
    ),
    "taco": SourcePolicy(
        source_id="taco",
        name="TACO / NEPA-Unicamp",
        license_id="source-specific-reuse-with-citation",
        use=SourceUse.MACHINE_INTEGRATION,
        commercial_use=True,
        redistribution=True,
        attribution_required=True,
        notes="Preserve edition and citation; validate current source terms before redistribution.",
    ),
    "tbca": SourcePolicy(
        source_id="tbca",
        name="TBCA / USP-FoRC",
        license_id="CC-BY-NC-ND-4.0",
        use=SourceUse.REFERENCE_ONLY,
        commercial_use=False,
        redistribution=False,
        attribution_required=True,
        notes="Do not mirror or redistribute; commercial use requires explicit permission.",
    ),
    "wger": SourcePolicy(
        source_id="wger",
        name="wger exercise/ingredient data",
        license_id="CC-BY-SA-3.0-data/AGPL-3.0-code",
        use=SourceUse.DISCOVERY_ONLY,
        commercial_use=True,
        redistribution=False,
        attribution_required=True,
        notes="Use REST API/reference by default; do not incorporate AGPL application code into the core.",
    ),
}


def policy_for(source_id: str) -> SourcePolicy:
    try:
        return POLICIES[source_id]
    except KeyError as exc:
        raise ValueError(f"unknown source policy: {source_id}") from exc


def assert_use_allowed(source_id: str, *, redistribution: bool = False, commercial: bool = False) -> None:
    policy = policy_for(source_id)
    if redistribution and not policy.redistribution:
        raise PermissionError(f"{source_id} is not approved for redistribution")
    if commercial and not policy.commercial_use:
        raise PermissionError(f"{source_id} is not approved for commercial use")
