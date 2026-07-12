package com.it.po.uo;

import lombok.Data;

@Data
public class CodeExecuteParam {
    private String code;
    private String language;
    private Integer timeout;
    /** 标准输入内容，逐行喂给沙箱内程序的 stdin */
    private String inputData;
}
