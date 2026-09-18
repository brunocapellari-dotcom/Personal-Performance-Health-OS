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
}
