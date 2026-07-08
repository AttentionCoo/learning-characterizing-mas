package com.learnagent.param;
import lombok.Data;

import java.util.List;

@Data
public class QuesParam {
    private String talkId;
    private String question;
    /** 影像识别：Base64 图片列表，最�?3 张，每张不超�?10MB（新增字段） */
    private List<String> images;
}
