package com.learnagent.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.learnagent.cache.SSEEventCache;
import com.learnagent.entity.Result;
import com.learnagent.entity.StudentProfile;
import com.learnagent.entity.Talk;
import com.learnagent.dto.ChatMessageDTO;
import com.learnagent.param.ProfileConversationParam;
import com.learnagent.param.QuestionParam;
import com.learnagent.service.AIStreamingService;
import com.learnagent.service.impl.ProfileUpdateService;
import com.learnagent.mapper.StudentProfileMapper;
import com.learnagent.utils.ThreadLocalUtil;
import com.learnagent.utils.ConversationType;
import com.learnagent.utils.ProfileMergePolicy;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;
import reactor.core.scheduler.Schedulers;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@CrossOrigin("*")
@RequestMapping("/api/profile")
@RequiredArgsConstructor
public class ProfileController {

    private final AIStreamingService streamingService;
    private final ProfileUpdateService profileUpdateService;
    private final ObjectMapper objectMapper;
    private final SSEEventCache eventCache;
    private final StudentProfileMapper studentProfileMapper;
    private final WebClient webClient;

    @PostMapping(value = "/conversation", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> conversation(
            @RequestBody ProfileConversationParam param,
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

        QuestionParam questionParam = new QuestionParam();
        questionParam.setTalkId(param.getTalkId());
        questionParam.setQuestion(param.getMessage());
        questionParam.setImages(param.getImages());

        return buildSSEStream(userId, questionParam, upstreamToken, lastEventId, "profile_build");
    }

    @GetMapping
    public Result getProfile() {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        StudentProfile profile = studentProfileMapper.selectOne(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<StudentProfile>()
                        .eq(StudentProfile::getUserId, userId)
                        .orderByDesc(StudentProfile::getUpdateTime)
                        .last("LIMIT 1")
        );
        if (profile == null) {
            return Result.success(null);
        }
        try {
            Map<String, Object> data = new HashMap<>();
            data.put("profileId", profile.getId());
            data.put("userId", profile.getUserId());
            data.put("dimensions", objectMapper.readValue(profile.getDimensions(), Map.class));
            data.put("rawConversationSummary", profile.getRawSummary());
            data.put("updateTime", profile.getUpdateTime());
            data.put("createTime", profile.getCreateTime());
            return Result.success(data);
        } catch (Exception e) {
            log.error("解析画像维度数据失败", e);
            return Result.error("画像数据格式异常");
        }
    }

    @PutMapping("/dimensions")
    public Result updateDimensions(@RequestBody Map<String, Object> dimensions) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        try {
            // 用户手动编辑 = 用户确认的事实，统一打上 confirmed 证据链元数据
            for (Map.Entry<String, Object> entry : dimensions.entrySet()) {
                if (entry.getValue() instanceof Map) {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> value = (Map<String, Object>) entry.getValue();
                    entry.setValue(ProfileMergePolicy.asUserConfirmed(value));
                }
            }
            updateDimensionsInternal(userId, dimensions);
            return Result.success();
        } catch (Exception e) {
            log.error("更新画像维度失败", e);
            return Result.error("更新画像维度失败");
        }
    }

    private Flux<ServerSentEvent<String>> buildSSEStream(Long userId, QuestionParam questionParam,
                                                          String upstreamToken, String lastEventId,
                                                          String reportMode) {
        String talkIdStr = questionParam.getTalkId();
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
            if (dbTalk == null || !dbTalk.getUserId().equals(userId)
                    || !ConversationType.matches(dbTalk.getContent(), ConversationType.PROFILE)) {
                needCreate = true;
            }
        }

        if (needCreate) {
            talkId = streamingService.createNewTalk(userId, ConversationType.PROFILE);
        }

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
                } catch (NumberFormatException ignored) {
                }
            }
        }

        Flux<String> initFlux = Flux.just(
                json("init", mapOf("talkId", finalTalkId.toString(), "newTalk", finalNeedCreate))
        );

        eventCache.registerStream(finalTalkIdStr);

        Flux<String> chatFlux = streamingService
                .streamChat(userId, finalTalkId, questionParam.getQuestion(), upstreamToken, questionParam.getImages(), reportMode)
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
                    if ("profile_build".equals(reportMode)) {
                        triggerProfileUpdate(userId, finalTalkId);
                    }
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

    private ServerSentEvent<String> sse(String event, String data) {
        return ServerSentEvent.<String>builder().event(event).data(data).build();
    }

    private ServerSentEvent<String> sseWithId(String id, String event, String data) {
        return ServerSentEvent.<String>builder().id(id).event(event).data(data).build();
    }

    private String resolveEventName(String data) {
        if (data == null || data.isBlank()) return "message";
        try {
            return objectMapper.readTree(data).path("type").asText("message");
        } catch (Exception e) {
            return "message";
        }
    }

    private String wrapChunkIfNeeded(String data) {
        if (data == null) return json("chunk", mapOf("content", ""));
        String trimmed = data.trim();
        if (!trimmed.isEmpty() && trimmed.startsWith("{") && trimmed.endsWith("}")) return data;
        return json("chunk", mapOf("content", data));
    }

    private String resolveToken(String token, String authorization) {
        if (token != null && !token.isBlank()) return token.trim();
        if (authorization != null && !authorization.isBlank()) {
            String v = authorization.trim();
            return v.startsWith("Bearer ") ? v.substring(7).trim() : v;
        }
        return null;
    }

    private String json(String type, Map<String, Object> payload) {
        try {
            Map<String, Object> root = new HashMap<>();
            root.put("type", type);
            if (payload != null && !payload.isEmpty()) root.putAll(payload);
            return objectMapper.writeValueAsString(root);
        } catch (Exception e) {
            return "{\"type\":\"error\",\"message\":\"json serialize error\"}";
        }
    }

    private Map<String, Object> mapOf(Object k1, Object v1) {
        Map<String, Object> m = new HashMap<>();
        m.put(String.valueOf(k1), v1);
        return m;
    }

    private Map<String, Object> mapOf(Object k1, Object v1, Object k2, Object v2) {
        Map<String, Object> m = new HashMap<>();
        m.put(String.valueOf(k1), v1);
        m.put(String.valueOf(k2), v2);
        return m;
    }

    private void triggerProfileUpdate(Long userId, Long talkId) {
        Mono.fromRunnable(() -> {
            try {
                List<ChatMessageDTO> history = streamingService.getPreContent(userId, talkId);
                if (history == null || history.isEmpty()) {
                    log.info("[profile_update] 对话历史为空，跳过画像更新: userId={}, talkId={}", userId, talkId);
                    return;
                }
                StringBuilder conversationText = new StringBuilder();
                for (ChatMessageDTO msg : history) {
                    conversationText.append(msg.getRole()).append(": ").append(msg.getContent()).append("\n");
                }

                Map<String, Object> requestBody = new HashMap<>();
                requestBody.put("conversation", conversationText.toString());
                requestBody.put("userId", userId);

                String responseJson = webClient.post()
                        .uri("/model/profile/extract")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .bodyValue(requestBody)
                        .retrieve()
                        .bodyToMono(String.class)
                        .block(Duration.ofSeconds(60));

                if (responseJson == null || responseJson.isEmpty()) {
                    log.warn("[profile_update] Python 画像解析返回空: userId={}", userId);
                    return;
                }

                com.fasterxml.jackson.databind.JsonNode root = objectMapper.readTree(responseJson);
                com.fasterxml.jackson.databind.JsonNode dimensionsNode = root.path("data").path("dimensions");
                if (dimensionsNode.isMissingNode() || !dimensionsNode.isObject()) {
                    log.warn("[profile_update] Python 画像解析返回无维度数据: userId={}", userId);
                    return;
                }

                Map<String, Object> dimensions = objectMapper.convertValue(dimensionsNode, new com.fasterxml.jackson.core.type.TypeReference<Map<String, Object>>() {});
                updateDimensionsInternal(userId, dimensions);
                log.info("[profile_update] 画像自动更新成功: userId={}, 维度数={}", userId, dimensions.size());
            } catch (Exception e) {
                log.error("[profile_update] 画像自动更新失败: userId={}, talkId={}, err={}", userId, talkId, e.getMessage(), e);
            }
        }).subscribeOn(Schedulers.boundedElastic()).subscribe();
    }

    /**
     * knowledgeBase 特殊合并：维度级字段按证据策略覆盖，但 topics 子主题逐项合并——
     * 新观测到"MCA weak"不应抹掉既有的"Willis环 ok"。
     */
    @SuppressWarnings("unchecked")
    private Map<String, Object> mergeKnowledgeBase(Map<String, Object> existing,
                                                   Map<String, Object> incoming) {
        Map<String, Object> merged = new HashMap<>(existing);
        // 维度级字段（level/description/masteredTopics/weakTopics 等）按策略覆盖
        if (ProfileMergePolicy.shouldApply(existing, incoming)) {
            Map<String, Object> incomingCopy = new HashMap<>(incoming);
            incomingCopy.remove("topics");
            merged.putAll(incomingCopy);
        }
        // 子主题逐项合并
        Object incomingTopics = incoming.get("topics");
        if (incomingTopics instanceof Map) {
            Map<String, Object> mergedTopics = new HashMap<>();
            Object existingTopics = existing.get("topics");
            if (existingTopics instanceof Map) {
                mergedTopics.putAll((Map<String, Object>) existingTopics);
            }
            for (Map.Entry<String, Object> entry :
                    ((Map<String, Object>) incomingTopics).entrySet()) {
                Object topicIn = entry.getValue();
                Object topicEx = mergedTopics.get(entry.getKey());
                if (topicIn instanceof Map && topicEx instanceof Map) {
                    if (ProfileMergePolicy.shouldApply(
                            (Map<String, Object>) topicEx,
                            (Map<String, Object>) topicIn)) {
                        mergedTopics.put(entry.getKey(), topicIn);
                    }
                } else {
                    mergedTopics.put(entry.getKey(), topicIn);
                }
            }
            merged.put("topics", mergedTopics);
        }
        return merged;
    }

    private void updateDimensionsInternal(Long userId, Map<String, Object> dimensions) {
        profileUpdateService.mergeAndSave(userId, dimensions);
    }
}
