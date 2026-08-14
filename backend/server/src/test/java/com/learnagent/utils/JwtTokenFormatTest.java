package com.learnagent.utils;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 回归测试：jjwt 0.12+ 的 signWith(Key) 会按密钥长度自动选择算法，
 * 512 位密钥会被签成 HS512，而模型层 PyJWT 只接受 HS256。
 * 该测试锁定后端签发的令牌必须显式使用 HS256。
 */
class JwtTokenFormatTest {

    private static final String TEST_SECRET = "0123456789abcdef0123456789abcdef0123456789abcdef";

    @Test
    void generatedTokenShouldUseHs256Algorithm() throws Exception {
        Jwt.setSecretKey(TEST_SECRET);

        String token = Jwt.generateToken(Map.of("id", "42"));

        String headerJson = new String(
                Base64.getUrlDecoder().decode(token.split("\\.")[0]),
                StandardCharsets.UTF_8);
        JsonNode header = new ObjectMapper().readTree(headerJson);

        assertThat(header.get("alg").asText()).isEqualTo("HS256");
    }

    @Test
    void generatedTokenShouldRoundTripParse() {
        Jwt.setSecretKey(TEST_SECRET);

        String token = Jwt.generateToken(Map.of("id", "42"));

        assertThat(Jwt.getUserIdFromToken(token)).isEqualTo(42L);
    }
}
