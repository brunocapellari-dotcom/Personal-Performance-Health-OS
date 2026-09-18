package com.brunocapellari.healthos

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

data class PlannedExerciseUi(
    val exerciseId: String,
    val plannedSets: Int,
    val suggestedLoadKg: Double?,
    val targetRir: Double,
)

data class ExerciseLogValues(
    val loadKg: String = "",
    val repsCsv: String = "",
    val rirCsv: String = "",
)

class MainActivity : ComponentActivity() {
    private val statusText = mutableStateOf("Inicializando")
    private val healthText = mutableStateOf("Health Connect não verificado")
    private val activeSessionId = mutableStateOf("")
    private val activeExercises = mutableStateOf<List<PlannedExerciseUi>>(emptyList())

    private val permissionsLauncher = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract(),
    ) { granted ->
        healthText.value = if (granted.isEmpty()) {
            "Permissões não concedidas"
        } else {
            "Permissões atualizadas"
        }
        refreshHealthStatus()
    }

    private val container: AppContainer
        get() = (application as HealthOsApplication).container

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        refreshHealthStatus()
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    if (intent?.action == "androidx.health.ACTION_SHOW_PERMISSIONS_RATIONALE" ||
                        intent?.action == "android.intent.action.VIEW_PERMISSION_USAGE"
                    ) {
                        PrivacyRationale()
                    } else {
                        Dashboard(
                            healthStatus = healthText.value,
                            operationStatus = statusText.value,
                            onCorePermissions = {
                                permissionsLauncher.launch(container.healthConnect.readPermissions())
                            },
                            onExtendedPermissions = {
                                permissionsLauncher.launch(container.healthConnect.extendedReadPermissions())
                            },
                            onEnroll = ::enroll,
                            onSync = ::syncNow,
                            activeSessionId = activeSessionId.value,
                            plannedExercises = activeExercises.value,
                            onNextBlock = ::nextBlock,
                            onRecordSession = ::recordSession,
                        )
                    }
                }
            }
        }
    }

    private fun refreshHealthStatus() {
        lifecycleScope.launch {
            val sdk = container.healthConnect.sdkStatus()
            if (sdk != HealthConnectClient.SDK_AVAILABLE) {
                healthText.value = "Health Connect indisponível neste dispositivo"
                return@launch
            }
            val status = withContext(Dispatchers.IO) {
                Triple(
                    container.healthConnect.hasCoreReadPermissions(),
                    container.healthConnect.hasHistoryReadPermission(),
                    container.healthConnect.hasBackgroundReadPermission(),
                )
            }
            healthText.value = if (status.first) {
                "Health Connect autorizado; histórico ampliado: " +
                    (if (status.second) "sim" else "não") +
                    "; leitura em segundo plano: " +
                    (if (status.third) "sim" else "não")
            } else {
                "Permissões básicas do Health Connect pendentes"
            }
        }
    }

    private fun enroll(bootstrapToken: String) {
        if (bootstrapToken.isBlank()) {
            statusText.value = "Informe o token temporário de vinculação"
            return
        }
        lifecycleScope.launch {
            statusText.value = "Vinculando dispositivo"
            runCatching {
                withContext(Dispatchers.IO) { container.repository.enroll(bootstrapToken) }
            }.onSuccess {
                statusText.value = "Dispositivo vinculado"
            }.onFailure {
                statusText.value = "Falha ao vincular dispositivo: ${it.message ?: "erro desconhecido"}"
            }
        }
    }

    private fun syncNow() {
        lifecycleScope.launch {
            statusText.value = "Sincronizando"
            runCatching {
                withContext(Dispatchers.IO) { container.repository.fullSync() }
            }.onSuccess { summary ->
                val healthNote = if (summary.healthIngestionSkipped) {
                    "; Health Connect não ingerido por falta de permissão"
                } else {
                    "; ${summary.healthEventsStaged} eventos de saúde processados"
                }
                statusText.value =
                    "Sync concluído: ${summary.pushed} enviados, ${summary.pulled} recebidos, " +
                    "${summary.conflicts} conflitos$healthNote"
                refreshHealthStatus()
            }.onFailure {
                statusText.value = "Falha de sync: ${it.message ?: "erro desconhecido"}"
            }
        }
    }

    private fun recordSession(
        plannedSessionId: String,
        completed: Boolean,
        durationMinutes: Int,
        rpe: Double?,
        notes: String,
        exercises: JSONArray,
    ) {
        lifecycleScope.launch {
            statusText.value = "Registrando treino realizado"
            runCatching {
                withContext(Dispatchers.IO) {
                    container.repository.recordPerformedSession(
                        plannedSessionId = plannedSessionId,
                        completed = completed,
                        durationMinutes = durationMinutes,
                        rpe = rpe,
                        notes = notes,
                        exercises = exercises,
                    )
                    container.repository.fullSync()
                }
            }.onSuccess {
                statusText.value = "Treino realizado registrado e sincronizado"
            }.onFailure {
                statusText.value = "Falha ao registrar treino: ${it.message ?: "erro desconhecido"}"
            }
        }
    }

    private fun nextBlock() {
        lifecycleScope.launch {
            statusText.value = "Montando próximo bloco"
            runCatching {
                withContext(Dispatchers.IO) { container.nextBlock.generate() }
            }.onSuccess { response ->
                val passed = response.getJSONObject("audit").getBoolean("passed")
                if (passed) {
                    val sessions = response.getJSONObject("plan").getJSONArray("sessions")
                    if (sessions.length() > 0) {
                        val firstSession = sessions.getJSONObject(0)
                        activeSessionId.value = firstSession.getString("session_id")
                        val prescriptions = firstSession.getJSONArray("prescriptions")
                        activeExercises.value = List(prescriptions.length()) { index ->
                            val item = prescriptions.getJSONObject(index)
                            PlannedExerciseUi(
                                exerciseId = item.getString("exercise_id"),
                                plannedSets = item.getInt("sets"),
                                suggestedLoadKg = if (item.isNull("load_kg")) null else item.getDouble("load_kg"),
                                targetRir = item.getDouble("target_rir"),
                            )
                        }
                    } else {
                        activeSessionId.value = ""
                        activeExercises.value = emptyList()
                    }
                    statusText.value =
                        "Novo bloco auditado e aprovado (${response.getString("snapshot_id").take(8)}); " +
                        "${sessions.length()} sessões planejadas"
                } else {
                    statusText.value = "Bloco rejeitado pela auditoria"
                }
            }.onFailure {
                statusText.value = "Não foi possível montar o bloco: ${it.message ?: "erro desconhecido"}"
            }
        }
    }
}

@Composable
private fun Dashboard(
    healthStatus: String,
    operationStatus: String,
    activeSessionId: String,
    plannedExercises: List<PlannedExerciseUi>,
    onCorePermissions: () -> Unit,
    onExtendedPermissions: () -> Unit,
    onEnroll: (String) -> Unit,
    onSync: () -> Unit,
    onNextBlock: () -> Unit,
    onRecordSession: (String, Boolean, Int, Double?, String, JSONArray) -> Unit,
) {
    var bootstrapToken by remember { mutableStateOf("") }
    var sessionId by remember(activeSessionId) { mutableStateOf(activeSessionId) }
    var completed by remember { mutableStateOf(true) }
    var duration by remember { mutableStateOf("") }
    var rpe by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    val exerciseLogs = remember(activeSessionId, plannedExercises) {
        mutableStateMapOf<String, ExerciseLogValues>().apply {
            plannedExercises.forEach { exercise ->
                put(
                    exercise.exerciseId,
                    ExerciseLogValues(
                        loadKg = exercise.suggestedLoadKg?.toString() ?: "",
                    ),
                )
            }
        }
    }
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Personal Performance & Health OS", style = MaterialTheme.typography.headlineSmall)
        Text(healthStatus)
        Button(onClick = onCorePermissions, modifier = Modifier.fillMaxWidth()) {
            Text("Autorizar leitura básica do Health Connect")
        }
        Button(onClick = onExtendedPermissions, modifier = Modifier.fillMaxWidth()) {
            Text("Autorizar histórico e segundo plano (opcional)")
        }
        OutlinedTextField(
            value = bootstrapToken,
            onValueChange = { bootstrapToken = it },
            label = { Text("Token temporário de vinculação") },
            visualTransformation = PasswordVisualTransformation(),
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = {
                onEnroll(bootstrapToken)
                bootstrapToken = ""
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Vincular este aparelho")
        }
        Button(onClick = onSync, modifier = Modifier.fillMaxWidth()) {
            Text("Sincronizar agora")
        }
        Button(onClick = onNextBlock, modifier = Modifier.fillMaxWidth()) {
            Text("Monta meu próximo bloco")
        }

        Text("Registrar treino realizado", style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(
            value = sessionId,
            onValueChange = { sessionId = it },
            label = { Text("ID da sessão planejada") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Column {
            Text("Sessão concluída")
            Checkbox(checked = completed, onCheckedChange = { completed = it })
        }
        OutlinedTextField(
            value = duration,
            onValueChange = { duration = it.filter { char -> char.isDigit() } },
            label = { Text("Duração em minutos") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = rpe,
            onValueChange = { value ->
                rpe = value.filter { char -> char.isDigit() || char == '.' || char == ',' }
            },
            label = { Text("RPE da sessão (0–10, opcional)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        plannedExercises.forEach { exercise ->
            val values = exerciseLogs[exercise.exerciseId] ?: ExerciseLogValues()
            Text(
                "${exercise.exerciseId} — ${exercise.plannedSets} séries; RIR alvo ${exercise.targetRir}",
                style = MaterialTheme.typography.bodyMedium,
            )
            OutlinedTextField(
                value = values.loadKg,
                onValueChange = { value ->
                    exerciseLogs[exercise.exerciseId] = values.copy(
                        loadKg = value.filter { char -> char.isDigit() || char == '.' || char == ',' },
                    )
                },
                label = { Text("Carga kg (vazio para peso corporal)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = values.repsCsv,
                onValueChange = { value ->
                    exerciseLogs[exercise.exerciseId] = values.copy(
                        repsCsv = value.filter { char -> char.isDigit() || char == ',' || char == ' ' },
                    )
                },
                label = { Text("Repetições por série, ex.: 12,12,10") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = values.rirCsv,
                onValueChange = { value ->
                    exerciseLogs[exercise.exerciseId] = values.copy(
                        rirCsv = value.filter { char ->
                            char.isDigit() || char == ',' || char == '.' || char == ' '
                        },
                    )
                },
                label = { Text("RIR por série, ex.: 3,2,2") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
        }

        OutlinedTextField(
            value = notes,
            onValueChange = { if (it.length <= 5000) notes = it },
            label = { Text("Observações") },
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = {
                val parsedDuration = duration.toIntOrNull()
                val parsedRpe = rpe.replace(',', '.').toDoubleOrNull()
                if (
                    sessionId.isNotBlank() &&
                    parsedDuration != null &&
                    (parsedRpe == null || parsedRpe in 0.0..10.0)
                ) {
                    val exercisePayload = JSONArray()
                    plannedExercises.forEach { exercise ->
                        val values = exerciseLogs[exercise.exerciseId] ?: ExerciseLogValues()
                        val reps = values.repsCsv.split(',')
                            .mapNotNull { item -> item.trim().toIntOrNull() }
                        val rirs = values.rirCsv.split(',')
                            .mapNotNull { item -> item.trim().replace(',', '.').toDoubleOrNull() }
                        val load = values.loadKg.replace(',', '.').toDoubleOrNull()
                        val sets = JSONArray()
                        reps.forEachIndexed { index, repetitions ->
                            sets.put(
                                JSONObject()
                                    .put("set_number", index + 1)
                                    .put("reps", repetitions)
                                    .put("load_kg", load ?: JSONObject.NULL)
                                    .put("rir", rirs.getOrNull(index) ?: JSONObject.NULL),
                            )
                        }
                        exercisePayload.put(
                            JSONObject()
                                .put("exercise_id", exercise.exerciseId)
                                .put("sets", sets),
                        )
                    }
                    onRecordSession(sessionId, completed, parsedDuration, parsedRpe, notes, exercisePayload)
                    duration = ""
                    rpe = ""
                    notes = ""
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Salvar e sincronizar treino")
        }
        Text(operationStatus, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun PrivacyRationale() {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Privacidade do Health OS", style = MaterialTheme.typography.headlineSmall)
        Text(
            "O Health OS lê apenas os tipos de dados que você autorizar para adaptar treino, recuperação e nutrição. " +
                "Os dados locais ficam em banco criptografado e não são compartilhados com anunciantes. Você pode " +
                "revogar as permissões do Health Connect a qualquer momento.",
        )
    }
}
