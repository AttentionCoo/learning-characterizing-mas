package com.learnagent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("evaluation_report")
public class EvalReport {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private Long pathId;

    private String period;

    private Integer overallScore;

    private String level;

    private String dimensions;

    private String strengths;

    private String weaknesses;

    private String suggestions;

    private LocalDateTime createTime;
}