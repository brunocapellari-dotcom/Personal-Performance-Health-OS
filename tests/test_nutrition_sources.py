from __future__ import annotations

import httpx
import pytest

from healthos.nutrition_sources import OpenFoodFactsProvider, UsdaFoodDataCentralProvider


def test_usda_search_normalizes_macros_provenance_and_quality() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/foods/search")
        assert request.url.params["api_key"] == "synthetic-key"
        return httpx.Response(
            200,
            json={
                "foods": [
                    {
                        "fdcId": 100304,
                        "description": "Synthetic chicken breast",
                        "dataType": "Foundation",
                        "publicationDate": "2026-01-01",
                        "foodNutrients": [
                            {"nutrientName": "Energy", "unitName": "KCAL", "value": 120},
                            {"nutrientName": "Protein", "unitName": "G", "value": 23.4},
                            {"nutrientName": "Carbohydrate, by difference", "unitName": "G", "value": 0},
                            {"nutrientName": "Total lipid (fat)", "unitName": "G", "value": 2.6},
                            {"nutrientName": "Iron, Fe", "unitName": "MG", "value": 0.7},
                        ],
                    }
                ]
            },
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = UsdaFoodDataCentralProvider("synthetic-key", client=client, base_url="https://example.test/fdc/v1")
    result = provider.search("  chicken   breast ")

    assert len(result) == 1
    food = result[0]
    assert food.food_id == "usda_fdc:100304"
    assert food.energy_kcal_per_100g == 120
    assert food.protein_g_per_100g == 23.4
    assert food.carbohydrate_g_per_100g == 0
    assert food.fat_g_per_100g == 2.6
    assert food.micronutrients["Iron, Fe [MG]"] == 0.7
    assert food.source_quality == "laboratory_reference"
    assert food.license_id == "CC0-1.0"
    assert food.raw_hash is not None and len(food.raw_hash) == 64


def test_open_food_facts_barcode_uses_v3_and_normalized_100g_values() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/product/7891234567890"
        assert request.headers["User-Agent"].startswith("HealthOSTest/")
        assert "nutriments" in request.url.params["fields"]
        return httpx.Response(
            200,
            json={
                "product": {
                    "code": "7891234567890",
                    "product_name": "Synthetic packaged food",
                    "completeness": 0.82,
                    "last_modified_t": 1_788_000_000,
                    "nutriments": {
                        "energy-kcal_100g": 210,
                        "proteins_100g": 8.5,
                        "carbohydrates_100g": 26.0,
                        "fat_100g": 7.5,
                        "fiber_100g": 4.2,
                        "sodium_100g": 0.31,
                    },
                }
            },
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenFoodFactsProvider(
        client=client,
        base_url="https://example.test",
        user_agent="HealthOSTest/1.0 (test@example.invalid)",
    )
    food = provider.lookup_barcode("7891234567890")

    assert food is not None
    assert food.food_id == "open_food_facts:7891234567890"
    assert food.energy_kcal_per_100g == 210
    assert food.protein_g_per_100g == 8.5
    assert food.carbohydrate_g_per_100g == 26
    assert food.fat_g_per_100g == 7.5
    assert food.micronutrients["fiber"] == 4.2
    assert food.micronutrients["sodium"] == 0.31
    assert food.license_id == "ODbL-1.0/DbCL"
    assert food.source_quality == "community_packaged_product;completeness=0.82"


def test_open_food_facts_missing_product_and_barcode_validation() -> None:
    def missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request)

    provider = OpenFoodFactsProvider(
        client=httpx.Client(transport=httpx.MockTransport(missing)),
        base_url="https://example.test",
        user_agent="HealthOSTest/1.0",
    )
    assert provider.lookup_barcode("7891234567890") is None
    with pytest.raises(ValueError, match="4 to 24 digits"):
        provider.lookup_barcode("not-a-barcode")


def test_usda_query_and_api_key_fail_closed() -> None:
    with pytest.raises(ValueError, match="API key"):
        UsdaFoodDataCentralProvider("  ")
    provider = UsdaFoodDataCentralProvider(
        "synthetic-key",
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request))),
        base_url="https://example.test/fdc/v1",
    )
    with pytest.raises(ValueError, match="1 to 200"):
        provider.search(" ")
