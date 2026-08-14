package com.learnagent.utils;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.Map;

public class Jwt {
    // 由 JwtConfig 在 Spring 启动时通过 setSecretKey() 注入，禁止在此处硬编码密钥
    private static String secretKey;

    /**
     * 由 JwtConfig#init() 调用，将配置文件中的密钥注入到静态字段。
     * 应用启动后仅调用一次。
     */
    public static void setSecretKey(String key) {
        secretKey = key;
    }

    /**
     * HS256 签名密钥：jjwt 0.13 要求至少 256 位（32 字节），弱密钥直接快速失败。
     */
    private static SecretKey signingKey() {
        if (secretKey == null || secretKey.isBlank()) {
            throw new IllegalStateException("JWT 密钥未初始化，请检查 ai.security.shared-jwt-secret 配置项");
        }
        byte[] bytes = secretKey.getBytes(StandardCharsets.UTF_8);
        if (bytes.length < 32) {
            throw new IllegalStateException(
                    "JWT 密钥过短（" + bytes.length + " 字节），HS256 至少需要 32 字节。" +
                    "请将 ai.security.shared-jwt-secret 设置为至少 32 字节的随机密钥");
        }
        return Keys.hmacShaKeyFor(bytes);
    }

    public static String generateToken(Map<String,Object> claims) {
        return Jwts.builder()
                .claims(claims)
                .expiration(new Date(System.currentTimeMillis() + 1000 * 60 * 60 * 24 * 3))
                // 必须显式指定 HS256：jjwt 0.12+ 的 signWith(Key) 会按密钥长度自动选择最强算法
                // （512 位密钥会签成 HS512），导致模型层 PyJWT(algorithms=["HS256"]) 校验失败
                .signWith(signingKey(), Jwts.SIG.HS256)
                .compact();
    }

    public static Claims parseToken(String token) {
        return Jwts.parser()
                .verifyWith(signingKey())
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }

    public static Long getUserIdFromToken(String token) {
        return Long.valueOf(parseToken(token).get("id").toString());
    }

    // --- 新增：从 Token 中获取 JTI ---
    public static String getJtiFromToken(String token) {
        return parseToken(token).get("jti").toString();
    }
}
