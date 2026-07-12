package com.learnagent.po.uo;

import lombok.Data;

@Data
public class CodeAssistParam {
    private String talkId;
    /** 辅助类型：complete（补全）/ diagnose（诊断）/ optimize（优化）/ explain（讲解） */
    private String assistType;
    private String prompt;
    private String language;
    private String existingCode;
    /** 运行报错信息（诊断场景） */
    private String errorMessage;
}
