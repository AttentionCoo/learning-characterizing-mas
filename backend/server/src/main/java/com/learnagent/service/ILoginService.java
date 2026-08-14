package com.learnagent.service;

import com.baomidou.mybatisplus.spring.service.IService;
import com.learnagent.entity.Result;
import com.learnagent.dto.User;

public interface ILoginService extends IService<User> {
    Result loginInto(User user);

    Result logOut(String token);
}
