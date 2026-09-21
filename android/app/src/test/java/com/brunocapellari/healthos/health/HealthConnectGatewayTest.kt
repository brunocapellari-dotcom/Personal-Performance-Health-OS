package com.brunocapellari.healthos.health

import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.metadata.Metadata
import androidx.health.connect.client.testing.FakeHealthConnectClient
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

class HealthConnectGatewayTest {
    @Test
    fun changesFlowNormalizesUpsertAndDeletion() = runBlocking {
        val fake = FakeHealthConnectClient()
        val gateway = HealthConnectGateway(fake)
        val start = Instant.parse("2027-03-01T10:00:00Z")
        val end = Instant.parse("2027-03-01T10:30:00Z")
        val token = gateway.newToken(TrackedHealthType.STEPS)

        val inserted = fake.insertRecords(
            listOf(
                StepsRecord(
                    startTime = start,
                    startZoneOffset = null,
                    endTime = end,
                    endZoneOffset = null,
                    count = 2500,
                    metadata = Metadata.manualEntry(),
                ),
            ),
        )

        val upsertBatch = gateway.drain(TrackedHealthType.STEPS, token)
        assertEquals(1, upsertBatch.deltas.size)
        assertFalse(upsertBatch.deltas.single().deleted)
        assertTrue(upsertBatch.deltas.single().payloadJson.contains("\"count\":2500"))

        fake.deleteRecords(
            StepsRecord::class,
            recordIdsList = listOf(inserted.recordIdsList.single()),
            clientRecordIdsList = emptyList(),
        )
        val deletionBatch = gateway.drain(TrackedHealthType.STEPS, upsertBatch.nextToken)
        assertEquals(1, deletionBatch.deltas.size)
        assertTrue(deletionBatch.deltas.single().deleted)
        assertEquals(inserted.recordIdsList.single(), deletionBatch.deltas.single().recordId)
    }

    @Test
    fun backfillReadsOnlyRequestedWindow() = runBlocking {
        val fake = FakeHealthConnectClient()
        val gateway = HealthConnectGateway(fake)
        val insideStart = Instant.parse("2027-03-01T10:00:00Z")
        val insideEnd = Instant.parse("2027-03-01T10:30:00Z")
        val outsideStart = Instant.parse("2027-02-01T10:00:00Z")
        val outsideEnd = Instant.parse("2027-02-01T10:30:00Z")

        fake.insertRecords(
            listOf(
                StepsRecord(
                    startTime = insideStart,
                    startZoneOffset = null,
                    endTime = insideEnd,
                    endZoneOffset = null,
                    count = 1800,
                    metadata = Metadata.manualEntry(),
                ),
                StepsRecord(
                    startTime = outsideStart,
                    startZoneOffset = null,
                    endTime = outsideEnd,
                    endZoneOffset = null,
                    count = 900,
                    metadata = Metadata.manualEntry(),
                ),
            ),
        )

        val deltas = gateway.backfill(
            TrackedHealthType.STEPS,
            Instant.parse("2027-03-01T00:00:00Z"),
            Instant.parse("2027-03-02T00:00:00Z"),
        )
        assertEquals(1, deltas.size)
        assertTrue(deltas.single().payloadJson.contains("\"count\":1800"))
    }


    @Test
    fun speedNormalizationPreservesSeriesAndProvenance() = runBlocking {
        val fake = FakeHealthConnectClient()
        val gateway = HealthConnectGateway(fake)
        val start = Instant.parse("2027-03-01T10:00:00Z")
        val end = Instant.parse("2027-03-01T10:01:00Z")
        val token = gateway.newToken(TrackedHealthType.SPEED)

        fake.insertRecords(
            listOf(
                SpeedRecord(
                    startTime = start,
                    startZoneOffset = null,
                    endTime = end,
                    endZoneOffset = null,
                    samples = listOf(
                        SpeedRecord.Sample(start.plusSeconds(30), Velocity.metersPerSecond(3.5)),
                    ),
                    metadata = Metadata.manualEntry(),
                ),
            ),
        )

        val batch = gateway.drain(TrackedHealthType.SPEED, token)
        val delta = batch.deltas.single()
        assertEquals(TrackedHealthType.SPEED, delta.recordType)
        assertTrue(delta.payloadJson.contains("\"metersPerSecond\":3.5"))
        assertTrue(delta.payloadJson.contains("\"_provenance\""))
        assertEquals(Metadata.RECORDING_METHOD_MANUAL_ENTRY, delta.recordingMethod)
        assertTrue(delta.lastModifiedAtEpochMillis > 0)
        assertTrue(delta.dataOriginPackage.isNotBlank())
    }
}
