package com.brunocapellari.healthos.data

import android.content.Context
import androidx.room3.Dao
import androidx.room3.Database
import androidx.room3.Entity
import androidx.room3.Insert
import androidx.room3.OnConflictStrategy
import androidx.room3.PrimaryKey
import androidx.room3.Query
import androidx.room3.Room
import androidx.room3.RoomDatabase
import androidx.room3.Upsert
import com.brunocapellari.healthos.security.DatabaseKeyManager
import net.zetetic.database.sqlcipher.driver.SQLCipherDriver

@Entity(tableName = "pending_changes")
data class PendingChangeEntity(
    @PrimaryKey val changeId: String,
    val entityType: String,
    val entityId: String,
    val logicalClock: Long,
    val deleted: Boolean,
    val payloadJson: String,
    val createdAtEpochMillis: Long,
)

@Entity(tableName = "sync_conflicts")
data class SyncConflictEntity(
    @PrimaryKey val changeId: String,
    val entityType: String,
    val entityId: String,
    val payloadJson: String,
    val detectedAtEpochMillis: Long,
)

@Entity(tableName = "sync_state")
data class SyncStateEntity(
    @PrimaryKey val key: String,
    val value: String,
    val updatedAtEpochMillis: Long,
)

@Entity(tableName = "health_observations")
data class LocalObservationEntity(
    @PrimaryKey val observationId: String,
    val recordType: String,
    val sourceRecordId: String,
    val observedAtEpochMillis: Long,
    val payloadJson: String,
    val dataOriginPackage: String,
    val deleted: Boolean = false,
)

@Entity(
    tableName = "remote_entities",
    primaryKeys = ["entityType", "entityId"],
)
data class RemoteEntityEntity(
    val entityType: String,
    val entityId: String,
    val logicalClock: Long,
    val originDeviceId: String,
    val deleted: Boolean,
    val payloadJson: String,
    val serverSeq: Long,
)

@Dao
interface PendingChangeDao {
    @Query("SELECT * FROM pending_changes ORDER BY createdAtEpochMillis, changeId LIMIT :limit")
    suspend fun oldest(limit: Int): List<PendingChangeEntity>

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(change: PendingChangeEntity): Long

    @Query("DELETE FROM pending_changes WHERE changeId IN (:changeIds)")
    suspend fun delete(changeIds: List<String>)

    @Query("SELECT COUNT(*) FROM pending_changes")
    suspend fun count(): Int
}

@Dao
interface SyncConflictDao {
    @Upsert
    suspend fun upsert(conflict: SyncConflictEntity)

    @Query("SELECT COUNT(*) FROM sync_conflicts")
    suspend fun count(): Int
}

@Dao
interface SyncStateDao {
    @Query("SELECT * FROM sync_state WHERE `key` = :key LIMIT 1")
    suspend fun get(key: String): SyncStateEntity?

    @Query("SELECT * FROM sync_state WHERE `key` LIKE :prefix || '%' ORDER BY updatedAtEpochMillis DESC LIMIT 1")
    suspend fun latestByPrefix(prefix: String): SyncStateEntity?

    @Upsert
    suspend fun upsert(state: SyncStateEntity)

    @Query("DELETE FROM sync_state WHERE `key` = :key")
    suspend fun delete(key: String)
}

@Dao
interface ObservationDao {
    @Query("SELECT * FROM health_observations WHERE observationId = :id LIMIT 1")
    suspend fun get(id: String): LocalObservationEntity?

    @Upsert
    suspend fun upsert(observation: LocalObservationEntity)

    @Query("SELECT MAX(observedAtEpochMillis) FROM health_observations WHERE recordType = :recordType")
    suspend fun latestObservedAt(recordType: String): Long?
}

@Dao
interface RemoteEntityDao {
    @Upsert
    suspend fun upsert(entity: RemoteEntityEntity)

    @Query("SELECT * FROM remote_entities WHERE entityType = :type AND deleted = 0 ORDER BY serverSeq DESC")
    suspend fun activeByType(type: String): List<RemoteEntityEntity>
}

@Database(
    entities = [
        PendingChangeEntity::class,
        SyncConflictEntity::class,
        SyncStateEntity::class,
        LocalObservationEntity::class,
        RemoteEntityEntity::class,
    ],
    version = 1,
    exportSchema = true,
)
abstract class HealthOsDatabase : RoomDatabase() {
    abstract fun pendingChangeDao(): PendingChangeDao
    abstract fun syncConflictDao(): SyncConflictDao
    abstract fun syncStateDao(): SyncStateDao
    abstract fun observationDao(): ObservationDao
    abstract fun remoteEntityDao(): RemoteEntityDao

    companion object {
        @Volatile
        private var instance: HealthOsDatabase? = null

        fun get(context: Context): HealthOsDatabase = instance ?: synchronized(this) {
            instance ?: build(context.applicationContext).also { instance = it }
        }

        private fun build(context: Context): HealthOsDatabase {
            System.loadLibrary("sqlcipher")
            val passphrase = DatabaseKeyManager(context).databasePassphrase()
            val driver = SQLCipherDriver(passphrase, null, null)
            return Room.databaseBuilder<HealthOsDatabase>(
                context = context,
                name = context.getDatabasePath("healthos.db").absolutePath,
            )
                .setDriver(driver)
                .build()
        }
    }
}
