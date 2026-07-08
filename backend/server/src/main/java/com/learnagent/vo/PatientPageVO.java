package com.learnagent.vo;

import lombok.Data;

import java.util.List;

/** 病人分页列表响应 */
@Data
public class PatientPageVO {

    private Long total;

    private List<PatientVO> patients;
}
