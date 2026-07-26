package com.learnagent.utils;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CodeAssistTypeTest {

    @Test
    void 仅接受四种明确的辅助功能() {
        assertEquals(CodeAssistType.COMPLETE, CodeAssistType.fromValue("complete").orElseThrow());
        assertEquals(CodeAssistType.EXPLAIN, CodeAssistType.fromValue("explain").orElseThrow());
        assertTrue(CodeAssistType.fromValue("").isEmpty());
        assertTrue(CodeAssistType.fromValue("all").isEmpty());
    }
}
