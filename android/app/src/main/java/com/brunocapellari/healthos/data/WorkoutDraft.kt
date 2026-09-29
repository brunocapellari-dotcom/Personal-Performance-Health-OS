package com.brunocapellari.healthos.data

import org.json.JSONArray
import org.json.JSONObject

data class WorkoutDraftExercise(
    val exerciseId: String,
    val plannedSets: Int,
    val suggestedLoadKg: Double?,
    val targetRir: Double,
    val loadKg: String = "",
    val repsCsv: String = "",
    val rirCsv: String = "",
)

data class WorkoutDraft(
    val sessionId: String,
    val completed: Boolean = true,
    val duration: String = "",
    val rpe: String = "",
    val notes: String = "",
    val exercises: List<WorkoutDraftExercise> = emptyList(),
    val updatedAtEpochMillis: Long = System.currentTimeMillis(),
) {
    fun toJson(): String {
        val exerciseArray = JSONArray()
        exercises.forEach { exercise ->
            exerciseArray.put(
                JSONObject()
                    .put("exercise_id", exercise.exerciseId)
                    .put("planned_sets", exercise.plannedSets)
                    .put("suggested_load_kg", exercise.suggestedLoadKg ?: JSONObject.NULL)
                    .put("target_rir", exercise.targetRir)
                    .put("load_kg", exercise.loadKg)
                    .put("reps_csv", exercise.repsCsv)
                    .put("rir_csv", exercise.rirCsv),
            )
        }
        return JSONObject()
            .put("session_id", sessionId)
            .put("completed", completed)
            .put("duration", duration)
            .put("rpe", rpe)
            .put("notes", notes)
            .put("exercises", exerciseArray)
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
                    add(
                        WorkoutDraftExercise(
                            exerciseId = exercise.getString("exercise_id"),
                            plannedSets = exercise.getInt("planned_sets"),
                            suggestedLoadKg = if (exercise.isNull("suggested_load_kg")) null else exercise.getDouble("suggested_load_kg"),
                            targetRir = exercise.getDouble("target_rir"),
                            loadKg = exercise.optString("load_kg", ""),
                            repsCsv = exercise.optString("reps_csv", ""),
                            rirCsv = exercise.optString("rir_csv", ""),
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
                updatedAtEpochMillis = json.optLong("updated_at_epoch_millis", 0L),
            )
        }
    }
}
