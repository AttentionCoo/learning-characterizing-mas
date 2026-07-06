package com.it.service;

import com.it.po.uo.ContDTO;
import com.it.po.vo.AnswerVO;
import com.it.pojo.Talk;
import org.springframework.http.codec.ServerSentEvent;
import reactor.core.publisher.Flux;
import java.util.List;
import java.util.Map;

public interface AIStreamingService {
    // 创建新对话
    Long createNewTalk(Long userId);

    // 断线重连/获取当前流式缓存
    String getResumeContent(Long userId, Long talkId);

    // 核心流式对话（images 为影像识别图片列表，无图片时传 null 或空列表）
    Flux<String> streamChat(Long userId, Long talkId, String question, String token, List<String> images);

    Flux<String> streamChat(Long userId, Long talkId, String question, String token, List<String> images, String reportMode);

    // 获取历史对话内容，返回含 role/content/images 的 DTO 列表
    List<ContDTO> getPreContent(Long userId, Long talkId);

    Talk getTalkById(Long talkId);

    // ============================================================
    // 医学多模态通用转发方法
    // ============================================================

    /** 同步调用 Python 模型层（非流式） */
    String callModelSync(String uri, Map<String, Object> body);

    /** 流式转发到 Python 模型层（SSE） */
    Flux<ServerSentEvent<String>> streamToModel(String uri, Map<String, Object> body, String token);
}