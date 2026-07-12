package com.learnagent.config;

import com.learnagent.utils.AliOssUpload;
import com.learnagent.config.AliOssProperties;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OssConfig {
    @Bean
    @ConditionalOnMissingBean
    public AliOssUpload aliOssUpload(AliOssProperties aliOssProperties) {
        return new AliOssUpload(
                aliOssProperties.getEndpoint(),
                aliOssProperties.getBucketName(),
                aliOssProperties.getRegion(),
                aliOssProperties.getAccessKeyId(),
                aliOssProperties.getAccessKeySecret()
        );
    }
}