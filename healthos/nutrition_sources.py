from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import httpx

from .contracts import FoodRecord
from .source_policy import policy_for


class UsdaFoodDataCentralProvider:
    """Search USDA FoodData Central without persisting the API key or raw user context."""

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        base_url: str = "https://api.nal.usda.gov/fdc/v1",
        page_size: int = 15,
    ) -> None:
        if not api_key.strip():
            raise ValueError("FoodData Central API key is required")
        if page_size < 1 or page_size > 50:
            raise ValueError("page_size must be between 1 and 50")
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=10.0, follow_redirects=False)
        self._base_url = base_url.rstrip("/")
        self._page_size = page_size

    def search(self, query: str) -> tuple[FoodRecord, ...]:
        normalized = " ".join(query.split())
        if not normalized or len(normalized) > 200:
            raise ValueError("nutrition search query must contain 1 to 200 characters")
        response = self._client.post(
            f"{self._base_url}/foods/search",
            params={"api_key": self._api_key},
            json={"query": normalized, "pageSize": self._page_size},
        )
        response.raise_for_status()
        payload = _json_object(response)
        foods = payload.get("foods", [])
        if not isinstance(foods, list):
            raise ValueError("FoodData Central response has invalid foods payload")
        return tuple(_fdc_food(item) for item in foods if isinstance(item, dict))


class OpenFoodFactsProvider:
    """Barcode lookup for packaged foods through the current Open Food Facts v3 read API."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        base_url: str = "https://world.openfoodfacts.org",
        user_agent: str = "PersonalPerformanceHealthOS/0.2",
    ) -> None:
        if not user_agent.strip():
            raise ValueError("Open Food Facts User-Agent is required")
        self._client = client or httpx.Client(timeout=10.0, follow_redirects=False)
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent

    def lookup_barcode(self, barcode: str) -> FoodRecord | None:
        code = barcode.strip()
        if not code.isdigit() or len(code) < 4 or len(code) > 24:
            raise ValueError("barcode must contain 4 to 24 digits")
        response = self._client.get(
            f"{self._base_url}/api/v3/product/{code}",
            params={
                "fields": "code,product_name,nutriments,completeness,last_modified_t,nutrition_data_per",
            },
            headers={"User-Agent": self._user_agent},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = _json_object(response)
        product = payload.get("product")
        if not isinstance(product, dict):
            return None
        return _off_product(product, fallback_code=code)


def _fdc_food(item: dict[str, Any]) -> FoodRecord:
    nutrients = item.get("foodNutrients")
    nutrient_rows = nutrients if isinstance(nutrients, list) else []
    macro: dict[str, float | None] = {
        "energy": None,
        "protein": None,
        "carbohydrate": None,
        "fat": None,
    }
    micronutrients: dict[str, float] = {}
    for row in nutrient_rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("nutrientName") or "").strip()
        unit = str(row.get("unitName") or "").strip().upper()
        value = _number(row.get("value"))
        if not name or value is None:
            continue
        lowered = name.casefold()
        if lowered == "energy" and unit == "KCAL" and macro["energy"] is None:
            macro["energy"] = value
        elif lowered == "protein" and unit == "G" and macro["protein"] is None:
            macro["protein"] = value
        elif lowered.startswith("carbohydrate") and unit == "G" and macro["carbohydrate"] is None:
            macro["carbohydrate"] = value
        elif lowered in {"total lipid (fat)", "total fat"} and unit == "G" and macro["fat"] is None:
            macro["fat"] = value
        else:
            micronutrients[f"{name} [{unit or 'unknown'}]"] = value

    policy = policy_for("usda_fdc")
    data_type = str(item.get("dataType") or "unknown")
    raw = _canonical_bytes(item)
    fdc_id = str(item.get("fdcId") or "")
    return FoodRecord(
        food_id=f"usda_fdc:{fdc_id}",
        name=str(item.get("description") or f"FDC {fdc_id}"),
        source="usda_fdc",
        source_version=str(item.get("publicationDate") or data_type),
        energy_kcal_per_100g=macro["energy"],
        protein_g_per_100g=macro["protein"],
        carbohydrate_g_per_100g=macro["carbohydrate"],
        fat_g_per_100g=macro["fat"],
        micronutrients=micronutrients,
        source_quality=_fdc_quality(data_type),
        source_record_id=fdc_id or None,
        license_id=policy.license_id,
        retrieved_at=datetime.now(UTC),
        raw_hash=hashlib.sha256(raw).hexdigest(),
    )


def _off_product(product: dict[str, Any], *, fallback_code: str) -> FoodRecord:
    nutriments = product.get("nutriments")
    values = nutriments if isinstance(nutriments, dict) else {}
    code = str(product.get("code") or fallback_code)
    policy = policy_for("open_food_facts")
    micronutrients: dict[str, float] = {}
    excluded = {"energy-kcal", "proteins", "carbohydrates", "fat"}
    for key, value in values.items():
        if not key.endswith("_100g"):
            continue
        nutrient = key.removesuffix("_100g")
        numeric = _number(value)
        if numeric is not None and nutrient not in excluded:
            micronutrients[nutrient] = numeric
    completeness = _number(product.get("completeness"))
    quality = "community_packaged_product"
    if completeness is not None:
        quality = f"community_packaged_product;completeness={completeness:.2f}"
    return FoodRecord(
        food_id=f"open_food_facts:{code}",
        name=str(product.get("product_name") or f"Barcode {code}"),
        source="open_food_facts",
        source_version=str(product.get("last_modified_t") or "api-v3"),
        energy_kcal_per_100g=_number(values.get("energy-kcal_100g")),
        protein_g_per_100g=_number(values.get("proteins_100g")),
        carbohydrate_g_per_100g=_number(values.get("carbohydrates_100g")),
        fat_g_per_100g=_number(values.get("fat_100g")),
        micronutrients=micronutrients,
        source_quality=quality,
        source_record_id=code,
        license_id=policy.license_id,
        retrieved_at=datetime.now(UTC),
        raw_hash=hashlib.sha256(_canonical_bytes(product)).hexdigest(),
    )


def _fdc_quality(data_type: str) -> str:
    normalized = data_type.casefold()
    if "foundation" in normalized:
        return "laboratory_reference"
    if "survey" in normalized or "fndds" in normalized or "sr legacy" in normalized:
        return "curated_reference"
    if "branded" in normalized:
        return "label_or_supplier"
    return "reference_unknown_type"


def _json_object(response: httpx.Response) -> dict[str, Any]:
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("nutrition source response must be a JSON object")
    return payload


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
