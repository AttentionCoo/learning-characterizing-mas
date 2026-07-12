package com.learnagent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDate;
import java.time.LocalDateTime;

@Data
@TableName("learning_path")
public class LearningPath {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private String courseName;

    private String goalDescription;

    private Integer totalSteps;

    private Integer completedSteps;

    private Integer estimatedDays;

    private LocalDate deadline;

    private String status;

    private LocalDateTime createTime;

    private LocalDateTime updateTime;
}