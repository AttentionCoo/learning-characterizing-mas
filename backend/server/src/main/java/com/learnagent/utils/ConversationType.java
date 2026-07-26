package com.learnagent.utils;

/**
 * 对话所属业务模块标记。
 *
 * <p>标记存放在 talk.content 首行，避免为了区分模块而要求现有数据库新增字段。
 */
public final class ConversationType {

    public static final String PROFILE = "profile";
    public static final String RESOURCE = "resource";
    public static final String CODE_ASSIST = "code_assist";

    private static final String MARKER_PREFIX = "[[conversation-type:";
    private static final String MARKER_SUFFIX = "]]\n";

    private ConversationType() {
    }

    public static String marker(String type) {
        if (type == null || type.isBlank()) {
            return "";
        }
        return MARKER_PREFIX + type.trim() + MARKER_SUFFIX;
    }

    public static String tag(String type, String content) {
        return marker(type) + (content == null ? "" : content);
    }

    public static boolean matches(String content, String type) {
        String marker = marker(type);
        return !marker.isEmpty() && content != null && content.startsWith(marker);
    }

    public static String preserveTag(String existingContent, String newContent) {
        if (existingContent != null && existingContent.startsWith(MARKER_PREFIX)) {
            int markerEnd = existingContent.indexOf(MARKER_SUFFIX);
            if (markerEnd >= 0) {
                String existingMarker = existingContent.substring(0, markerEnd + MARKER_SUFFIX.length());
                return existingMarker + (newContent == null ? "" : newContent);
            }
        }
        return newContent == null ? "" : newContent;
    }
}
