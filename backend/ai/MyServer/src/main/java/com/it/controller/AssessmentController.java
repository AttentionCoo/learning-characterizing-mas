package com.it.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.cache.SSEEventCache;
import com.it.mapper.EvalReportMapper;
import com.it.mapper.LearningBehaviorRecordMapper;
import com.it.pojo.EvalReport;
import com.it.pojo.LearningBehaviorRecord;
import com.it.pojo.Result;
import com.it.po.uo.AssessmentGenerateParam;
import com.it.po.uo.BehaviorSubmitParam;
import com.it.po.uo.OptimizeParam;
import com.it.service.AIStreamingService;
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
import java.time.LocalDateTime;
import java.util.*;

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

        StringBuilder questionBuilder = new StringBuilder("请为我生成学习效果评估报告：");
        if (param.getAssessmentType() != null) questionBuilder.append("\n评估类型：").append(param.getAssessmentType());
        if (param.getCourseName() != null) questionBuilder.append("\n课程：").append(param.getCourseName());
        if (param.getTimeRange() != null) {
            questionBuilder.append("\n时间范围：").append(param.getTimeRange().getStart()).append(" 至 ").append(param.getTimeRange().getEnd());
        }

        Long talkId = streamingService.createNewTalk(userId);
        final String finalTalkIdStr = String.valueOf(talkId);

        Flux<String> initFlux = Flux.just(json("init", mapOf("talkId", finalTalkIdStr, "newTalk", true)));
        eventCache.registerStream(finalTalkIdStr);

        Flux<String> chatFlux = streamingService
                .streamChat(userId, talkId, questionBuilder.toString(), upstreamToken, null, "assessment")
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

        Flux<ServerSentEvent<String>> dataStream = initSSE.concatWith(chatSSE)
                .doFinally(signal -> { doneSink.tryEmitEmpty(); eventCache.completeStream(finalTalkIdStr); });

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
        wrapper.orderByDesc(EvalReport::getCreateTime);
        wrapper.last("LIMIT 1");

        EvalReport report = evalReportMapper.selectOne(wrapper);
        if (report == null) {
            Map<String, Object> emptyData = new HashMap<>();
            emptyData.put("overallScore", 0);
            emptyData.put("level", "unknown");
            emptyData.put("period", period);
            emptyData.put("dimensions", new HashMap<>());
            emptyData.put("strengths", List.of());
            emptyData.put("weaknesses", List.of());
            emptyData.put("suggestions", List.of());
            emptyData.put("generateTime", LocalDateTime.now().toString());
            return Result.success(emptyData);
        }

        Map<String, Object> data = new HashMap<>();
        data.put("overallScore", report.getOverallScore());
        data.put("level", resolveLevel(report.getOverallScore()));
        data.put("period", period);
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
        data.put("score", report.getOverallScore());
        data.put("courseName", "");
        data.put("dimensions", report.getDimensions());
        data.put("strengths", report.getStrengths());
        data.put("weaknesses", report.getWeaknesses());
        data.put("suggestions", report.getSuggestions());
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
        Map<String, Object> data = new HashMap<>();
        data.put("pathId", param.getPathId());
        data.put("optimizationApplied", false);
        data.put("changes", List.of());
        return Result.success(data);
    }

    @PostMapping("/quiz/{quizId}/submit")
    @SuppressWarnings("unchecked")
    public Result submitQuiz(@PathVariable Long quizId, @RequestBody Map<String, Object> body) {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        List<Map<String, Object>> answers = (List<Map<String, Object>>) body.get("answers");
        if (answers == null || answers.isEmpty()) {
            return Result.error("答案不能为空");
        }

        Map<String, Object> requestBody = new HashMap<>();
        requestBody.put("quiz_id", quizId);
        requestBody.put("answers", answers);
        requestBody.put("user_id", userId);

        try {
            String responseStr = webClient.post()
                    .uri("/model/evaluation/quiz/submit")
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(requestBody)
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(Duration.ofMinutes(2))
                    .block();

            JsonNode root = objectMapper.readTree(responseStr);
            JsonNode data = root.path("data");
            if (!data.isMissingNode()) {
                return Result.success(objectMapper.convertValue(data, Object.class));
            }
            return Result.success(responseStr);
        } catch (Exception e) {
            log.error("测验提交失败: {}", e.getMessage(), e);
            Map<String, Object> fallback = new HashMap<>();
            fallback.put("quizId", quizId);
            fallback.put("totalQuestions", answers.size());
            fallback.put("correctCount", 0);
            fallback.put("score", 0);
            fallback.put("details", List.of());
            return Result.success(fallback);
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
}