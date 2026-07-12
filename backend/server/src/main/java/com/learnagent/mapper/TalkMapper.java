package com.learnagent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.learnagent.entity.Talk;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface TalkMapper extends BaseMapper<Talk> {
}
