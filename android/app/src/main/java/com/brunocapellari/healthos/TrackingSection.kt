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

@Composable
fun TrackingSection(
    onBodyMeasurement: (String, Double, String, String?) -> Unit,
    onAssessment: (String, Double, String, String?) -> Unit,
) {
    var bodyMetric by remember { mutableStateOf("waist") }
    var bodyValue by remember { mutableStateOf("") }
    var bodyUnit by remember { mutableStateOf("cm") }
    var bodyLabel by remember { mutableStateOf("") }

    var assessmentMetric by remember { mutableStateOf("") }
    var assessmentValue by remember { mutableStateOf("") }
    var assessmentUnit by remember { mutableStateOf("") }
    var assessmentContext by remember { mutableStateOf("") }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Corpo e avaliações", style = MaterialTheme.typography.titleMedium)
        Text(
            "Medidas corporais aceitas: weight, waist, abdomen, chest, arm, thigh, hip, neck ou other.",
            style = MaterialTheme.typography.bodySmall,
        )
        OutlinedTextField(
            value = bodyMetric,
            onValueChange = { bodyMetric = it.lowercase().filter { char -> char.isLetter() || char == '_' }.take(32) },
            label = { Text("Métrica corporal") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = bodyValue,
            onValueChange = { bodyValue = decimalTrackingInput(it, 10) },
            label = { Text("Valor") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = bodyUnit,
            onValueChange = { bodyUnit = it.take(32) },
            label = { Text("Unidade") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = bodyLabel,
            onValueChange = { bodyLabel = it.take(128) },
            label = { Text("Rótulo opcional") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = {
                val parsed = bodyValue.replace(',', '.').toDoubleOrNull()
                if (parsed != null) {
                    onBodyMeasurement(
                        bodyMetric,
                        parsed,
                        bodyUnit,
                        bodyLabel.trim().takeIf(String::isNotBlank),
                    )
                    bodyValue = ""
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Registrar medida corporal")
        }

        Text("Avaliação física", style = MaterialTheme.typography.titleSmall)
        OutlinedTextField(
            value = assessmentMetric,
            onValueChange = { assessmentMetric = it.take(128) },
            label = { Text("Métrica, ex.: grip_left_kg, plank_seconds") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = assessmentValue,
            onValueChange = { assessmentValue = signedDecimalTrackingInput(it, 16) },
            label = { Text("Resultado") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = assessmentUnit,
            onValueChange = { assessmentUnit = it.take(64) },
            label = { Text("Unidade") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = assessmentContext,
            onValueChange = { assessmentContext = it.take(1000) },
            label = { Text("Contexto opcional") },
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = {
                val parsed = assessmentValue.replace(',', '.').toDoubleOrNull()
                if (parsed != null && assessmentMetric.isNotBlank() && assessmentUnit.isNotBlank()) {
                    onAssessment(
                        assessmentMetric,
                        parsed,
                        assessmentUnit,
                        assessmentContext.trim().takeIf(String::isNotBlank),
                    )
                    assessmentValue = ""
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Registrar avaliação")
        }
    }
}

private fun decimalTrackingInput(value: String, maxLength: Int): String =
    value.filter { it.isDigit() || it == '.' || it == ',' }.take(maxLength)

private fun signedDecimalTrackingInput(value: String, maxLength: Int): String =
    value.filter { it.isDigit() || it == '.' || it == ',' || it == '-' }.take(maxLength)
