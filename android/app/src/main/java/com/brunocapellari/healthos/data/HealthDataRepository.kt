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
    suspend fun enroll(bootstrapToken: String) {
        api.enroll(bootstrapToken, identity)
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

        val fingerprint = "performed_session|$performedId|${payload}"
        val changeId = sha256(fingerprint)
        database.pendingChangeDao().insert(
            PendingChangeEntity(
                changeId = changeId,
                entityType = "performed_session",
                entityId = performedId,
                logicalClock = now.toEpochMilli().coerceAtLeast(1),
                deleted = false,
                payloadJson = payload.toString(),
                createdAtEpochMillis = now.toEpochMilli(),
            ),
        )
        return performedId
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

    private fun JSONArray.toStringList(): List<String> = List(length()) { index -> getString(index) }
}
