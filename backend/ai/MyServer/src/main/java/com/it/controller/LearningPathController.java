package com.it.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.cache.SSEEventCache;
import com.it.mapper.LearningPathMapper;
import com.it.mapper.LearningPathStepMapper;
import com.it.mapper.LearningResourceMapper;
import com.it.mapper.StepResourceRelMapper;
import com.it.po.uo.QuesParam;
import com.it.pojo.*;
import com.it.po.uo.PathAdjustParam;
import com.it.po.uo.PathGenerateParam;
import com.it.po.uo.StepProgressParam;
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

import java.math.BigDecimal;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

@Slf4j
@RestController
@CrossOrigin("*")
@RequestMapping("/api/learning-path")
@RequiredArgsConstructor
public class LearningPathController {

    private final AIStreamingService streamingService;
    private final ObjectMapper objectMapper;
    private final SSEEventCache eventCache;
    private final LearningPathMapper learningPathMapper;
    private final LearningPathStepMapper learningPathStepMapper;
    private final LearningResourceMapper learningResourceMapper;
    private final StepResourceRelMapper stepResourceRelMapper;
    private final IInitialPageService initialPageService;

    @PostMapping(value = "/generate", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> generate(
            @RequestBody PathGenerateParam param,
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

        StringBuilder questionBuilder = new StringBuilder("请为我规划学习路径：");
        if (param.getCourseName() != null) questionBuilder.append("\n课程：").append(param.getCourseName());
        if (param.getGoalDescription() != null) questionBuilder.append("\n学习目标：").append(param.getGoalDescription());
        if (param.getDeadline() != null) questionBuilder.append("\n截止日期：").append(param.getDeadline());
        if (param.getWeeklyHours() != null) questionBuilder.append("\n每周可投入学时：").append(param.getWeeklyHours());
        if (param.getExistingKnowledge() != null && !param.getExistingKnowledge().isEmpty())
            questionBuilder.append("\n已掌握知识点：").append(String.join("、", param.getExistingKnowledge()));
        if (param.getTargetKnowledge() != null && !param.getTargetKnowledge().isEmpty())
            questionBuilder.append("\n目标知识点：").append(String.join("、", param.getTargetKnowledge()));

        QuesParam quesParam = new QuesParam();
        quesParam.setQuestion(questionBuilder.toString());

        Long talkId = streamingService.createNewTalk(userId);
        final String finalTalkIdStr = String.valueOf(talkId);

        Flux<String> initFlux = Flux.just(
                json("init", mapOf("talkId", finalTalkIdStr, "newTalk", true))
        );
        eventCache.registerStream(finalTalkIdStr);

        Flux<String> chatFlux = streamingService
                .streamChat(userId, talkId, quesParam.getQuestion(), upstreamToken, null)
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

    @GetMapping
    public Result getLearningPaths(
            @RequestParam(required = false) String courseName,
            @RequestParam(required = false) String status) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        LambdaQueryWrapper<LearningPath> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(LearningPath::getUserId, userId);
        if (courseName != null && !courseName.isEmpty()) {
            wrapper.eq(LearningPath::getCourseName, courseName);
        }
        if (status != null && !status.isEmpty()) {
            wrapper.eq(LearningPath::getStatus, status);
        }
        wrapper.orderByDesc(LearningPath::getUpdateTime);

        List<LearningPath> paths = learningPathMapper.selectList(wrapper);
        List<Map<String, Object>> records = paths.stream().map(p -> {
            Map<String, Object> m = new HashMap<>();
            m.put("pathId", p.getId());
            m.put("courseName", p.getCourseName());
            m.put("totalSteps", p.getTotalSteps());
            m.put("completedSteps", p.getCompletedSteps());
            m.put("progress", p.getTotalSteps() > 0 ? (double) p.getCompletedSteps() / p.getTotalSteps() : 0);
            m.put("status", p.getStatus());
            m.put("createTime", p.getCreateTime());
            return m;
        }).toList();

        Map<String, Object> data = new HashMap<>();
        data.put("total", paths.size());
        data.put("records", records);
        return Result.success(data);
    }

    @GetMapping("/{pathId}")
    public Result getLearningPathDetail(@PathVariable Long pathId) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        LearningPath path = learningPathMapper.selectById(pathId);
        if (path == null || !path.getUserId().equals(userId)) {
            return Result.error("学习路径不存在");
        }

        Map<String, Object> data = buildPathDetail(path, userId);
        return Result.success(data);
    }

    @PutMapping("/{pathId}/steps/{stepId}/progress")
    public Result updateStepProgress(@PathVariable Long pathId, @PathVariable Long stepId,
                                      @RequestBody StepProgressParam param) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        LearningPath path = learningPathMapper.selectById(pathId);
        if (path == null || !path.getUserId().equals(userId)) {
            return Result.error("学习路径不存在");
        }

        LearningPathStepEntity step = learningPathStepMapper.selectById(stepId);
        if (step == null || !step.getPathId().equals(pathId)) {
            return Result.error("步骤不存在");
        }

        if (param.getStatus() != null) step.setStatus(param.getStatus());
        if (param.getActualHours() != null) step.setActualHours(param.getActualHours());
        if (param.getFeedback() != null) step.setFeedback(param.getFeedback());
        if (param.getSelfRating() != null) step.setSelfRating(param.getSelfRating());
        step.setUpdateTime(LocalDateTime.now());
        learningPathStepMapper.updateById(step);

        long completedCount = learningPathStepMapper.selectCount(
                new LambdaQueryWrapper<LearningPathStepEntity>()
                        .eq(LearningPathStepEntity::getPathId, pathId)
                        .eq(LearningPathStepEntity::getStatus, "completed")
        );
        path.setCompletedSteps((int) completedCount);
        path.setUpdateTime(LocalDateTime.now());
        learningPathMapper.updateById(path);

        Map<String, Object> data = new HashMap<>();
        data.put("pathId", pathId);
        data.put("completedSteps", completedCount);
        data.put("progress", path.getTotalSteps() > 0 ? (double) completedCount / path.getTotalSteps() : 0);
        return Result.success(data);
    }

    @PutMapping("/tasks/{taskId}/progress")
    public Result updateTaskProgress(@PathVariable Long taskId, @RequestBody StepProgressParam param) {
        return updateStepProgress(null, taskId, param);
    }

    @PostMapping("/{pathId}/adjust")
    public Result adjustPath(@PathVariable Long pathId, @RequestBody PathAdjustParam param) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        LearningPath path = learningPathMapper.selectById(pathId);
        if (path == null || !path.getUserId().equals(userId)) {
            return Result.error("学习路径不存在");
        }

        Map<String, Object> data = new HashMap<>();
        data.put("pathId", pathId);
        data.put("adjustments", List.of());
        data.put("newTotalSteps", path.getTotalSteps());
        data.put("newEstimatedDays", path.getEstimatedDays());
        return Result.success(data);
    }

    @GetMapping("/recommendations")
    public Result getRecommendations(
            @RequestParam(required = false) String courseName,
            @RequestParam(required = false) String type,
            @RequestParam(defaultValue = "10") int count) {
        return doGetRecommendations(courseName, type, count);
    }

    @PostMapping("/recommend")
    public Result recommend(@RequestBody Map<String, Object> body) {
        String courseName = (String) body.get("courseName");
        String type = (String) body.get("type");
        Integer count = body.get("count") != null ? ((Number) body.get("count")).intValue() : 10;
        return doGetRecommendations(courseName, type, count);
    }

    private Result doGetRecommendations(String courseName, String type, int count) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        LambdaQueryWrapper<LearningResource> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(LearningResource::getUserId, userId);
        if (type != null && !type.isEmpty()) {
            wrapper.eq(LearningResource::getType, type);
        }
        if (courseName != null && !courseName.isEmpty()) {
            wrapper.eq(LearningResource::getCourseName, courseName);
        }
        wrapper.orderByDesc(LearningResource::getCreateTime);
        wrapper.last("LIMIT " + count);

        List<LearningResource> resources = learningResourceMapper.selectList(wrapper);
        List<Map<String, Object>> recommendations = resources.stream().map(r -> {
            Map<String, Object> m = new HashMap<>();
            m.put("resourceId", r.getId());
            m.put("title", r.getTitle());
            m.put("type", r.getType());
            m.put("courseName", r.getCourseName());
            m.put("difficulty", r.getDifficulty());
            m.put("matchScore", 0.8);
            m.put("matchReason", "基于画像推荐");
            m.put("knowledgePoints", r.getKnowledgePoints());
            return m;
        }).toList();

        Map<String, Object> data = new HashMap<>();
        data.put("recommendations", recommendations);
        return Result.success(data);
    }

    @GetMapping("/conversations")
    public Result getConversationList() {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        List<InitialPageVO> talks = initialPageService.getPage(userId);
        return Result.success(talks);
    }

    private Map<String, Object> buildPathDetail(LearningPath path, Long userId) {
        Map<String, Object> data = new HashMap<>();
        data.put("pathId", path.getId());
        data.put("userId", path.getUserId());
        data.put("goal", path.getGoalDescription());
        data.put("courseName", path.getCourseName());
        data.put("totalSteps", path.getTotalSteps());
        data.put("completedSteps", path.getCompletedSteps());
        data.put("estimatedDays", path.getEstimatedDays());
        data.put("deadline", path.getDeadline());
        data.put("status", path.getStatus());
        data.put("createTime", path.getCreateTime());
        data.put("updateTime", path.getUpdateTime());

        List<LearningPathStepEntity> steps = learningPathStepMapper.selectList(
                new LambdaQueryWrapper<LearningPathStepEntity>()
                        .eq(LearningPathStepEntity::getPathId, path.getId())
                        .orderByAsc(LearningPathStepEntity::getOrderIndex)
        );

        List<Map<String, Object>> stepList = steps.stream().map(step -> {
            Map<String, Object> s = new HashMap<>();
            s.put("stepId", step.getId());
            s.put("title", step.getTitle());
            s.put("description", step.getDescription());
            s.put("knowledgePoints", step.getKnowledgePoints());
            s.put("estimatedHours", step.getEstimatedHours());
            s.put("difficulty", step.getDifficulty());
            s.put("status", step.getStatus());
            s.put("orderIndex", step.getOrderIndex());

            List<StepResourceRel> rels = stepResourceRelMapper.selectList(
                    new LambdaQueryWrapper<StepResourceRel>().eq(StepResourceRel::getStepId, step.getId())
            );
            List<Map<String, Object>> resources = rels.stream().map(rel -> {
                LearningResource r = learningResourceMapper.selectById(rel.getResourceId());
                Map<String, Object> rm = new HashMap<>();
                if (r != null) {
                    rm.put("resourceId", r.getId());
                    rm.put("title", r.getTitle());
                    rm.put("type", r.getType());
                    rm.put("relevance", rel.getRelevance());
                }
                return rm;
            }).filter(rm -> !rm.isEmpty()).toList();
            s.put("resources", resources);
            return s;
        }).toList();
        data.put("steps", stepList);
        return data;
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
}