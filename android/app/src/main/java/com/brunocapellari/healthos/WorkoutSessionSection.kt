package com.brunocapellari.healthos

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.brunocapellari.healthos.data.WorkoutDraft
import com.brunocapellari.healthos.data.WorkoutDraftExercise
import com.brunocapellari.healthos.data.WorkoutDraftSet
import kotlinx.coroutines.delay
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import kotlin.math.ceil

private val SET_TYPES = listOf("warm_up", "working", "back_off", "drop", "amrap")

@Composable
fun WorkoutSessionSection(
    activeSessionId: String,
    plannedExercises: List<PlannedExerciseUi>,
    initialDraft: WorkoutDraft?,
    onSaveWorkoutDraft: (WorkoutDraft) -> Unit,
    onRecordSession: (String, Boolean, Int, Double?, String, JSONArray) -> Unit,
) {
    if (activeSessionId.isBlank()) {
        Text("Nenhum treino ativo. Gere o próximo bloco para iniciar.")
        return
    }

    val restored = initialDraft?.takeIf { it.sessionId == activeSessionId }
    val startedAt = remember(activeSessionId, restored?.startedAtEpochMillis) {
        restored?.startedAtEpochMillis ?: System.currentTimeMillis()
    }
    var nowEpochMillis by remember(activeSessionId) { mutableLongStateOf(System.currentTimeMillis()) }
    var sessionCompleted by remember(activeSessionId, restored?.updatedAtEpochMillis) {
        mutableStateOf(restored?.completed ?: true)
    }
    var sessionRpe by remember(activeSessionId, restored?.updatedAtEpochMillis) {
        mutableStateOf(restored?.rpe.orEmpty())
    }
    var notes by remember(activeSessionId, restored?.updatedAtEpochMillis) {
        mutableStateOf(restored?.notes.orEmpty())
    }
    var restDeadlineEpochMillis by remember(activeSessionId, restored?.updatedAtEpochMillis) {
        mutableStateOf(restored?.restDeadlineEpochMillis)
    }
    var restPausedRemainingSeconds by remember(activeSessionId, restored?.updatedAtEpochMillis) {
        mutableStateOf(restored?.restPausedRemainingSeconds)
    }
    var restExerciseId by remember(activeSessionId, restored?.updatedAtEpochMillis) {
        mutableStateOf(restored?.restExerciseId)
    }

    val exerciseState = remember(activeSessionId, plannedExercises, restored?.updatedAtEpochMillis) {
        mutableStateMapOf<String, WorkoutDraftExercise>().apply {
            val restoredByPlanned = restored?.exercises?.associateBy { it.plannedExerciseId }.orEmpty()
            plannedExercises.forEach { planned ->
                val saved = restoredByPlanned[planned.exerciseId]
                put(
                    planned.exerciseId,
                    saved ?: WorkoutDraftExercise(
                        plannedExerciseId = planned.exerciseId,
                        exerciseId = planned.exerciseId,
                        plannedSets = planned.plannedSets,
                        suggestedLoadKg = planned.suggestedLoadKg,
                        targetRir = planned.targetRir,
                        restSeconds = planned.restSeconds,
                        setType = planned.setType,
                        groupType = planned.groupType,
                        groupId = planned.groupId,
                        alternatives = planned.alternatives,
                        sets = List(planned.plannedSets) { index ->
                            WorkoutDraftSet(
                                setNumber = index + 1,
                                loadKg = planned.suggestedLoadKg?.toString().orEmpty(),
                                setType = planned.setType,
                            )
                        },
                    ),
                )
            }
        }
    }

    LaunchedEffect(activeSessionId) {
        while (true) {
            nowEpochMillis = System.currentTimeMillis()
            delay(1000)
        }
    }

    val restRemainingSeconds = when {
        restDeadlineEpochMillis != null -> ceil(
            ((restDeadlineEpochMillis ?: nowEpochMillis) - nowEpochMillis).coerceAtLeast(0) / 1000.0,
        ).toInt()
        restPausedRemainingSeconds != null -> restPausedRemainingSeconds ?: 0
        else -> 0
    }

    LaunchedEffect(restDeadlineEpochMillis, nowEpochMillis) {
        val deadline = restDeadlineEpochMillis
        if (deadline != null && deadline <= nowEpochMillis) {
            restDeadlineEpochMillis = null
            restPausedRemainingSeconds = null
            restExerciseId = null
        }
    }

    fun updateExercise(plannedId: String, transform: (WorkoutDraftExercise) -> WorkoutDraftExercise) {
        val current = exerciseState[plannedId] ?: return
        exerciseState[plannedId] = transform(current)
    }

    fun updateSet(
        plannedId: String,
        setIndex: Int,
        transform: (WorkoutDraftSet) -> WorkoutDraftSet,
    ) {
        updateExercise(plannedId) { exercise ->
            val updated = exercise.sets.toMutableList()
            updated[setIndex] = transform(updated[setIndex])
            exercise.copy(sets = updated)
        }
    }

    val exerciseSnapshot = exerciseState.toMap()
    val elapsedMinutes = ((nowEpochMillis - startedAt).coerceAtLeast(0) / 60_000L).toInt()

    LaunchedEffect(
        sessionCompleted,
        sessionRpe,
        notes,
        exerciseSnapshot,
        restDeadlineEpochMillis,
        restPausedRemainingSeconds,
        restExerciseId,
        elapsedMinutes,
    ) {
        delay(500)
        onSaveWorkoutDraft(
            WorkoutDraft(
                sessionId = activeSessionId,
                completed = sessionCompleted,
                duration = elapsedMinutes.toString(),
                rpe = sessionRpe,
                notes = notes,
                exercises = plannedExercises.mapNotNull { exerciseSnapshot[it.exerciseId] },
                startedAtEpochMillis = startedAt,
                restDeadlineEpochMillis = restDeadlineEpochMillis,
                restPausedRemainingSeconds = restPausedRemainingSeconds,
                restExerciseId = restExerciseId,
            ),
        )
    }

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Registrar treino realizado", style = MaterialTheme.typography.titleMedium)
        Text("Sessão: $activeSessionId")
        Text("Tempo decorrido: ${formatElapsed(nowEpochMillis - startedAt)}")

        if (restRemainingSeconds > 0) {
            Text(
                "Descanso${restExerciseId?.let { " — $it" }.orEmpty()}: ${restRemainingSeconds}s",
                style = MaterialTheme.typography.titleMedium,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = {
                        if (restDeadlineEpochMillis != null) {
                            restPausedRemainingSeconds = restRemainingSeconds
                            restDeadlineEpochMillis = null
                        } else if (restPausedRemainingSeconds != null) {
                            restDeadlineEpochMillis =
                                System.currentTimeMillis() + (restPausedRemainingSeconds ?: 0) * 1000L
                            restPausedRemainingSeconds = null
                        }
                    },
                ) {
                    Text(if (restDeadlineEpochMillis != null) "Pausar" else "Retomar")
                }
                Button(
                    onClick = {
                        if (restDeadlineEpochMillis != null) {
                            restDeadlineEpochMillis = (restDeadlineEpochMillis ?: nowEpochMillis) + 15_000L
                        } else {
                            restPausedRemainingSeconds = (restPausedRemainingSeconds ?: 0) + 15
                        }
                    },
                ) {
                    Text("+15s")
                }
                Button(
                    onClick = {
                        val reduced = (restRemainingSeconds - 15).coerceAtLeast(0)
                        if (reduced == 0) {
                            restDeadlineEpochMillis = null
                            restPausedRemainingSeconds = null
                            restExerciseId = null
                        } else if (restDeadlineEpochMillis != null) {
                            restDeadlineEpochMillis = System.currentTimeMillis() + reduced * 1000L
                        } else {
                            restPausedRemainingSeconds = reduced
                        }
                    },
                ) {
                    Text("-15s")
                }
                Button(
                    onClick = {
                        restDeadlineEpochMillis = null
                        restPausedRemainingSeconds = null
                        restExerciseId = null
                    },
                ) {
                    Text("Pular")
                }
            }
        }

        Column {
            Text("Sessão concluída")
            Checkbox(
                checked = sessionCompleted,
                onCheckedChange = { sessionCompleted = it },
            )
        }
        OutlinedTextField(
            value = sessionRpe,
            onValueChange = { sessionRpe = decimalInput(it, maxLength = 4) },
            label = { Text("RPE da sessão (0–10, opcional)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        plannedExercises.forEach { planned ->
            val exercise = exerciseState[planned.exerciseId] ?: return@forEach
            val groupLabel = when (exercise.groupType) {
                "superset" -> "superset ${exercise.groupId.orEmpty()}"
                "circuit" -> "circuito ${exercise.groupId.orEmpty()}"
                else -> ""
            }
            Text(
                buildString {
                    append(exercise.exerciseId)
                    if (exercise.exerciseId != exercise.plannedExerciseId) {
                        append(" (planejado: ${exercise.plannedExerciseId})")
                    }
                    if (groupLabel.isNotBlank()) append(" — $groupLabel")
                },
                style = MaterialTheme.typography.titleMedium,
            )
            if (exercise.alternatives.isNotEmpty()) {
                Button(
                    onClick = {
                        val candidates = listOf(exercise.plannedExerciseId) + exercise.alternatives
                        val currentIndex = candidates.indexOf(exercise.exerciseId).coerceAtLeast(0)
                        val nextId = candidates[(currentIndex + 1) % candidates.size]
                        updateExercise(planned.exerciseId) {
                            it.copy(
                                exerciseId = nextId,
                                substitutionReason = if (nextId == it.plannedExerciseId) {
                                    null
                                } else {
                                    "user_selected_environment_safe_alternative"
                                },
                            )
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Substituir exercício")
                }
            }

            exercise.sets.forEachIndexed { setIndex, set ->
                Text("Série ${set.setNumber} — ${set.setType}")
                Button(
                    onClick = {
                        val currentIndex = SET_TYPES.indexOf(set.setType).coerceAtLeast(0)
                        updateSet(planned.exerciseId, setIndex) {
                            it.copy(setType = SET_TYPES[(currentIndex + 1) % SET_TYPES.size])
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Tipo da série: ${set.setType}")
                }
                OutlinedTextField(
                    value = set.loadKg,
                    onValueChange = { value ->
                        updateSet(planned.exerciseId, setIndex) {
                            it.copy(loadKg = decimalInput(value, maxLength = 8))
                        }
                    },
                    label = { Text("Carga kg") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = set.reps,
                    onValueChange = { value ->
                        updateSet(planned.exerciseId, setIndex) {
                            it.copy(reps = integerInput(value, maxLength = 5))
                        }
                    },
                    label = { Text("Repetições") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = set.rir,
                    onValueChange = { value ->
                        updateSet(planned.exerciseId, setIndex) {
                            it.copy(rir = decimalInput(value, maxLength = 4))
                        }
                    },
                    label = { Text("RIR") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = set.rpe,
                    onValueChange = { value ->
                        updateSet(planned.exerciseId, setIndex) {
                            it.copy(rpe = decimalInput(value, maxLength = 4))
                        }
                    },
                    label = { Text("RPE da série") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = set.durationSeconds,
                    onValueChange = { value ->
                        updateSet(planned.exerciseId, setIndex) {
                            it.copy(durationSeconds = integerInput(value, maxLength = 6))
                        }
                    },
                    label = { Text("Duração (s), se aplicável") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = set.distanceM,
                    onValueChange = { value ->
                        updateSet(planned.exerciseId, setIndex) {
                            it.copy(distanceM = decimalInput(value, maxLength = 10))
                        }
                    },
                    label = { Text("Distância (m), se aplicável") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Checkbox(
                        checked = set.completed,
                        onCheckedChange = { checked ->
                            val completedAt = if (checked) System.currentTimeMillis() else null
                            updateSet(planned.exerciseId, setIndex) {
                                it.copy(
                                    completed = checked,
                                    completedAtEpochMillis = completedAt,
                                )
                            }
                            if (checked && (exercise.restSeconds ?: 0) > 0) {
                                restDeadlineEpochMillis =
                                    System.currentTimeMillis() + (exercise.restSeconds ?: 0) * 1000L
                                restPausedRemainingSeconds = null
                                restExerciseId = exercise.exerciseId
                            }
                        },
                    )
                    Text(if (set.completed) "Concluída" else "Marcar série como concluída")
                }
            }
        }

        OutlinedTextField(
            value = notes,
            onValueChange = { if (it.length <= 5000) notes = it },
            label = { Text("Observações") },
            modifier = Modifier.fillMaxWidth(),
        )

        Button(
            onClick = {
                val parsedRpe = sessionRpe.replace(',', '.').toDoubleOrNull()
                if (parsedRpe == null || parsedRpe in 0.0..10.0) {
                    onRecordSession(
                        activeSessionId,
                        sessionCompleted,
                        elapsedMinutes.coerceAtLeast(0),
                        parsedRpe,
                        notes,
                        buildExercisePayload(plannedExercises, exerciseState),
                    )
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Salvar e sincronizar treino")
        }
    }
}

private fun buildExercisePayload(
    plannedExercises: List<PlannedExerciseUi>,
    state: Map<String, WorkoutDraftExercise>,
): JSONArray {
    val payload = JSONArray()
    plannedExercises.forEach { planned ->
        val exercise = state[planned.exerciseId] ?: return@forEach
        val sets = JSONArray()
        exercise.sets
            .filter { it.completed || it.hasEnteredData() }
            .forEach { set ->
                sets.put(
                    JSONObject()
                        .put("set_number", set.setNumber)
                        .put("completed", set.completed)
                        .put(
                            "completed_at",
                            set.completedAtEpochMillis?.let { Instant.ofEpochMilli(it).toString() }
                                ?: JSONObject.NULL,
                        )
                        .put("reps", set.reps.toIntOrNull() ?: JSONObject.NULL)
                        .put("load_kg", set.loadKg.replace(',', '.').toDoubleOrNull() ?: JSONObject.NULL)
                        .put("rir", set.rir.replace(',', '.').toDoubleOrNull() ?: JSONObject.NULL)
                        .put("rpe", set.rpe.replace(',', '.').toDoubleOrNull() ?: JSONObject.NULL)
                        .put("duration_seconds", set.durationSeconds.toIntOrNull() ?: JSONObject.NULL)
                        .put("distance_m", set.distanceM.replace(',', '.').toDoubleOrNull() ?: JSONObject.NULL)
                        .put("set_type", set.setType),
                )
            }
        payload.put(
            JSONObject()
                .put("planned_exercise_id", exercise.plannedExerciseId)
                .put("exercise_id", exercise.exerciseId)
                .put("substitution_reason", exercise.substitutionReason ?: JSONObject.NULL)
                .put("sets", sets)
                .put("group_type", exercise.groupType ?: JSONObject.NULL)
                .put("group_id", exercise.groupId ?: JSONObject.NULL),
        )
    }
    return payload
}

private fun WorkoutDraftSet.hasEnteredData(): Boolean =
    loadKg.isNotBlank() ||
        reps.isNotBlank() ||
        rir.isNotBlank() ||
        rpe.isNotBlank() ||
        durationSeconds.isNotBlank() ||
        distanceM.isNotBlank()

private fun integerInput(value: String, maxLength: Int): String =
    value.filter(Char::isDigit).take(maxLength)

private fun decimalInput(value: String, maxLength: Int): String =
    value
        .filter { it.isDigit() || it == '.' || it == ',' }
        .take(maxLength)

private fun formatElapsed(elapsedMillis: Long): String {
    val totalSeconds = elapsedMillis.coerceAtLeast(0) / 1000L
    val hours = totalSeconds / 3600
    val minutes = (totalSeconds % 3600) / 60
    val seconds = totalSeconds % 60
    return if (hours > 0) {
        "%02d:%02d:%02d".format(hours, minutes, seconds)
    } else {
        "%02d:%02d".format(minutes, seconds)
    }
}
