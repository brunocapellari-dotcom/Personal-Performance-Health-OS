package com.brunocapellari.healthos

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun HistorySection(
    summary: String,
    onRefresh: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Histórico e evolução", style = MaterialTheme.typography.titleMedium)
        Text(summary, style = MaterialTheme.typography.bodyMedium)
        Button(onClick = onRefresh, modifier = Modifier.fillMaxWidth()) {
            Text("Atualizar histórico")
        }
    }
}
