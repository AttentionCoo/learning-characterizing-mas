package com.learnagent.utils;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ConversationTypeTest {

    @Test
    void 应保留原有模块标记并替换正文() {
        String original = ConversationType.tag(ConversationType.PROFILE, "旧回答");

        String updated = ConversationType.preserveTag(original, "新回答");

        assertTrue(ConversationType.matches(updated, ConversationType.PROFILE));
        assertEquals(ConversationType.tag(ConversationType.PROFILE, "新回答"), updated);
    }

    @Test
    void 不同模块不能互相匹配() {
        String content = ConversationType.tag(ConversationType.RESOURCE, "资源内容");

        assertFalse(ConversationType.matches(content, ConversationType.PROFILE));
    }
}
