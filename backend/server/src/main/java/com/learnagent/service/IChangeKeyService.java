package com.learnagent.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.learnagent.entity.ChangeKey;
import com.learnagent.entity.Result;
import com.learnagent.dto.User;

public interface IChangeKeyService extends IService<User>{

    Result changeKeyById(Long currentId, ChangeKey changeKey);



    Result getUserInfo(Long currentId);
}
