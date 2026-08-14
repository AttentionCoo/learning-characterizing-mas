package com.learnagent.service;

import com.baomidou.mybatisplus.spring.service.IService;
import com.learnagent.vo.InitialPageVO;
import com.learnagent.entity.Talk;

import java.util.List;

public interface IInitialPageService extends IService<Talk> {
    List<InitialPageVO> getPage(Long currentId);

    List<InitialPageVO> getPage(Long userId, String conversationType);

    boolean isConversationType(Long userId, Long talkId, String conversationType);

    void deleteTalk(Long userId, Long talkId);
}
