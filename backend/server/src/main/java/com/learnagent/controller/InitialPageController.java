package com.learnagent.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.learnagent.entity.EvalReport;
import com.learnagent.entity.LearningPath;
import com.learnagent.entity.LearningResource;
import com.learnagent.entity.StudentProfile;
import com.learnagent.entity.Talk;
import com.learnagent.mapper.EvalReportMapper;
import com.learnagent.mapper.LearningPathMapper;
import com.learnagent.mapper.LearningResourceMapper;
import com.learnagent.mapper.StudentProfileMapper;
import com.learnagent.mapper.TalkMapper;
import com.learnagent.utils.ThreadLocalUtil;
import com.learnagent.entity.Result;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@CrossOrigin("*")
@RequestMapping("/api/user")
@Slf4j
@RequiredArgsConstructor
public class InitialPageController {

    private final StudentProfileMapper studentProfileMapper;
    private final LearningPathMapper learningPathMapper;
    private final LearningResourceMapper learningResourceMapper;
    private final EvalReportMapper evalReportMapper;
    private final TalkMapper talkMapper;

    /**
     * 学习闭环总览：聚合画像 / 路径 / 资源 / 评估 / 辅导数据，
     * 供首页展示「画像 → 学习 → 评估 → 再学习」的闭环状态。
     */
    @GetMapping("/overview")
    public Result getOverview() {
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        Map<String, Object> data = new HashMap<>();

        // 1. 画像完整度：维度数 / 是否构建
        StudentProfile profile = studentProfileMapper.selectOne(
                new LambdaQueryWrapper<StudentProfile>()
                        .eq(StudentProfile::getUserId, userId)
                        .orderByDesc(StudentProfile::getUpdateTime)
                        .last("LIMIT 1")
        );
        int dimensionCount = 0;
        if (profile != null && profile.getDimensions() != null && !profile.getDimensions().isBlank()) {
            try {
                Map<String, Object> dims = new com.fasterxml.jackson.databind.ObjectMapper()
                        .readValue(profile.getDimensions(), Map.class);
                dimensionCount = dims.size();
            } catch (Exception ignored) {
            }
        }
        Map<String, Object> profileInfo = new HashMap<>();
        profileInfo.put("built", profile != null && dimensionCount > 0);
        profileInfo.put("dimensionCount", dimensionCount);
        data.put("profile", profileInfo);

        // 2. 学习路径：条数 / 进度
        List<LearningPath> paths = learningPathMapper.selectList(
                new LambdaQueryWrapper<LearningPath>()
                        .eq(LearningPath::getUserId, userId)
                        .orderByDesc(LearningPath::getUpdateTime)
        );
        int totalSteps = 0;
        int completedSteps = 0;
        int activePaths = 0;
        for (LearningPath p : paths) {
            if ("active".equals(p.getStatus())) activePaths++;
            totalSteps += p.getTotalSteps() != null ? p.getTotalSteps() : 0;
            completedSteps += p.getCompletedSteps() != null ? p.getCompletedSteps() : 0;
        }
        Map<String, Object> pathInfo = new HashMap<>();
        pathInfo.put("count", paths.size());
        pathInfo.put("activeCount", activePaths);
        pathInfo.put("totalSteps", totalSteps);
        pathInfo.put("completedSteps", completedSteps);
        pathInfo.put("progress", totalSteps > 0 ? Math.round(completedSteps * 100.0 / totalSteps) : 0);
        data.put("learningPath", pathInfo);

        // 3. 学习资源：数量
        Long resourceCount = learningResourceMapper.selectCount(
                new LambdaQueryWrapper<LearningResource>()
                        .eq(LearningResource::getUserId, userId)
        );
        Map<String, Object> resourceInfo = new HashMap<>();
        resourceInfo.put("count", resourceCount != null ? resourceCount : 0L);
        data.put("resources", resourceInfo);

        // 4. 学习评估：最新分数 / 报告数
        EvalReport latest = evalReportMapper.selectOne(
                new LambdaQueryWrapper<EvalReport>()
                        .eq(EvalReport::getUserId, userId)
                        .orderByDesc(EvalReport::getCreateTime)
                        .last("LIMIT 1")
        );
        Long reportCount = evalReportMapper.selectCount(
                new LambdaQueryWrapper<EvalReport>().eq(EvalReport::getUserId, userId)
        );
        Map<String, Object> evalInfo = new HashMap<>();
        evalInfo.put("latestScore", latest != null ? latest.getOverallScore() : null);
        evalInfo.put("latestLevel", latest != null ? latest.getLevel() : null);
        evalInfo.put("reportCount", reportCount != null ? reportCount : 0L);
        data.put("assessment", evalInfo);

        // 5. 辅导/对话轮数：talk 条数
        Long talkCount = talkMapper.selectCount(
                new LambdaQueryWrapper<Talk>().eq(Talk::getUserId, userId)
        );
        Map<String, Object> tutorInfo = new HashMap<>();
        tutorInfo.put("talkCount", talkCount != null ? talkCount : 0L);
        data.put("tutor", tutorInfo);

        // 闭环状态机：依据画像/路径/评估的有无推断当前阶段
        String stage = "not_started";
        if (profileInfo.containsKey("built") && Boolean.TRUE.equals(profileInfo.get("built"))) {
            stage = "learning";
        }
        if (evalInfo.get("latestScore") != null) {
            stage = "assessed";
        }
        Object progressVal = pathInfo.get("progress");
        int progressInt = progressVal instanceof Number ? ((Number) progressVal).intValue() : 0;
        if (stage.equals("assessed") && progressInt >= 100) {
            stage = "completed";
        }
        data.put("stage", stage);

        return Result.success(data);
    }
}
