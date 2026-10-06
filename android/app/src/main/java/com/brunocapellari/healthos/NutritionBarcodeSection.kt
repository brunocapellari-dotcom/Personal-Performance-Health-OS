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
import org.json.JSONObject
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
    foods: List<JSONObject>,
    onLookupBarcode: (String) -> Unit,
    onSearchFoods: (String) -> Unit,
    onLogFood: (JSONObject, Double, String) -> Unit,
) {
    var manualBarcode by remember { mutableStateOf("") }
    var foodQuery by remember { mutableStateOf("") }
    var portionGrams by remember { mutableStateOf("100") }
    var meal by remember { mutableStateOf("lanche") }
    var scannerOpen by remember { mutableStateOf(false) }

    Text("Nutrição", style = MaterialTheme.typography.titleMedium)
    OutlinedTextField(
        value = foodQuery,
        onValueChange = { foodQuery = it.take(200) },
        label = { Text("Buscar alimento") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
    Button(
        onClick = {
            val query = foodQuery.trim()
            if (query.isNotEmpty()) onSearchFoods(query)
        },
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text("Buscar alimento")
    }

    Text("Produto por código de barras", style = MaterialTheme.typography.titleSmall)
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
    if (foods.isNotEmpty()) {
        OutlinedTextField(
            value = portionGrams,
            onValueChange = { value ->
                portionGrams = value
                    .filter { it.isDigit() || it == '.' || it == ',' }
                    .take(8)
            },
            label = { Text("Porção consumida (g)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = meal,
            onValueChange = { meal = it.take(64) },
            label = { Text("Refeição") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        foods.forEach { food ->
            val name = food.optString("name", "Alimento")
            Button(
                onClick = {
                    val quantity = portionGrams.replace(',', '.').toDoubleOrNull()
                    val cleanMeal = meal.trim()
                    if (quantity != null && quantity > 0.0 && cleanMeal.isNotBlank()) {
                        onLogFood(food, quantity, cleanMeal)
                    }
                },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Registrar $name")
            }
        }
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
                        .mapNotNull { result -> result.text?.filter { char -> char.isDigit() } }
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
