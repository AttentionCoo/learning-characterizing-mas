package com.learnagent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("learning_resource")
public class LearningResource {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private String title;

    private String type;

    private String courseName;

    private String knowledgePoints;

    private String difficulty;

    private String content;

    private String fileUrl;

    private String metadata;

    private Long talkId;

    private LocalDateTime createTime;

    private LocalDateTime updateTime;
}