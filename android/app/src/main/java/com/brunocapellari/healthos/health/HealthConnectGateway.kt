package com.brunocapellari.healthos.health

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.changes.DeletionChange
import androidx.health.connect.client.changes.UpsertionChange
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.Record
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.TotalCaloriesBurnedRecord
import androidx.health.connect.client.records.WeightRecord
import androidx.health.connect.client.request.ChangesTokenRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import kotlin.reflect.KClass

enum class TrackedHealthType(
    val wireName: String,
    val recordClass: KClass<out Record>,
) {
    STEPS("steps", StepsRecord::class),
    HEART_RATE("heart_rate", HeartRateRecord::class),
    WEIGHT("weight", WeightRecord::class),
    SLEEP("sleep", SleepSessionRecord::class),
    EXERCISE("exercise", ExerciseSessionRecord::class),
    DISTANCE("distance", DistanceRecord::class),
    TOTAL_CALORIES("total_calories", TotalCaloriesBurnedRecord::class),
}

data class HealthDelta(
    val recordType: TrackedHealthType,
    val recordId: String,
    val observedAtEpochMillis: Long,
    val dataOriginPackage: String,
    val payloadJson: String,
    val deleted: Boolean,
)

data class ChangeBatch(
    val deltas: List<HealthDelta>,
    val nextToken: String,
)

class HealthConnectTokenExpiredException : IllegalStateException("Health Connect changes token expired")

class HealthConnectGateway(private val context: Context) {
    private val client: HealthConnectClient by lazy { HealthConnectClient.getOrCreate(context) }

    fun sdkStatus(): Int = HealthConnectClient.getSdkStatus(context)

    fun readPermissions(): Set<String> = TrackedHealthType.entries
        .mapTo(mutableSetOf()) { HealthPermission.getReadPermission(it.recordClass) }

    fun backgroundReadPermission(): String = HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND

    fun historyReadPermission(): String = HealthPermission.PERMISSION_READ_HEALTH_DATA_HISTORY

    fun extendedReadPermissions(): Set<String> = readPermissions() + setOf(
        backgroundReadPermission(),
        historyReadPermission(),
    )

    suspend fun grantedPermissions(): Set<String> = client.permissionController.getGrantedPermissions()

    suspend fun hasPermissions(permissions: Set<String> = readPermissions()): Boolean =
        grantedPermissions().containsAll(permissions)

    suspend fun hasCoreReadPermissions(): Boolean = hasPermissions(readPermissions())

    suspend fun hasBackgroundReadPermission(): Boolean = grantedPermissions().contains(backgroundReadPermission())

    suspend fun hasHistoryReadPermission(): Boolean = grantedPermissions().contains(historyReadPermission())

    suspend fun newToken(type: TrackedHealthType): String = client.getChangesToken(
        ChangesTokenRequest(recordTypes = setOf(type.recordClass)),
    )

    suspend fun backfill(
        type: TrackedHealthType,
        start: Instant = Instant.EPOCH,
        end: Instant = Instant.now(),
    ): List<HealthDelta> = when (type) {
        TrackedHealthType.STEPS -> readAll(StepsRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.HEART_RATE -> readAll(HeartRateRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.WEIGHT -> readAll(WeightRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.SLEEP -> readAll(SleepSessionRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.EXERCISE -> readAll(ExerciseSessionRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.DISTANCE -> readAll(DistanceRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.TOTAL_CALORIES -> readAll(TotalCaloriesBurnedRecord::class, start, end).map { normalize(type, it) }
    }

    suspend fun drain(type: TrackedHealthType, token: String): ChangeBatch {
        val deltas = mutableListOf<HealthDelta>()
        var next = token
        do {
            val response = client.getChanges(next)
            if (response.changesTokenExpired) throw HealthConnectTokenExpiredException()
            response.changes.forEach { change ->
                when (change) {
                    is UpsertionChange -> deltas += normalize(type, change.record)
                    is DeletionChange -> deltas += HealthDelta(
                        recordType = type,
                        recordId = change.recordId,
                        observedAtEpochMillis = System.currentTimeMillis(),
                        dataOriginPackage = "health-connect",
                        payloadJson = "{}",
                        deleted = true,
                    )
                }
            }
            next = response.nextChangesToken
        } while (response.hasMore)
        return ChangeBatch(deltas = deltas, nextToken = next)
    }

    private suspend fun <T : Record> readAll(recordClass: KClass<T>, start: Instant, end: Instant): List<T> {
        val records = mutableListOf<T>()
        var pageToken: String? = null
        do {
            val response = client.readRecords(
                ReadRecordsRequest(
                    recordType = recordClass,
                    timeRangeFilter = TimeRangeFilter.between(start, end),
                    pageToken = pageToken,
                ),
            )
            records += response.records
            pageToken = response.pageToken
        } while (!pageToken.isNullOrEmpty())
        return records
    }

    private fun normalize(type: TrackedHealthType, record: Record): HealthDelta {
        val payload = JSONObject()
        val observedAt = when (record) {
            is StepsRecord -> {
                payload.put("count", record.count)
                payload.put("startTime", record.startTime.toString())
                payload.put("endTime", record.endTime.toString())
                record.endTime.toEpochMilli()
            }
            is HeartRateRecord -> {
                payload.put("startTime", record.startTime.toString())
                payload.put("endTime", record.endTime.toString())
                payload.put(
                    "samples",
                    JSONArray().apply {
                        record.samples.forEach { sample ->
                            put(JSONObject().put("time", sample.time.toString()).put("bpm", sample.beatsPerMinute))
                        }
                    },
                )
                record.endTime.toEpochMilli()
            }
            is WeightRecord -> {
                payload.put("kilograms", record.weight.inKilograms)
                payload.put("time", record.time.toString())
                record.time.toEpochMilli()
            }
            is SleepSessionRecord -> {
                payload.put("startTime", record.startTime.toString())
                payload.put("endTime", record.endTime.toString())
                payload.put("title", record.title)
                payload.put("notes", record.notes)
                record.endTime.toEpochMilli()
            }
            is ExerciseSessionRecord -> {
                payload.put("startTime", record.startTime.toString())
                payload.put("endTime", record.endTime.toString())
                payload.put("exerciseType", record.exerciseType)
                payload.put("title", record.title)
                record.endTime.toEpochMilli()
            }
            is DistanceRecord -> {
                payload.put("meters", record.distance.inMeters)
                payload.put("startTime", record.startTime.toString())
                payload.put("endTime", record.endTime.toString())
                record.endTime.toEpochMilli()
            }
            is TotalCaloriesBurnedRecord -> {
                payload.put("kilocalories", record.energy.inKilocalories)
                payload.put("startTime", record.startTime.toString())
                payload.put("endTime", record.endTime.toString())
                record.endTime.toEpochMilli()
            }
            else -> throw IllegalArgumentException("Unsupported Health Connect record: ${record::class}")
        }
        return HealthDelta(
            recordType = type,
            recordId = record.metadata.id,
            observedAtEpochMillis = observedAt,
            dataOriginPackage = record.metadata.dataOrigin.packageName,
            payloadJson = payload.toString(),
            deleted = false,
        )
    }
}
