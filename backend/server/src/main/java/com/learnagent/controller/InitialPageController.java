package com.learnagent.controller;

import com.learnagent.utils.ThreadLocalUtil;
import com.learnagent.entity.Result;
import com.learnagent.service.IInitialPageService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

@RestController
@CrossOrigin("*")
@RequestMapping("/api/user")
@Slf4j
public class InitialPageController {
    @Autowired
    private IInitialPageService initialPageService;

    @GetMapping("/title")
    public Result getTitle(){
        return Result.success(initialPageService.getPage(ThreadLocalUtil.getCurrentUser().getId()));
    }

    @DeleteMapping("deleteTalk/{talk_id}")
    public Result deleteTalk(@PathVariable("talk_id") Long talkId){
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        initialPageService.deleteTalk(userId,talkId);
        return Result.success();
    }
}
