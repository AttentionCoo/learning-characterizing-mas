package com.learnagent.param;

import lombok.Data;

import java.util.Map;

@Data
public class CodeAssistParam {
    private String prompt;
    private String language;
    private Map<String, Object> context;
    private String existingCode;
}