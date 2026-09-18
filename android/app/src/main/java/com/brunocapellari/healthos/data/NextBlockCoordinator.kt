package com.brunocapellari.healthos.data

import com.brunocapellari.healthos.network.HealthOsApiClient
import com.brunocapellari.healthos.security.DeviceIdentity
import org.json.JSONObject
import java.time.LocalDate

class NextBlockCoordinator(
    private val repository: HealthDataRepository,
    private val api: HealthOsApiClient,
    private val identity: DeviceIdentity,
) {
    suspend fun generate(weeks: Int = 4): JSONObject {
        require(weeks in 1..12)
        repository.fullSync(HealthIngestionMode.FOREGROUND)
        val request = JSONObject()
            .put("today", LocalDate.now().toString())
            .put("weeks", weeks)
        return api.nextBlock(api.authenticate(identity), request)
    }
}
