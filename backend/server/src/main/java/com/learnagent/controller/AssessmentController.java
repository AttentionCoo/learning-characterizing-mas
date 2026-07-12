package com.learnagent.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.learnagent.cache.SSEEventCache;
import com.learnagent.mapper.EvalReportMapper;
import com.learnagent.mapper.LearningBehaviorRecordMapper;
import com.learnagent.mapper.LearningPathMapper;
import com.learnagent.mapper.LearningPathStepMapper;
import com.learnagent.mapper.StudentProfileMapper;
import com.learnagent.entity.EvalReport;
import com.learnagent.entity.LearningBehaviorRecord;
import com.learnagent.entity.LearningPath;
import com.learnagent.entity.LearningPathStepEntity;
import com.learnagent.entity.Result;
import com.learnagent.entity.StudentProfile;
import com.learnagent.param.AssessmentGenerateParam;
import com.learnagent.param.BehaviorSubmitParam;
import com.learnagent.param.OptimizeParam;
import com.learnagent.service.AIStreamingService;
import com.learnagent.utils.ThreadLocalUtil;
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
import java.math.RoundingMode;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.stream.Collectors;

@Slf4j
@RestController
@CrossOrigin("*")
@RequestMapping("/api/evaluation")
@RequiredArgsConstructor
public class AssessmentController {

    private final AIStreamingService streamingService;
    private final ObjectMapper objectMapper;
    private final SSEEventCache eventCache;
    private final EvalReportMapper evalReportMapper;
    private final LearningBehaviorRecordMapper learningBehaviorRecordMapper;
    private final LearningPathMapper learningPathMapper;
    private final LearningPathStepMapper learningPathStepMapper;
    private final StudentProfileMapper studentProfileMapper;
    private final org.springframework.web.reactive.function.client.WebClient webClient;

    @PostMapping(value = "/generate", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> generate(
            @RequestBody AssessmentGenerateParam param,
            @RequestHeader(value = "token", required = false) String token,
            @RequestHeader(value = "Authorization", required = false) String authorization,
            HttpServletResponse response
    ) {
        response.setHeader("X-Accel-Buffering", "no");
        response.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");

        if (ThreadLocalUtil.getCurrentUser() == null) {
            return Flux.just(sse("error", json("error", mapOf("message", "未登录"))));
        }

        String upstreamToken = resolveToken(token, authorization);
        Long userId = ThreadLocalUtil.getCurrentUser().getId();

        String learningDataContext = buildLearningDataContext(userId, param);

        StringBuilder questionBuilder = new StringBuilder("请为我生成学习效果评估报告：\n");
        questionBuilder.append(learningDataContext);
        if (param.getPathId() != null) questionBuilder.append("\n指定学习路径ID：").append(param.getPathId());
        if (param.getMessage() != null && !param.getMessage().isBlank()) questionBuilder.append("\n补充说明：").append(param.getMessage());
        if (param.getAssessmentType() != null) questionBuilder.append("\n评估类型：").append(param.getAssessmentType());
        if (param.getCourseName() != null) questionBuilder.append("\n课程：").append(param.getCourseName());
        if (param.getTimeRange() != null) {
            questionBuilder.append("\n时间范围：").append(param.getTimeRange().getStart()).append(" 至 ").append(param.getTimeRange().getEnd());
        }
        questionBuilder.append("\n\n请严格基于以上真实学习数据进行分析评估，不要编造数据。请给出综合评分（0-100分），并在报告中明确标注「综合评分：XX分/100」。");

        Long talkId = streamingService.createNewTalk(userId);
        final String finalTalkIdStr = String.valueOf(talkId);

        Flux<String> initFlux = Flux.just(json("init", mapOf("talkId", finalTalkIdStr, "newTalk", true)));
        eventCache.registerStream(finalTalkIdStr);

        Flux<String> chatFlux = streamingService
                .streamChat(userId, talkId, questionBuilder.toString(), upstreamToken, null,
                        param.getAssessmentType() != null ? "assessment_" + param.getAssessmentType() : "assessment_comprehensive")
                .map(this::wrapChunkIfNeeded);
        StringBuilder fullAnswer = new StringBuilder();

        Sinks.One<Void> doneSink = Sinks.one();

        Flux<ServerSentEvent<String>> initSSE = initFlux.map(data -> sse(resolveEventName(data), data));
        Flux<ServerSentEvent<String>> chatSSE = chatFlux
                .onErrorResume(e -> Flux.just(
                        json("error", mapOf("talkId", finalTalkIdStr, "message", e.getMessage() == null ? "stream error" : e.getMessage())),
                        json("done", mapOf("talkId", finalTalkIdStr, "name", "异常结束"))
                ))
                .doOnNext(data -> appendContent(fullAnswer, data))
                .map(data -> {
                    long seq = eventCache.addEvent(finalTalkIdStr, data);
                    return sseWithId(finalTalkIdStr + ":" + seq, resolveEventName(data), data);
                });

        Flux<ServerSentEvent<String>> dataStream = initSSE.concatWith(chatSSE)
                .doFinally(signal -> {
                    if (fullAnswer.length() > 0) {
                        persistEvaluationReport(userId, param, fullAnswer.toString());
                    }
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

    @GetMapping("/report")
    public Result getReport(
            @RequestParam(required = false) Long pathId,
            @RequestParam(defaultValue = "all") String period) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        LambdaQueryWrapper<EvalReport> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(EvalReport::getUserId, userId);
        if (pathId != null) wrapper.eq(EvalReport::getPathId, pathId);
        wrapper.orderByDesc(EvalReport::getCreateTime);
        wrapper.last("LIMIT 1");

        EvalReport report = evalReportMapper.selectOne(wrapper);
        if (report == null) {
            Map<String, Object> computedData = computeReportFromRawData(userId, pathId, period);
            return Result.success(computedData);
        }

        Map<String, Object> data = new HashMap<>();
        data.put("reportId", report.getId());
        data.put("overallScore", report.getOverallScore());
        data.put("level", resolveLevel(report.getOverallScore()));
        data.put("period", report.getPeriod() != null ? report.getPeriod() : period);
        try {
            data.put("dimensions", report.getDimensions() != null ? objectMapper.readValue(report.getDimensions(), Map.class) : new HashMap<>());
            data.put("strengths", report.getStrengths() != null ? objectMapper.readValue(report.getStrengths(), List.class) : List.of());
            data.put("weaknesses", report.getWeaknesses() != null ? objectMapper.readValue(report.getWeaknesses(), List.class) : List.of());
            data.put("suggestions", report.getSuggestions() != null ? objectMapper.readValue(report.getSuggestions(), List.class) : List.of());
        } catch (Exception e) {
            log.error("解析评估报告数据失败", e);
        }
        data.put("generateTime", report.getCreateTime());
        return Result.success(data);
    }

    private Map<String, Object> computeReportFromRawData(Long userId, Long pathId, String period) {
        Map<String, Object> data = new HashMap<>();
        data.put("overallScore", 0);
        data.put("level", "unknown");
        data.put("period", period);

        List<LearningPath> paths;
        if (pathId != null) {
            LearningPath p = learningPathMapper.selectById(pathId);
            paths = p != null ? List.of(p) : List.of();
        } else {
            paths = learningPathMapper.selectList(
                    new LambdaQueryWrapper<LearningPath>()
                            .eq(LearningPath::getUserId, userId)
                            .orderByDesc(LearningPath::getUpdateTime)
            );
        }

        Map<String, Object> dimensions = new LinkedHashMap<>();
        List<String> strengths = new ArrayList<>();
        List<String> weaknesses = new ArrayList<>();
        List<String> suggestions = new ArrayList<>();

        if (!paths.isEmpty()) {
            int totalSteps = 0;
            int completedSteps = 0;
            int inProgressSteps = 0;
            double totalSelfRating = 0;
            int ratingCount = 0;

            for (LearningPath p : paths) {
                totalSteps += p.getTotalSteps() != null ? p.getTotalSteps() : 0;
                completedSteps += p.getCompletedSteps() != null ? p.getCompletedSteps() : 0;

                List<LearningPathStepEntity> steps = learningPathStepMapper.selectList(
                        new LambdaQueryWrapper<LearningPathStepEntity>()
                                .eq(LearningPathStepEntity::getPathId, p.getId())
                );
                for (LearningPathStepEntity step : steps) {
                    if ("in_progress".equals(step.getStatus())) inProgressSteps++;
                    if (step.getSelfRating() != null) {
                        totalSelfRating += step.getSelfRating();
                        ratingCount++;
                    }
                }
            }

            double progressRate = totalSteps > 0 ? (double) completedSteps / totalSteps : 0;
            int progressScore = (int) Math.round(progressRate * 100);
            dimensions.put("学习进度", progressScore);

            double avgRating = ratingCount > 0 ? totalSelfRating / ratingCount : 0;
            int masteryScore = (int) Math.round(avgRating / 5.0 * 100);
            dimensions.put("知识掌握", masteryScore);

            int engagementScore = Math.min(100, (completedSteps + inProgressSteps) * 15);
            dimensions.put("学习投入", engagementScore);

            if (progressRate > 0.6) strengths.add("学习进度良好，已完成超过60%的学习步骤");
            if (avgRating >= 4) strengths.add("自我评估较高，知识掌握扎实");
            if (progressRate < 0.3) weaknesses.add("学习进度偏慢，需要加快节奏");
            if (avgRating > 0 && avgRating < 3) weaknesses.add("部分知识点掌握不牢，需要重点复习");
            if (completedSteps == 0) weaknesses.add("尚未完成任何学习步骤");

            if (progressRate < 0.5) suggestions.add("建议按学习路径逐步推进，每天至少完成一个步骤");
            if (avgRating > 0 && avgRating < 3) suggestions.add("建议对自评较低的步骤进行重点复盘");
            suggestions.add("建议定期进行学习评估，跟踪学习效果变化");

            int overallScore = (int) Math.round(progressScore * 0.4 + masteryScore * 0.4 + engagementScore * 0.2);
            data.put("overallScore", overallScore);
            data.put("level", resolveLevel(overallScore));
        }

        List<LearningBehaviorRecord> recentBehaviors = learningBehaviorRecordMapper.selectList(
                new LambdaQueryWrapper<LearningBehaviorRecord>()
                        .eq(LearningBehaviorRecord::getUserId, userId)
                        .ge(LearningBehaviorRecord::getCreateTime, LocalDateTime.now().minus(30, ChronoUnit.DAYS))
        );

        if (!recentBehaviors.isEmpty()) {
            int totalDuration = recentBehaviors.stream()
                    .filter(b -> b.getDuration() != null)
                    .mapToInt(LearningBehaviorRecord::getDuration)
                    .sum();
            int activityScore = Math.min(100, recentBehaviors.size() * 5 + totalDuration / 60);
            dimensions.put("学习活跃度", activityScore);

            List<LearningBehaviorRecord> quizAttempts = recentBehaviors.stream()
                    .filter(b -> "quiz_attempt".equals(b.getBehaviorType()) && b.getScore() != null)
                    .toList();
            if (!quizAttempts.isEmpty()) {
                double avgQuizScore = quizAttempts.stream()
                        .mapToDouble(b -> b.getScore().doubleValue())
                        .average().orElse(0);
                int quizScore = (int) Math.round(avgQuizScore * 100);
                dimensions.put("测验表现", quizScore);
                if (avgQuizScore >= 0.8) strengths.add("测验成绩优秀，知识掌握牢固");
                if (avgQuizScore < 0.6) {
                    weaknesses.add("测验成绩偏低，需要加强练习");
                    suggestions.add("建议多做练习题，巩固薄弱知识点");
                }
            }

            long activeDays = recentBehaviors.stream()
                    .map(b -> b.getCreateTime().toLocalDate())
                    .distinct().count();
            if (activeDays >= 15) strengths.add("学习频率较高，近30天活跃" + activeDays + "天");
            if (activeDays < 5) {
                weaknesses.add("学习频率偏低，近30天仅活跃" + activeDays + "天");
                suggestions.add("建议保持每天至少30分钟的学习时间");
            }
        }

        data.put("dimensions", dimensions);
        data.put("strengths", strengths);
        data.put("weaknesses", weaknesses);
        data.put("suggestions", suggestions);
        data.put("generateTime", LocalDateTime.now().toString());
        return data;
    }

    private String resolveLevel(Integer score) {
        if (score == null) return "unknown";
        if (score >= 90) return "excellent";
        if (score >= 75) return "good";
        if (score >= 60) return "moderate";
        return "needs_improvement";
    }

    @GetMapping("/reports")
    public Result getReportList(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) String courseName) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        LambdaQueryWrapper<EvalReport> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(EvalReport::getUserId, userId);
        wrapper.orderByDesc(EvalReport::getCreateTime);

        Page<EvalReport> pageResult = evalReportMapper.selectPage(new Page<>(page, size), wrapper);
        List<Map<String, Object>> records = pageResult.getRecords().stream().map(r -> {
            Map<String, Object> m = new HashMap<>();
            m.put("reportId", r.getId());
            m.put("title", "学习评估报告");
            m.put("assessmentType", "comprehensive");
            m.put("type", "comprehensive");
            m.put("score", r.getOverallScore());
            m.put("courseName", "");
            m.put("createTime", r.getCreateTime());
            return m;
        }).toList();

        Map<String, Object> data = new HashMap<>();
        data.put("total", pageResult.getTotal());
        data.put("records", records);
        return Result.success(data);
    }

    @GetMapping("/reports/{id}")
    public Result getReportDetail(@PathVariable Long id) {
        EvalReport report = evalReportMapper.selectById(id);
        if (report == null) {
            return Result.error("报告不存在");
        }
        Map<String, Object> data = new HashMap<>();
        data.put("reportId", report.getId());
        data.put("title", "学习评估报告");
        data.put("assessmentType", "comprehensive");
        data.put("type", "comprehensive");
        data.put("score", report.getOverallScore());
        data.put("courseName", "");
        data.put("dimensions", report.getDimensions());
        data.put("strengths", report.getStrengths());
        data.put("weaknesses", report.getWeaknesses());
        data.put("suggestions", report.getSuggestions());
        data.put("scores", buildScoreMap(report));
        data.put("content", buildReportContent(report));
        data.put("createTime", report.getCreateTime());
        return Result.success(data);
    }

    @PostMapping("/behavior")
    public Result submitBehavior(@RequestBody BehaviorSubmitParam param) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        int processed = 0;
        if (param.getBehaviors() != null) {
            for (BehaviorSubmitParam.BehaviorItem item : param.getBehaviors()) {
                LearningBehaviorRecord record = new LearningBehaviorRecord();
                record.setUserId(userId);
                record.setPathId(param.getPathId());
                record.setStepId(param.getStepId());
                record.setResourceId(item.getResourceId());
                record.setBehaviorType(item.getType());
                record.setDuration(item.getDuration());
                record.setScore(item.getScore());
                record.setCreateTime(LocalDateTime.now());
                learningBehaviorRecordMapper.insert(record);
                processed++;
            }
        }
        Map<String, Object> data = new HashMap<>();
        data.put("received", param.getBehaviors() != null ? param.getBehaviors().size() : 0);
        data.put("processed", processed);
        return Result.success(data);
    }

    @PostMapping("/optimize")
    public Result optimize(@RequestBody OptimizeParam param) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();

        if (param.getPathId() == null) {
            LearningPath firstPath = learningPathMapper.selectOne(
                    new LambdaQueryWrapper<LearningPath>()
                            .eq(LearningPath::getUserId, userId)
                            .eq(LearningPath::getStatus, "active")
                            .orderByDesc(LearningPath::getUpdateTime)
                            .last("LIMIT 1")
            );
            if (firstPath == null) {
                firstPath = learningPathMapper.selectOne(
                        new LambdaQueryWrapper<LearningPath>()
                                .eq(LearningPath::getUserId, userId)
                                .orderByDesc(LearningPath::getUpdateTime)
                                .last("LIMIT 1")
                );
            }
            if (firstPath != null) {
                param.setPathId(firstPath.getId());
            } else {
                return Result.error("暂无学习路径，请先生成学习路径后再优化");
            }
        }

        LearningPath path = learningPathMapper.selectById(param.getPathId());
        if (path == null || !path.getUserId().equals(userId)) {
            return Result.error("学习路径不存在");
        }

        if (param.getEvaluationData() == null || param.getEvaluationData().isEmpty()) {
            EvalReport latestReport = evalReportMapper.selectOne(
                    new LambdaQueryWrapper<EvalReport>()
                            .eq(EvalReport::getUserId, userId)
                            .orderByDesc(EvalReport::getCreateTime)
                            .last("LIMIT 1")
            );
            if (latestReport != null) {
                try {
                    Map<String, Object> evalData = new HashMap<>();
                    evalData.put("overallScore", latestReport.getOverallScore());
                    evalData.put("level", latestReport.getLevel());
                    if (latestReport.getDimensions() != null) {
                        evalData.put("dimensions", objectMapper.readValue(latestReport.getDimensions(), Map.class));
                    }
                    if (latestReport.getWeaknesses() != null) {
                        evalData.put("weaknesses", objectMapper.readValue(latestReport.getWeaknesses(), List.class));
                    }
                    if (latestReport.getSuggestions() != null) {
                        evalData.put("suggestions", objectMapper.readValue(latestReport.getSuggestions(), List.class));
                    }
                    param.setEvaluationData(evalData);
                } catch (Exception e) {
                    log.warn("解析最新评估报告数据失败", e);
                }
            }
        }

        List<LearningPathStepEntity> steps = learningPathStepMapper.selectList(
                new LambdaQueryWrapper<LearningPathStepEntity>()
                        .eq(LearningPathStepEntity::getPathId, param.getPathId())
                        .orderByAsc(LearningPathStepEntity::getOrderIndex)
        );

        Map<String, Object> requestBody = new HashMap<>();
        requestBody.put("pathId", param.getPathId());
        requestBody.put("triggerReason", param.getTriggerReason());
        requestBody.put("evaluationData", param.getEvaluationData());

        Map<String, Object> pathInfo = new HashMap<>();
        pathInfo.put("courseName", path.getCourseName());
        pathInfo.put("goalDescription", path.getGoalDescription());
        pathInfo.put("totalSteps", path.getTotalSteps());
        pathInfo.put("completedSteps", path.getCompletedSteps());
        pathInfo.put("estimatedDays", path.getEstimatedDays());
        pathInfo.put("status", path.getStatus());
        requestBody.put("pathInfo", pathInfo);

        List<Map<String, Object>> stepList = steps.stream().map(step -> {
            Map<String, Object> s = new HashMap<>();
            s.put("stepId", step.getId());
            s.put("title", step.getTitle());
            s.put("status", step.getStatus());
            s.put("difficulty", step.getDifficulty());
            s.put("knowledgePoints", step.getKnowledgePoints());
            s.put("selfRating", step.getSelfRating());
            return s;
        }).toList();
        requestBody.put("steps", stepList);

        try {
            String responseStr = webClient.post()
                    .uri("/model/evaluation/optimize")
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(requestBody)
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(Duration.ofMinutes(2))
                    .block();

            JsonNode root = objectMapper.readTree(responseStr);
            JsonNode data = root.path("data");
            if (!data.isMissingNode()) {
                Map<String, Object> result = objectMapper.convertValue(data, Map.class);
                applyOptimizationChanges(param.getPathId(), result);
                return Result.success(result);
            }
            return Result.success(responseStr);
        } catch (Exception e) {
            log.error("学习方案优化失败: {}", e.getMessage(), e);
            Map<String, Object> fallback = new HashMap<>();
            fallback.put("pathId", param.getPathId());
            fallback.put("optimizationApplied", false);
            fallback.put("changes", List.of());
            fallback.put("reason", "优化服务暂时不可用");
            return Result.success(fallback);
        }
    }

    @SuppressWarnings("unchecked")
    private void applyOptimizationChanges(Long pathId, Map<String, Object> result) {
        Boolean applied = (Boolean) result.get("optimizationApplied");
        if (applied == null || !applied) return;

        List<Map<String, Object>> changes = (List<Map<String, Object>>) result.get("changes");
        if (changes == null || changes.isEmpty()) return;

        for (Map<String, Object> change : changes) {
            String type = (String) change.get("type");
            try {
                if ("adjust_difficulty".equals(type)) {
                    Object stepIdObj = change.get("stepId");
                    Long stepIdLong = null;
                    if (stepIdObj instanceof Number num) {
                        stepIdLong = num.longValue();
                    } else if (stepIdObj instanceof String str) {
                        stepIdLong = Long.parseLong(str);
                    }
                    if (stepIdLong != null) {
                        LearningPathStepEntity step = learningPathStepMapper.selectById(stepIdLong);
                        if (step != null && step.getPathId().equals(pathId)) {
                            String newDifficulty = (String) change.get("newDifficulty");
                            if (newDifficulty != null) {
                                step.setDifficulty(newDifficulty);
                                step.setUpdateTime(LocalDateTime.now());
                                learningPathStepMapper.updateById(step);
                                log.info("优化-调整难度: stepId={}, newDifficulty={}", stepIdLong, newDifficulty);
                            }
                        }
                    }
                } else if ("insert_step".equals(type)) {
                    String description = (String) change.get("description");
                    if (description != null) {
                        List<LearningPathStepEntity> existingSteps = learningPathStepMapper.selectList(
                                new LambdaQueryWrapper<LearningPathStepEntity>()
                                        .eq(LearningPathStepEntity::getPathId, pathId)
                                        .orderByDesc(LearningPathStepEntity::getOrderIndex)
                        );
                        int maxOrder = existingSteps.stream()
                                .mapToInt(s -> s.getOrderIndex() != null ? s.getOrderIndex() : 0)
                                .max().orElse(0);

                        LearningPathStepEntity newStep = new LearningPathStepEntity();
                        newStep.setPathId(pathId);
                        newStep.setOrderIndex(maxOrder + 1);
                        newStep.setTitle(description);
                        newStep.setDescription((String) change.get("reason"));
                        newStep.setEstimatedHours(BigDecimal.valueOf(2));
                        newStep.setDifficulty("intermediate");
                        newStep.setStatus("not_started");
                        newStep.setPrerequisites("[]");
                        newStep.setCreateTime(LocalDateTime.now());
                        newStep.setUpdateTime(LocalDateTime.now());
                        learningPathStepMapper.insert(newStep);

                        LearningPath path = learningPathMapper.selectById(pathId);
                        if (path != null) {
                            path.setTotalSteps(path.getTotalSteps() != null ? path.getTotalSteps() + 1 : 1);
                            path.setUpdateTime(LocalDateTime.now());
                            learningPathMapper.updateById(path);
                        }
                        log.info("优化-插入步骤: pathId={}, title={}", pathId, description);
                    }
                }
            } catch (Exception e) {
                log.warn("应用优化变更失败: type={}, error={}", type, e.getMessage());
            }
        }
    }

    private ServerSentEvent<String> sse(String event, String data) { return ServerSentEvent.<String>builder().event(event).data(data).build(); }
    private ServerSentEvent<String> sseWithId(String id, String event, String data) { return ServerSentEvent.<String>builder().id(id).event(event).data(data).build(); }
    private String resolveEventName(String data) { if (data == null || data.isBlank()) return "message"; try { return objectMapper.readTree(data).path("type").asText("message"); } catch (Exception e) { return "message"; } }
    private String wrapChunkIfNeeded(String data) { if (data == null) return json("chunk", mapOf("content", "")); String trimmed = data.trim(); if (!trimmed.isEmpty() && trimmed.startsWith("{") && trimmed.endsWith("}")) return data; return json("chunk", mapOf("content", data)); }
    private String resolveToken(String token, String authorization) { if (token != null && !token.isBlank()) return token.trim(); if (authorization != null && !authorization.isBlank()) { String v = authorization.trim(); return v.startsWith("Bearer ") ? v.substring(7).trim() : v; } return null; }
    private String json(String type, Map<String, Object> payload) { try { Map<String, Object> root = new HashMap<>(); root.put("type", type); if (payload != null && !payload.isEmpty()) root.putAll(payload); return objectMapper.writeValueAsString(root); } catch (Exception e) { return "{\"type\":\"error\",\"message\":\"json serialize error\"}"; } }
    private Map<String, Object> mapOf(Object k1, Object v1) { Map<String, Object> m = new HashMap<>(); m.put(String.valueOf(k1), v1); return m; }
    private Map<String, Object> mapOf(Object k1, Object v1, Object k2, Object v2) { Map<String, Object> m = new HashMap<>(); m.put(String.valueOf(k1), v1); m.put(String.valueOf(k2), v2); return m; }

    private void persistEvaluationReport(Long userId, AssessmentGenerateParam param, String content) {
        try {
            int score = extractScore(content);
            EvalReport report = new EvalReport();
            report.setUserId(userId);
            report.setPathId(param.getPathId());
            report.setPeriod(param.getTimeRange() != null ? "custom" : "all");
            report.setOverallScore(score);
            report.setLevel(resolveLevel(score));
            report.setDimensions(objectMapper.writeValueAsString(extractDimensionsFromContent(content, score)));
            report.setStrengths(objectMapper.writeValueAsString(extractSectionItems(content, List.of("优势", "突出", "擅长"))));
            report.setWeaknesses(objectMapper.writeValueAsString(extractSectionItems(content, List.of("薄弱", "不足", "欠缺", "弱项"))));
            report.setSuggestions(objectMapper.writeValueAsString(extractSectionItems(content, List.of("建议", "改进", "推荐", "优化"))));
            report.setCreateTime(LocalDateTime.now());
            evalReportMapper.insert(report);
            log.info("学习评估报告已落库: userId={}, reportId={}, score={}", userId, report.getId(), score);
        } catch (Exception e) {
            log.error("学习评估报告落库失败", e);
        }
    }

    private String buildLearningDataContext(Long userId, AssessmentGenerateParam param) {
        StringBuilder sb = new StringBuilder();
        sb.append("\n=== 学生真实学习数据 ===\n");

        StudentProfile profile = studentProfileMapper.selectOne(
                new LambdaQueryWrapper<StudentProfile>()
                        .eq(StudentProfile::getUserId, userId)
                        .orderByDesc(StudentProfile::getUpdateTime)
                        .last("LIMIT 1")
        );
        if (profile != null && profile.getDimensions() != null) {
            try {
                Map<String, Object> dims = objectMapper.readValue(profile.getDimensions(), Map.class);
                sb.append("\n【学生画像维度】\n");
                for (Map.Entry<String, Object> entry : dims.entrySet()) {
                    sb.append("- ").append(entry.getKey()).append(": ")
                      .append(objectMapper.writeValueAsString(entry.getValue())).append("\n");
                }
            } catch (Exception e) {
                log.warn("序列化画像维度失败", e);
            }
        } else {
            sb.append("\n【学生画像维度】暂无画像数据\n");
        }

        List<LearningPath> paths;
        if (param.getPathId() != null) {
            LearningPath specificPath = learningPathMapper.selectById(param.getPathId());
            paths = specificPath != null ? List.of(specificPath) : List.of();
        } else {
            paths = learningPathMapper.selectList(
                    new LambdaQueryWrapper<LearningPath>()
                            .eq(LearningPath::getUserId, userId)
                            .orderByDesc(LearningPath::getUpdateTime)
            );
        }
        if (!paths.isEmpty()) {
            sb.append("\n【学习路径概览】\n");
            for (LearningPath p : paths) {
                double progress = p.getTotalSteps() != null && p.getTotalSteps() > 0
                        ? (double) (p.getCompletedSteps() != null ? p.getCompletedSteps() : 0) / p.getTotalSteps()
                        : 0;
                sb.append("- 路径「").append(p.getCourseName() != null ? p.getCourseName() : "未命名").append("」")
                  .append(": 目标=").append(p.getGoalDescription() != null ? p.getGoalDescription() : "无")
                  .append(", 进度=").append(String.format("%.0f%%", progress * 100))
                  .append("(").append(p.getCompletedSteps() != null ? p.getCompletedSteps() : 0)
                  .append("/").append(p.getTotalSteps() != null ? p.getTotalSteps() : 0).append("步)")
                  .append(", 状态=").append(p.getStatus()).append("\n");

                List<LearningPathStepEntity> steps = learningPathStepMapper.selectList(
                        new LambdaQueryWrapper<LearningPathStepEntity>()
                                .eq(LearningPathStepEntity::getPathId, p.getId())
                                .orderByAsc(LearningPathStepEntity::getOrderIndex)
                );
                if (!steps.isEmpty()) {
                    sb.append("  步骤详情:\n");
                    for (LearningPathStepEntity step : steps) {
                        sb.append("  ").append(step.getOrderIndex()).append(". ")
                          .append(step.getTitle())
                          .append(" [").append(step.getStatus() != null ? step.getStatus() : "unknown").append("]")
                          .append(" 难度=").append(step.getDifficulty() != null ? step.getDifficulty() : "未设定");
                        if (step.getSelfRating() != null) {
                            sb.append(" 自评=").append(step.getSelfRating()).append("/5");
                        }
                        if (step.getActualHours() != null) {
                            sb.append(" 实际用时=").append(step.getActualHours()).append("h");
                        }
                        sb.append("\n");
                    }
                }
            }
        } else {
            sb.append("\n【学习路径概览】暂无学习路径\n");
        }

        LocalDateTime since = null;
        if (param.getTimeRange() != null && param.getTimeRange().getStart() != null) {
            try { since = LocalDateTime.parse(param.getTimeRange().getStart() + "T00:00:00"); } catch (Exception ignored) {}
        }
        if (since == null) {
            since = LocalDateTime.now().minus(30, ChronoUnit.DAYS);
        }

        List<LearningBehaviorRecord> behaviors = learningBehaviorRecordMapper.selectList(
                new LambdaQueryWrapper<LearningBehaviorRecord>()
                        .eq(LearningBehaviorRecord::getUserId, userId)
                        .ge(LearningBehaviorRecord::getCreateTime, since)
                        .orderByDesc(LearningBehaviorRecord::getCreateTime)
        );

        if (!behaviors.isEmpty()) {
            sb.append("\n【学习行为记录】(近30天共").append(behaviors.size()).append("条)\n");

            Map<String, Long> typeCount = behaviors.stream()
                    .collect(Collectors.groupingBy(
                            b -> b.getBehaviorType() != null ? b.getBehaviorType() : "unknown",
                            Collectors.counting()));
            sb.append(" 行为类型分布: ");
            typeCount.forEach((type, count) -> sb.append(type).append("=").append(count).append(" "));
            sb.append("\n");

            int totalDuration = behaviors.stream()
                    .filter(b -> b.getDuration() != null)
                    .mapToInt(LearningBehaviorRecord::getDuration)
                    .sum();
            sb.append(" 总学习时长: ").append(String.format("%.1f", totalDuration / 3600.0)).append("小时\n");

            List<LearningBehaviorRecord> quizAttempts = behaviors.stream()
                    .filter(b -> "quiz_attempt".equals(b.getBehaviorType()) && b.getScore() != null)
                    .toList();
            if (!quizAttempts.isEmpty()) {
                double avgScore = quizAttempts.stream()
                        .mapToDouble(b -> b.getScore().doubleValue())
                        .average().orElse(0);
                sb.append(" 测验平均分: ").append(String.format("%.1f%%", avgScore * 100))
                  .append("(共").append(quizAttempts.size()).append("次测验)\n");
            }

            List<LearningBehaviorRecord> codeSubmits = behaviors.stream()
                    .filter(b -> "code_submit".equals(b.getBehaviorType()))
                    .toList();
            if (!codeSubmits.isEmpty()) {
                long passed = codeSubmits.stream()
                        .filter(b -> b.getScore() != null && b.getScore().compareTo(BigDecimal.ONE) >= 0)
                        .count();
                sb.append(" 代码提交通过率: ")
                  .append(String.format("%.0f%%", (double) passed / codeSubmits.size() * 100))
                  .append("(共").append(codeSubmits.size()).append("次提交)\n");
            }

            long uniqueDays = behaviors.stream()
                    .map(b -> b.getCreateTime().toLocalDate())
                    .distinct().count();
            sb.append(" 活跃学习天数: ").append(uniqueDays).append("天\n");

            sb.append(" 近期行为明细(最近10条):\n");
            behaviors.stream().limit(10).forEach(b -> {
                sb.append("  - ").append(b.getCreateTime().toString())
                  .append(" ").append(b.getBehaviorType());
                if (b.getDuration() != null) sb.append(" 时长=").append(b.getDuration()).append("s");
                if (b.getScore() != null) sb.append(" 分数=").append(b.getScore());
                sb.append("\n");
            });
        } else {
            sb.append("\n【学习行为记录】暂无行为数据\n");
        }

        List<EvalReport> recentReports = evalReportMapper.selectList(
                new LambdaQueryWrapper<EvalReport>()
                        .eq(EvalReport::getUserId, userId)
                        .orderByDesc(EvalReport::getCreateTime)
                        .last("LIMIT 3")
        );
        if (!recentReports.isEmpty()) {
            sb.append("\n【历史评估记录】\n");
            for (EvalReport r : recentReports) {
                sb.append("- ").append(r.getCreateTime().toString())
                  .append(" 综合分=").append(r.getOverallScore())
                  .append(" 等级=").append(r.getLevel()).append("\n");
            }
        }

        sb.append("\n=== 数据结束 ===\n");
        return sb.toString();
    }

    private Map<String, Object> extractDimensionsFromContent(String content, int overallScore) {
        Map<String, Object> dimensions = new LinkedHashMap<>();
        String[] dimensionKeywords = {"知识掌握", "临床应用", "学习效率", "学习进度", "技能应用", "复盘质量", "自主学习", "学习投入"};
        int[] baseOffsets = {0, -5, 3, 5, -3, -8, 2, -2};

        for (int i = 0; i < dimensionKeywords.length; i++) {
            String keyword = dimensionKeywords[i];
            int extractedScore = -1;
            if (content != null) {
                java.util.regex.Matcher dimMatcher = java.util.regex.Pattern
                        .compile(keyword + "[^0-9]{0,10}(\\d{1,3})")
                        .matcher(content);
                if (dimMatcher.find()) {
                    int val = Integer.parseInt(dimMatcher.group(1));
                    if (val >= 0 && val <= 100) extractedScore = val;
                }
            }
            int finalScore = extractedScore >= 0 ? extractedScore
                    : Math.max(0, Math.min(100, overallScore + baseOffsets[i]));
            dimensions.put(keyword, finalScore);
        }
        return dimensions;
    }

    private List<String> extractSectionItems(String content, List<String> keywords) {
        if (content == null || content.isBlank()) return List.of();
        for (String keyword : keywords) {
            int sectionStart = content.indexOf(keyword);
            if (sectionStart < 0) continue;

            String afterSection = content.substring(sectionStart);
            String[] lines = afterSection.split("\\R");

            List<String> items = new ArrayList<>();
            boolean inSection = false;
            for (int i = 0; i < lines.length; i++) {
                String line = lines[i].trim();
                if (i == 0) { inSection = true; continue; }
                if (!inSection) continue;

                if (line.startsWith("#") || line.matches("^[一二三四五六七八九十]+[、.．].*")) break;

                if (line.matches("^[-*•]\\s+.*")) {
                    String item = line.replaceFirst("^[-*•]\\s+", "").trim();
                    if (!item.isBlank()) items.add(item);
                } else if (line.matches("^\\d+[.、)）]\\s+.*")) {
                    String item = line.replaceFirst("^\\d+[.、)）]\\s+", "").trim();
                    if (!item.isBlank()) items.add(item);
                } else if (line.isBlank()) {
                    if (!items.isEmpty()) continue;
                } else if (!line.isBlank() && !line.startsWith("|") && !line.startsWith("---")) {
                    items.add(line);
                }
                if (items.size() >= 5) break;
            }
            if (!items.isEmpty()) return items;
        }
        return List.of();
    }

    private int extractScore(String content) {
        if (content == null) return 75;
        java.util.regex.Matcher matcher = java.util.regex.Pattern
                .compile("(\\d{1,3})\\s*(分|/100)")
                .matcher(content);
        while (matcher.find()) {
            int value = Integer.parseInt(matcher.group(1));
            if (value >= 0 && value <= 100) return value;
        }
        return 75;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> buildScoreMap(EvalReport report) {
        Map<String, Object> scores = new LinkedHashMap<>();
        scores.put("综合", report.getOverallScore() == null ? 0 : report.getOverallScore());
        try {
            Map<String, Object> dimensions = report.getDimensions() != null
                    ? objectMapper.readValue(report.getDimensions(), Map.class)
                    : Map.of();
            dimensions.forEach((key, value) -> {
                if (value instanceof Number number) scores.put(key, number.intValue());
            });
        } catch (Exception ignored) {}
        return scores;
    }

    private String buildReportContent(EvalReport report) {
        StringBuilder sb = new StringBuilder();
        sb.append("# 学习评估报告\n\n");
        sb.append("综合得分：").append(report.getOverallScore() == null ? 0 : report.getOverallScore()).append("分\n\n");
        sb.append("等级：").append(report.getLevel()).append("\n\n");
        appendJsonSection(sb, "优势", report.getStrengths());
        appendJsonSection(sb, "薄弱点", report.getWeaknesses());
        appendJsonSection(sb, "改进建议", report.getSuggestions());
        return sb.toString();
    }

    private void appendJsonSection(StringBuilder sb, String title, String json) {
        sb.append("## ").append(title).append("\n");
        try {
            List<?> list = json != null ? objectMapper.readValue(json, List.class) : List.of();
            if (list.isEmpty()) {
                sb.append("- 暂无\n\n");
                return;
            }
            for (Object item : list) sb.append("- ").append(item).append("\n");
            sb.append("\n");
        } catch (Exception e) {
            sb.append("- ").append(json == null ? "暂无" : json).append("\n\n");
        }
    }

    private void appendContent(StringBuilder target, String data) {
        if (data == null) return;
        try {
            JsonNode node = objectMapper.readTree(data);
            String type = node.path("type").asText("");
            if ("chunk".equals(type) || "result".equals(type)) {
                target.append(node.path("content").asText(""));
            }
        } catch (Exception ignored) {}
    }
}
