package com.brunocapellari.healthos.sync

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.brunocapellari.healthos.HealthOsApplication
import java.io.IOException

class SyncWorker(
    appContext: Context,
    workerParams: WorkerParameters,
) : CoroutineWorker(appContext, workerParams) {
    override suspend fun doWork(): Result {
        val application = applicationContext as HealthOsApplication
        return try {
            application.container.repository.fullSync()
            Result.success()
        } catch (_: IOException) {
            retryOrFail()
        } catch (_: IllegalStateException) {
            retryOrFail()
        }
    }

    private fun retryOrFail(): Result = if (runAttemptCount < MAX_RETRIES) Result.retry() else Result.failure()

    companion object {
        const val UNIQUE_NAME = "healthos-periodic-sync"
        private const val MAX_RETRIES = 5
    }
}
