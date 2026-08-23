package com.learnagent.utils;

import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProfileMergePolicyTest {

    private Map<String, Object> dim(String source, double confidence, String updatedAt) {
        Map<String, Object> m = new HashMap<>();
        m.put("source", source);
        m.put("confidence", confidence);
        m.put("updated_at", updatedAt);
        return m;
    }

    @Test
    void userStatementOverwritesAnything() {
        Map<String, Object> existing = dim(ProfileMergePolicy.SOURCE_USER, 1.0, "2026-08-01");
        Map<String, Object> incoming = dim(ProfileMergePolicy.SOURCE_USER, 0.8, "2026-08-20");
        assertTrue(ProfileMergePolicy.shouldApply(existing, incoming));

        Map<String, Object> existingInferred = dim(ProfileMergePolicy.SOURCE_INFERRED, 0.9, "2026-08-20");
        Map<String, Object> incomingUser = dim(ProfileMergePolicy.SOURCE_USER, 1.0, "2026-08-21");
        assertTrue(ProfileMergePolicy.shouldApply(existingInferred, incomingUser));
    }

    @Test
    void confirmedFactNotDowngradedByInference() {
        Map<String, Object> existing = dim(ProfileMergePolicy.SOURCE_USER, 1.0, "2026-08-01");
        Map<String, Object> incoming = dim(ProfileMergePolicy.SOURCE_INFERRED, 0.9, "2026-08-20");
        assertFalse(ProfileMergePolicy.shouldApply(existing, incoming));
    }

    @Test
    void higherConfidenceInferenceWins() {
        Map<String, Object> existing = dim(ProfileMergePolicy.SOURCE_INFERRED, 0.5, "2026-08-20");
        Map<String, Object> incoming = dim(ProfileMergePolicy.SOURCE_INFERRED, 0.8, "2026-08-20");
        assertTrue(ProfileMergePolicy.shouldApply(existing, incoming));
    }

    @Test
    void casePerformanceBeatsPlainInference() {
        Map<String, Object> existing = dim(ProfileMergePolicy.SOURCE_INFERRED, 0.7, "2026-08-20");
        Map<String, Object> incoming = dim(ProfileMergePolicy.SOURCE_CASE_PERFORMANCE, 0.6, "2026-08-21");
        assertTrue(ProfileMergePolicy.shouldApply(existing, incoming));
    }

    @Test
    void newerObservationWinsWhenConfidenceTies() {
        Map<String, Object> existing = dim(ProfileMergePolicy.SOURCE_INFERRED, 0.6, "2026-08-01");
        Map<String, Object> incoming = dim(ProfileMergePolicy.SOURCE_INFERRED, 0.6, "2026-08-20");
        assertTrue(ProfileMergePolicy.shouldApply(existing, incoming));
    }

    @Test
    void weakerOlderInferenceKeepsExisting() {
        Map<String, Object> existing = dim(ProfileMergePolicy.SOURCE_INFERRED, 0.8, "2026-08-20");
        Map<String, Object> incoming = dim(ProfileMergePolicy.SOURCE_INFERRED, 0.5, "2026-08-20");
        assertFalse(ProfileMergePolicy.shouldApply(existing, incoming));
    }

    @Test
    void emptyExistingAlwaysAccepts() {
        Map<String, Object> incoming = dim(ProfileMergePolicy.SOURCE_INFERRED, 0.5, "2026-08-20");
        assertTrue(ProfileMergePolicy.shouldApply(null, incoming));
        assertTrue(ProfileMergePolicy.shouldApply(new HashMap<>(), incoming));
    }

    @Test
    void asUserConfirmedAddsMetadataWithoutOverwriting() {
        Map<String, Object> value = new HashMap<>();
        value.put("level", "beginner");
        ProfileMergePolicy.asUserConfirmed(value);

        assertTrue(value.containsKey("source"));
        assertTrue(value.containsKey("confidence"));
        assertTrue(value.containsKey("updated_at"));
    }
}
