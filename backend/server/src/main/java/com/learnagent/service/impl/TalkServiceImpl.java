package com.learnagent.service.impl;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.learnagent.mapper.TalkMapper;
import com.learnagent.entity.Talk;
import com.learnagent.service.ITalkService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional
public class TalkServiceImpl extends ServiceImpl<TalkMapper, Talk> implements ITalkService {
}
