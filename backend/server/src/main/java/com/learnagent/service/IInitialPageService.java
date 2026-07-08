package com.learnagent.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.learnagent.vo.InitialPageVO;
import com.learnagent.entity.Talk;

import java.util.List;

public interface IInitialPageService extends IService<Talk> {
    List<InitialPageVO> getPage(Long currentId);

    void deleteTalk(Long userId, Long talkId);
}
