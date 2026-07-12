package com.learnagent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.learnagent.dto.User;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface RegiMapper extends BaseMapper<User> {
}
