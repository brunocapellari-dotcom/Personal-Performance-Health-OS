package com.brunocapellari.healthos

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import java.time.LocalDate

data class InitialSetupInput(
    val goalDescription: String,
    val goalMetric: String,
    val goalPriority: Int,
    val goalBaseline: Double?,
    val goalTarget: Double?,
    val goalTargetDate: LocalDate?,
    val environment: String,
    val equipment: List<String>,
    val spaceM2: Double,
    val fixationPoints: List<String>,
    val noiseLimit: String,
    val surface: String,
    val availableMinutes: Int,
    val loadOptionsKg: List<Double>,
    val sleepHours: Double,
    val sleepQuality: Int,
    val energy: Int,
    val fatigue: Int,
    val soreness: Int,
    val stress: Int,
    val painFlag: Boolean,
)

@Composable
fun InitialSetupSection(
    onSave: (InitialSetupInput) -> Unit,
) {
    var goalDescription by remember { mutableStateOf("") }
    var goalMetric by remember { mutableStateOf("") }
    var goalPriority by remember { mutableStateOf("5") }
    var goalBaseline by remember { mutableStateOf("") }
    var goalTarget by remember { mutableStateOf("") }
    var goalTargetDate by remember { mutableStateOf("") }
    var environment by remember { mutableStateOf("HOME") }
    var equipment by remember { mutableStateOf("") }
    var spaceM2 by remember { mutableStateOf("10") }
    var fixationPoints by remember { mutableStateOf("") }
    var noiseLimit by remember { mutableStateOf("moderate") }
    var surface by remember { mutableStateOf("indoor") }
    var availableMinutes by remember { mutableStateOf("60") }
    var loadOptions by remember { mutableStateOf("") }
    var sleepHours by remember { mutableStateOf("7") }
    var sleepQuality by remember { mutableStateOf("3") }
    var energy by remember { mutableStateOf("3") }
    var fatigue by remember { mutableStateOf("3") }
    var soreness by remember { mutableStateOf("3") }
    var stress by remember { mutableStateOf("3") }
    var painFlag by remember { mutableStateOf(false) }
    var setupError by remember { mutableStateOf("") }

    Text("Configuração inicial", style = MaterialTheme.typography.titleMedium)
    OutlinedTextField(
        value = goalDescription,
        onValueChange = { goalDescription = it },
        label = { Text("Objetivo principal") },
        modifier = Modifier.fillMaxWidth(),
    )
    OutlinedTextField(
        value = goalMetric,
        onValueChange = { goalMetric = it },
        label = { Text("Métrica do objetivo, ex.: weight_kg ou distance_m") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
    OutlinedTextField(
        value = goalPriority,
        onValueChange = { goalPriority = it.onlyDigits() },
        label = { Text("Prioridade 1–5") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
    DecimalField("Baseline do objetivo (opcional)", goalBaseline) { goalBaseline = it }
    DecimalField("Meta numérica (opcional)", goalTarget) { goalTarget = it }
    OutlinedTextField(
        value = goalTargetDate,
        onValueChange = { goalTargetDate = it.filter { char -> char.isDigit() || char == '-' } },
        label = { Text("Data-alvo AAAA-MM-DD (opcional)") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )

    Text("Ambiente de treino")
    ChoiceRows(
        values = listOf("HOME", "GYM", "OUTDOOR", "TRAVEL", "MINIMAL_EQUIPMENT"),
        selected = environment,
        onSelected = { environment = it },
    )
    OutlinedTextField(
        value = equipment,
        onValueChange = { equipment = it },
        label = { Text("Equipamentos separados por vírgula") },
        modifier = Modifier.fillMaxWidth(),
    )
    DecimalField("Espaço disponível em m²", spaceM2) { spaceM2 = it }
    OutlinedTextField(
        value = fixationPoints,
        onValueChange = { fixationPoints = it },
        label = { Text("Pontos de fixação seguros, separados por vírgula") },
        modifier = Modifier.fillMaxWidth(),
    )
    Text("Limite de ruído")
    ChoiceRows(
        values = listOf("low", "moderate", "high"),
        selected = noiseLimit,
        onSelected = { noiseLimit = it },
    )
    OutlinedTextField(
        value = surface,
        onValueChange = { surface = it },
        label = { Text("Superfície, ex.: indoor, concrete, grass") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
    OutlinedTextField(
        value = availableMinutes,
        onValueChange = { availableMinutes = it.onlyDigits() },
        label = { Text("Minutos disponíveis por sessão") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
    OutlinedTextField(
        value = loadOptions,
        onValueChange = { loadOptions = it },
        label = { Text("Cargas realmente disponíveis em kg, ex.: 10,16,20,22") },
        modifier = Modifier.fillMaxWidth(),
    )

    Text("Check-in de readiness", style = MaterialTheme.typography.titleSmall)
    DecimalField("Horas de sono", sleepHours) { sleepHours = it }
    RatingField("Qualidade do sono", sleepQuality) { sleepQuality = it }
    RatingField("Energia", energy) { energy = it }
    RatingField("Fadiga", fatigue) { fatigue = it }
    RatingField("Dor muscular", soreness) { soreness = it }
    RatingField("Estresse", stress) { stress = it }
    Row {
        Checkbox(checked = painFlag, onCheckedChange = { painFlag = it })
        Text("Dor incomum / sinal de segurança")
    }

    Button(
        onClick = {
            val parsed = parseInitialSetup(
                goalDescription = goalDescription,
                goalMetric = goalMetric,
                goalPriority = goalPriority,
                goalBaseline = goalBaseline,
                goalTarget = goalTarget,
                goalTargetDate = goalTargetDate,
                environment = environment.trim(),
                equipment = equipment,
                spaceM2 = spaceM2,
                fixationPoints = fixationPoints,
                noiseLimit = noiseLimit.trim(),
                surface = surface,
                availableMinutes = availableMinutes,
                loadOptions = loadOptions,
                sleepHours = sleepHours,
                sleepQuality = sleepQuality,
                energy = energy,
                fatigue = fatigue,
                soreness = soreness,
                stress = stress,
                painFlag = painFlag,
            )
            if (parsed == null) {
                setupError = "Revise os campos da configuração inicial."
            } else {
                setupError = ""
                onSave(parsed)
            }
        },
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text("Salvar configuração inicial")
    }
    if (setupError.isNotBlank()) {
        Text(setupError, style = MaterialTheme.typography.bodyMedium)
    }
}

@Suppress("LongParameterList")
private fun parseInitialSetup(
    goalDescription: String,
    goalMetric: String,
    goalPriority: String,
    goalBaseline: String,
    goalTarget: String,
    goalTargetDate: String,
    environment: String,
    equipment: String,
    spaceM2: String,
    fixationPoints: String,
    noiseLimit: String,
    surface: String,
    availableMinutes: String,
    loadOptions: String,
    sleepHours: String,
    sleepQuality: String,
    energy: String,
    fatigue: String,
    soreness: String,
    stress: String,
    painFlag: Boolean,
): InitialSetupInput? {
    val priority = goalPriority.toIntOrNull() ?: return null
    val space = spaceM2.decimalOrNull() ?: return null
    val minutes = availableMinutes.toIntOrNull() ?: return null
    val sleep = sleepHours.decimalOrNull() ?: return null
    val ratings = listOf(sleepQuality, energy, fatigue, soreness, stress).map { it.toIntOrNull() }
    val baseline = goalBaseline.optionalDecimalOrNull()
    val target = goalTarget.optionalDecimalOrNull()
    val targetDate = when {
        goalTargetDate.isBlank() -> null
        else -> runCatching { LocalDate.parse(goalTargetDate) }.getOrNull() ?: return null
    }
    val loads = parseDecimalCsv(loadOptions) ?: return null

    if (
        goalDescription.isBlank() ||
        goalMetric.isBlank() ||
        priority !in 1..5 ||
        space <= 0.0 ||
        minutes !in 15..240 ||
        sleep !in 0.0..24.0 ||
        ratings.any { it == null || it !in 1..5 } ||
        (goalBaseline.isNotBlank() && baseline == null) ||
        (goalTarget.isNotBlank() && target == null) ||
        surface.isBlank()
    ) {
        return null
    }

    return InitialSetupInput(
        goalDescription = goalDescription.trim(),
        goalMetric = goalMetric.trim(),
        goalPriority = priority,
        goalBaseline = baseline,
        goalTarget = target,
        goalTargetDate = targetDate,
        environment = environment,
        equipment = equipment.csvValues(),
        spaceM2 = space,
        fixationPoints = fixationPoints.csvValues(),
        noiseLimit = noiseLimit,
        surface = surface.trim(),
        availableMinutes = minutes,
        loadOptionsKg = loads,
        sleepHours = sleep,
        sleepQuality = requireNotNull(ratings[0]),
        energy = requireNotNull(ratings[1]),
        fatigue = requireNotNull(ratings[2]),
        soreness = requireNotNull(ratings[3]),
        stress = requireNotNull(ratings[4]),
        painFlag = painFlag,
    )
}

@Composable
private fun RatingField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
) {
    OutlinedTextField(
        value = value,
        onValueChange = { onValueChange(it.onlyDigits()) },
        label = { Text("$label 1–5") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun DecimalField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
) {
    OutlinedTextField(
        value = value,
        onValueChange = { onValueChange(it.decimalInput()) },
        label = { Text(label) },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun ChoiceRows(
    values: List<String>,
    selected: String,
    onSelected: (String) -> Unit,
) {
    values.forEach { option ->
        Row {
            RadioButton(selected = selected == option, onClick = { onSelected(option) })
            Text(option)
        }
    }
}

private fun String.onlyDigits(): String = filter { char -> char.isDigit() }

private fun String.decimalInput(): String =
    filter { char -> char.isDigit() || char == '.' || char == ',' || char == '-' }

private fun String.decimalOrNull(): Double? = trim().replace(',', '.').toDoubleOrNull()

private fun String.optionalDecimalOrNull(): Double? = if (isBlank()) null else decimalOrNull()

private fun String.csvValues(): List<String> =
    split(',').map(String::trim).filter(String::isNotBlank).distinct()

private fun parseDecimalCsv(value: String): List<Double>? {
    if (value.isBlank()) return emptyList()
    val parts = value.split(',').map(String::trim).filter(String::isNotBlank)
    val parsed = parts.map { it.decimalOrNull() }
    if (parsed.any { it == null }) return null
    val values = parsed.map { requireNotNull(it) }
    if (values.any { it <= 0.0 || it > 5000.0 } || values.distinct().size != values.size) return null
    return values.sorted()
}
