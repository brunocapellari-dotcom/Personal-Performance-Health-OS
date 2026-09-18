package com.brunocapellari.healthos

import android.app.Application
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import com.brunocapellari.healthos.data.HealthDataRepository
import com.brunocapellari.healthos.data.HealthOsDatabase
import com.brunocapellari.healthos.data.NextBlockCoordinator
import com.brunocapellari.healthos.health.HealthConnectGateway
import com.brunocapellari.healthos.network.HealthOsApiClient
import com.brunocapellari.healthos.security.DeviceIdentity
import com.brunocapellari.healthos.sync.SyncWorker
import java.util.concurrent.TimeUnit

class HealthOsApplication : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
        scheduleSync()
    }

    private fun scheduleSync() {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        val request = PeriodicWorkRequestBuilder<SyncWorker>(6, TimeUnit.HOURS)
            .setConstraints(constraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(this).enqueueUniquePeriodicWork(
            SyncWorker.UNIQUE_NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }
}

class AppContainer(application: Application) {
    val database: HealthOsDatabase by lazy { HealthOsDatabase.get(application) }
    val identity: DeviceIdentity by lazy { DeviceIdentity() }
    val healthConnect: HealthConnectGateway by lazy { HealthConnectGateway(application) }
    val api: HealthOsApiClient by lazy { HealthOsApiClient(BuildConfig.API_BASE_URL) }
    val repository: HealthDataRepository by lazy {
        HealthDataRepository(database, healthConnect, api, identity)
    }
    val nextBlock: NextBlockCoordinator by lazy {
        NextBlockCoordinator(repository, api, identity)
    }
}
