FROM maven:3.9-eclipse-temurin-21 AS build

WORKDIR /build
# 阿里云 Maven 镜像：国内网络直连 Maven Central 不稳定
COPY settings-docker.xml /build/settings-docker.xml
COPY pom.xml .
RUN mvn -q -s /build/settings-docker.xml dependency:go-offline

COPY src ./src
RUN mvn -q -s /build/settings-docker.xml package -DskipTests

FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --from=build /build/target/*.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "app.jar", "--spring.profiles.active=prod"]
