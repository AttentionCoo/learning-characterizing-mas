FROM maven:3.9-eclipse-temurin-21 AS build

WORKDIR /build
# Docker Desktop VM 的 IPv6 路由不稳定，直连 Maven Central 偶发 Network is unreachable；强制走 IPv4
ENV MAVEN_OPTS="-Djava.net.preferIPv4Stack=true"
COPY pom.xml .
# 网络偶发抖动时重试，避免单次失败中断构建
RUN set -e; ok=0; for i in 1 2 3 4 5; do \
        if mvn -q dependency:go-offline; then ok=1; break; fi; \
        echo "go-offline attempt $i failed, retrying..."; sleep 10; \
    done; [ "$ok" = "1" ]

COPY src ./src
RUN set -e; ok=0; for i in 1 2 3 4 5; do \
        if mvn -q package -DskipTests; then ok=1; break; fi; \
        echo "package attempt $i failed, retrying..."; sleep 10; \
    done; [ "$ok" = "1" ]

FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --from=build /build/target/*.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "app.jar", "--spring.profiles.active=prod"]
