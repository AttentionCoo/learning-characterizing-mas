# LearnAgent Backend

多智能体个性化学习系统后端服务

## 项目简介

基于 **Spring Boot 3.3** 构建的个性化学习系统后端服务。作为前端交互层与模型推理层的中间枢纽，提供 JWT 鉴权、Redisson 分布式限流、WebClient 响应式流式转发、SSE 断线续传、对话持久化等企业级能力。

## 技术栈

### 核心框架
- **后端框架**: Spring Boot 3.3 (Java 21)
- **ORM 框架**: MyBatis-Plus 3.5
- **响应式编程**: Project Reactor (Flux/Mono), Spring WebFlux Client
- **工具库**: Hutool, Lombok, Jackson

### 中间件与存储
- **数据库**: MySQL 8.0
- **缓存/会话**: Redis (StringRedisTemplate)
- **分布式组件**: Redisson (分布式锁、信号量限流)
- **连接池**: HikariCP
- **对象存储**: 阿里云 OSS

## 核心亮点

### 1. 响应式 AI 流式转发
核心业务采用 `WebClient` + `Flux` 实现全异步非阻塞的流式响应，支持高并发下的实时 AI 回复。
- **并发控制**: Redisson `RSemaphore` 全局并发量控制（permits=20），防止 AI 服务过载
- **异步持久化**: `ConversationPersistenceService` 异步线程池策略，对话记录入库与 AI 回复流分离
- **多级缓存**: 对话上下文支持 Redis 短期缓存，减少数据库查询压力

### 2. 企业级鉴权体系
- **双重拦截器机制**:
  - `RefreshTokenInterceptor`: 全局 Token 自动续期，用户活跃时自动延长有效期
  - `TokenInterceptor`: 权限校验与路径放行
- **单设备登录**: 登录时生成唯一 `JTI` (JWT ID)，新设备登录时旧设备 Token 自动失效
- **ThreadLocal 上下文隔离**: 请求链路中通过 `ThreadLocal` 传递用户信息

### 3. SSE 断线续传
- **滑动窗口缓存**: SSE 事件缓存（TTL=5min），支持断线重连后自动回放
- **Last-Event-ID 机制**: 浏览器断线重连时携带最后收到的事件 ID，后端精准续传

### 4. 高性能架构设计
- **Redis 会话管理**: Redis Hash 存储用户信息，String 存储 JTI
- **优雅停机**: Spring Boot Graceful Shutdown，保障流式请求完整性

## 核心业务流程

### 用户登录与鉴权
1. **登录**: 验证通过后，生成 JWT 与 JTI
2. **互斥**: 清理该用户在 Redis 中的旧 Token，设置新 JTI
3. **缓存**: 将 UserDTO 存入 `user:token:{token}`，设置 TTL
4. **请求**: 拦截器校验 → 自动续期 TTL → 存入 ThreadLocal → 业务处理 → 销毁 ThreadLocal

### AI 对话流
1. **用户请求**: 前端发起 SSE 或流式请求
2. **限流检查**: Redisson 信号量获取许可
3. **构建上下文**: 从 Redis/MySQL 获取最近 N 条历史记录
4. **请求模型层**: WebClient 异步调用 Python FastAPI 模型服务
5. **流式回传**: 收到 Chunk 数据即刻推送到前端
6. **异步入库**: 对话结束时，异步任务将完整问答落库 MySQL

## 快速开始

### 1. 环境准备
- MySQL 8.0+
- Redis 6.0+
- JDK 21+

### 2. 配置文件
修改 `src/main/resources/application.yml`:
```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/medai?serverTimezone=Asia/Shanghai
    username: root
    password: your_password
  data:
    redis:
      host: localhost
      port: 6379
```

### 3. 运行
```bash
cd backend/ai/MyServer
mvn clean spring-boot:run
```

## 目录结构

```
com.it
├── config          # 配置类（Security/WebClient/Redisson/OSS/Jackson/MyBatisPlus）
├── controller      # REST 控制器（15个：画像/资源/路径/辅导/评估/医学影像/代码/监控/用户/课程/文档/题目/登录/上传/首页）
├── handler         # 全局异常处理
├── interceptor     # 拦截器（Token 校验与刷新）
├── mapper          # MyBatis Mapper 接口
├── po              # 持久化对象
│   ├── dto/        # 数据传输对象
│   ├── uo/         # 请求参数对象
│   └── vo/         # 响应视图对象
├── pojo/           # 实体类
├── service         # 业务逻辑层
│   └── impl/       # 服务实现
├── utils           # 工具类（JWT/OSS/IP/ThreadLocal）
└── MyServerApplication.java  # 启动类
```

## API 控制器一览

| 控制器 | 路径前缀 | 职责 |
|:---|:---|:---|
| `LoginController` | `/api/user` | 用户注册/登录/信息管理 |
| `ProfileController` | `/api/profile` | 对话式学习画像构建 |
| `ResourceController` | `/api/resource` | 个性化资源生成 |
| `TutorController` | `/api/tutor` | 智能辅导问答 |
| `LearningPathController` | `/api/learning-path` | 学习路径规划 |
| `AssessmentController` | `/api/assessment` | 学习效果评估 |
| `MedicalController` | `/api/medical` | 医学多模态影像分析 |
| `CodeController` | `/api/code` | 代码执行与辅助 |
| `UploadController` | `/api/user/upload` | 文件上传 |
| `MonitorController` | `/api/monitor` | 系统监控与限流状态 |

完整接口规范详见 `docs/多智能体个性化学习系统接口文档.md`。

## 部署

| 文档 | 说明 |
|:---|:---|
| `baota-deploy.md` | 宝塔面板部署指南 |
| `deploy-guide.md` | 通用部署文档 |