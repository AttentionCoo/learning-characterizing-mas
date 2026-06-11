package com.it.po.uo;

import lombok.Data;

import java.util.List;

@Data
public class ResourceGenerateParam {
    private String talkId;
    private String message;
    private List<String> resourceTypes;
    private String courseName;
    private List<String> knowledgePoints;
    private String difficulty;
    private List<String> images;
}