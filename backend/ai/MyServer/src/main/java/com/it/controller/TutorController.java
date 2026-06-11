package com.it.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.cache.SSEEventCache;
import com.it.pojo.Result;
import com.it.pojo.Talk;
import com.it.po.uo.QuesParam;
import com.it.po.uo.TutorChatParam;
import com.it.po.vo.InitialPageVO;
import com.it.service.AIStreamingService;
import com.it.service.IInitialPageService;
import com.it.utils.ThreadLocalUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@CrossOrigin("*")
@RequestMapping("/api/tutor")
@RequiredArgsConstructor
public class TutorController {

    private final AIStreamingService streamingService;
    private final ObjectMapper objectMapper;
    private final SSEEventCache eventCache;
    private final IInitialPageService initialPageService;

    @PostMapping(value = "/chat", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> chat(
            @RequestBody TutorChatParam param,
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

        StringBuilder questionBuilder = new StringBuilder(param.getMessage());
        if (param.getMode() != null) {
            questionBuilder.append("\n辅导模式：").append(param.getMode());
        }
        if (param.getResponseFormat() != null) {
            questionBuilder.append("\n回复格式：").append(param.getResponseFormat());
        }
        if (param.getContext() != null) {
            if (param.getContext().getCourseName() != null) {
                questionBuilder.append("\n课程：").append(param.getContext().getCourseName());
            }
            if (param.getContext().getKnowledgePoints() != null) {
                questionBuilder.append("\n知识点：").append(String.join("、", param.getContext().getKnowledgePoints()));
            }
        }
        if (param.getCodeSnippet() != null) {
            questionBuilder.append("\n代码片段：\n").append(param.getCodeSnippet());
        }

        QuesParam quesParam = new QuesParam();
        quesParam.setTalkId(param.getTalkId());
        quesParam.setQuestion(questionBuilder.toString());
        quesParam.setImages(param.getImages());

        return buildSSEStream(userId, quesParam, upstreamToken, lastEventId);
    }

    @PostMapping(value = "/ask", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> ask(
            @RequestBody Map<String, Object> body,
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
        Object message = body.get("message");
        if (message != null) {
            questionBuilder.append(message.toString());
        }
        if (body.get("mode") != null) questionBuilder.append("\n辅导模式：").append(body.get("mode"));
        if (body.get("courseName") != null) questionBuilder.append("\n课程：").append(body.get("courseName"));
        if (body.get("knowledgePoint") != null) questionBuilder.append("\n知识点：").append(body.get("knowledgePoint"));

        QuesParam quesParam = new QuesParam();
        quesParam.setTalkId((String) body.get("talkId"));
        quesParam.setQuestion(questionBuilder.toString());
        @SuppressWarnings("unchecked")
        List<String> images = (List<String>) body.get("images");
        quesParam.setImages(images);

        return buildSSEStream(userId, quesParam, upstreamToken, lastEventId);
    }

    @GetMapping("/conversation/{talkId}")
    public Result getConversationHistory(@PathVariable Long talkId) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        return Result.success(streamingService.getPreContent(userId, talkId));
    }

    @GetMapping("/conversations")
    public Result getConversationList() {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        List<InitialPageVO> talks = initialPageService.getPage(userId);
        return Result.success(talks);
    }

    @DeleteMapping("/conversation/{talkId}")
    public Result deleteConversation(@PathVariable Long talkId) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        initialPageService.deleteTalk(userId, talkId);
        return Result.success();
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
                .streamChat(userId, finalTalkId, quesParam.getQuestion(), upstreamToken, quesParam.getImages())
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