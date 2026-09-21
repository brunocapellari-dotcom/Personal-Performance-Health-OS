package com.brunocapellari.healthos.health

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.changes.DeletionChange
import androidx.health.connect.client.changes.UpsertionChange
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.ElevationGainedRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.PowerRecord
import androidx.health.connect.client.records.Record
import androidx.health.connect.client.records.RestingHeartRateRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.SpeedRecord
import androidx.health.connect.client.records.StepsCadenceRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.TotalCaloriesBurnedRecord
import androidx.health.connect.client.records.WeightRecord
import androidx.health.connect.client.records.metadata.Metadata
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
    STEPS_CADENCE("steps_cadence", StepsCadenceRecord::class),
    HEART_RATE("heart_rate", HeartRateRecord::class),
    RESTING_HEART_RATE("resting_heart_rate", RestingHeartRateRecord::class),
    WEIGHT("weight", WeightRecord::class),
    SLEEP("sleep", SleepSessionRecord::class),
    EXERCISE("exercise", ExerciseSessionRecord::class),
    DISTANCE("distance", DistanceRecord::class),
    SPEED("speed", SpeedRecord::class),
    ELEVATION_GAINED("elevation_gained", ElevationGainedRecord::class),
    POWER("power", PowerRecord::class),
    ACTIVE_CALORIES("active_calories", ActiveCaloriesBurnedRecord::class),
    TOTAL_CALORIES("total_calories", TotalCaloriesBurnedRecord::class),
}

data class HealthDelta(
    val recordType: TrackedHealthType,
    val recordId: String,
    val observedAtEpochMillis: Long,
    val dataOriginPackage: String,
    val lastModifiedAtEpochMillis: Long,
    val clientRecordId: String?,
    val clientRecordVersion: Long,
    val recordingMethod: Int,
    val deviceType: Int?,
    val deviceManufacturer: String?,
    val deviceModel: String?,
    val payloadJson: String,
    val deleted: Boolean,
)

data class ChangeBatch(
    val deltas: List<HealthDelta>,
    val nextToken: String,
)

data class ExerciseAggregate(
    val sourcePackage: String,
    val durationSeconds: Long?,
    val steps: Long?,
    val distanceMeters: Double?,
    val totalCaloriesKcal: Double?,
    val activeCaloriesKcal: Double?,
    val minHeartRateBpm: Long?,
    val maxHeartRateBpm: Long?,
    val avgHeartRateBpm: Long?,
    val avgSpeedMetersPerSecond: Double?,
    val elevationGainedMeters: Double?,
    val avgPowerWatts: Double?,
    val avgStepsCadence: Double?,
)


class HealthConnectTokenExpiredException : IllegalStateException("Health Connect changes token expired")

interface HealthConnectPort {
    suspend fun hasCoreReadPermissions(): Boolean
    suspend fun hasBackgroundReadPermission(): Boolean
    suspend fun hasHistoryReadPermission(): Boolean
    suspend fun newToken(type: TrackedHealthType): String
    suspend fun backfill(type: TrackedHealthType, start: Instant, end: Instant): List<HealthDelta>
    suspend fun drain(type: TrackedHealthType, token: String): ChangeBatch
}

class HealthConnectGateway private constructor(
    private val context: Context?,
    private val client: HealthConnectClient,
) : HealthConnectPort {
    constructor(context: Context) : this(context, HealthConnectClient.getOrCreate(context))

    internal constructor(client: HealthConnectClient) : this(null, client)

    fun sdkStatus(): Int =
        if (context != null) HealthConnectClient.getSdkStatus(context) else HealthConnectClient.SDK_AVAILABLE

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

    override suspend fun hasCoreReadPermissions(): Boolean = hasPermissions(readPermissions())

    override suspend fun hasBackgroundReadPermission(): Boolean =
        grantedPermissions().contains(backgroundReadPermission())

    override suspend fun hasHistoryReadPermission(): Boolean =
        grantedPermissions().contains(historyReadPermission())

    override suspend fun newToken(type: TrackedHealthType): String = client.getChangesToken(
        ChangesTokenRequest(recordTypes = setOf(type.recordClass)),
    )

    override suspend fun backfill(
        type: TrackedHealthType,
        start: Instant,
        end: Instant,
    ): List<HealthDelta> = when (type) {
        TrackedHealthType.STEPS -> readAll(StepsRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.STEPS_CADENCE ->
            readAll(StepsCadenceRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.HEART_RATE -> readAll(HeartRateRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.RESTING_HEART_RATE ->
            readAll(RestingHeartRateRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.WEIGHT -> readAll(WeightRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.SLEEP -> readAll(SleepSessionRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.EXERCISE -> readAll(ExerciseSessionRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.DISTANCE -> readAll(DistanceRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.SPEED -> readAll(SpeedRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.ELEVATION_GAINED ->
            readAll(ElevationGainedRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.POWER -> readAll(PowerRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.ACTIVE_CALORIES ->
            readAll(ActiveCaloriesBurnedRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.TOTAL_CALORIES ->
            readAll(TotalCaloriesBurnedRecord::class, start, end).map { normalize(type, it) }
    }

    suspend fun aggregateExerciseSession(uid: String): ExerciseAggregate {
        val session = client.readRecord(ExerciseSessionRecord::class, uid).record
        val timeRange = TimeRangeFilter.between(session.startTime, session.endTime)
        val response = client.aggregate(
            AggregateRequest(
                metrics = setOf(
                    ExerciseSessionRecord.EXERCISE_DURATION_TOTAL,
                    StepsRecord.COUNT_TOTAL,
                    DistanceRecord.DISTANCE_TOTAL,
                    TotalCaloriesBurnedRecord.ENERGY_TOTAL,
                    ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL,
                    HeartRateRecord.BPM_MIN,
                    HeartRateRecord.BPM_MAX,
                    HeartRateRecord.BPM_AVG,
                    SpeedRecord.SPEED_AVG,
                    ElevationGainedRecord.ELEVATION_GAINED_TOTAL,
                    PowerRecord.POWER_AVG,
                    StepsCadenceRecord.RATE_AVG,
                ),
                timeRangeFilter = timeRange,
                dataOriginFilter = setOf(session.metadata.dataOrigin),
            ),
        )
        return ExerciseAggregate(
            sourcePackage = session.metadata.dataOrigin.packageName,
            durationSeconds = response[ExerciseSessionRecord.EXERCISE_DURATION_TOTAL]?.seconds,
            steps = response[StepsRecord.COUNT_TOTAL],
            distanceMeters = response[DistanceRecord.DISTANCE_TOTAL]?.inMeters,
            totalCaloriesKcal = response[TotalCaloriesBurnedRecord.ENERGY_TOTAL]?.inKilocalories,
            activeCaloriesKcal = response[ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL]?.inKilocalories,
            minHeartRateBpm = response[HeartRateRecord.BPM_MIN],
            maxHeartRateBpm = response[HeartRateRecord.BPM_MAX],
            avgHeartRateBpm = response[HeartRateRecord.BPM_AVG],
            avgSpeedMetersPerSecond = response[SpeedRecord.SPEED_AVG]?.inMetersPerSecond,
            elevationGainedMeters = response[ElevationGainedRecord.ELEVATION_GAINED_TOTAL]?.inMeters,
            avgPowerWatts = response[PowerRecord.POWER_AVG]?.inWatts,
            avgStepsCadence = response[StepsCadenceRecord.RATE_AVG],
        )
    }

    override suspend fun drain(type: TrackedHealthType, token: String): ChangeBatch {
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
                        lastModifiedAtEpochMillis = System.currentTimeMillis(),
                        clientRecordId = null,
                        clientRecordVersion = 0,
                        recordingMethod = Metadata.RECORDING_METHOD_UNKNOWN,
                        deviceType = null,
                        deviceManufacturer = null,
                        deviceModel = null,
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
            is StepsCadenceRecord -> {
                payload.put("startTime", record.startTime.toString())
                payload.put("endTime", record.endTime.toString())
                payload.put(
                    "samples",
                    JSONArray().apply {
                        record.samples.forEach { sample ->
                            put(JSONObject().put("time", sample.time.toString()).put("stepsPerMinute", sample.rate))
                        }
                    },
                )
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
            is RestingHeartRateRecord -> {
                payload.put("bpm", record.beatsPerMinute)
                payload.put("time", record.time.toString())
                record.time.toEpochMilli()
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
                payload.put(
                    "stages",
                    JSONArray().apply {
                        record.stages.forEach { stage ->
                            put(
                                JSONObject()
                                    .put("stage", stage.stage)
                                    .put("startTime", stage.startTime.toString())
                                    .put("endTime", stage.endTime.toString()),
                            )
                        }
                    },
                )
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
            is SpeedRecord -> {
                payload.put("startTime", record.startTime.toString())
                payload.put("endTime", record.endTime.toString())
                payload.put(
                    "samples",
                    JSONArray().apply {
                        record.samples.forEach { sample ->
                            put(
                                JSONObject()
                                    .put("time", sample.time.toString())
                                    .put("metersPerSecond", sample.speed.inMetersPerSecond),
                            )
                        }
                    },
                )
                record.endTime.toEpochMilli()
            }
            is ElevationGainedRecord -> {
                payload.put("meters", record.elevation.inMeters)
                payload.put("startTime", record.startTime.toString())
                payload.put("endTime", record.endTime.toString())
                record.endTime.toEpochMilli()
            }
            is PowerRecord -> {
                payload.put("startTime", record.startTime.toString())
                payload.put("endTime", record.endTime.toString())
                payload.put(
                    "samples",
                    JSONArray().apply {
                        record.samples.forEach { sample ->
                            put(JSONObject().put("time", sample.time.toString()).put("watts", sample.power.inWatts))
                        }
                    },
                )
                record.endTime.toEpochMilli()
            }
            is ActiveCaloriesBurnedRecord -> {
                payload.put("kilocalories", record.energy.inKilocalories)
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
        payload.put("_provenance", provenance(record.metadata))
        val metadata = record.metadata
        return HealthDelta(
            recordType = type,
            recordId = metadata.id,
            observedAtEpochMillis = observedAt,
            dataOriginPackage = metadata.dataOrigin.packageName,
            lastModifiedAtEpochMillis = metadata.lastModifiedTime.toEpochMilli(),
            clientRecordId = metadata.clientRecordId,
            clientRecordVersion = metadata.clientRecordVersion,
            recordingMethod = metadata.recordingMethod,
            deviceType = metadata.device?.type,
            deviceManufacturer = metadata.device?.manufacturer,
            deviceModel = metadata.device?.model,
            payloadJson = payload.toString(),
            deleted = false,
        )
    }

    private fun provenance(metadata: Metadata): JSONObject = JSONObject()
        .put("dataOriginPackage", metadata.dataOrigin.packageName)
        .put("lastModifiedTime", metadata.lastModifiedTime.toString())
        .put("clientRecordId", metadata.clientRecordId ?: JSONObject.NULL)
        .put("clientRecordVersion", metadata.clientRecordVersion)
        .put("recordingMethod", metadata.recordingMethod)
        .put("deviceType", metadata.device?.type ?: JSONObject.NULL)
        .put("deviceManufacturer", metadata.device?.manufacturer ?: JSONObject.NULL)
        .put("deviceModel", metadata.device?.model ?: JSONObject.NULL)
}
