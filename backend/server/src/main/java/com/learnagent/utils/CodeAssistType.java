package com.learnagent.utils;

import java.util.Arrays;
import java.util.Optional;

/** 代码辅助功能及其互斥执行约束。 */
public enum CodeAssistType {
    COMPLETE("complete", "代码补全",
            "仅补全现有代码或实现明确缺失部分，保持已有结构和行为，不额外执行错误诊断、性能优化或教学讲解。"),
    DIAGNOSE("diagnose", "错误诊断",
            "仅定位错误根因并给出修复方案，说明报错位置、原因、修复代码和验证方式，不扩展无关功能。"),
    OPTIMIZE("optimize", "优化建议",
            "仅在保持功能与输出语义不变的前提下优化性能、可读性或健壮性，说明优化点并给出优化后代码。"),
    EXPLAIN("explain", "代码讲解",
            "仅讲解现有代码的结构、执行流程、关键语句及输入输出，不重写代码，也不附带补全、诊断或优化方案。" );

    private final String value;
    private final String label;
    private final String instruction;

    CodeAssistType(String value, String label, String instruction) {
        this.value = value;
        this.label = label;
        this.instruction = instruction;
    }

    public String getValue() {
        return value;
    }

    public String getLabel() {
        return label;
    }

    public String getInstruction() {
        return instruction;
    }

    public static Optional<CodeAssistType> fromValue(String value) {
        if (value == null || value.isBlank()) {
            return Optional.empty();
        }
        return Arrays.stream(values())
                .filter(type -> type.value.equals(value.trim()))
                .findFirst();
    }
}
