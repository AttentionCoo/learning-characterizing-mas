package com.it.po.vo;

import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import com.fasterxml.jackson.databind.ser.std.ToStringSerializer;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@AllArgsConstructor
@NoArgsConstructor
public class InitialPageVO {
    @JsonSerialize(using = ToStringSerializer.class)
    private Long talkId;
    private String title;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}