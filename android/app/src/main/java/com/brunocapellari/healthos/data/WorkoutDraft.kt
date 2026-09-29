package com.brunocapellari.healthos.data

import org.json.JSONArray
import org.json.JSONObject

data class WorkoutDraftSet(
    val setNumber: Int,
    val completed: Boolean = false,
    val completedAtEpochMillis: Long? = null,
    val loadKg: String = "",
    val reps: String = "",
    val rir: String = "",
    val rpe: String = "",
    val durationSeconds: String = "",
    val distanceM: String = "",
    val setType: String = "working",
)

data class WorkoutDraftExercise(
    val plannedExerciseId: String,
    val exerciseId: String,
    val plannedSets: Int,
    val suggestedLoadKg: Double?,
    val targetRir: Double,
    val restSeconds: Int? = null,
    val setType: String = "working",
    val groupType: String? = null,
    val groupId: String? = null,
    val alternatives: List<String> = emptyList(),
    val substitutionReason: String? = null,
    val sets: List<WorkoutDraftSet> = emptyList(),
)

data class WorkoutDraft(
    val sessionId: String,
    val completed: Boolean = true,
    val duration: String = "",
    val rpe: String = "",
    val notes: String = "",
    val exercises: List<WorkoutDraftExercise> = emptyList(),
    val startedAtEpochMillis: Long = System.currentTimeMillis(),
    val restDeadlineEpochMillis: Long? = null,
    val restExerciseId: String? = null,
    val updatedAtEpochMillis: Long = System.currentTimeMillis(),
) {
    fun toJson(): String {
        val exerciseArray = JSONArray()
        exercises.forEach { exercise ->
            exerciseArray.put(
                JSONObject()
                    .put("planned_exercise_id", exercise.plannedExerciseId)
                    .put("exercise_id", exercise.exerciseId)
                    .put("planned_sets", exercise.plannedSets)
                    .put("suggested_load_kg", exercise.suggestedLoadKg ?: JSONObject.NULL)
                    .put("target_rir", exercise.targetRir)
                    .put("rest_seconds", exercise.restSeconds ?: JSONObject.NULL)
                    .put("set_type", exercise.setType)
                    .put("group_type", exercise.groupType ?: JSONObject.NULL)
                    .put("group_id", exercise.groupId ?: JSONObject.NULL)
                    .put("alternatives", JSONArray(exercise.alternatives))
                    .put("substitution_reason", exercise.substitutionReason ?: JSONObject.NULL)
                    .put(
                        "sets",
                        JSONArray().apply {
                            exercise.sets.forEach { set ->
                                put(
                                    JSONObject()
                                        .put("set_number", set.setNumber)
                                        .put("completed", set.completed)
                                        .put(
                                            "completed_at_epoch_millis",
                                            set.completedAtEpochMillis ?: JSONObject.NULL,
                                        )
                                        .put("load_kg", set.loadKg)
                                        .put("reps", set.reps)
                                        .put("rir", set.rir)
                                        .put("rpe", set.rpe)
                                        .put("duration_seconds", set.durationSeconds)
                                        .put("distance_m", set.distanceM)
                                        .put("set_type", set.setType),
                                )
                            }
                        },
                    ),
            )
        }
        return JSONObject()
            .put("session_id", sessionId)
            .put("completed", completed)
            .put("duration", duration)
            .put("rpe", rpe)
            .put("notes", notes)
            .put("exercises", exerciseArray)
            .put("started_at_epoch_millis", startedAtEpochMillis)
            .put("rest_deadline_epoch_millis", restDeadlineEpochMillis ?: JSONObject.NULL)
            .put("rest_exercise_id", restExerciseId ?: JSONObject.NULL)
            .put("updated_at_epoch_millis", updatedAtEpochMillis)
            .toString()
    }

    companion object {
        fun fromJson(raw: String): WorkoutDraft {
            val json = JSONObject(raw)
            val exerciseArray = json.optJSONArray("exercises") ?: JSONArray()
            val exercises = buildList {
                for (index in 0 until exerciseArray.length()) {
                    val exercise = exerciseArray.getJSONObject(index)
                    val currentExerciseId = exercise.getString("exercise_id")
                    val alternatives = exercise.optJSONArray("alternatives") ?: JSONArray()
                    val plannedSets = exercise.getInt("planned_sets")
                    val defaultSetType = exercise.optString("set_type", "working")
                    add(
                        WorkoutDraftExercise(
                            plannedExerciseId = exercise.optString("planned_exercise_id", currentExerciseId),
                            exerciseId = currentExerciseId,
                            plannedSets = plannedSets,
                            suggestedLoadKg = exercise.optNullableDouble("suggested_load_kg"),
                            targetRir = exercise.getDouble("target_rir"),
                            restSeconds = exercise.optNullableInt("rest_seconds"),
                            setType = defaultSetType,
                            groupType = exercise.optNullableString("group_type"),
                            groupId = exercise.optNullableString("group_id"),
                            alternatives = List(alternatives.length()) {
                                alternativeIndex -> alternatives.getString(alternativeIndex)
                            },
                            substitutionReason = exercise.optNullableString("substitution_reason"),
                            sets = parseSets(exercise, plannedSets, defaultSetType),
                        ),
                    )
                }
            }
            return WorkoutDraft(
                sessionId = json.getString("session_id"),
                completed = json.optBoolean("completed", true),
                duration = json.optString("duration", ""),
                rpe = json.optString("rpe", ""),
                notes = json.optString("notes", ""),
                exercises = exercises,
                startedAtEpochMillis = json.optLong(
                    "started_at_epoch_millis",
                    json.optLong("updated_at_epoch_millis", System.currentTimeMillis()),
                ),
                restDeadlineEpochMillis = json.optNullableLong("rest_deadline_epoch_millis"),
                restExerciseId = json.optNullableString("rest_exercise_id"),
                updatedAtEpochMillis = json.optLong("updated_at_epoch_millis", 0L),
            )
        }

        private fun parseSets(
            exercise: JSONObject,
            plannedSets: Int,
            defaultSetType: String,
        ): List<WorkoutDraftSet> {
            val setArray = exercise.optJSONArray("sets")
            if (setArray != null) {
                return List(setArray.length()) { index ->
                    val set = setArray.getJSONObject(index)
                    WorkoutDraftSet(
                        setNumber = set.optInt("set_number", index + 1),
                        completed = set.optBoolean("completed", false),
                        completedAtEpochMillis = set.optNullableLong("completed_at_epoch_millis"),
                        loadKg = set.optString("load_kg", ""),
                        reps = set.optString("reps", ""),
                        rir = set.optString("rir", ""),
                        rpe = set.optString("rpe", ""),
                        durationSeconds = set.optString("duration_seconds", ""),
                        distanceM = set.optString("distance_m", ""),
                        setType = set.optString("set_type", defaultSetType),
                    )
                }
            }

            // Backward-compatible migration from the original CSV draft format.
            val load = exercise.optString("load_kg", "")
            val reps = exercise.optString("reps_csv", "").split(',').map(String::trim)
            val rirs = exercise.optString("rir_csv", "").split(',').map(String::trim)
            return List(plannedSets) { index ->
                WorkoutDraftSet(
                    setNumber = index + 1,
                    loadKg = load,
                    reps = reps.getOrNull(index).orEmpty(),
                    rir = rirs.getOrNull(index).orEmpty(),
                    setType = defaultSetType,
                )
            }
        }

        private fun JSONObject.optNullableString(key: String): String? =
            if (!has(key) || isNull(key)) null else optString(key).takeIf(String::isNotBlank)

        private fun JSONObject.optNullableDouble(key: String): Double? =
            if (!has(key) || isNull(key)) null else getDouble(key)

        private fun JSONObject.optNullableInt(key: String): Int? =
            if (!has(key) || isNull(key)) null else getInt(key)

        private fun JSONObject.optNullableLong(key: String): Long? =
            if (!has(key) || isNull(key)) null else getLong(key)
    }
}
