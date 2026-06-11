package com.it.po.uo;

import lombok.Data;

import java.util.List;

@Data
public class TutorChatParam {
    private String talkId;
    private String message;
    private String mode;
    private String responseFormat;
    private TutorContext context;
    private List<String> images;
    private String codeSnippet;

    @Data
    public static class TutorContext {
        private String courseName;
        private List<String> knowledgePoints;
        private Long relatedQuizId;
        private Long relatedCodePracticeId;
    }
}