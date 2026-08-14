package com.learnagent.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.core.env.PropertySource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mock.env.MockEnvironment;

import java.io.IOException;

import static org.assertj.core.api.Assertions.assertThat;

class ProductionJwtConfigurationTest {

    private static final String PROPERTY = "aiserver.ai-api.shared-jwt-secret";
    private static final String DATABASE_PASSWORD = "aiserver.datasource.password";

    @Test
    void shouldUseDeploymentDatabasePasswordWhenBaotaDoesNotInjectIt() throws IOException {
        MockEnvironment environment = loadProductionEnvironment();

        assertThat(environment.getProperty(DATABASE_PASSWORD)).isEqualTo("123456");
    }

    @Test
    void shouldPreferDatabasePasswordEnvironmentVariable() throws IOException {
        MockEnvironment environment = loadProductionEnvironment()
                .withProperty("DB_PASSWORD", "secure-database-password");

        assertThat(environment.getProperty(DATABASE_PASSWORD)).isEqualTo("secure-database-password");
    }

    @Test
    void shouldUseCompatibilityDefaultWhenBaotaDoesNotInjectEnvironmentVariables() throws IOException {
        MockEnvironment environment = loadProductionEnvironment();

        assertThat(environment.getProperty(PROPERTY)).isEqualTo("your-secret-key-here-please-change-this");
    }

    @Test
    void shouldReuseModelServiceSecretKeyInBaota() throws IOException {
        MockEnvironment environment = loadProductionEnvironment()
                .withProperty("SECRET_KEY", "shared-model-secret");

        assertThat(environment.getProperty(PROPERTY)).isEqualTo("shared-model-secret");
    }

    @Test
    void shouldPreferDedicatedBackendSecret() throws IOException {
        MockEnvironment environment = loadProductionEnvironment()
                .withProperty("SECRET_KEY", "shared-model-secret")
                .withProperty("AI_API_SHARED_JWT_SECRET", "dedicated-backend-secret");

        assertThat(environment.getProperty(PROPERTY)).isEqualTo("dedicated-backend-secret");
    }

    private MockEnvironment loadProductionEnvironment() throws IOException {
        YamlPropertySourceLoader loader = new YamlPropertySourceLoader();
        PropertySource<?> production = loader
                .load("application-prod", new ClassPathResource("application-prod.yml"))
                .getFirst();
        MockEnvironment environment = new MockEnvironment();
        environment.getPropertySources().addLast(production);
        return environment;
    }
}
