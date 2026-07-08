package com.learnagent.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.learnagent.entity.Result;
import com.learnagent.param.CodeAssistParam;
import com.learnagent.param.CodeExecuteParam;
import com.learnagent.utils.ThreadLocalUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.reactive.function.client.WebClient;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

@Slf4j
@RestController
@CrossOrigin("*")
@RequestMapping("/api/code")
@RequiredArgsConstructor
public class CodeController {

    private final WebClient webClient;
    private final ObjectMapper objectMapper;

    @PostMapping("/execute")
    public Result execute(@RequestBody CodeExecuteParam param) {
        if (ThreadLocalUtil.getCurrentUser() == null) {
            return Result.error("未登�?);
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
            JsonNode data = root.path("data");
            return Result.success(objectMapper.convertValue(data, Object.class));
        } catch (Exception e) {
            log.error("代码执行失败: {}", e.getMessage(), e);
            return Result.error("代码执行失败�? + e.getMessage());
        }
    }

    @PostMapping("/assist")
    public Result assist(@RequestBody CodeAssistParam param) {
        if (ThreadLocalUtil.getCurrentUser() == null) {
            return Result.error("未登�?);
        }

        Map<String, Object> body = new HashMap<>();
        body.put("prompt", param.getPrompt());
        body.put("language", param.getLanguage() != null ? param.getLanguage() : "python");
        if (param.getContext() != null) body.put("context", param.getContext());
        if (param.getExistingCode() != null) body.put("existing_code", param.getExistingCode());

        try {
            String responseStr = webClient.post()
                    .uri("/model/code/assist")
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(body)
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(Duration.ofMinutes(2))
                    .block();

            JsonNode root = objectMapper.readTree(responseStr);
            JsonNode data = root.path("data");
            return Result.success(objectMapper.convertValue(data, Object.class));
        } catch (Exception e) {
            log.error("代码辅助生成失败: {}", e.getMessage(), e);
            return Result.error("代码辅助生成失败�? + e.getMessage());
        }
    }
}