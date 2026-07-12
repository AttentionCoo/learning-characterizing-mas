package com.it.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.cache.SSEEventCache;
import com.it.pojo.Result;
import com.it.pojo.Talk;
import com.it.po.uo.CodeAssistParam;
import com.it.po.uo.CodeExecuteParam;
import com.it.po.uo.QuesParam;
import com.it.service.AIStreamingService;
import com.it.utils.ThreadLocalUtil;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

/**
 * 代码辅助开发模块：
 * - /execute 代理 Python 沙箱执行接口（非流式）
 * - /assist 走统一多智能体 SSE 管道（report_mode=code_assist）
 */
@Slf4j
@RestController
@CrossOrigin("*")
@RequestMapping("/api/code")
@RequiredArgsConstructor
public class CodeController {

    private final WebClient webClient;
    private final ObjectMapper objectMapper;
    private final AIStreamingService streamingService;
    private final SSEEventCache eventCache;

    @PostMapping("/execute")
    public Result execute(@RequestBody CodeExecuteParam param) {
        if (ThreadLocalUtil.getCurrentUser() == null) {
            return Result.error("未登录");
        }
        if (param.getCode() == null || param.getCode().isBlank()) {
            return Result.error("代码内容为空");
        }

        Map<String, Object> body = new HashMap<>();
        body.put("code", param.getCode());
        body.put("language", param.getLanguage() != null ? param.getLanguage() : "python");
        body.put("timeout", param.getTimeout() != null ? param.getTimeout() : 30);
        if (param.getInputData() != null) {
            body.put("input_data", param.getInputData());
        }

        try {
            String responseStr = webClient.post()
                    .uri("/model/code/execute")
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(body)
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(Duration.ofMinutes(2))
                    .block();

            JsonNode root = objectMapper.readTree(responseStr);
            if (root.path("code").asInt(0) != 1) {
                return Result.error(root.path("msg").asText("代码执行失败"));
            }
            return Result.success(objectMapper.convertValue(root.path("data"), Object.class));
        } catch (Exception e) {
            log.error("代码执行失败: {}", e.getMessage(), e);
            return Result.error("代码执行失败：" + e.getMessage());
        }
    }

    @PostMapping(value = "/assist", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> assist(
            @RequestBody CodeAssistParam param,
            @RequestHeader(value = "token", required = false) String token,
            @RequestHeader(value = "Authorization", required = false) String authorization,
            @RequestHeader(value = "Last-Event-ID", required = false) String lastEventId,
            HttpServletResponse response
    ) {
        response.setHeader("X-Accel-Buffering", "no");
        response.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");

        if (ThreadLocalUtil.getCurrentUser() == null) {
            return Flux.just(sse("error", json("error", mapOf("message", "未登录"))));
        }

        String upstreamToken = resolveToken(token, authorization);
        Long userId = ThreadLocalUtil.getCurrentUser().getId();

        StringBuilder questionBuilder = new StringBuilder();
        if (param.getAssistType() != null) {
            questionBuilder.append("辅助类型：").append(resolveAssistTypeLabel(param.getAssistType()));
        }
        if (param.getPrompt() != null && !param.getPrompt().isBlank()) {
            questionBuilder.append("\n诉求：").append(param.getPrompt());
        }
        questionBuilder.append("\n语言：").append(param.getLanguage() != null ? param.getLanguage() : "python");
        if (param.getExistingCode() != null && !param.getExistingCode().isBlank()) {
            questionBuilder.append("\n现有代码：\n```python\n").append(param.getExistingCode()).append("\n```");
        }
        if (param.getErrorMessage() != null && !param.getErrorMessage().isBlank()) {
            questionBuilder.append("\n运行报错：\n```\n").append(param.getErrorMessage()).append("\n```");
        }

        QuesParam quesParam = new QuesParam();
        quesParam.setTalkId(param.getTalkId());
        quesParam.setQuestion(questionBuilder.toString());

        return buildSSEStream(userId, quesParam, upstreamToken, lastEventId);
    }

    private String resolveAssistTypeLabel(String assistType) {
        return switch (assistType) {
            case "complete" -> "代码补全";
            case "diagnose" -> "错误诊断";
            case "optimize" -> "优化建议";
            case "explain" -> "代码讲解";
            default -> assistType;
        };
    }

    private Flux<ServerSentEvent<String>> buildSSEStream(Long userId, QuesParam quesParam,
                                                          String upstreamToken, String lastEventId) {
        String talkIdStr = quesParam.getTalkId();
        Long talkId = null;
        if (talkIdStr != null && !talkIdStr.isBlank()) {
            try {
                talkId = Long.parseLong(talkIdStr);
                if (talkId <= 0) talkId = null;
            } catch (NumberFormatException e) {
                talkId = null;
            }
        }

        boolean needCreate = (talkId == null || talkId <= 0);
        if (!needCreate) {
            Talk dbTalk = streamingService.getTalkById(talkId);
            if (dbTalk == null || !dbTalk.getUserId().equals(userId)) needCreate = true;
        }
        if (needCreate) talkId = streamingService.createNewTalk(userId);

        final Long finalTalkId = talkId;
        final boolean finalNeedCreate = needCreate;
        final String finalTalkIdStr = String.valueOf(finalTalkId);

        if (lastEventId != null && !lastEventId.isBlank()) {
            int colonIdx = lastEventId.lastIndexOf(':');
            if (colonIdx > 0) {
                String idTalkId = lastEventId.substring(0, colonIdx);
                try {
                    long lastSeq = Long.parseLong(lastEventId.substring(colonIdx + 1));
                    return handleReconnect(idTalkId, lastSeq, finalTalkId, finalTalkIdStr);
                } catch (NumberFormatException ignored) {}
            }
        }

        Flux<String> initFlux = Flux.just(
                json("init", mapOf("talkId", finalTalkId.toString(), "newTalk", finalNeedCreate))
        );
        eventCache.registerStream(finalTalkIdStr);

        Flux<String> chatFlux = streamingService
                .streamChat(userId, finalTalkId, quesParam.getQuestion(), upstreamToken, quesParam.getImages(), "code_assist")
                .map(this::wrapChunkIfNeeded);

        Sinks.One<Void> doneSink = Sinks.one();

        Flux<ServerSentEvent<String>> initSSE = initFlux.map(data -> sse(resolveEventName(data), data));
        Flux<ServerSentEvent<String>> chatSSE = chatFlux
                .onErrorResume(e -> Flux.just(
                        json("error", mapOf("talkId", finalTalkIdStr, "message", e.getMessage() == null ? "stream error" : e.getMessage())),
                        json("done", mapOf("talkId", finalTalkIdStr, "name", "异常结束"))
                ))
                .map(data -> {
                    long seq = eventCache.addEvent(finalTalkIdStr, data);
                    return sseWithId(finalTalkIdStr + ":" + seq, resolveEventName(data), data);
                });

        Flux<ServerSentEvent<String>> dataStream = initSSE
                .concatWith(chatSSE)
                .doFinally(signal -> {
                    doneSink.tryEmitEmpty();
                    eventCache.completeStream(finalTalkIdStr);
                });

        Flux<ServerSentEvent<String>> heartbeatFlux = Flux.interval(Duration.ofSeconds(15))
                .map(i -> ServerSentEvent.<String>builder().comment("heartbeat").build())
                .takeUntilOther(doneSink.asMono());

        Flux<ServerSentEvent<String>> closeFlux = Mono.<ServerSentEvent<String>>just(
                ServerSentEvent.<String>builder().comment("close").build()
        ).delayElement(Duration.ofMillis(500)).flux();

        return Flux.merge(dataStream, heartbeatFlux).concatWith(closeFlux);
    }

    private Flux<ServerSentEvent<String>> handleReconnect(String idTalkId, long lastSeq, Long finalTalkId, String finalTalkIdStr) {
        if (!finalTalkIdStr.equals(idTalkId)) {
            return Flux.just(sse("error", json("error", mapOf("code", "E2004", "message", "talkId 不匹配"))));
        }
        Flux<SSEEventCache.SequencedEvent> replayStream = eventCache.getReplayStream(finalTalkIdStr, lastSeq);
        if (replayStream == null) {
            return Flux.just(
                    sseWithId(finalTalkIdStr + ":0", "error", json("error", mapOf("code", "E2003", "message", "会话缓存已过期"))),
                    sse("done", json("done", mapOf("talkId", finalTalkIdStr, "name", "")))
            );
        }
        Sinks.One<Void> doneSink = Sinks.one();
        Flux<ServerSentEvent<String>> replaySSE = replayStream
                .map(se -> sseWithId(finalTalkIdStr + ":" + se.seq(), resolveEventName(se.data()), se.data()))
                .doFinally(signal -> doneSink.tryEmitEmpty());
        Flux<ServerSentEvent<String>> heartbeatFlux = Flux.interval(Duration.ofSeconds(15))
                .map(i -> ServerSentEvent.<String>builder().comment("heartbeat").build())
                .takeUntilOther(doneSink.asMono());
        Flux<ServerSentEvent<String>> closeFlux = Mono.<ServerSentEvent<String>>just(
                ServerSentEvent.<String>builder().comment("close").build()
        ).delayElement(Duration.ofMillis(500)).flux();
        return Flux.merge(replaySSE, heartbeatFlux).concatWith(closeFlux);
    }

    private ServerSentEvent<String> sse(String event, String data) { return ServerSentEvent.<String>builder().event(event).data(data).build(); }
    private ServerSentEvent<String> sseWithId(String id, String event, String data) { return ServerSentEvent.<String>builder().id(id).event(event).data(data).build(); }
    private String resolveEventName(String data) { if (data == null || data.isBlank()) return "message"; try { return objectMapper.readTree(data).path("type").asText("message"); } catch (Exception e) { return "message"; } }
    private String wrapChunkIfNeeded(String data) { if (data == null) return json("chunk", mapOf("content", "")); String trimmed = data.trim(); if (!trimmed.isEmpty() && trimmed.startsWith("{") && trimmed.endsWith("}")) return data; return json("chunk", mapOf("content", data)); }
    private String resolveToken(String token, String authorization) { if (token != null && !token.isBlank()) return token.trim(); if (authorization != null && !authorization.isBlank()) { String v = authorization.trim(); return v.startsWith("Bearer ") ? v.substring(7).trim() : v; } return null; }
    private String json(String type, Map<String, Object> payload) { try { Map<String, Object> root = new HashMap<>(); root.put("type", type); if (payload != null && !payload.isEmpty()) root.putAll(payload); return objectMapper.writeValueAsString(root); } catch (Exception e) { return "{\"type\":\"error\",\"message\":\"json serialize error\"}"; } }
    private Map<String, Object> mapOf(Object k1, Object v1) { Map<String, Object> m = new HashMap<>(); m.put(String.valueOf(k1), v1); return m; }
    private Map<String, Object> mapOf(Object k1, Object v1, Object k2, Object v2) { Map<String, Object> m = new HashMap<>(); m.put(String.valueOf(k1), v1); m.put(String.valueOf(k2), v2); return m; }
}
