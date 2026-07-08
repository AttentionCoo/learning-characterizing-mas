package com.learnagent.param;

import lombok.Data;

import java.util.List;

/**
 * 医学多模态影像分析请求参�? * Medical Multimodal Image Analysis Request Param
 */
@Data
public class MedicalImageParam {

    /** Base64编码的医学影像列�?*/
    private List<String> images;

    /** 用户问题/病例描述 */
    private String question;

    /** 学生画像信息（可选） */
    private String allInfo;

    /** 期望的影像类型（为空则自动检测） */
    private String expectedImageType;

    /** 病例类型: stroke/neuro/general */
    private String caseType = "general";

    /** 是否检索循证证�?*/
    private Boolean includeEvidence = true;

    /** 对话ID（可选） */
    private String talkId;

    /** 用户问题（同question，兼容旧接口�?*/
    private String message;
}
