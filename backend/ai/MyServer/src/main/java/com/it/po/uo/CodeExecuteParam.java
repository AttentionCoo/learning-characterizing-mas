package com.it.po.uo;

import lombok.Data;

@Data
public class CodeExecuteParam {
    private String code;
    private String language;
    private Integer timeout;
    private java.util.Map<String, String> inputData;
}