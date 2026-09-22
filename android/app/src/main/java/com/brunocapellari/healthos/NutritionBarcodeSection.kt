package com.brunocapellari.healthos

import android.Manifest
import android.content.pm.PackageManager
import android.os.Handler
import android.os.Looper
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.view.CameraController
import androidx.camera.view.LifecycleCameraController
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import zxingcpp.BarcodeReader

private val RETAIL_BARCODE_FORMATS = setOf(
    BarcodeReader.Format.EAN_13,
    BarcodeReader.Format.EAN_8,
    BarcodeReader.Format.UPC_A,
    BarcodeReader.Format.UPC_E,
)

@Composable
fun NutritionBarcodeSection(
    resultText: String,
    onLookupBarcode: (String) -> Unit,
) {
    var manualBarcode by remember { mutableStateOf("") }
    var scannerOpen by remember { mutableStateOf(false) }

    Text("Alimento por código de barras", style = MaterialTheme.typography.titleMedium)
    OutlinedTextField(
        value = manualBarcode,
        onValueChange = { value -> manualBarcode = value.filter { it.isDigit() }.take(24) },
        label = { Text("EAN/UPC") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
    Button(
        onClick = {
            if (manualBarcode.length in 4..24) {
                onLookupBarcode(manualBarcode)
            }
        },
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text("Buscar código digitado")
    }
    Button(
        onClick = { scannerOpen = !scannerOpen },
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(if (scannerOpen) "Fechar scanner" else "Escanear código de barras")
    }

    if (scannerOpen) {
        RetailBarcodeScanner(
            onBarcode = { code ->
                manualBarcode = code
                scannerOpen = false
                onLookupBarcode(code)
            },
        )
    }
    if (resultText.isNotBlank()) {
        Text(resultText, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun RetailBarcodeScanner(
    onBarcode: (String) -> Unit,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    var cameraGranted by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED,
        )
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        cameraGranted = granted
    }

    LaunchedEffect(Unit) {
        if (!cameraGranted) permissionLauncher.launch(Manifest.permission.CAMERA)
    }

    if (!cameraGranted) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("A câmera só é usada durante a leitura do código e nenhum frame é armazenado.")
            Button(onClick = { permissionLauncher.launch(Manifest.permission.CAMERA) }) {
                Text("Autorizar câmera")
            }
        }
        return
    }

    val executor = remember { Executors.newSingleThreadExecutor() }
    val delivered = remember { AtomicBoolean(false) }
    val mainHandler = remember { Handler(Looper.getMainLooper()) }
    val reader = remember {
        BarcodeReader(
            BarcodeReader.Options(
                formats = RETAIL_BARCODE_FORMATS,
                tryHarder = true,
                tryRotate = true,
                maxNumberOfSymbols = 1,
            ),
        )
    }
    val controller = remember {
        LifecycleCameraController(context).apply {
            cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA
            setEnabledUseCases(CameraController.IMAGE_ANALYSIS)
        }
    }

    DisposableEffect(lifecycleOwner) {
        controller.bindToLifecycle(lifecycleOwner)
        controller.setImageAnalysisAnalyzer(executor) { image ->
            val code = runCatching {
                image.use {
                    reader.read(it)
                        .asSequence()
                        .mapNotNull { result -> result.text?.filter(Char::isDigit) }
                        .firstOrNull { value -> value.length in 4..24 }
                }
            }.getOrNull()
            if (code != null && delivered.compareAndSet(false, true)) {
                mainHandler.post { onBarcode(code) }
            }
        }
        onDispose {
            controller.clearImageAnalysisAnalyzer()
            controller.unbind()
            executor.shutdown()
        }
    }

    AndroidView(
        factory = { viewContext ->
            PreviewView(viewContext).apply {
                this.controller = controller
            }
        },
        modifier = Modifier.fillMaxWidth().height(280.dp),
    )
}
