package com.it.po.uo;

import lombok.Data;

import java.util.List;
import java.util.Map;

@Data
public class PathAdjustParam {
    private String reason;
    private Map<String, Object> adjustmentData;
}