package com.learnagent.service.impl;

import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.learnagent.mapper.ChatMessageMapper;
import com.learnagent.mapper.TalkMapper;
import com.learnagent.dto.ChatMessage;
import com.learnagent.entity.Talk;
import com.learnagent.service.IChatMessageService;
import com.learnagent.service.ITalkService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional
public class ChatMessageServiceImpl extends ServiceImpl<ChatMessageMapper, ChatMessage> implements IChatMessageService {
}
