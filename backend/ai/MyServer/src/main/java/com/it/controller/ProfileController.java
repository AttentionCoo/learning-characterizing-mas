package com.it.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.cache.SSEEventCache;
import com.it.pojo.Result;
import com.it.pojo.StudentProfile;
import com.it.pojo.Talk;
import com.it.po.uo.ContDTO;
import com.it.po.uo.ProfileConversationParam;
import com.it.po.uo.QuesParam;
import com.it.po.vo.InitialPageVO;
import com.it.service.AIStreamingService;
import com.it.service.IInitialPageService;
import com.it.mapper.StudentProfileMapper;
import com.it.utils.ThreadLocalUtil;
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
    private final ObjectMapper objectMapper;
    private final SSEEventCache eventCache;
    private final StudentProfileMapper studentProfileMapper;
    private final IInitialPageService initialPageService;
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

        QuesParam quesParam = new QuesParam();
        quesParam.setTalkId(param.getTalkId());
        quesParam.setQuestion(param.getMessage());
        quesParam.setImages(param.getImages());

        return buildSSEStream(userId, quesParam, upstreamToken, lastEventId, "profile_build");
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
        StudentProfile profile = studentProfileMapper.selectOne(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<StudentProfile>()
                        .eq(StudentProfile::getUserId, userId)
        );
        try {
            String dimensionsJson = objectMapper.writeValueAsString(dimensions);
            if (profile == null) {
                profile = new StudentProfile();
                profile.setUserId(userId);
                profile.setDimensions(dimensionsJson);
                profile.setVersion(1);
                profile.setCreateTime(LocalDateTime.now());
                profile.setUpdateTime(LocalDateTime.now());
                studentProfileMapper.insert(profile);
            } else {
                Map<String, Object> existing = objectMapper.readValue(profile.getDimensions(), Map.class);
                existing.putAll(dimensions);
                profile.setDimensions(objectMapper.writeValueAsString(existing));
                profile.setVersion(profile.getVersion() + 1);
                profile.setUpdateTime(LocalDateTime.now());
                studentProfileMapper.updateById(profile);
            }
            return Result.success();
        } catch (Exception e) {
            log.error("更新画像维度失败", e);
            return Result.error("更新画像维度失败");
        }
    }

    @GetMapping("/conversation/{talkId}")
    public Result getConversationHistory(@PathVariable Long talkId) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        List<ContDTO> history = streamingService.getPreContent(userId, talkId);
        return Result.success(history);
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
                                                          String upstreamToken, String lastEventId,
                                                          String reportMode) {
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
            if (dbTalk == null || !dbTalk.getUserId().equals(userId)) {
                needCreate = true;
            }
        }

        if (needCreate) {
            talkId = streamingService.createNewTalk(userId);
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
                .streamChat(userId, finalTalkId, quesParam.getQuestion(), upstreamToken, quesParam.getImages(), reportMode)
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
                List<ContDTO> history = streamingService.getPreContent(userId, talkId);
                if (history == null || history.isEmpty()) {
                    log.info("[profile_update] 对话历史为空，跳过画像更新: userId={}, talkId={}", userId, talkId);
                    return;
                }
                StringBuilder conversationText = new StringBuilder();
                for (ContDTO msg : history) {
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

    private void updateDimensionsInternal(Long userId, Map<String, Object> dimensions) {
        StudentProfile profile = studentProfileMapper.selectOne(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<StudentProfile>()
                        .eq(StudentProfile::getUserId, userId)
        );
        try {
            String dimensionsJson = objectMapper.writeValueAsString(dimensions);
            if (profile == null) {
                profile = new StudentProfile();
                profile.setUserId(userId);
                profile.setDimensions(dimensionsJson);
                profile.setVersion(1);
                profile.setCreateTime(LocalDateTime.now());
                profile.setUpdateTime(LocalDateTime.now());
                studentProfileMapper.insert(profile);
            } else {
                Map<String, Object> existing = objectMapper.readValue(profile.getDimensions(), Map.class);
                existing.putAll(dimensions);
                profile.setDimensions(objectMapper.writeValueAsString(existing));
                profile.setVersion(profile.getVersion() + 1);
                profile.setUpdateTime(LocalDateTime.now());
                studentProfileMapper.updateById(profile);
            }
        } catch (Exception e) {
            log.error("[profile_update] 维度持久化失败: userId={}", userId, e);
        }
    }
}