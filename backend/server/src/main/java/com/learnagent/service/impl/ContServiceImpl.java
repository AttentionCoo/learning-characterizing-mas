package com.learnagent.service.impl;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.learnagent.mapper.ContMapper;
import com.learnagent.mapper.TalkMapper;
import com.learnagent.dto.Cont;
import com.learnagent.entity.Talk;
import com.learnagent.service.IContService;
import com.learnagent.service.ITalkService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional
public class ContServiceImpl extends ServiceImpl<ContMapper, Cont> implements IContService {
}
