package com.learnagent.controller;

import com.learnagent.entity.ChangeKey;
import com.learnagent.utils.ThreadLocalUtil;
import com.learnagent.entity.Result;
import com.learnagent.service.IChangeKeyService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

@RestController
@CrossOrigin("*")
@RequestMapping("/api/user/showInfo")
public class ChangeKeyController {
    @Autowired
    private IChangeKeyService changeKeyService;

    @PutMapping("/changeKey")
    public Result changeKey(@RequestBody ChangeKey changeKey) {
        return changeKeyService.changeKeyById(ThreadLocalUtil.getCurrentUser().getId(),changeKey);
    }

    @GetMapping
    public Result getUserInfo() {
        return changeKeyService.getUserInfo(ThreadLocalUtil.getCurrentUser().getId());
    }
}
