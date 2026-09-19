package com.learnagent.service.impl;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.learnagent.mapper.StudentProfileMapper;
import com.learnagent.service.IChatMessageService;
import com.learnagent.service.ITalkService;
import org.junit.jupiter.api.Test;
import org.redisson.api.RedissonClient;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;

class AIStreamingServiceImplTest {

    @Test
    void completeReportEventReplacesPreviouslyAccumulatedTokens() throws Exception {
        ObjectMapper objectMapper = new ObjectMapper();
        AIStreamingServiceImpl service = new AIStreamingServiceImpl(
                mock(WebClient.class),
                mock(StringRedisTemplate.class),
                mock(RedissonClient.class),
                mock(ITalkService.class),
                mock(IChatMessageService.class),
                mock(ConversationPersistenceService.class),
                objectMapper,
                mock(StudentProfileMapper.class),
                mock(ProfileUpdateService.class)
        );
        StringBuilder fullAnswer = new StringBuilder();
        String[] title = {null};
        String[] allInfo = {""};

        parse(service, "{\"type\":\"token\",\"content\":\"一、旧内容\"}", title, allInfo, fullAnswer)
                .collectList()
                .block();
        String output = parse(
                service,
                "{\"type\":\"replace\",\"content\":\"一、新内容\\n二、下一项\"}",
                title,
                allInfo,
                fullAnswer
        ).blockFirst();

        JsonNode response = objectMapper.readTree(output);
        assertEquals("一、新内容\n二、下一项", fullAnswer.toString());
        assertEquals("replace", response.path("type").asText());
        assertEquals("一、新内容\n二、下一项", response.path("content").asText());
    }

    @Test
    void textStreamEventsPassThroughWithChannelFields() throws Exception {
        ObjectMapper objectMapper = new ObjectMapper();
        AIStreamingServiceImpl service = newService(objectMapper);

        JsonNode delta = objectMapper.readTree(parse(
                service,
                "{\"type\":\"text_delta\",\"node\":\"reason\",\"channel\":\"expert:需求分析智能体\",\"label\":\"需求分析智能体\",\"delta\":\"先讲清\"}",
                new String[]{null}, new String[]{""}, new StringBuilder()
        ).blockFirst());
        assertEquals("text_delta", delta.path("type").asText());
        assertEquals("expert:需求分析智能体", delta.path("channel").asText());
        assertEquals("需求分析智能体", delta.path("label").asText());
        assertEquals("先讲清", delta.path("delta").asText());

        JsonNode end = objectMapper.readTree(parse(
                service,
                "{\"type\":\"text_end\",\"node\":\"reason\",\"channel\":\"convergence\",\"label\":\"收敛结论\",\"content\":\"三层递进结论\"}",
                new String[]{null}, new String[]{""}, new StringBuilder()
        ).blockFirst());
        assertEquals("text_end", end.path("type").asText());
        assertEquals("convergence", end.path("channel").asText());
        assertEquals("三层递进结论", end.path("content").asText());
    }

    @Test
    void expertSpeechEventPassesThroughWithRoleAndIndex() throws Exception {
        ObjectMapper objectMapper = new ObjectMapper();
        AIStreamingServiceImpl service = newService(objectMapper);

        JsonNode speech = objectMapper.readTree(parse(
                service,
                "{\"type\":\"expert_speech\",\"node\":\"reason\",\"role\":\"医学影像分析智能体\",\"content\":\"NCCT 是溶栓前提\",\"index\":2,\"total\":3}",
                new String[]{null}, new String[]{""}, new StringBuilder()
        ).blockFirst());
        assertEquals("expert_speech", speech.path("type").asText());
        assertEquals("医学影像分析智能体", speech.path("role").asText());
        assertEquals("NCCT 是溶栓前提", speech.path("content").asText());
        assertEquals(2, speech.path("index").asInt());
        assertEquals(3, speech.path("total").asInt());
    }

    @Test
    void agentMsgEventPassesThroughWithEvidence() throws Exception {
        ObjectMapper objectMapper = new ObjectMapper();
        AIStreamingServiceImpl service = newService(objectMapper);

        JsonNode msg = objectMapper.readTree(parse(
                service,
                "{\"type\":\"agent_msg\",\"node\":\"reason\",\"from\":\"需求分析智能体\",\"to\":\"题目生成智能体\",\"round\":1,\"kind\":\"question\",\"content\":\"难度怎么定？\",\"evidence\":\"学生画像显示知识基础偏弱\"}",
                new String[]{null}, new String[]{""}, new StringBuilder()
        ).blockFirst());
        assertEquals("agent_msg", msg.path("type").asText());
        assertEquals("需求分析智能体", msg.path("from").asText());
        assertEquals("题目生成智能体", msg.path("to").asText());
        assertEquals("question", msg.path("kind").asText());
        // 依据必须透传：会诊消息的可审计证据，丢失则前端「依据」行恒空
        assertEquals("学生画像显示知识基础偏弱", msg.path("evidence").asText());
    }

    private AIStreamingServiceImpl newService(ObjectMapper objectMapper) {
        return new AIStreamingServiceImpl(
                mock(WebClient.class),
                mock(StringRedisTemplate.class),
                mock(RedissonClient.class),
                mock(ITalkService.class),
                mock(IChatMessageService.class),
                mock(ConversationPersistenceService.class),
                objectMapper,
                mock(StudentProfileMapper.class),
                mock(ProfileUpdateService.class)
        );
    }

    @SuppressWarnings("unchecked")
    private Flux<String> parse(
            AIStreamingServiceImpl service,
            String line,
            String[] title,
            String[] allInfo,
            StringBuilder fullAnswer
    ) throws Exception {
        Method method = AIStreamingServiceImpl.class.getDeclaredMethod(
                "parseModelLine",
                Long.class,
                String.class,
                Long.class,
                String[].class,
                String[].class,
                StringBuilder.class
        );
        method.setAccessible(true);
        return (Flux<String>) method.invoke(service, 1L, line, 1L, title, allInfo, fullAnswer);
    }
}
