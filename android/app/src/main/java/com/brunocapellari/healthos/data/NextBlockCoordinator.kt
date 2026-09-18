package com.brunocapellari.healthos.data

import com.brunocapellari.healthos.network.HealthOsApiClient
import com.brunocapellari.healthos.security.DeviceIdentity
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate

class NextBlockCoordinator(
    private val database: HealthOsDatabase,
    private val api: HealthOsApiClient,
    private val identity: DeviceIdentity,
) {
    suspend fun generate(weeks: Int = 4): JSONObject {
        require(weeks in 1..12)
        val goals = database.remoteEntityDao().activeByType("goal")
        val environment = database.remoteEntityDao().activeByType("training_environment").firstOrNull()
        val readiness = database.remoteEntityDao().activeByType("readiness").firstOrNull()
        val nutrition = database.remoteEntityDao().activeByType("nutrition_trend").firstOrNull()
        val event = database.remoteEntityDao().activeByType("event").firstOrNull()

        require(goals.isNotEmpty()) { "At least one active goal is required" }
        require(environment != null) { "Training environment is required" }
        require(readiness != null) { "Readiness check-in is required" }

        val request = JSONObject()
            .put("goals", JSONArray().apply { goals.forEach { put(JSONObject(it.payloadJson)) } })
            .put("environment", JSONObject(environment.payloadJson))
            .put("readiness", JSONObject(readiness.payloadJson))
            .put("nutrition_trend", nutrition?.let { JSONObject(it.payloadJson) } ?: JSONObject.NULL)
            .put("event", event?.let { JSONObject(it.payloadJson) } ?: JSONObject.NULL)
            .put("today", LocalDate.now().toString())
            .put("weeks", weeks)

        return api.nextBlock(api.authenticate(identity), request)
    }
}
