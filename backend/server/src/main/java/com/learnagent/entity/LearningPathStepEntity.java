package com.learnagent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
@TableName("learning_path_step")
public class LearningPathStepEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long pathId;

    private Integer orderIndex;

    private String title;

    private String description;

    private String knowledgePoints;

    private BigDecimal estimatedHours;

    private String difficulty;

    private String status;

    private BigDecimal actualHours;

    private String feedback;

    private Integer selfRating;

    private String prerequisites;

    private LocalDateTime createTime;

    private LocalDateTime updateTime;
}