package com.brunocapellari.healthos

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class InitialSetupSectionTest {
    @Test
    fun validSetupParsesDecimalCommaAndCanonicalLists() {
        val parsed = parseInitialSetupInput(
            goalDescription = "Melhorar condicionamento",
            goalMetric = "distance_m",
            goalPriority = "5",
            goalBaseline = "5000,5",
            goalTarget = "10000",
            goalTargetDate = "2026-12-31",
            environment = "HOME",
            equipment = "dumbbells, band, dumbbells",
            spaceM2 = "10,5",
            fixationPoints = "anchor, anchor",
            noiseLimit = "moderate",
            surface = "indoor",
            availableMinutes = "60",
            loadOptions = "10,16,20,22",
            sleepHours = "7,5",
            sleepQuality = "4",
            energy = "4",
            fatigue = "2",
            soreness = "2",
            stress = "2",
            painFlag = false,
        )

        requireNotNull(parsed)
        assertEquals(5000.5, parsed.goalBaseline)
        assertEquals(10000.0, parsed.goalTarget)
        assertEquals(LocalDate.of(2026, 12, 31), parsed.goalTargetDate)
        assertEquals(listOf("dumbbells", "band"), parsed.equipment)
        assertEquals(listOf("anchor"), parsed.fixationPoints)
        assertEquals(listOf(10.0, 16.0, 20.0, 22.0), parsed.loadOptionsKg)
        assertEquals(7.5, parsed.sleepHours)
    }

    @Test
    fun invalidReadinessRatingIsRejected() {
        val parsed = parseInitialSetupInput(
            goalDescription = "Meta",
            goalMetric = "weight_kg",
            goalPriority = "5",
            goalBaseline = "",
            goalTarget = "",
            goalTargetDate = "",
            environment = "HOME",
            equipment = "",
            spaceM2 = "10",
            fixationPoints = "",
            noiseLimit = "low",
            surface = "indoor",
            availableMinutes = "45",
            loadOptions = "",
            sleepHours = "8",
            sleepQuality = "6",
            energy = "4",
            fatigue = "2",
            soreness = "2",
            stress = "2",
            painFlag = false,
        )

        assertNull(parsed)
    }

    @Test
    fun duplicateAvailableLoadsAreRejected() {
        val parsed = parseInitialSetupInput(
            goalDescription = "Meta",
            goalMetric = "strength",
            goalPriority = "5",
            goalBaseline = "",
            goalTarget = "",
            goalTargetDate = "",
            environment = "GYM",
            equipment = "barbell",
            spaceM2 = "20",
            fixationPoints = "",
            noiseLimit = "moderate",
            surface = "rubber",
            availableMinutes = "60",
            loadOptions = "20,20,40",
            sleepHours = "8",
            sleepQuality = "4",
            energy = "4",
            fatigue = "2",
            soreness = "2",
            stress = "2",
            painFlag = false,
        )

        assertNull(parsed)
    }

    @Test
    fun painFlagIsPreservedAsSafetySignal() {
        val parsed = parseInitialSetupInput(
            goalDescription = "Meta",
            goalMetric = "strength",
            goalPriority = "4",
            goalBaseline = "",
            goalTarget = "",
            goalTargetDate = "",
            environment = "HOME",
            equipment = "",
            spaceM2 = "8",
            fixationPoints = "",
            noiseLimit = "low",
            surface = "indoor",
            availableMinutes = "30",
            loadOptions = "",
            sleepHours = "6",
            sleepQuality = "3",
            energy = "3",
            fatigue = "4",
            soreness = "4",
            stress = "3",
            painFlag = true,
        )

        requireNotNull(parsed)
        assertTrue(parsed.painFlag)
    }
}
