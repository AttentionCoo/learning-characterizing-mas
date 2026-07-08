package com.learnagent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
@TableName("learning_behavior")
public class LearningBehaviorRecord {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private Long pathId;

    private Long stepId;

    private Long resourceId;

    private String behaviorType;

    private Integer duration;

    private BigDecimal score;

    private String detail;

    private LocalDateTime createTime;
}