package com.learnagent.service.impl;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.learnagent.service.IContService;
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
                mock(IContService.class),
                mock(ConversationPersistenceService.class),
                objectMapper
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
                String.class,
                Long.class,
                String[].class,
                String[].class,
                StringBuilder.class
        );
        method.setAccessible(true);
        return (Flux<String>) method.invoke(service, line, 1L, title, allInfo, fullAnswer);
    }
}
