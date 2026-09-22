package com.brunocapellari.healthos.network

import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.json.JSONArray
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class HealthOsApiClientTest {
    private lateinit var server: MockWebServer
    private lateinit var client: HealthOsApiClient

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        client = HealthOsApiClient(server.url("/").toString())
    }

    @After
    fun tearDown() {
        server.close()
    }

    @Test
    fun pushUsesBearerAndCanonicalEndpoint() {
        server.enqueue(
            MockResponse.Builder()
                .code(200)
                .body("{\"accepted\":[],\"duplicates\":[],\"conflicts\":[],\"cursor\":0}")
                .build(),
        )

        val response = client.push("short-lived-token", JSONArray())
        val request = server.takeRequest()

        assertEquals("/v1/sync/push", request.url.encodedPath)
        assertEquals("Bearer short-lived-token", request.headers["Authorization"])
        assertTrue(response.has("cursor"))
    }


    @Test
    fun pairingTokenUsesAuthenticatedOwnerEndpoint() {
        server.enqueue(
            MockResponse.Builder()
                .code(200)
                .body(
                    "{\"token\":\"pair-token\",\"role\":\"owner_device\"," +
                        "\"expires_at\":\"2026-09-21T20:00:00Z\"}",
                )
                .build(),
        )

        val response = client.createPairingToken("owner-access-token", ttlSeconds = 300)
        val request = server.takeRequest()

        assertEquals("/v1/devices/pairing-token", request.url.encodedPath)
        assertEquals("Bearer owner-access-token", request.headers["Authorization"])
        val body = org.json.JSONObject(request.body?.utf8() ?: "{}")
        assertEquals("owner_device", body.getString("role"))
        assertEquals(300, body.getInt("ttl_seconds"))
        assertEquals("pair-token", response.getString("token"))
    }


    @Test
    fun barcodeLookupUsesAuthenticatedCanonicalNutritionEndpoint() {
        server.enqueue(
            MockResponse.Builder()
                .code(200)
                .body("{\"name\":\"Synthetic Food\",\"source\":\"open_food_facts\"}")
                .build(),
        )

        val response = client.lookupFoodBarcode("nutrition-token", "7891234567890")
        val request = server.takeRequest()

        assertEquals("/v1/nutrition/barcode/7891234567890", request.url.encodedPath)
        assertEquals("Bearer nutrition-token", request.headers["Authorization"])
        assertEquals("Synthetic Food", response.getString("name"))
    }

    @Test
    fun foodSearchEncodesQueryAndUsesBearer() {
        server.enqueue(
            MockResponse.Builder()
                .code(200)
                .body("{\"foods\":[]}")
                .build(),
        )

        client.searchFoods("nutrition-token", "arroz integral")
        val request = server.takeRequest()

        assertEquals("/v1/nutrition/search", request.url.encodedPath)
        assertEquals("arroz integral", request.url.queryParameter("q"))
        assertEquals("Bearer nutrition-token", request.headers["Authorization"])
    }

    @Test(expected = IllegalArgumentException::class)
    fun barcodeLookupRejectsNonNumericCodeBeforeNetwork() {
        client.lookupFoodBarcode("nutrition-token", "ABC-123")
    }
}
