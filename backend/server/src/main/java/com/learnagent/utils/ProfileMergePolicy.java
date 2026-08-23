package com.learnagent.utils;

import java.util.Map;

/**
 * 学习画像"状态感知合并"策略。
 *
 * 每个维度值携带证据链元数据：source（user_statement/inferred/case_performance/unknown）、
 * confidence（0~1）、evidence（原话引用）、updated_at。
 *
 * 核心原则：Profile 只接受有依据的更新——
 * - 用户明确陈述（user_statement）可覆盖任何旧值；
 * - 已有用户确认事实，不被推断值降级；
 * - 推断值之间按置信度与时间戳择优；
 * - 情绪状态等"当前状态"维度始终以最新观测为准（由调用方单独处理）。
 */
public final class ProfileMergePolicy {

    public static final String SOURCE_USER = "user_statement";
    public static final String SOURCE_INFERRED = "inferred";
    public static final String SOURCE_CASE_PERFORMANCE = "case_performance";

    private ProfileMergePolicy() {
    }

    /** 判断 incoming 是否应覆盖 existing（existing 为空时恒为 true）。 */
    public static boolean shouldApply(Map<String, Object> existing, Map<String, Object> incoming) {
        if (incoming == null || incoming.isEmpty()) {
            return false;
        }
        if (existing == null || existing.isEmpty()) {
            return true;
        }

        String existingSource = str(existing.get("source"));
        String incomingSource = str(incoming.get("source"));
        double existingConf = conf(existing.get("confidence"), 0.5);
        double incomingConf = conf(incoming.get("confidence"), 0.5);

        // 用户明确陈述：以用户为准
        if (SOURCE_USER.equals(incomingSource)) {
            return true;
        }
        // 已有用户确认的事实，不因系统推断而降级
        if (SOURCE_USER.equals(existingSource)) {
            return false;
        }
        // 评估/测验表现证据高于一般推断
        if (SOURCE_CASE_PERFORMANCE.equals(incomingSource)
                && !SOURCE_CASE_PERFORMANCE.equals(existingSource)) {
            return true;
        }
        // 置信度更高者胜出
        if (incomingConf > existingConf) {
            return true;
        }
        // 同为推断且置信度相近：更新的观测胜出
        String existingTs = str(existing.get("updated_at"));
        String incomingTs = str(incoming.get("updated_at"));
        if (incomingTs.compareTo(existingTs) > 0) {
            return true;
        }
        return false;
    }

    /** 把无元数据的旧式维度值包装为"用户确认"（用于手动编辑等可信入口）。 */
    @SuppressWarnings("unchecked")
    public static Map<String, Object> asUserConfirmed(Map<String, Object> value) {
        if (value == null) {
            return value;
        }
        value.putIfAbsent("source", SOURCE_USER);
        value.putIfAbsent("confidence", 1.0);
        value.putIfAbsent("evidence", "");
        value.putIfAbsent("updated_at", java.time.LocalDate.now().toString());
        return value;
    }

    private static String str(Object v) {
        return v == null ? "" : String.valueOf(v);
    }

    private static double conf(Object v, double def) {
        if (v == null) {
            return def;
        }
        try {
            return Math.max(0.0, Math.min(1.0, Double.parseDouble(String.valueOf(v))));
        } catch (NumberFormatException e) {
            return def;
        }
    }
}
