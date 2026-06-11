package com.it.po.uo;

import lombok.Data;

import java.util.List;
import java.util.Map;

@Data
public class OptimizeParam {
    private Long pathId;
    private String triggerReason;
    private Map<String, Object> evaluationData;
}