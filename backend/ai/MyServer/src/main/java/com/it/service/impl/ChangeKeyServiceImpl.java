package com.it.service.impl;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.it.pojo.ChangeKey;
import com.it.pojo.Result;
import com.it.mapper.ChangeKeyMapper;
import com.it.po.uo.User;
import com.it.service.IChangeKeyService;
import lombok.RequiredArgsConstructor;
import org.springframework.data.redis.core.StringRedisTemplate;
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

    @Override
    public Result changeKeyById(Long currentId, ChangeKey changeKey) {
        User user = query().eq("id", currentId).one();

        if (changeKey.getPrePassword() != null && !changeKey.getPrePassword().isEmpty()) {
            String password = stringRedisTemplate.opsForValue().get("user:password:" + currentId);
            if (password != null) {
                return Result.success("密码已修改,三十天内不能重复修改");
            }
            if (user.getPassword().equals(changeKey.getPrePassword())) {
                user.setPassword(changeKey.getNewPassword());
            } else {
                return Result.error("密码错误");
            }
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

        if (changeKey.getNewPassword() != null && !changeKey.getNewPassword().isEmpty()) {
            stringRedisTemplate.opsForValue().set("user:password:" + currentId, changeKey.getNewPassword(), 30, TimeUnit.DAYS);
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