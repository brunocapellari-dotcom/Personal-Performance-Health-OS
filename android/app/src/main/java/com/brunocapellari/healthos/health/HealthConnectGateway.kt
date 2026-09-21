package com.brunocapellari.healthos.health

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.aggregate.AggregateMetric
import androidx.health.connect.client.changes.DeletionChange
import androidx.health.connect.client.changes.UpsertionChange
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.BodyFatRecord
import androidx.health.connect.client.records.CyclingPedalingCadenceRecord
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.ElevationGainedRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.FloorsClimbedRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.HeartRateVariabilityRmssdRecord
import androidx.health.connect.client.records.HydrationRecord
import androidx.health.connect.client.records.LeanBodyMassRecord
import androidx.health.connect.client.records.PowerRecord
import androidx.health.connect.client.records.Record
import androidx.health.connect.client.records.RestingHeartRateRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.SpeedRecord
import androidx.health.connect.client.records.StepsCadenceRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.TotalCaloriesBurnedRecord
import androidx.health.connect.client.records.WeightRecord
import androidx.health.connect.client.records.Vo2MaxRecord
import androidx.health.connect.client.records.metadata.Metadata
import androidx.health.connect.client.request.ChangesTokenRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import kotlin.reflect.KClass

enum class HealthMetricTier {
    CORE,
    PERFORMANCE,
    BODY_COMPOSITION,
    NUTRITION,
}

enum class TrackedHealthType(
    val wireName: String,
    val recordClass: KClass<out Record>,
    val tier: HealthMetricTier,
) {
    STEPS("steps", StepsRecord::class, HealthMetricTier.CORE),
    HEART_RATE("heart_rate", HeartRateRecord::class, HealthMetricTier.CORE),
    RESTING_HEART_RATE("resting_heart_rate", RestingHeartRateRecord::class, HealthMetricTier.CORE),
    WEIGHT("weight", WeightRecord::class, HealthMetricTier.CORE),
    SLEEP("sleep", SleepSessionRecord::class, HealthMetricTier.CORE),
    EXERCISE("exercise", ExerciseSessionRecord::class, HealthMetricTier.CORE),
    DISTANCE("distance", DistanceRecord::class, HealthMetricTier.CORE),
    TOTAL_CALORIES("total_calories", TotalCaloriesBurnedRecord::class, HealthMetricTier.CORE),
    ACTIVE_CALORIES("active_calories", ActiveCaloriesBurnedRecord::class, HealthMetricTier.PERFORMANCE),
    STEPS_CADENCE("steps_cadence", StepsCadenceRecord::class, HealthMetricTier.PERFORMANCE),
    SPEED("speed", SpeedRecord::class, HealthMetricTier.PERFORMANCE),
    ELEVATION_GAINED("elevation_gained", ElevationGainedRecord::class, HealthMetricTier.PERFORMANCE),
    POWER("power", PowerRecord::class, HealthMetricTier.PERFORMANCE),
    VO2_MAX("vo2_max", Vo2MaxRecord::class, HealthMetricTier.PERFORMANCE),
    HEART_RATE_VARIABILITY(
        "heart_rate_variability_rmssd",
        HeartRateVariabilityRmssdRecord::class,
        HealthMetricTier.PERFORMANCE,
    ),
    CYCLING_CADENCE(
        "cycling_pedaling_cadence",
        CyclingPedalingCadenceRecord::class,
        HealthMetricTier.PERFORMANCE,
    ),
    FLOORS_CLIMBED("floors_climbed", FloorsClimbedRecord::class, HealthMetricTier.PERFORMANCE),
    BODY_FAT("body_fat", BodyFatRecord::class, HealthMetricTier.BODY_COMPOSITION),
    LEAN_BODY_MASS("lean_body_mass", LeanBodyMassRecord::class, HealthMetricTier.BODY_COMPOSITION),
    HYDRATION("hydration", HydrationRecord::class, HealthMetricTier.NUTRITION),
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
    suspend fun hasAnyReadPermission(): Boolean
    suspend fun readableTypes(): Set<TrackedHealthType>
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
        .filter { it.tier == HealthMetricTier.CORE }
        .mapTo(mutableSetOf()) { HealthPermission.getReadPermission(it.recordClass) }

    fun performanceReadPermissions(): Set<String> = permissionsForTier(HealthMetricTier.PERFORMANCE)

    fun bodyCompositionReadPermissions(): Set<String> = permissionsForTier(HealthMetricTier.BODY_COMPOSITION)

    fun nutritionReadPermissions(): Set<String> = permissionsForTier(HealthMetricTier.NUTRITION)

    private fun permissionsForTier(tier: HealthMetricTier): Set<String> = TrackedHealthType.entries
        .filter { it.tier == tier }
        .mapTo(mutableSetOf()) { HealthPermission.getReadPermission(it.recordClass) }

    fun allReadPermissions(): Set<String> =
        readPermissions() + performanceReadPermissions() + bodyCompositionReadPermissions() + nutritionReadPermissions()

    fun backgroundReadPermission(): String = HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND

    fun historyReadPermission(): String = HealthPermission.PERMISSION_READ_HEALTH_DATA_HISTORY

    fun extendedReadPermissions(): Set<String> = setOf(
        backgroundReadPermission(),
        historyReadPermission(),
    )

    suspend fun grantedPermissions(): Set<String> = client.permissionController.getGrantedPermissions()

    suspend fun hasPermissions(permissions: Set<String> = readPermissions()): Boolean =
        grantedPermissions().containsAll(permissions)

    override suspend fun hasCoreReadPermissions(): Boolean = hasPermissions(readPermissions())

    override suspend fun hasAnyReadPermission(): Boolean {
        val granted = grantedPermissions()
        return TrackedHealthType.entries.any {
            granted.contains(HealthPermission.getReadPermission(it.recordClass))
        }
    }

    override suspend fun readableTypes(): Set<TrackedHealthType> {
        val granted = grantedPermissions()
        return TrackedHealthType.entries.filterTo(mutableSetOf()) {
            granted.contains(HealthPermission.getReadPermission(it.recordClass))
        }
    }

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
        TrackedHealthType.VO2_MAX -> readAll(Vo2MaxRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.HEART_RATE_VARIABILITY ->
            readAll(HeartRateVariabilityRmssdRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.CYCLING_CADENCE ->
            readAll(CyclingPedalingCadenceRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.FLOORS_CLIMBED ->
            readAll(FloorsClimbedRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.BODY_FAT -> readAll(BodyFatRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.LEAN_BODY_MASS ->
            readAll(LeanBodyMassRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.HYDRATION -> readAll(HydrationRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.ACTIVE_CALORIES ->
            readAll(ActiveCaloriesBurnedRecord::class, start, end).map { normalize(type, it) }
        TrackedHealthType.TOTAL_CALORIES ->
            readAll(TotalCaloriesBurnedRecord::class, start, end).map { normalize(type, it) }
    }

    suspend fun aggregateExerciseSession(uid: String): ExerciseAggregate {
        val readable = readableTypes()
        require(TrackedHealthType.EXERCISE in readable) {
            "Exercise read permission is required for exercise-session aggregates"
        }

        val session = client.readRecord(ExerciseSessionRecord::class, uid).record
        val metrics = mutableSetOf<AggregateMetric<*>>(ExerciseSessionRecord.EXERCISE_DURATION_TOTAL)
        if (TrackedHealthType.STEPS in readable) metrics += StepsRecord.COUNT_TOTAL
        if (TrackedHealthType.DISTANCE in readable) metrics += DistanceRecord.DISTANCE_TOTAL
        if (TrackedHealthType.TOTAL_CALORIES in readable) metrics += TotalCaloriesBurnedRecord.ENERGY_TOTAL
        if (TrackedHealthType.ACTIVE_CALORIES in readable) metrics += ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL
        if (TrackedHealthType.HEART_RATE in readable) {
            metrics += HeartRateRecord.BPM_MIN
            metrics += HeartRateRecord.BPM_MAX
            metrics += HeartRateRecord.BPM_AVG
        }
        if (TrackedHealthType.SPEED in readable) metrics += SpeedRecord.SPEED_AVG
        if (TrackedHealthType.ELEVATION_GAINED in readable) metrics += ElevationGainedRecord.ELEVATION_GAINED_TOTAL
        if (TrackedHealthType.POWER in readable) metrics += PowerRecord.POWER_AVG
        if (TrackedHealthType.STEPS_CADENCE in readable) metrics += StepsCadenceRecord.RATE_AVG

        val response = client.aggregate(
            AggregateRequest(
                metrics = metrics,
                timeRangeFilter = TimeRangeFilter.between(session.startTime, session.endTime),
                dataOriginFilter = setOf(session.metadata.dataOrigin),
            ),
        )
        return ExerciseAggregate(
            sourcePackage = session.metadata.dataOrigin.packageName,
            durationSeconds = response[ExerciseSessionRecord.EXERCISE_DURATION_TOTAL]?.seconds,
            steps = if (TrackedHealthType.STEPS in readable) response[StepsRecord.COUNT_TOTAL] else null,
            distanceMeters = if (TrackedHealthType.DISTANCE in readable) {
                response[DistanceRecord.DISTANCE_TOTAL]?.inMeters
            } else {
                null
            },
            totalCaloriesKcal = if (TrackedHealthType.TOTAL_CALORIES in readable) {
                response[TotalCaloriesBurnedRecord.ENERGY_TOTAL]?.inKilocalories
            } else {
                null
            },
            activeCaloriesKcal = if (TrackedHealthType.ACTIVE_CALORIES in readable) {
                response[ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL]?.inKilocalories
            } else {
                null
            },
            minHeartRateBpm = if (TrackedHealthType.HEART_RATE in readable) response[HeartRateRecord.BPM_MIN] else null,
            maxHeartRateBpm = if (TrackedHealthType.HEART_RATE in readable) response[HeartRateRecord.BPM_MAX] else null,
            avgHeartRateBpm = if (TrackedHealthType.HEART_RATE in readable) response[HeartRateRecord.BPM_AVG] else null,
            avgSpeedMetersPerSecond = if (TrackedHealthType.SPEED in readable) {
                response[SpeedRecord.SPEED_AVG]?.inMetersPerSecond
            } else {
                null
            },
            elevationGainedMeters = if (TrackedHealthType.ELEVATION_GAINED in readable) {
                response[ElevationGainedRecord.ELEVATION_GAINED_TOTAL]?.inMeters
            } else {
                null
            },
            avgPowerWatts = if (TrackedHealthType.POWER in readable) {
                response[PowerRecord.POWER_AVG]?.inWatts
            } else {
                null
            },
            avgStepsCadence = if (TrackedHealthType.STEPS_CADENCE in readable) {
                response[StepsCadenceRecord.RATE_AVG]
            } else {
                null
            },
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
            is Vo2MaxRecord -> {
                payload.put("millilitersPerMinuteKilogram", record.vo2MillilitersPerMinuteKilogram)
                payload.put("measurementMethod", record.measurementMethod)
                payload.put("time", record.time.toString())
                record.time.toEpochMilli()
            }
            is HeartRateVariabilityRmssdRecord -> {
                payload.put("rmssdMillis", record.heartRateVariabilityMillis)
                payload.put("time", record.time.toString())
                record.time.toEpochMilli()
            }
            is CyclingPedalingCadenceRecord -> {
                payload.put("startTime", record.startTime.toString())
                payload.put("endTime", record.endTime.toString())
                payload.put(
                    "samples",
                    JSONArray().apply {
                        record.samples.forEach { sample ->
                            put(
                                JSONObject()
                                    .put("time", sample.time.toString())
                                    .put("revolutionsPerMinute", sample.revolutionsPerMinute),
                            )
                        }
                    },
                )
                record.endTime.toEpochMilli()
            }
            is FloorsClimbedRecord -> {
                payload.put("floors", record.floors)
                payload.put("startTime", record.startTime.toString())
                payload.put("endTime", record.endTime.toString())
                record.endTime.toEpochMilli()
            }
            is BodyFatRecord -> {
                payload.put("percent", record.percentage.value)
                payload.put("time", record.time.toString())
                record.time.toEpochMilli()
            }
            is LeanBodyMassRecord -> {
                payload.put("kilograms", record.mass.inKilograms)
                payload.put("time", record.time.toString())
                record.time.toEpochMilli()
            }
            is HydrationRecord -> {
                payload.put("liters", record.volume.inLiters)
                payload.put("startTime", record.startTime.toString())
                payload.put("endTime", record.endTime.toString())
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
