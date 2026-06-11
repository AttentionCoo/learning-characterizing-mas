package com.it.pojo;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
@TableName("step_resource")
public class StepResourceRel {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long stepId;

    private Long resourceId;

    private BigDecimal relevance;

    private Integer isRecommended;

    private LocalDateTime createTime;
}