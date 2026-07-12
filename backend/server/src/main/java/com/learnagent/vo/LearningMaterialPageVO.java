package com.learnagent.vo;

import lombok.Data;

import java.util.List;

@Data
public class LearningMaterialPageVO {
    private long                    total;
    private List<LearningMaterialVO> materials;
}
