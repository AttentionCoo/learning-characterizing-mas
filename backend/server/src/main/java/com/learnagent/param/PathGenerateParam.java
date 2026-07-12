package com.learnagent.param;

import lombok.Data;

import java.util.List;

@Data
public class PathGenerateParam {
    private String courseName;
    private String goalDescription;
    private String deadline;
    private Integer weeklyHours;
    private List<String> existingKnowledge;
    private List<String> targetKnowledge;
}