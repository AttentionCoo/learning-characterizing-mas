package com.learnagent.param;

import lombok.Data;

@Data
public class AssessmentGenerateParam {
    private Long pathId;
    private String message;
    private String assessmentType;
    private TimeRange timeRange;
    private String courseName;

    @Data
    public static class TimeRange {
        private String start;
        private String end;
    }
}