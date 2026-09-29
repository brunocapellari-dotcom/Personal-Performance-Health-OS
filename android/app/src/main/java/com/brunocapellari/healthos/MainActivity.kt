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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.lifecycle.lifecycleScope
import com.brunocapellari.healthos.data.WorkoutDraft
import com.brunocapellari.healthos.data.WorkoutDraftExercise
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate

data class HealthPermissionStatus(
    val coreComplete: Boolean,
    val readableCount: Int,
    val totalCount: Int,
    val history: Boolean,
    val background: Boolean,
)

data class PlannedExerciseUi(
    val exerciseId: String,
    val plannedSets: Int,
    val suggestedLoadKg: Double?,
    val targetRir: Double,
    val restSeconds: Int? = null,
    val setType: String = "working",
    val groupType: String? = null,
    val groupId: String? = null,
    val alternatives: List<String> = emptyList(),
)

class MainActivity : ComponentActivity() {
    private val statusText = mutableStateOf("Inicializando")
    private val healthText = mutableStateOf("Health Connect não verificado")
    private val activeSessionId = mutableStateOf("")
    private val activeExercises = mutableStateOf<List<PlannedExerciseUi>>(emptyList())
    private val pairingTokenText = mutableStateOf("")
    private val nutritionText = mutableStateOf("")
    private val nutritionFoods = mutableStateOf<List<JSONObject>>(emptyList())
    private val dashboardText = mutableStateOf("Resumo diário ainda não carregado")
    private val workoutDraft = mutableStateOf<WorkoutDraft?>(null)

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
        restoreWorkoutDraft()
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
                            onPerformancePermissions = {
                                permissionsLauncher.launch(container.healthConnect.performanceReadPermissions())
                            },
                            onBodyPermissions = {
                                permissionsLauncher.launch(container.healthConnect.bodyCompositionReadPermissions())
                            },
                            onNutritionPermissions = {
                                permissionsLauncher.launch(container.healthConnect.nutritionReadPermissions())
                            },
                            onExtendedPermissions = {
                                permissionsLauncher.launch(container.healthConnect.extendedReadPermissions())
                            },
                            pairingToken = pairingTokenText.value,
                            onGeneratePairingToken = ::generatePairingToken,
                            onEnroll = ::enroll,
                            onSync = ::syncNow,
                            onSaveInitialSetup = ::saveInitialSetup,
                            nutritionResult = nutritionText.value,
                            nutritionFoods = nutritionFoods.value,
                            dashboardResult = dashboardText.value,
                            onRefreshDashboard = ::refreshDashboard,
                            onLookupBarcode = ::lookupFoodBarcode,
                            onSearchFoods = ::searchFoods,
                            onLogFood = ::logFood,
                            activeSessionId = activeSessionId.value,
                            plannedExercises = activeExercises.value,
                            initialDraft = workoutDraft.value,
                            onNextBlock = ::nextBlock,
                            onSaveWorkoutDraft = ::saveWorkoutDraft,
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
                val readable = container.healthConnect.readableTypes()
                HealthPermissionStatus(
                    coreComplete = container.healthConnect.hasCoreReadPermissions(),
                    readableCount = readable.size,
                    totalCount = com.brunocapellari.healthos.health.TrackedHealthType.entries.size,
                    history = container.healthConnect.hasHistoryReadPermission(),
                    background = container.healthConnect.hasBackgroundReadPermission(),
                )
            }
            healthText.value = when {
                status.readableCount == 0 -> "Nenhuma métrica do Health Connect autorizada"
                status.coreComplete ->
                    "Health Connect: ${status.readableCount}/${status.totalCount} métricas autorizadas; " +
                        "histórico ampliado: ${if (status.history) "sim" else "não"}; " +
                        "segundo plano: ${if (status.background) "sim" else "não"}"
                else ->
                    "Health Connect parcialmente autorizado: ${status.readableCount}/${status.totalCount} métricas"
            }
        }
    }

    private fun generatePairingToken() {
        lifecycleScope.launch {
            statusText.value = "Gerando token temporário para outro aparelho"
            runCatching {
                withContext(Dispatchers.IO) { container.repository.createOwnerPairingToken() }
            }.onSuccess { response ->
                pairingTokenText.value =
                    response.getString("token") + "\nValidade: " + response.getString("expires_at")
                statusText.value = "Token temporário gerado; use apenas no aparelho que será vinculado"
            }.onFailure {
                pairingTokenText.value = ""
                statusText.value = "Falha ao gerar token: ${it.message ?: "erro desconhecido"}"
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

    private fun saveInitialSetup(input: InitialSetupInput) {
        lifecycleScope.launch {
            statusText.value = "Salvando configuração inicial"
            runCatching {
                withContext(Dispatchers.IO) {
                    container.repository.saveInitialSetup(
                        goalDescription = input.goalDescription,
                        goalMetric = input.goalMetric,
                        goalPriority = input.goalPriority,
                        goalBaseline = input.goalBaseline,
                        goalTarget = input.goalTarget,
                        goalTargetDate = input.goalTargetDate,
                        environment = input.environment,
                        equipment = input.equipment,
                        spaceM2 = input.spaceM2,
                        fixationPoints = input.fixationPoints,
                        noiseLimit = input.noiseLimit,
                        surface = input.surface,
                        availableMinutes = input.availableMinutes,
                        loadOptionsKg = input.loadOptionsKg,
                        sleepHours = input.sleepHours,
                        sleepQuality = input.sleepQuality,
                        energy = input.energy,
                        fatigue = input.fatigue,
                        soreness = input.soreness,
                        stress = input.stress,
                        painFlag = input.painFlag,
                    )
                    container.repository.fullSync()
                }
            }.onSuccess {
                statusText.value = "Configuração inicial salva e sincronizada"
            }.onFailure {
                statusText.value = "Falha na configuração inicial: ${it.message ?: "erro desconhecido"}"
            }
        }
    }

    private fun lookupFoodBarcode(barcode: String) {
        lifecycleScope.launch {
            nutritionText.value = "Buscando produto..."
            runCatching {
                withContext(Dispatchers.IO) { container.repository.lookupFoodBarcode(barcode) }
            }.onSuccess { food ->
                nutritionFoods.value = listOf(food)
                nutritionText.value = formatFood(food)
            }.onFailure {
                nutritionFoods.value = emptyList()
                nutritionText.value = "Produto não encontrado ou fonte indisponível: ${it.message ?: "erro desconhecido"}"
            }
        }
    }

    private fun searchFoods(query: String) {
        lifecycleScope.launch {
            nutritionText.value = "Buscando alimentos..."
            runCatching {
                withContext(Dispatchers.IO) { container.repository.searchFoods(query) }
            }.onSuccess { response ->
                val foods = response.optJSONArray("foods") ?: JSONArray()
                nutritionFoods.value = List(minOf(foods.length(), 8)) { index -> foods.getJSONObject(index) }
                nutritionText.value = if (foods.length() == 0) {
                    "Nenhum alimento encontrado."
                } else {
                    buildString {
                        val limit = minOf(foods.length(), 8)
                        for (index in 0 until limit) {
                            if (index > 0) append("\n\n")
                            append(formatFood(foods.getJSONObject(index)))
                        }
                    }
                }
            }.onFailure {
                nutritionFoods.value = emptyList()
                nutritionText.value = "Busca de alimentos indisponível: ${it.message ?: "erro desconhecido"}"
            }
        }
    }

    private fun logFood(food: JSONObject, quantityG: Double, meal: String) {
        lifecycleScope.launch {
            statusText.value = "Registrando alimento consumido"
            runCatching {
                withContext(Dispatchers.IO) {
                    container.repository.recordNutritionEntry(food, quantityG, meal)
                    container.repository.fullSync()
                }
            }.onSuccess {
                statusText.value = "Alimento registrado e sincronizado"
                refreshDashboard()
            }.onFailure {
                statusText.value = "Falha ao registrar alimento: ${it.message ?: "erro desconhecido"}"
            }
        }
    }

    private fun formatFood(food: JSONObject): String {
        fun nutrient(label: String, key: String, unit: String): String? =
            if (food.isNull(key) || !food.has(key)) null else "$label: ${food.optDouble(key)} $unit/100 g"

        return buildString {
            append(food.optString("name", "Alimento"))
            append("\nFonte: ")
            append(food.optString("source", "desconhecida"))
            listOfNotNull(
                nutrient("Energia", "energy_kcal_per_100g", "kcal"),
                nutrient("Proteína", "protein_g_per_100g", "g"),
                nutrient("Carboidrato", "carbohydrate_g_per_100g", "g"),
                nutrient("Gordura", "fat_g_per_100g", "g"),
            ).forEach {
                append("\n")
                append(it)
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
                refreshDashboard()
            }.onFailure {
                statusText.value = "Falha de sync: ${it.message ?: "erro desconhecido"}"
            }
        }
    }

    private fun restoreWorkoutDraft() {
        lifecycleScope.launch {
            runCatching {
                withContext(Dispatchers.IO) { container.repository.loadLatestWorkoutDraft() }
            }.onSuccess { draft ->
                if (draft != null) {
                    workoutDraft.value = draft
                    activeSessionId.value = draft.sessionId
                    activeExercises.value = draft.exercises.map { exercise ->
                        PlannedExerciseUi(
                            exerciseId = exercise.plannedExerciseId,
                            plannedSets = exercise.plannedSets,
                            suggestedLoadKg = exercise.suggestedLoadKg,
                            targetRir = exercise.targetRir,
                            restSeconds = exercise.restSeconds,
                            setType = exercise.setType,
                            groupType = exercise.groupType,
                            groupId = exercise.groupId,
                            alternatives = exercise.alternatives,
                        )
                    }
                    statusText.value = "Treino em andamento restaurado do armazenamento local"
                }
            }.onFailure {
                statusText.value = "Não foi possível restaurar o treino em andamento"
            }
        }
    }

    private fun saveWorkoutDraft(draft: WorkoutDraft) {
        lifecycleScope.launch {
            runCatching {
                withContext(Dispatchers.IO) { container.repository.saveWorkoutDraft(draft) }
            }.onFailure {
                statusText.value = "Falha ao salvar rascunho local do treino"
            }
        }
    }

    private fun refreshDashboard() {
        lifecycleScope.launch {
            runCatching {
                withContext(Dispatchers.IO) { container.repository.loadDashboard(LocalDate.now()) }
            }.onSuccess { response ->
                dashboardText.value = formatDashboard(response)
            }.onFailure {
                dashboardText.value = "Resumo diário indisponível: ${it.message ?: "erro desconhecido"}"
            }
        }
    }

    private fun formatDashboard(response: JSONObject): String {
        fun display(obj: JSONObject, key: String): String =
            if (!obj.has(key) || obj.isNull(key)) "—" else obj.get(key).toString()

        val training = response.optJSONObject("training") ?: JSONObject()
        val recovery = response.optJSONObject("recovery") ?: JSONObject()
        val activity = response.optJSONObject("activity") ?: JSONObject()
        val body = response.optJSONObject("body") ?: JSONObject()
        val nutrition = response.optJSONObject("nutrition") ?: JSONObject()
        val reconciliation = response.optJSONObject("reconciliation") ?: JSONObject()
        val alerts = response.optJSONArray("alerts") ?: JSONArray()

        return buildString {
            append("Treino: ")
            append(display(training, "focus"))
            append(" • ")
            append(display(training, "duration_minutes"))
            append(" min")
            append("\nRecuperação: ")
            append(display(recovery, "readiness_score"))
            append(" • ")
            append(display(recovery, "action"))
            append("\nSemana: ")
            append(display(activity, "sessions"))
            append(" sessões • ")
            append(display(activity, "total_minutes"))
            append(" min")
            append("\nPassos hoje: ")
            append(display(activity, "steps_today"))
            append("\nPeso: ")
            append(display(body, "latest_weight_kg"))
            append(" kg • média móvel ")
            append(display(body, "weight_rolling_average_kg"))
            append(" kg")
            append("\nNutrição: ")
            append(display(nutrition, "energy_kcal"))
            append(" kcal • proteína ")
            append(display(nutrition, "protein_g"))
            append(" g • fibra ")
            append(display(nutrition, "fiber_g"))
            append(" g")
            if (!nutrition.isNull("target_energy_kcal")) {
                append(" • meta ")
                append(display(nutrition, "target_energy_kcal"))
                append(" kcal")
            }
            append("\nHealth Connect: ")
            append(display(reconciliation, "match_count"))
            append(" treino(s) reconciliado(s), classificação ")
            append(display(reconciliation, "evidence_kind"))
            if (alerts.length() > 0) {
                append("\nAlertas:")
                for (index in 0 until alerts.length()) {
                    append("\n• ")
                    append(alerts.getString(index))
                }
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
                    container.repository.clearWorkoutDraft(plannedSessionId)
                }
            }.onSuccess {
                workoutDraft.value = null
                activeSessionId.value = ""
                activeExercises.value = emptyList()
                statusText.value = "Treino realizado registrado e sincronizado"
                refreshDashboard()
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
                                restSeconds = if (item.isNull("rest_seconds")) null else item.getInt("rest_seconds"),
                                setType = item.optString("set_type", "working"),
                                groupType = item.optString("group_type").takeIf(String::isNotBlank),
                                groupId = item.optString("group_id").takeIf(String::isNotBlank),
                                alternatives = item.optJSONArray("alternatives")?.let { array ->
                                    List(array.length()) { alternativeIndex -> array.getString(alternativeIndex) }
                                }.orEmpty(),
                            )
                        }
                        val draft = WorkoutDraft(
                            sessionId = activeSessionId.value,
                            exercises = activeExercises.value.map { exercise ->
                                WorkoutDraftExercise(
                                    plannedExerciseId = exercise.exerciseId,
                                    exerciseId = exercise.exerciseId,
                                    plannedSets = exercise.plannedSets,
                                    suggestedLoadKg = exercise.suggestedLoadKg,
                                    targetRir = exercise.targetRir,
                                    restSeconds = exercise.restSeconds,
                                    setType = exercise.setType,
                                    groupType = exercise.groupType,
                                    groupId = exercise.groupId,
                                    alternatives = exercise.alternatives,
                                    loadKg = exercise.suggestedLoadKg?.toString() ?: "",
                                )
                            },
                        )
                        workoutDraft.value = draft
                        saveWorkoutDraft(draft)
                    } else {
                        activeSessionId.value = ""
                        activeExercises.value = emptyList()
                    }
                    statusText.value =
                        "Novo bloco auditado e aprovado (${response.getString("snapshot_id").take(8)}); " +
                        "${sessions.length()} sessões planejadas"
                    refreshDashboard()
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
    initialDraft: WorkoutDraft?,
    pairingToken: String,
    onCorePermissions: () -> Unit,
    onPerformancePermissions: () -> Unit,
    onBodyPermissions: () -> Unit,
    onNutritionPermissions: () -> Unit,
    onExtendedPermissions: () -> Unit,
    onGeneratePairingToken: () -> Unit,
    onEnroll: (String) -> Unit,
    onSync: () -> Unit,
    onSaveInitialSetup: (InitialSetupInput) -> Unit,
    nutritionResult: String,
    nutritionFoods: List<JSONObject>,
    dashboardResult: String,
    onRefreshDashboard: () -> Unit,
    onLookupBarcode: (String) -> Unit,
    onSearchFoods: (String) -> Unit,
    onLogFood: (JSONObject, Double, String) -> Unit,
    onNextBlock: () -> Unit,
    onSaveWorkoutDraft: (WorkoutDraft) -> Unit,
    onRecordSession: (String, Boolean, Int, Double?, String, JSONArray) -> Unit,
) {
    var bootstrapToken by remember { mutableStateOf("") }
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Personal Performance & Health OS", style = MaterialTheme.typography.headlineSmall)
        Text("Resumo de hoje", style = MaterialTheme.typography.titleMedium)
        Text(dashboardResult, style = MaterialTheme.typography.bodyMedium)
        Button(onClick = onRefreshDashboard, modifier = Modifier.fillMaxWidth()) {
            Text("Atualizar resumo")
        }

        Text(healthStatus)
        Button(onClick = onCorePermissions, modifier = Modifier.fillMaxWidth()) {
            Text("Autorizar métricas básicas do Health Connect")
        }
        Button(onClick = onPerformancePermissions, modifier = Modifier.fillMaxWidth()) {
            Text("Autorizar métricas de performance (opcional)")
        }
        Button(onClick = onBodyPermissions, modifier = Modifier.fillMaxWidth()) {
            Text("Autorizar composição corporal (opcional)")
        }
        Button(onClick = onNutritionPermissions, modifier = Modifier.fillMaxWidth()) {
            Text("Autorizar hidratação (opcional)")
        }
        Button(onClick = onExtendedPermissions, modifier = Modifier.fillMaxWidth()) {
            Text("Autorizar histórico ampliado e segundo plano (opcional)")
        }

        Button(onClick = onGeneratePairingToken, modifier = Modifier.fillMaxWidth()) {
            Text("Gerar token temporário para outro aparelho")
        }
        if (pairingToken.isNotBlank()) {
            Text(pairingToken, style = MaterialTheme.typography.bodyMedium)
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

        InitialSetupSection(onSave = onSaveInitialSetup)
        NutritionBarcodeSection(
            resultText = nutritionResult,
            foods = nutritionFoods,
            onLookupBarcode = onLookupBarcode,
            onSearchFoods = onSearchFoods,
            onLogFood = onLogFood,
        )
        Button(onClick = onNextBlock, modifier = Modifier.fillMaxWidth()) {
            Text("Monta meu próximo bloco")
        }

        WorkoutSessionSection(
            activeSessionId = activeSessionId,
            plannedExercises = plannedExercises,
            initialDraft = initialDraft,
            onSaveWorkoutDraft = onSaveWorkoutDraft,
            onRecordSession = onRecordSession,
        )
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
