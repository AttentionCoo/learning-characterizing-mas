package com.learnagent.controller;

import com.learnagent.dto.User;
import com.learnagent.entity.*;
import com.learnagent.service.ILoginService;
import com.learnagent.service.IRegiService;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

@RestController
@CrossOrigin("*")
@RequestMapping("/api/user")
@Slf4j
@RequiredArgsConstructor
public class LoginController {

    private final IRegiService regiService;

    private final ILoginService loginService;

    @PostMapping("/register")
    public Result register(@RequestBody User user) {
        return regiService.insertUser(user);
    }
    @PostMapping("/login")
    public Result login(@RequestBody User user) {
        return loginService.loginInto(user);
    }
    @PostMapping("/logOut")
    public Result logOut(HttpServletRequest request){
        return loginService.logOut(request.getHeader("token"));
    }
}
