package com.learnagent.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.LocalDateTime;

@Data
@TableName("talk")
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class Talk {

    // 关键：前端传入时间戳
    @TableId(type = IdType.INPUT)
    private Long id;

    private Long userId;
    private String title;
    private String content;

    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}