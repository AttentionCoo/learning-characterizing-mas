package com.it.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.cache.SSEEventCache;
import com.it.mapper.LearningResourceMapper;
import com.it.pojo.LearningResource;
import com.it.pojo.Result;
import com.it.pojo.Talk;
import com.it.po.uo.QuesParam;
import com.it.po.uo.ResourceGenerateParam;
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
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@CrossOrigin("*")
@RequestMapping("/api/resources")
@RequiredArgsConstructor
public class ResourceController {

    private final AIStreamingService streamingService;
    private final ObjectMapper objectMapper;
    private final SSEEventCache eventCache;
    private final LearningResourceMapper learningResourceMapper;
    private final IInitialPageService initialPageService;

    @PostMapping(value = "/generate", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> generate(
            @RequestBody ResourceGenerateParam param,
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
        if (param.getCourseName() != null) {
            questionBuilder.append("\n课程：").append(param.getCourseName());
        }
        if (param.getKnowledgePoints() != null && !param.getKnowledgePoints().isEmpty()) {
            questionBuilder.append("\n知识点：").append(String.join("、", param.getKnowledgePoints()));
        }
        if (param.getDifficulty() != null) {
            questionBuilder.append("\n难度：").append(param.getDifficulty());
        }
        if (param.getResourceTypes() != null && !param.getResourceTypes().isEmpty()) {
            questionBuilder.append("\n资源类型：").append(String.join("、", param.getResourceTypes()));
        }

        QuesParam quesParam = new QuesParam();
        quesParam.setTalkId(param.getTalkId());
        quesParam.setQuestion(questionBuilder.toString());
        quesParam.setImages(param.getImages());

        return buildSSEStream(userId, quesParam, upstreamToken, lastEventId);
    }

    @GetMapping
    public Result getResourceList(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) String type,
            @RequestParam(required = false) String courseName,
            @RequestParam(required = false) String difficulty) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        LambdaQueryWrapper<LearningResource> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(LearningResource::getUserId, userId);
        if (type != null && !type.isEmpty()) {
            wrapper.eq(LearningResource::getType, type);
        }
        if (courseName != null && !courseName.isEmpty()) {
            wrapper.eq(LearningResource::getCourseName, courseName);
        }
        if (difficulty != null && !difficulty.isEmpty()) {
            wrapper.eq(LearningResource::getDifficulty, difficulty);
        }
        wrapper.orderByDesc(LearningResource::getCreateTime);

        Page<LearningResource> pageResult = learningResourceMapper.selectPage(new Page<>(page, size), wrapper);
        List<Map<String, Object>> records = pageResult.getRecords().stream().map(r -> {
            Map<String, Object> m = new HashMap<>();
            m.put("resourceId", r.getId());
            m.put("title", r.getTitle());
            m.put("type", r.getType());
            m.put("courseName", r.getCourseName());
            m.put("difficulty", r.getDifficulty());
            m.put("knowledgePoints", r.getKnowledgePoints());
            m.put("fileUrl", r.getFileUrl());
            m.put("createTime", r.getCreateTime());
            return m;
        }).toList();

        Map<String, Object> data = new HashMap<>();
        data.put("total", pageResult.getTotal());
        data.put("records", records);
        return Result.success(data);
    }

    @GetMapping("/{id}")
    public Result getResourceDetail(@PathVariable Long id) {
        LearningResource r = learningResourceMapper.selectById(id);
        if (r == null) {
            return Result.error("资源不存在");
        }
        Map<String, Object> data = new HashMap<>();
        data.put("resourceId", r.getId());
        data.put("title", r.getTitle());
        data.put("type", r.getType());
        data.put("courseName", r.getCourseName());
        data.put("difficulty", r.getDifficulty());
        data.put("knowledgePoints", r.getKnowledgePoints());
        data.put("content", r.getContent());
        data.put("fileUrl", r.getFileUrl());
        data.put("metadata", r.getMetadata());
        data.put("createTime", r.getCreateTime());
        data.put("updateTime", r.getUpdateTime());
        return Result.success(data);
    }

    @GetMapping("/{id}/download")
    public Result downloadResource(@PathVariable Long id) {
        LearningResource r = learningResourceMapper.selectById(id);
        if (r == null) {
            return Result.error("资源不存在");
        }
        Map<String, Object> data = new HashMap<>();
        data.put("resourceId", r.getId());
        data.put("previewUrl", r.getFileUrl());
        data.put("downloadUrl", r.getFileUrl());
        return Result.success(data);
    }

    @DeleteMapping("/{id}")
    public Result deleteResource(@PathVariable Long id) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        LearningResource r = learningResourceMapper.selectById(id);
        if (r == null || !r.getUserId().equals(userId)) {
            return Result.error("资源不存在或无权限");
        }
        learningResourceMapper.deleteById(id);
        return Result.success();
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

    @PostMapping(value = "/generate/document", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @SuppressWarnings("unchecked")
    public Flux<ServerSentEvent<String>> generateDocument(
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

        StringBuilder questionBuilder = new StringBuilder("请生成课程讲解文档：");
        appendIfNotNull(questionBuilder, "课程", body.get("courseName"));
        appendListIfNotNull(questionBuilder, "知识点", (List<String>) body.get("knowledgePoints"));
        appendIfNotNull(questionBuilder, "难度", body.get("difficulty"));
        appendIfNotNull(questionBuilder, "风格", body.get("style"));
        if (Boolean.TRUE.equals(body.get("profileAware"))) {
            questionBuilder.append("\n请结合我的学习画像进行个性化生成");
        }

        QuesParam quesParam = new QuesParam();
        quesParam.setTalkId((String) body.get("talkId"));
        quesParam.setQuestion(questionBuilder.toString());
        quesParam.setImages((List<String>) body.get("images"));
        return buildSSEStream(userId, quesParam, upstreamToken, lastEventId);
    }

    @PostMapping(value = "/generate/mindmap", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @SuppressWarnings("unchecked")
    public Flux<ServerSentEvent<String>> generateMindmap(
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

        StringBuilder questionBuilder = new StringBuilder("请生成知识点思维导图：");
        appendIfNotNull(questionBuilder, "课程", body.get("courseName"));
        appendListIfNotNull(questionBuilder, "知识点", (List<String>) body.get("knowledgePoints"));
        appendIfNotNull(questionBuilder, "格式", body.get("format"));
        appendIfNotNull(questionBuilder, "展开层级", body.get("depth"));

        QuesParam quesParam = new QuesParam();
        quesParam.setTalkId((String) body.get("talkId"));
        quesParam.setQuestion(questionBuilder.toString());
        return buildSSEStream(userId, quesParam, upstreamToken, lastEventId);
    }

    @PostMapping(value = "/generate/quiz", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @SuppressWarnings("unchecked")
    public Flux<ServerSentEvent<String>> generateQuiz(
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

        StringBuilder questionBuilder = new StringBuilder("请生成练习题目：");
        appendIfNotNull(questionBuilder, "课程", body.get("courseName"));
        appendListIfNotNull(questionBuilder, "知识点", (List<String>) body.get("knowledgePoints"));
        appendIfNotNull(questionBuilder, "难度", body.get("difficulty"));
        appendListIfNotNull(questionBuilder, "题目类型", (List<String>) body.get("quizTypes"));
        appendIfNotNull(questionBuilder, "题目数量", body.get("count"));
        appendIfNotNull(questionBuilder, "是否包含答案", body.get("includeAnswer"));

        QuesParam quesParam = new QuesParam();
        quesParam.setTalkId((String) body.get("talkId"));
        quesParam.setQuestion(questionBuilder.toString());
        return buildSSEStream(userId, quesParam, upstreamToken, lastEventId);
    }

    @PostMapping(value = "/generate/reading", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @SuppressWarnings("unchecked")
    public Flux<ServerSentEvent<String>> generateReading(
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

        StringBuilder questionBuilder = new StringBuilder("请生成拓展阅读材料：");
        appendIfNotNull(questionBuilder, "课程", body.get("courseName"));
        appendListIfNotNull(questionBuilder, "知识点", (List<String>) body.get("knowledgePoints"));
        appendIfNotNull(questionBuilder, "阅读类型", body.get("readingType"));
        appendIfNotNull(questionBuilder, "语言", body.get("language"));
        appendIfNotNull(questionBuilder, "数量", body.get("count"));

        QuesParam quesParam = new QuesParam();
        quesParam.setTalkId((String) body.get("talkId"));
        quesParam.setQuestion(questionBuilder.toString());
        return buildSSEStream(userId, quesParam, upstreamToken, lastEventId);
    }

    @PostMapping(value = "/generate/video-script", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> generateVideoScript(
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

        StringBuilder questionBuilder = new StringBuilder("请生成教学视频/动画脚本：");
        appendIfNotNull(questionBuilder, "课程", body.get("courseName"));
        appendListIfNotNull(questionBuilder, "知识点", (List<String>) body.get("knowledgePoints"));
        appendIfNotNull(questionBuilder, "时长", body.get("duration"));
        appendIfNotNull(questionBuilder, "风格", body.get("style"));
        appendIfNotNull(questionBuilder, "包含旁白", body.get("includeNarration"));
        appendIfNotNull(questionBuilder, "包含画面描述", body.get("includeVisual"));

        QuesParam quesParam = new QuesParam();
        quesParam.setTalkId((String) body.get("talkId"));
        quesParam.setQuestion(questionBuilder.toString());
        return buildSSEStream(userId, quesParam, upstreamToken, lastEventId);
    }

    @PostMapping(value = "/generate/code-practice", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @SuppressWarnings("unchecked")
    public Flux<ServerSentEvent<String>> generateCodePractice(
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

        StringBuilder questionBuilder = new StringBuilder("请生成代码实操案例：");
        appendIfNotNull(questionBuilder, "课程", body.get("courseName"));
        appendListIfNotNull(questionBuilder, "知识点", (List<String>) body.get("knowledgePoints"));
        appendIfNotNull(questionBuilder, "编程语言", body.get("language"));
        appendIfNotNull(questionBuilder, "难度", body.get("difficulty"));
        appendIfNotNull(questionBuilder, "类型", body.get("projectType"));
        appendIfNotNull(questionBuilder, "包含测试", body.get("includeTest"));
        appendIfNotNull(questionBuilder, "包含说明", body.get("includeExplanation"));

        QuesParam quesParam = new QuesParam();
        quesParam.setTalkId((String) body.get("talkId"));
        quesParam.setQuestion(questionBuilder.toString());
        return buildSSEStream(userId, quesParam, upstreamToken, lastEventId);
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

    private ServerSentEvent<String> sse(String event, String data) {
        return ServerSentEvent.<String>builder().event(event).data(data).build();
    }
    private ServerSentEvent<String> sseWithId(String id, String event, String data) {
        return ServerSentEvent.<String>builder().id(id).event(event).data(data).build();
    }
    private String resolveEventName(String data) {
        if (data == null || data.isBlank()) return "message";
        try { return objectMapper.readTree(data).path("type").asText("message"); } catch (Exception e) { return "message"; }
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
        } catch (Exception e) { return "{\"type\":\"error\",\"message\":\"json serialize error\"}"; }
    }
    private Map<String, Object> mapOf(Object k1, Object v1) { Map<String, Object> m = new HashMap<>(); m.put(String.valueOf(k1), v1); return m; }
    private Map<String, Object> mapOf(Object k1, Object v1, Object k2, Object v2) { Map<String, Object> m = new HashMap<>(); m.put(String.valueOf(k1), v1); m.put(String.valueOf(k2), v2); return m; }
    private void appendIfNotNull(StringBuilder sb, String label, Object value) {
        if (value != null && !value.toString().isBlank()) sb.append("\n").append(label).append("：").append(value);
    }
    private void appendIfNotNull(StringBuilder sb, String label, Boolean value) {
        if (value != null) sb.append("\n").append(label).append("：").append(value);
    }
    private void appendListIfNotNull(StringBuilder sb, String label, List<String> list) {
        if (list != null && !list.isEmpty()) sb.append("\n").append(label).append("：").append(String.join("、", list));
    }
}