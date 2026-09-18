package com.brunocapellari.healthos.data

import com.brunocapellari.healthos.health.TrackedHealthType
import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.Duration
import java.time.Instant

class HealthBackfillPolicyTest {
    private val now = Instant.parse("2027-03-01T12:00:00Z")
    private val policy = HealthBackfillPolicy()

    @Test
    fun corePermissionWithoutHistoryIsBoundedToThirtyDays() {
        val start = policy.initialStart(TrackedHealthType.WEIGHT, now, canReadHistory = false)
        assertEquals(30L, Duration.between(start, now).toDays())
    }

    @Test
    fun historyPermissionUsesTypeSpecificWindows() {
        val weightStart = policy.initialStart(TrackedHealthType.WEIGHT, now, canReadHistory = true)
        val heartStart = policy.initialStart(TrackedHealthType.HEART_RATE, now, canReadHistory = true)
        assertEquals(1825L, Duration.between(weightStart, now).toDays())
        assertEquals(90L, Duration.between(heartStart, now).toDays())
    }

    @Test
    fun expiredTokenRecoveryRereadsAtLeastThirtyDays() {
        val latestYesterday = now.minus(Duration.ofDays(1))
        val start = policy.recoveryStart(now, latestYesterday, canReadHistory = true)
        assertEquals(30L, Duration.between(start, now).toDays())
    }

    @Test
    fun expiredTokenRecoveryUsesOlderLastObservationWhenHistoryIsAllowed() {
        val latestSixtyDaysAgo = now.minus(Duration.ofDays(60))
        val start = policy.recoveryStart(now, latestSixtyDaysAgo, canReadHistory = true)
        assertEquals(60L, Duration.between(start, now).toDays())
    }

    @Test
    fun expiredTokenRecoveryCannotExceedThirtyDaysWithoutHistoryPermission() {
        val latestSixtyDaysAgo = now.minus(Duration.ofDays(60))
        val start = policy.recoveryStart(now, latestSixtyDaysAgo, canReadHistory = false)
        assertEquals(30L, Duration.between(start, now).toDays())
    }
}
