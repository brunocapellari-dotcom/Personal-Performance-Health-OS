package com.brunocapellari.healthos

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    private val statusText = mutableStateOf("Inicializando")
    private val healthText = mutableStateOf("Health Connect não verificado")

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
                            onPermissions = {
                                permissionsLauncher.launch(container.healthConnect.extendedReadPermissions())
                            },
                            onEnroll = ::enroll,
                            onSync = ::syncNow,
                            onNextBlock = ::nextBlock,
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
            val granted = withContext(Dispatchers.IO) {
                container.healthConnect.hasPermissions(container.healthConnect.extendedReadPermissions())
            }
            healthText.value = if (granted) "Health Connect autorizado" else "Permissões do Health Connect pendentes"
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

    private fun nextBlock() {
        lifecycleScope.launch {
            statusText.value = "Montando próximo bloco"
            runCatching {
                withContext(Dispatchers.IO) { container.nextBlock.generate() }
            }.onSuccess { response ->
                val passed = response.getJSONObject("audit").getBoolean("passed")
                statusText.value = if (passed) {
                    "Novo bloco auditado e aprovado (${response.getString("snapshot_id").take(8)})"
                } else {
                    "Bloco rejeitado pela auditoria"
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
    onPermissions: () -> Unit,
    onEnroll: (String) -> Unit,
    onSync: () -> Unit,
    onNextBlock: () -> Unit,
) {
    var bootstrapToken by remember { mutableStateOf("") }
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Personal Performance & Health OS", style = MaterialTheme.typography.headlineSmall)
        Text(healthStatus)
        Button(onClick = onPermissions, modifier = Modifier.fillMaxWidth()) {
            Text("Autorizar Health Connect")
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
