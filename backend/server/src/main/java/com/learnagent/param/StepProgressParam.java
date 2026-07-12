package com.learnagent.param;

import lombok.Data;

@Data
public class StepProgressParam {
    private String status;
    private java.math.BigDecimal actualHours;
    private String feedback;
    private Integer selfRating;
}