package com.learnagent.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.learnagent.param.MedicalImageParam;
import com.learnagent.entity.Result;
import com.learnagent.service.AIStreamingService;
import com.learnagent.utils.ThreadLocalUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;

import java.util.Map;

/**
 * 医学多模态影像分析控制器
 * Medical Multimodal Image Analysis Controller
 *
 * 代理前端请求�?Python FastAPI 模型推理层（/model/medical/*�? */
@Slf4j
@RestController
@CrossOrigin("*")
@RequestMapping("/api/medical")
@RequiredArgsConstructor
public class MedicalController {

    private final AIStreamingService streamingService;
    private final ObjectMapper objectMapper;

    /**
     * 医学影像结构化分析（非流式，代理�?Python /model/medical/analyze-image�?     */
    @PostMapping("/analyze-image")
    public Result analyzeImage(@RequestBody MedicalImageParam param) {
        log.info("[Medical] 收到影像分析请求 - 图片数量: {}, 问题: {}",
                param.getImages() != null ? param.getImages().size() : 0,
                param.getQuestion() != null ? param.getQuestion().substring(0, Math.min(50, param.getQuestion().length())) : "");

        try {
            // 通过 streamingService 转发�?Python 模型�?            Map<String, Object> requestBody = Map.of(
                    "images", param.getImages() != null ? param.getImages() : java.util.Collections.emptyList(),
                    "question", param.getQuestion() != null ? param.getQuestion() : "",
                    "all_info", param.getAllInfo() != null ? param.getAllInfo() : "",
                    "expected_image_type", param.getExpectedImageType() != null ? param.getExpectedImageType() : ""
            );

            String response = streamingService.callModelSync("/model/medical/analyze-image", requestBody);
            JsonNode jsonNode = objectMapper.readTree(response);
            return Result.success(jsonNode.get("data"));
        } catch (Exception e) {
            log.error("[Medical] 影像分析失败: {}", e.getMessage(), e);
            return Result.error("医学影像分析失败: " + e.getMessage());
        }
    }

    /**
     * 多模态病例综合分析（SSE 流式，代理到 Python /model/medical/analyze-case�?     */
    @PostMapping(value = "/analyze-case", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> analyzeCase(
            @RequestBody MedicalImageParam param,
            @RequestHeader(value = "token", required = false) String token,
            @RequestHeader(value = "Authorization", required = false) String authorization,
            HttpServletResponse response
    ) {
        response.setHeader("X-Accel-Buffering", "no");
        response.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");

        log.info("[Medical] 收到多模态病例分析SSE请求 - 图片数量: {}",
                param.getImages() != null ? param.getImages().size() : 0);

        Map<String, Object> requestBody = new java.util.HashMap<>();
        requestBody.put("message", param.getMessage() != null ? param.getMessage() : param.getQuestion());
        requestBody.put("images", param.getImages() != null ? param.getImages() : java.util.Collections.emptyList());
        requestBody.put("case_type", param.getCaseType() != null ? param.getCaseType() : "general");
        requestBody.put("include_evidence", param.getIncludeEvidence() != null ? param.getIncludeEvidence() : true);
        if (param.getTalkId() != null) {
            requestBody.put("talkId", param.getTalkId());
        }

        return streamingService.streamToModel("/model/medical/analyze-case", requestBody, token);
    }

    /**
     * 多图对比分析（代理到 Python /model/medical/compare-images�?     */
    @PostMapping("/compare-images")
    public Result compareImages(@RequestBody MedicalImageParam param) {
        log.info("[Medical] 收到多图对比请求 - 图片数量: {}",
                param.getImages() != null ? param.getImages().size() : 0);

        try {
            Map<String, Object> requestBody = Map.of(
                    "images", param.getImages() != null ? param.getImages() : java.util.Collections.emptyList(),
                    "question", param.getQuestion() != null ? param.getQuestion() : "",
                    "all_info", param.getAllInfo() != null ? param.getAllInfo() : ""
            );

            String response = streamingService.callModelSync("/model/medical/compare-images", requestBody);
            JsonNode jsonNode = objectMapper.readTree(response);
            return Result.success(jsonNode.get("data"));
        } catch (Exception e) {
            log.error("[Medical] 多图对比失败: {}", e.getMessage(), e);
            return Result.error("多图对比分析失败: " + e.getMessage());
        }
    }

    /**
     * DICOM元数据提取（代理�?Python /model/medical/dicom-metadata�?     */
    @PostMapping("/dicom-metadata")
    public Result extractDICOMMetadata(@RequestBody MedicalImageParam param) {
        log.info("[Medical] 收到DICOM元数据提取请�?);

        try {
            if (param.getImages() == null || param.getImages().isEmpty()) {
                return Result.error("需要DICOM文件数据");
            }

            Map<String, Object> requestBody = Map.of(
                    "image", param.getImages().get(0)
            );

            String response = streamingService.callModelSync("/model/medical/dicom-metadata", requestBody);
            JsonNode jsonNode = objectMapper.readTree(response);
            return Result.success(jsonNode.get("data"));
        } catch (Exception e) {
            log.error("[Medical] DICOM元数据提取失�? {}", e.getMessage(), e);
            return Result.error("DICOM元数据提取失�? " + e.getMessage());
        }
    }

    /**
     * 检验报告OCR提取（代理到 Python /model/medical/ocr/lab-report�?     */
    @PostMapping("/ocr/lab-report")
    public Result extractLabReport(@RequestBody MedicalImageParam param) {
        log.info("[Medical] 收到检验报告OCR请求");

        try {
            if (param.getImages() == null || param.getImages().isEmpty()) {
                return Result.error("需要检验报告图�?);
            }

            Map<String, Object> requestBody = Map.of(
                    "images", param.getImages(),
                    "question", param.getQuestion() != null ? param.getQuestion() : "",
                    "all_info", param.getAllInfo() != null ? param.getAllInfo() : ""
            );

            String response = streamingService.callModelSync("/model/medical/ocr/lab-report", requestBody);
            JsonNode jsonNode = objectMapper.readTree(response);
            return Result.success(jsonNode.get("data"));
        } catch (Exception e) {
            log.error("[Medical] 检验报告OCR失败: {}", e.getMessage(), e);
            return Result.error("检验报告OCR提取失败: " + e.getMessage());
        }
    }

    /**
     * 处方OCR提取（代理到 Python /model/medical/ocr/prescription�?     */
    @PostMapping("/ocr/prescription")
    public Result extractPrescription(@RequestBody MedicalImageParam param) {
        log.info("[Medical] 收到处方OCR请求");

        try {
            if (param.getImages() == null || param.getImages().isEmpty()) {
                return Result.error("需要处方图�?);
            }

            Map<String, Object> requestBody = Map.of(
                    "images", param.getImages(),
                    "question", param.getQuestion() != null ? param.getQuestion() : ""
            );

            String response = streamingService.callModelSync("/model/medical/ocr/prescription", requestBody);
            JsonNode jsonNode = objectMapper.readTree(response);
            return Result.success(jsonNode.get("data"));
        } catch (Exception e) {
            log.error("[Medical] 处方OCR失败: {}", e.getMessage(), e);
            return Result.error("处方OCR提取失败: " + e.getMessage());
        }
    }

    /**
     * DICOM �?PNG 预览转换（代理到 Python /model/medical/dicom-to-png�?     * 用于前端无法直接渲染 DICOM 文件时的缩略图预�?     */
    @PostMapping("/dicom-to-png")
    public Result dicomToPng(@RequestBody MedicalImageParam param) {
        log.info("[Medical] 收到DICOM转PNG请求");

        try {
            if (param.getImages() == null || param.getImages().isEmpty()) {
                return Result.error("需要DICOM文件数据");
            }

            Map<String, Object> requestBody = Map.of(
                    "image", param.getImages().get(0)
            );

            String response = streamingService.callModelSync("/model/medical/dicom-to-png", requestBody);
            JsonNode jsonNode = objectMapper.readTree(response);
            return Result.success(jsonNode.get("data"));
        } catch (Exception e) {
            log.error("[Medical] DICOM转PNG失败: {}", e.getMessage(), e);
            return Result.error("DICOM转PNG失败: " + e.getMessage());
        }
    }
}