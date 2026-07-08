package com.learnagent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.learnagent.vo.InitialPageVO;
import com.learnagent.entity.Talk;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface InitialPageMapper extends BaseMapper<Talk> {
//    //@Select("select id as talkId, title from talk where user_id=#{currentId} order by create_time desc")
//    List<InitialPageVO> getPage(Integer currentId);
//
//
//    void deleteTalk(Integer userId, Integer talkId);
}
