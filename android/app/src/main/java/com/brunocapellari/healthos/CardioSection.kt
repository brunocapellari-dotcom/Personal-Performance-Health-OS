package com.brunocapellari.healthos

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

data class ManualCardioInput(
    val modality: String,
    val durationMinutes: Int,
    val rpe: Double?,
    val distanceM: Double?,
    val avgHrBpm: Double?,
    val maxHrBpm: Double?,
    val avgPowerW: Double?,
    val avgCadenceRpm: Double?,
    val intervalStructure: String?,
    val notes: String,
)

@Composable
fun CardioSection(onSave: (ManualCardioInput) -> Unit) {
    var modality by remember { mutableStateOf("bike") }
    var duration by remember { mutableStateOf("") }
    var distance by remember { mutableStateOf("") }
    var avgHr by remember { mutableStateOf("") }
    var maxHr by remember { mutableStateOf("") }
    var avgPower by remember { mutableStateOf("") }
    var cadence by remember { mutableStateOf("") }
    var rpe by remember { mutableStateOf("") }
    var intervals by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Cardio / condicionamento", style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(
            value = modality,
            onValueChange = { modality = it.lowercase().take(64) },
            label = { Text("Modalidade: bike, walk, run, conditioning...") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = duration,
            onValueChange = { duration = it.filter(Char::isDigit).take(4) },
            label = { Text("Duração (min)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = distance,
            onValueChange = { distance = cardioDecimal(it, 12) },
            label = { Text("Distância (m), opcional") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = avgHr,
            onValueChange = { avgHr = cardioDecimal(it, 6) },
            label = { Text("FC média, opcional") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = maxHr,
            onValueChange = { maxHr = cardioDecimal(it, 6) },
            label = { Text("FC máxima, opcional") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = avgPower,
            onValueChange = { avgPower = cardioDecimal(it, 8) },
            label = { Text("Potência média (W), opcional") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = cadence,
            onValueChange = { cadence = cardioDecimal(it, 8) },
            label = { Text("Cadência média (rpm), opcional") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = rpe,
            onValueChange = { rpe = cardioDecimal(it, 4) },
            label = { Text("RPE 0–10, opcional") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = intervals,
            onValueChange = { intervals = it.take(1000) },
            label = { Text("Estrutura de intervalos, opcional") },
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = notes,
            onValueChange = { notes = it.take(5000) },
            label = { Text("Observações") },
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = {
                val parsedDuration = duration.toIntOrNull()
                val parsedRpe = rpe.asNullableDouble()
                val parsedAvgHr = avgHr.asNullableDouble()
                val parsedMaxHr = maxHr.asNullableDouble()
                if (
                    modality.isNotBlank() &&
                    parsedDuration != null &&
                    parsedDuration in 1..1440 &&
                    (parsedRpe == null || parsedRpe in 0.0..10.0) &&
                    (parsedAvgHr == null || parsedAvgHr in 20.0..300.0) &&
                    (parsedMaxHr == null || parsedMaxHr in 20.0..300.0) &&
                    (parsedAvgHr == null || parsedMaxHr == null || parsedAvgHr <= parsedMaxHr)
                ) {
                    onSave(
                        ManualCardioInput(
                            modality = modality,
                            durationMinutes = parsedDuration,
                            rpe = parsedRpe,
                            distanceM = distance.asNullableDouble(),
                            avgHrBpm = parsedAvgHr,
                            maxHrBpm = parsedMaxHr,
                            avgPowerW = avgPower.asNullableDouble(),
                            avgCadenceRpm = cadence.asNullableDouble(),
                            intervalStructure = intervals.trim().takeIf(String::isNotBlank),
                            notes = notes,
                        ),
                    )
                    duration = ""
                    distance = ""
                    avgHr = ""
                    maxHr = ""
                    avgPower = ""
                    cadence = ""
                    rpe = ""
                    intervals = ""
                    notes = ""
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Registrar cardio")
        }
    }
}

private fun cardioDecimal(value: String, maxLength: Int): String =
    value.filter { it.isDigit() || it == '.' || it == ',' }.take(maxLength)

private fun String.asNullableDouble(): Double? = replace(',', '.').toDoubleOrNull()
