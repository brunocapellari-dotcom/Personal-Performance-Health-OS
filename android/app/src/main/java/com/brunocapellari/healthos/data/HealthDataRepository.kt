package com.brunocapellari.healthos.data

import com.brunocapellari.healthos.health.HealthConnectPort
import com.brunocapellari.healthos.health.HealthConnectTokenExpiredException
import com.brunocapellari.healthos.health.HealthDelta
import com.brunocapellari.healthos.health.TrackedHealthType
import com.brunocapellari.healthos.network.HealthOsApiClient
import com.brunocapellari.healthos.security.DeviceIdentity
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.util.UUID


enum class HealthIngestionMode {
    FOREGROUND,
    BACKGROUND,
}

data class HealthBackfillPolicy(
    val windowDays: Long = 90,
    val recoveryMinimumDays: Long = 30,
    val historyDaysByType: Map<TrackedHealthType, Long> = mapOf(
        TrackedHealthType.HEART_RATE to 90,
        TrackedHealthType.RESTING_HEART_RATE to 365,
        TrackedHealthType.STEPS to 90,
        TrackedHealthType.STEPS_CADENCE to 90,
        TrackedHealthType.DISTANCE to 90,
        TrackedHealthType.SPEED to 90,
        TrackedHealthType.ELEVATION_GAINED to 90,
        TrackedHealthType.POWER to 90,
        TrackedHealthType.VO2_MAX to 365,
        TrackedHealthType.HEART_RATE_VARIABILITY to 365,
        TrackedHealthType.CYCLING_CADENCE to 90,
        TrackedHealthType.FLOORS_CLIMBED to 90,
        TrackedHealthType.BODY_FAT to 1825,
        TrackedHealthType.LEAN_BODY_MASS to 1825,
        TrackedHealthType.HYDRATION to 90,
        TrackedHealthType.ACTIVE_CALORIES to 90,
        TrackedHealthType.TOTAL_CALORIES to 90,
        TrackedHealthType.SLEEP to 365,
        TrackedHealthType.EXERCISE to 365,
        TrackedHealthType.WEIGHT to 1825,
    ),
) {
    init {
        require(windowDays > 0) { "windowDays must be positive" }
        require(recoveryMinimumDays >= 30) { "recoveryMinimumDays must cover at least 30 days" }
        require(historyDaysByType.values.all { it >= recoveryMinimumDays }) {
            "history windows must not be shorter than recovery minimum"
        }
    }

    fun initialStart(type: TrackedHealthType, now: Instant, canReadHistory: Boolean): Instant {
        val days = if (canReadHistory) {
            historyDaysByType[type] ?: recoveryMinimumDays
        } else {
            recoveryMinimumDays
        }
        return now.minus(Duration.ofDays(days))
    }

    fun recoveryStart(now: Instant, latestObserved: Instant?, canReadHistory: Boolean): Instant {
        val minimumStart = now.minus(Duration.ofDays(recoveryMinimumDays))
        if (!canReadHistory || latestObserved == null) return minimumStart
        return if (latestObserved.isBefore(minimumStart)) latestObserved else minimumStart
    }
}

data class SyncSummary(
    val healthEventsStaged: Int,
    val healthIngestionSkipped: Boolean,
    val pushed: Int,
    val conflicts: Int,
    val pulled: Int,
    val pending: Int,
)

class HealthDataRepository(
    private val database: HealthOsDatabase,
    private val healthConnect: HealthConnectPort,
    private val api: HealthOsApiClient,
    private val identity: DeviceIdentity,
    private val backfillPolicy: HealthBackfillPolicy = HealthBackfillPolicy(),
) {
    suspend fun enroll(linkToken: String) {
        api.enroll(linkToken, identity)
    }

    suspend fun createOwnerPairingToken(ttlSeconds: Int = 300): JSONObject {
        require(ttlSeconds in 30..900) { "pairing token TTL must be between 30 and 900 seconds" }
        val token = api.authenticate(identity)
        return api.createPairingToken(token, role = "owner_device", ttlSeconds = ttlSeconds)
    }

    suspend fun lookupFoodBarcode(barcode: String): JSONObject {
        require(barcode.matches(Regex("^\\d{4,24}$"))) { "barcode must contain 4 to 24 digits" }
        val token = api.authenticate(identity)
        return api.lookupFoodBarcode(token, barcode)
    }

    suspend fun searchFoods(query: String): JSONObject {
        val normalized = query.trim().replace(Regex("\\s+"), " ")
        require(normalized.length in 1..200) { "nutrition query must contain 1 to 200 characters" }
        val token = api.authenticate(identity)
        return api.searchFoods(token, normalized)
    }

    suspend fun loadDashboard(today: LocalDate): JSONObject {
        val token = api.authenticate(identity)
        return api.dashboard(token, today.toString())
    }

    suspend fun recordNutritionEntry(
        food: JSONObject,
        quantityG: Double,
        meal: String,
    ): String {
        require(quantityG > 0.0 && quantityG <= 10000.0) { "quantity must be between 0 and 10000 g" }
        val cleanMeal = meal.trim().replace(Regex("\\s+"), " ")
        require(cleanMeal.length in 1..64) { "meal must contain 1 to 64 characters" }
        val foodId = food.optString("food_id").trim()
        val foodName = food.optString("name").trim()
        val source = food.optString("source").trim()
        require(foodId.isNotBlank() && foodName.isNotBlank() && source.isNotBlank()) {
            "food record is missing canonical identity or provenance"
        }

        val factor = quantityG / 100.0
        fun scaled(key: String): Double? =
            if (!food.has(key) || food.isNull(key)) null else food.getDouble(key) * factor

        val micronutrients = JSONObject()
        val rawMicros = food.optJSONObject("micronutrients") ?: JSONObject()
        val keys = rawMicros.keys()
        while (keys.hasNext()) {
            val key = keys.next()
            val value = rawMicros.optDouble(key, Double.NaN)
            if (value.isFinite() && value >= 0.0) micronutrients.put(key, value * factor)
        }
        val fiberG = sequence {
            val micronutrientKeys = micronutrients.keys()
            while (micronutrientKeys.hasNext()) yield(micronutrientKeys.next())
        }
            .firstOrNull { key -> key.lowercase().contains("fiber") }
            ?.let { key -> micronutrients.optDouble(key, Double.NaN) }
            ?.takeIf(Double::isFinite)

        val entryId = UUID.randomUUID().toString()
        val now = Instant.now()
        val payload = JSONObject()
            .put("entry_id", entryId)
            .put("consumed_at", now.toString())
            .put("meal", cleanMeal)
            .put("food_id", foodId)
            .put("food_name", foodName)
            .put("quantity_g", quantityG)
            .put("source", source)
            .put("source_version", food.optNullable("source_version"))
            .put("source_record_id", food.optNullable("source_record_id"))
            .put("source_quality", food.optNullable("source_quality"))
            .put("license_id", food.optNullable("license_id"))
            .put("raw_hash", food.optNullable("raw_hash"))
            .put("energy_kcal", scaled("energy_kcal_per_100g") ?: JSONObject.NULL)
            .put("protein_g", scaled("protein_g_per_100g") ?: JSONObject.NULL)
            .put("carbohydrate_g", scaled("carbohydrate_g_per_100g") ?: JSONObject.NULL)
            .put("fat_g", scaled("fat_g_per_100g") ?: JSONObject.NULL)
            .put("fiber_g", fiberG ?: JSONObject.NULL)
            .put("micronutrients", micronutrients)

        stageEntity(
            entityType = "nutrition_entry",
            entityId = entryId,
            payload = payload,
            logicalClock = now.toEpochMilli().coerceAtLeast(1),
        )
        return entryId
    }

    suspend fun fullSync(mode: HealthIngestionMode = HealthIngestionMode.FOREGROUND): SyncSummary {
        val hasAnyRead = healthConnect.hasAnyReadPermission()
        val backgroundAllowed = mode != HealthIngestionMode.BACKGROUND || healthConnect.hasBackgroundReadPermission()
        val canIngestHealth = hasAnyRead && backgroundAllowed
        val staged = if (canIngestHealth) ingestHealthConnect() else 0
        val network = syncBackend()
        return network.copy(
            healthEventsStaged = staged,
            healthIngestionSkipped = !canIngestHealth,
        )
    }

    suspend fun ingestHealthConnect(): Int {
        val readableTypes = healthConnect.readableTypes()
        if (readableTypes.isEmpty()) {
            throw IllegalStateException("No Health Connect read permissions are granted")
        }
        var staged = 0
        for (type in readableTypes.sortedBy { it.wireName }) {
            staged += syncHealthType(type)
        }
        return staged
    }

    suspend fun pendingCount(): Int = database.pendingChangeDao().count()

    suspend fun conflictCount(): Int = database.syncConflictDao().count()

    suspend fun saveWorkoutDraft(draft: WorkoutDraft) {
        require(draft.sessionId.isNotBlank()) { "workout draft sessionId is required" }
        require(draft.duration.length <= 4 && draft.duration.all(Char::isDigit)) { "invalid workout draft duration" }
        val normalizedRpe = draft.rpe.replace(',', '.')
        require(
            draft.rpe.isBlank() ||
                (normalizedRpe.toDoubleOrNull()?.let { it in 0.0..10.0 } == true),
        ) { "invalid workout draft RPE" }
        require(draft.notes.length <= 5000) { "workout draft notes exceed 5000 characters" }
        database.syncStateDao().upsert(
            SyncStateEntity(
                key = "workout_draft:active",
                value = draft.toJson(),
                updatedAtEpochMillis = draft.updatedAtEpochMillis,
            ),
        )
    }

    suspend fun loadLatestWorkoutDraft(): WorkoutDraft? =
        database.syncStateDao()
            .get("workout_draft:active")
            ?.value
            ?.let(WorkoutDraft::fromJson)

    suspend fun clearWorkoutDraft(sessionId: String) {
        require(sessionId.isNotBlank()) { "sessionId is required" }
        val active = loadLatestWorkoutDraft()
        if (active?.sessionId == sessionId) {
            database.syncStateDao().delete("workout_draft:active")
        }
    }

    suspend fun saveInitialSetup(
        goalDescription: String,
        goalMetric: String,
        goalPriority: Int,
        goalBaseline: Double?,
        goalTarget: Double?,
        goalTargetDate: LocalDate?,
        environment: String,
        equipment: List<String>,
        spaceM2: Double,
        fixationPoints: List<String>,
        noiseLimit: String,
        surface: String,
        availableMinutes: Int,
        loadOptionsKg: List<Double>,
        sleepHours: Double,
        sleepQuality: Int,
        energy: Int,
        fatigue: Int,
        soreness: Int,
        stress: Int,
        painFlag: Boolean,
    ): String {
        require(goalDescription.isNotBlank()) { "goal description is required" }
        require(goalMetric.isNotBlank()) { "goal metric is required" }
        require(goalPriority in 1..5) { "goal priority must be between 1 and 5" }
        require(environment in setOf("HOME", "GYM", "OUTDOOR", "TRAVEL", "MINIMAL_EQUIPMENT")) {
            "unsupported training environment"
        }
        require(spaceM2 > 0.0) { "space must be positive" }
        require(noiseLimit in setOf("low", "moderate", "high")) { "invalid noise limit" }
        require(surface.isNotBlank()) { "surface is required" }
        require(availableMinutes in 15..240) { "available minutes must be between 15 and 240" }
        require(loadOptionsKg.all { it > 0.0 && it <= 5000.0 }) { "invalid available load" }
        require(loadOptionsKg.distinct().size == loadOptionsKg.size) { "available loads must be unique" }
        require(sleepHours in 0.0..24.0) { "sleep hours must be between 0 and 24" }
        require(listOf(sleepQuality, energy, fatigue, soreness, stress).all { it in 1..5 }) {
            "readiness ratings must be between 1 and 5"
        }

        val now = Instant.now()
        val logicalClock = now.toEpochMilli().coerceAtLeast(1)
        val goalId = "primary-goal"
        val goal = JSONObject()
            .put("goal_id", goalId)
            .put("description", goalDescription.trim())
            .put("priority", goalPriority)
            .put("metric", goalMetric.trim())
            .put("constraints", JSONArray())
        if (goalBaseline != null) goal.put("baseline", goalBaseline)
        if (goalTarget != null) goal.put("target", goalTarget)
        if (goalTargetDate != null) goal.put("target_date", goalTargetDate.toString())

        val cleanEquipment = equipment.map(String::trim).filter(String::isNotBlank).distinct()
        val cleanFixationPoints = fixationPoints.map(String::trim).filter(String::isNotBlank).distinct()
        val trainingEnvironment = JSONObject()
            .put("environment", environment)
            .put("equipment", JSONArray(cleanEquipment))
            .put("space_m2", spaceM2)
            .put("fixation_points", JSONArray(cleanFixationPoints))
            .put("noise_limit", noiseLimit)
            .put("surface", surface.trim())
            .put("available_minutes", availableMinutes)
            .put("load_options_kg", JSONArray(loadOptionsKg.sorted()))

        val readinessId = "readiness-${UUID.randomUUID()}"
        val readiness = JSONObject()
            .put("observed_at", now.toString())
            .put("sleep_hours", sleepHours)
            .put("sleep_quality_1_5", sleepQuality)
            .put("energy_1_5", energy)
            .put("fatigue_1_5", fatigue)
            .put("soreness_1_5", soreness)
            .put("stress_1_5", stress)
            .put("pain_flag", painFlag)

        stageEntity("goal", goalId, goal, logicalClock)
        stageEntity("training_environment", "primary", trainingEnvironment, logicalClock + 1)
        stageEntity("readiness", readinessId, readiness, logicalClock + 2)
        return goalId
    }

    suspend fun recordPerformedSession(
        plannedSessionId: String,
        completed: Boolean,
        durationMinutes: Int,
        rpe: Double?,
        notes: String = "",
        exercises: JSONArray = JSONArray(),
    ): String {
        require(plannedSessionId.isNotBlank()) { "plannedSessionId is required" }
        require(durationMinutes in 0..1440) { "durationMinutes must be between 0 and 1440" }
        require(rpe == null || rpe in 0.0..10.0) { "RPE must be between 0 and 10" }
        require(notes.length <= 5000) { "notes exceed 5000 characters" }

        val performedId = UUID.randomUUID().toString()
        val now = Instant.now()
        val payload = JSONObject()
            .put("planned_session_id", plannedSessionId)
            .put("performed_at", now.toString())
            .put("completed", completed)
            .put("duration_minutes", durationMinutes)
            .put("rpe", rpe ?: JSONObject.NULL)
            .put("notes", notes)
            .put("exercises", exercises)

        stageEntity(
            entityType = "performed_session",
            entityId = performedId,
            payload = payload,
            logicalClock = now.toEpochMilli().coerceAtLeast(1),
        )
        return performedId
    }

    private suspend fun stageEntity(
        entityType: String,
        entityId: String,
        payload: JSONObject,
        logicalClock: Long,
    ) {
        val fingerprint = "$entityType|$entityId|$logicalClock|${payload}"
        val changeId = sha256(fingerprint)
        database.pendingChangeDao().insert(
            PendingChangeEntity(
                changeId = changeId,
                entityType = entityType,
                entityId = entityId,
                logicalClock = logicalClock,
                deleted = false,
                payloadJson = payload.toString(),
                createdAtEpochMillis = System.currentTimeMillis(),
            ),
        )
    }

    private suspend fun syncHealthType(type: TrackedHealthType): Int {
        val stateKey = "health_connect_token_${type.wireName}"
        val state = database.syncStateDao().get(stateKey)
        var token = state?.value
        var staged = 0
        val now = Instant.now()
        val canReadHistory = healthConnect.hasHistoryReadPermission()

        if (token == null) {
            token = healthConnect.newToken(type)
            staged += backfillWindowed(type, backfillPolicy.initialStart(type, now, canReadHistory), now)
        }

        val batch = try {
            healthConnect.drain(type, token)
        } catch (_: HealthConnectTokenExpiredException) {
            token = healthConnect.newToken(type)
            staged += backfillWindowed(type, recoveryBackfillStart(type, now, canReadHistory), now)
            healthConnect.drain(type, token)
        }
        staged += stageDeltas(batch.deltas)
        database.syncStateDao().upsert(
            SyncStateEntity(
                key = stateKey,
                value = batch.nextToken,
                updatedAtEpochMillis = System.currentTimeMillis(),
            ),
        )
        return staged
    }

    private suspend fun recoveryBackfillStart(
        type: TrackedHealthType,
        now: Instant,
        canReadHistory: Boolean,
    ): Instant {
        val latest = database.observationDao().latestObservedAt(type.wireName)?.let(Instant::ofEpochMilli)
        return backfillPolicy.recoveryStart(now, latest, canReadHistory)
    }

    private suspend fun backfillWindowed(type: TrackedHealthType, start: Instant, end: Instant): Int {
        require(!start.isAfter(end)) { "Health Connect backfill start must not be after end" }
        var cursor = start
        var staged = 0
        val window = Duration.ofDays(backfillPolicy.windowDays.coerceAtLeast(1))
        while (cursor.isBefore(end)) {
            val next = minOf(cursor.plus(window), end)
            staged += stageDeltas(healthConnect.backfill(type, cursor, next))
            cursor = next
        }
        return staged
    }

    private suspend fun stageDeltas(deltas: List<HealthDelta>): Int {
        var inserted = 0
        for (delta in deltas) {
            val currentKey = "${delta.recordType.wireName}:${delta.recordId}"
            val existing = database.observationDao().get(currentKey)
            val current = if (delta.deleted) {
                existing?.copy(deleted = true) ?: LocalObservationEntity(
                    observationId = currentKey,
                    recordType = delta.recordType.wireName,
                    sourceRecordId = delta.recordId,
                    observedAtEpochMillis = delta.observedAtEpochMillis,
                    payloadJson = "{}",
                    dataOriginPackage = delta.dataOriginPackage,
                    deleted = true,
                )
            } else {
                LocalObservationEntity(
                    observationId = currentKey,
                    recordType = delta.recordType.wireName,
                    sourceRecordId = delta.recordId,
                    observedAtEpochMillis = delta.observedAtEpochMillis,
                    payloadJson = delta.payloadJson,
                    dataOriginPackage = delta.dataOriginPackage,
                    deleted = false,
                )
            }
            database.observationDao().upsert(current)

            val fingerprint = if (delta.deleted) {
                "delete|${delta.recordType.wireName}|${delta.recordId}"
            } else {
                "upsert|${delta.recordType.wireName}|${delta.recordId}|${delta.payloadJson}"
            }
            val changeId = sha256(fingerprint)
            val payload = JSONObject()
                .put("record_type", delta.recordType.wireName)
                .put("source_record_id", delta.recordId)
                .put("observed_at_epoch_ms", delta.observedAtEpochMillis)
                .put("data_origin_package", delta.dataOriginPackage)
                .put("last_modified_at_epoch_ms", delta.lastModifiedAtEpochMillis)
                .put("client_record_id", delta.clientRecordId ?: JSONObject.NULL)
                .put("client_record_version", delta.clientRecordVersion)
                .put("recording_method", delta.recordingMethod)
                .put("device_type", delta.deviceType ?: JSONObject.NULL)
                .put("device_manufacturer", delta.deviceManufacturer ?: JSONObject.NULL)
                .put("device_model", delta.deviceModel ?: JSONObject.NULL)
                .put("health_connect_deleted", delta.deleted)
                .put("data", JSONObject(delta.payloadJson))
            val result = database.pendingChangeDao().insert(
                PendingChangeEntity(
                    changeId = changeId,
                    entityType = if (delta.deleted) "health_connect_tombstone" else "observation",
                    entityId = changeId,
                    logicalClock = delta.observedAtEpochMillis.coerceAtLeast(1),
                    deleted = false,
                    payloadJson = payload.toString(),
                    createdAtEpochMillis = System.currentTimeMillis(),
                ),
            )
            if (result != -1L) inserted += 1
        }
        return inserted
    }

    private suspend fun syncBackend(): SyncSummary {
        val token = api.authenticate(identity)
        var pushed = 0
        var conflictCount = 0

        while (true) {
            val pending = database.pendingChangeDao().oldest(250)
            if (pending.isEmpty()) break
            val response = api.push(
                token,
                JSONArray().apply {
                    pending.forEach { change ->
                        put(
                            JSONObject()
                                .put("change_id", change.changeId)
                                .put("entity_type", change.entityType)
                                .put("entity_id", change.entityId)
                                .put("logical_clock", change.logicalClock)
                                .put("deleted", change.deleted)
                                .put("payload", JSONObject(change.payloadJson)),
                        )
                    }
                },
            )
            val accepted = response.getJSONArray("accepted").toStringList()
            val duplicates = response.getJSONArray("duplicates").toStringList()
            val conflicts = response.getJSONArray("conflicts").toStringList()
            val pendingById = pending.associateBy { it.changeId }
            conflicts.forEach { id ->
                pendingById[id]?.let { change ->
                    database.syncConflictDao().upsert(
                        SyncConflictEntity(
                            changeId = change.changeId,
                            entityType = change.entityType,
                            entityId = change.entityId,
                            payloadJson = change.payloadJson,
                            detectedAtEpochMillis = System.currentTimeMillis(),
                        ),
                    )
                }
            }
            database.pendingChangeDao().delete(accepted + duplicates + conflicts)
            pushed += accepted.size + duplicates.size
            conflictCount += conflicts.size
            if (accepted.isEmpty() && duplicates.isEmpty() && conflicts.isEmpty()) {
                throw IllegalStateException("Sync push made no progress")
            }
        }

        val pulled = pullAll(token)
        return SyncSummary(
            healthEventsStaged = 0,
            healthIngestionSkipped = false,
            pushed = pushed,
            conflicts = conflictCount,
            pulled = pulled,
            pending = database.pendingChangeDao().count(),
        )
    }

    private suspend fun pullAll(token: String): Int {
        val cursorState = database.syncStateDao().get("backend_cursor")
        var cursor = cursorState?.value?.toLongOrNull() ?: 0L
        var pulled = 0
        while (true) {
            val response = api.pull(token, cursor)
            val changes = response.getJSONArray("changes")
            for (index in 0 until changes.length()) {
                val item = changes.getJSONObject(index)
                database.remoteEntityDao().upsert(
                    RemoteEntityEntity(
                        entityType = item.getString("entity_type"),
                        entityId = item.getString("entity_id"),
                        logicalClock = item.getLong("logical_clock"),
                        originDeviceId = item.getString("origin_device_id"),
                        deleted = item.getBoolean("deleted"),
                        payloadJson = item.getJSONObject("payload").toString(),
                        serverSeq = item.getLong("server_seq"),
                    ),
                )
                pulled += 1
            }
            val next = response.getLong("cursor")
            database.syncStateDao().upsert(
                SyncStateEntity("backend_cursor", next.toString(), System.currentTimeMillis()),
            )
            if (changes.length() < 500 || next <= cursor) break
            cursor = next
        }
        return pulled
    }

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }

    private fun JSONObject.optNullable(key: String): Any =
        if (!has(key) || isNull(key)) JSONObject.NULL else get(key)

    private fun JSONArray.toStringList(): List<String> = List(length()) { index -> getString(index) }
}
