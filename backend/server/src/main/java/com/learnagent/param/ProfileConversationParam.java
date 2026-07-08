package com.learnagent.param;

import lombok.Data;

import java.util.List;

@Data
public class ProfileConversationParam {
    private String talkId;
    private String message;
    private List<String> images;
}