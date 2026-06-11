package com.it.po.uo;

import lombok.Data;

import java.util.List;

@Data
public class BehaviorSubmitParam {
    private Long pathId;
    private Long stepId;
    private List<BehaviorItem> behaviors;

    @Data
    public static class BehaviorItem {
        private String type;
        private Long resourceId;
        private Integer duration;
        private java.math.BigDecimal score;
        private String timestamp;
    }
}