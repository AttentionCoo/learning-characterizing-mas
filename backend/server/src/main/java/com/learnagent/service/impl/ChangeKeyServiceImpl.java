package com.learnagent.service.impl;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.learnagent.entity.ChangeKey;
import com.learnagent.entity.Result;
import com.learnagent.mapper.ChangeKeyMapper;
import com.learnagent.dto.User;
import com.learnagent.service.IChangeKeyService;
import lombok.RequiredArgsConstructor;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

@Service
@RequiredArgsConstructor
@Transactional
public class ChangeKeyServiceImpl extends ServiceImpl<ChangeKeyMapper, User> implements IChangeKeyService {

    private final StringRedisTemplate stringRedisTemplate;
    private final BCryptPasswordEncoder passwordEncoder;

    private static final String PWD_COOLDOWN_KEY_PREFIX = "user:pwd_changed:";

    @Override
    public Result changeKeyById(Long currentId, ChangeKey changeKey) {
        User user = query().eq("id", currentId).one();

        if (changeKey.getPrePassword() != null && !changeKey.getPrePassword().isEmpty()) {
            // 检查 30 天改密冷却：只存标记位，不存明文/密文密码
            String cooldownKey = PWD_COOLDOWN_KEY_PREFIX + currentId;
            if (stringRedisTemplate.hasKey(cooldownKey)) {
                return Result.success("密码已修改,三十天内不能重复修改");
            }
            // 使用 BCrypt 安全比对，兼容明文旧数据
            String storedPassword = user.getPassword();
            boolean matched;
            if (storedPassword != null && (storedPassword.startsWith("$2a$") || storedPassword.startsWith("$2b$"))) {
                matched = passwordEncoder.matches(changeKey.getPrePassword(), storedPassword);
            } else {
                matched = storedPassword != null && storedPassword.equals(changeKey.getPrePassword());
            }
            if (!matched) {
                return Result.error("密码错误");
            }
            // 新密码使用 BCrypt 加密后存储
            user.setPassword(passwordEncoder.encode(changeKey.getNewPassword()));
        }

        if (changeKey.getImage() != null) {
            user.setImage(changeKey.getImage());
        }
        if (changeKey.getMajor() != null) {
            user.setMajor(changeKey.getMajor());
        }
        if (changeKey.getGrade() != null) {
            user.setGrade(changeKey.getGrade());
        }
        if (changeKey.getSpecialty() != null) {
            user.setSpecialty(changeKey.getSpecialty());
        }

        user.setUpdateTime(LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")));
        updateById(user);

        // 仅在本次修改了密码时写入冷却标记（不存密码原文/哈希）
        if (changeKey.getNewPassword() != null && !changeKey.getNewPassword().isEmpty()) {
            stringRedisTemplate.opsForValue().set(PWD_COOLDOWN_KEY_PREFIX + currentId, "1", 30, TimeUnit.DAYS);
        }

        return Result.success();
    }

    @Override
    public Result getUserInfo(Long currentId) {
        User user = query().eq("id", currentId).one();
        Map<String, Object> info = new HashMap<>();
        info.put("id", user.getId());
        info.put("name", user.getName());
        info.put("image", user.getImage());
        info.put("major", user.getMajor());
        info.put("grade", user.getGrade());
        info.put("specialty", user.getSpecialty());
        return Result.success(info);
    }
}
