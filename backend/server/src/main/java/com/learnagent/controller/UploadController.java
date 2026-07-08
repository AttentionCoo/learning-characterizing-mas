package com.learnagent.controller;

import com.learnagent.utils.AliOssUpload;
import com.learnagent.entity.Result;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;

@RestController
@CrossOrigin("*")
@RequestMapping("/api/user")
@Slf4j
public class UploadController {
    @Autowired
    private AliOssUpload aliOssUpload;

    private static final long MAX_IMAGE_SIZE = 5 * 1024 * 1024;
    private static final Set<String> ALLOWED_EXTENSIONS = Set.of("jpg", "jpeg", "png", "webp", "gif");

    @PostMapping("/upload")
    public Result upload(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            return Result.error("请选择要上传的图片");
        }
        if (file.getSize() > MAX_IMAGE_SIZE) {
            return Result.error("图片不能超过5MB");
        }

        String originalFilename = StringUtils.cleanPath(file.getOriginalFilename() == null ? "" : file.getOriginalFilename());
        String extension = getExtension(originalFilename);
        if (!ALLOWED_EXTENSIONS.contains(extension)) {
            return Result.error("仅支�?jpg、png、webp、gif 图片");
        }

        try {
            String url = aliOssUpload.upload(file.getBytes(), originalFilename);
            return Result.success(url);
        } catch (Exception e) {
            log.warn("OSS 上传失败，切换到本地上传: {}", e.getMessage());
            try {
                return Result.success(saveLocal(file, extension));
            } catch (Exception localError) {
                log.error("本地文件上传失败", localError);
                return Result.error("文件上传失败");
            }
        }
    }

    private String saveLocal(MultipartFile file, String extension) throws Exception {
        String datePath = LocalDate.now().format(DateTimeFormatter.ofPattern("yyyy/MM"));
        String filename = UUID.randomUUID() + "." + extension;
        Path uploadDir = Path.of("uploads", "avatar", datePath).toAbsolutePath().normalize();
        Files.createDirectories(uploadDir);
        Files.write(uploadDir.resolve(filename), file.getBytes());
        return "/uploads/avatar/" + datePath + "/" + filename;
    }

    private String getExtension(String filename) {
        int dot = filename.lastIndexOf('.');
        if (dot < 0 || dot == filename.length() - 1) return "";
        return filename.substring(dot + 1).toLowerCase(Locale.ROOT);
    }
}
