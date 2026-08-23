package com.learnagent.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.learnagent.entity.StudentProfile;
import com.learnagent.mapper.StudentProfileMapper;
import com.learnagent.utils.ProfileMergePolicy;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 学习画像写入服务：状态感知合并 + Profile Update Candidate 应用。
 *
 * 所有画像写入（对话自动提取、手动编辑、评估回流、会话候选）都经
 * ProfileMergePolicy 校验，确保"推理结果不会反向污染长期画像"。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ProfileUpdateService {

    private final StudentProfileMapper studentProfileMapper;
    private final ObjectMapper objectMapper;

    /** 状态感知合并并保存画像维度（无画像时新建）。 */
    public void mergeAndSave(Long userId, Map<String, Object> dimensions) {
        if (dimensions == null || dimensions.isEmpty()) {
            return;
        }
        StudentProfile profile = studentProfileMapper.selectOne(
                new LambdaQueryWrapper<StudentProfile>()
                        .eq(StudentProfile::getUserId, userId)
        );
        try {
            if (profile == null) {
                profile = new StudentProfile();
                profile.setUserId(userId);
                profile.setDimensions(objectMapper.writeValueAsString(dimensions));
                profile.setVersion(1);
                profile.setCreateTime(LocalDateTime.now());
                profile.setUpdateTime(LocalDateTime.now());
                studentProfileMapper.insert(profile);
                return;
            }
            Map<String, Object> existing = objectMapper.readValue(profile.getDimensions(), Map.class);
            for (Map.Entry<String, Object> entry : dimensions.entrySet()) {
                String key = entry.getKey();
                Object incoming = entry.getValue();
                // 情绪状态属于"当前状态"：始终以最新观测为准，不参与长期画像合并
                if ("emotionState".equals(key) || "currentLearningState".equals(key)) {
                    existing.put(key, incoming);
                    continue;
                }
                Object existingValue = existing.get(key);
                if ("knowledgeBase".equals(key)
                        && incoming instanceof Map && existingValue instanceof Map) {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> existingMap = (Map<String, Object>) existingValue;
                    @SuppressWarnings("unchecked")
                    Map<String, Object> incomingMap = (Map<String, Object>) incoming;
                    existing.put(key, mergeKnowledgeBase(existingMap, incomingMap));
                    continue;
                }
                if (incoming instanceof Map && existingValue instanceof Map) {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> existingMap = (Map<String, Object>) existingValue;
                    @SuppressWarnings("unchecked")
                    Map<String, Object> incomingMap = (Map<String, Object>) incoming;
                    if (ProfileMergePolicy.shouldApply(existingMap, incomingMap)) {
                        existing.put(key, incoming);
                    } else {
                        log.info("[profile_merge] 保留既有画像（新值证据不足）: dim={}", key);
                    }
                } else {
                    existing.put(key, incoming);
                }
            }
            profile.setDimensions(objectMapper.writeValueAsString(existing));
            profile.setVersion(profile.getVersion() + 1);
            profile.setUpdateTime(LocalDateTime.now());
            studentProfileMapper.updateById(profile);
        } catch (Exception e) {
            log.error("[profile_merge] 维度持久化失败: userId={}", userId, e);
        }
    }

    /**
     * 应用会话产生的画像更新候选（Profile Update Candidate）。
     * 候选经模型层证据过滤，此处再经状态感知合并，最终决定是否写入。
     */
    public void applyCandidates(Long userId, List<Map<String, Object>> candidates) {
        if (candidates == null || candidates.isEmpty()) {
            return;
        }
        Map<String, Object> dims = new HashMap<>();
        String today = LocalDate.now().toString();
        for (Map<String, Object> c : candidates) {
            Object dimensionObj = c.get("dimension");
            if (!(dimensionObj instanceof String)) {
                continue;
            }
            String dimension = (String) dimensionObj;
            @SuppressWarnings("unchecked")
            Map<String, Object> entry =
                    (Map<String, Object>) dims.computeIfAbsent(dimension, k -> new HashMap<>());
            entry.putIfAbsent("source", c.getOrDefault("source", "inferred"));
            entry.putIfAbsent("confidence", c.getOrDefault("confidence", 0.5));
            entry.put("updated_at", today);
            Object evidence = c.get("evidence");
            if (evidence != null && !String.valueOf(evidence).isBlank()) {
                entry.put("evidence", evidence);
            }
            if (c.containsKey("topic") && c.get("topic") != null) {
                @SuppressWarnings("unchecked")
                Map<String, Object> topics =
                        (Map<String, Object>) entry.computeIfAbsent("topics", k -> new HashMap<>());
                Map<String, Object> topic = new HashMap<>();
                topic.put("status", c.getOrDefault("topic_status", "unknown"));
                topic.put("source", c.getOrDefault("source", "inferred"));
                topic.put("confidence", c.getOrDefault("confidence", 0.5));
                topic.put("evidence", evidence == null ? "" : evidence);
                topic.put("updated_at", today);
                topics.put(String.valueOf(c.get("topic")), topic);
            } else if (c.containsKey("field") && c.get("field") != null) {
                entry.put(String.valueOf(c.get("field")), c.get("value"));
            }
        }
        if (!dims.isEmpty()) {
            mergeAndSave(userId, dims);
        }
    }

    /**
     * knowledgeBase 特殊合并：维度级字段按证据策略覆盖，但 topics 子主题逐项合并——
     * 新观测到"MCA weak"不应抹掉既有的"Willis环 ok"。
     */
    @SuppressWarnings("unchecked")
    private Map<String, Object> mergeKnowledgeBase(Map<String, Object> existing,
                                                   Map<String, Object> incoming) {
        Map<String, Object> merged = new HashMap<>(existing);
        if (ProfileMergePolicy.shouldApply(existing, incoming)) {
            Map<String, Object> incomingCopy = new HashMap<>(incoming);
            incomingCopy.remove("topics");
            merged.putAll(incomingCopy);
        }
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
}
