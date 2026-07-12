
<div align="center">

# LearnAgent

### 多智能体个性化学习系统

**基于大模型技术体系的高等教育个性化学习智能体系统**

[![Java 21](https://img.shields.io/badge/Java-21+-ED8B00?style=flat-square&logo=openjdk&logoColor=white)](https://openjdk.org/)
[![Python 3.11](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Vue 3.5](https://img.shields.io/badge/Vue-3.5-4FC08D?style=flat-square&logo=vue.js&logoColor=white)](https://vuejs.org/)
[![Spring Boot 3.3](https://img.shields.io/badge/Spring%20Boot-3.3-6DB33F?style=flat-square&logo=springboot&logoColor=white)](https://spring.io/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2.20-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

</div>

---

面向高等教育场景（脑卒中方向医学生）的个性化学习智能体系统。以高校专业课程知识库为底座，融合 **多智能体协同推理**、**Hybrid RAG**、**多模态影像识别** 与 **全栈响应式流式架构**，实现从学生画像构建到个性化资源生成、学习路径规划、智能辅导、学习效果评估的完整闭环。

## ✦ 核心亮点

| 特性 | 说明 |
|:---|:---|
| 🧠 **三群协同多智能体架构** | 基于 LangGraph StateGraph 构建 8 个专家智能体，YAML 配置驱动，支持动态编排与辩论-仲裁机制 |
| 🔍 **证据前置 Hybrid RAG** | ChromaDB + DashScope 语义向量 + BM25 精准匹配，Reranker 深度重排，强制文献溯源 |
| ⚡ **全栈响应式流式管道** | Java WebFlux + Python Asyncio 深度流式融合，AI 思考过程完全透明可视化，SSE 断线续传 |
| 🖼️ **多模态视觉理解** | qwen-vl-max 视觉理解，课件笔记 / 代码截图 / 医学影像自动分类分析，图文联合理解 |

---

## 📐 系统架构

### 三层解耦架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        前端交互层 Frontend                        │
│   Vue 3.5 · Vite 7 · Pinia 3 · marked 17 · DOMPurify · pdfjs   │
├──────────────────────────────────────────────────────────────────┤
│                        后端服务层 Backend                         │
│   Java 21 · Spring Boot 3.3 · WebFlux · Security · Redisson     │
│   MySQL 8.0 · MyBatis-Plus 3.5 · 阿里云 OSS                     │
├──────────────────────────────────────────────────────────────────┤
│                        模型推理层 Model                           │
│   Python 3.11 · FastAPI · LangGraph · LangChain · Qwen          │
│   ChromaDB · gte-rerank · qwen-vl-max                           │
└──────────────────────────────────────────────────────────────────┘
```

### 全链路流式数据管道

```
 学生输入                                                    前端渲染
    │                                                          ▲
    ▼                                                          │
┌─────────┐  WebClient   ┌─────────┐  AsyncTaskManager  ┌──────────┐
│  Java   │ ──────────► │ FastAPI │ ─────────────────► │ Learning │
│ 鉴权限流 │   异步调用    │  接收    │    创建任务         │  Agent   │
└─────────┘              └─────────┘                    └──────────┘
                                                              │
                         ┌────────────────────────────────────┘
                         ▼
              LangGraph astream_events
                         │
                         ▼
              _translate_event 翻译标准事件
                         │
                         ▼
              asyncio.Queue ──► Java Flux 转发 ──► Vue3 ReadableStream
```

### 技术矩阵

| 层级 | 核心技术 | 职责 |
|:---|:---|:---|
| **前端** | Vue 3.5 · Vite 7 · Pinia 3 · marked 17 · DOMPurify · pdfjs-dist | 流式渲染 · Markdown 展示 · 思考步骤折叠 · 学习路径可视化 · PDF 预览 |
| **后端** | Java 21 · Spring Boot 3.3 · WebFlux · Security · Redisson 3.27 · MySQL 8.0 · MyBatis-Plus 3.5 | 响应式高并发 · JWT 认证 · 分布式限流 · WebClient 流式转发 · SSE 断线续传 |
| **模型** | Python 3.11 · FastAPI 0.128 · LangGraph 0.2.20 · Qwen-Max/Plus/Turbo · ChromaDB 0.5 · gte-rerank · qwen-vl-max | 多智能体编排 · Hybrid RAG · 流式事件输出 · 多模态识别 · 文献检索 |

---

## 📁 项目结构

```
learning-multi-agent-system/
├── frontend/                        # 前端交互层（Vue 3）
│   └── src/
│       ├── api/                     # API 请求（画像/资源/路径/辅导/评估）
│       ├── components/              # 组件（表单/头像/加载/对话）
│       ├── views/                   # 页面（登录/画像/资源/路径/辅导/评估）
│       ├── stores/                  # Pinia 状态管理
│       ├── utils/                   # 工具（请求封装/图片压缩）
│       └── router/                  # 路由配置
│
├── backend/ai/MyServer/             # 后端服务层（Java Spring Boot）
│   └── src/main/java/com/it/
│       ├── controller/              # REST 控制器（14 个）
│       ├── service/                 # 业务逻辑（AI 流式/对话持久化/OSS）
│       ├── cache/                   # SSE 事件缓存
│       ├── config/                  # 配置（Security/WebClient/Redisson/OSS）
│       ├── pojo/                    # 实体类
│       ├── po/                      # 请求参数 & 响应视图对象
│       ├── mapper/                  # MyBatis-Plus Mapper
│       └── utils/                   # JWT/OSS/IP 工具
│
├── model/                           # 模型推理层（Python FastAPI）
│   └── app/
│       ├── main.py                  # FastAPI 入口（应用装配 & lifespan）
│       ├── runtime.py               # 全局资源容器 & JWT 校验
│       ├── routers/                 # API 路由（推理流式 / 画像抽取 / 评估优化 / 管理）
│       ├── agents/                  # 多智能体核心
│       │   ├── orchestrators/       # LangGraph 图定义 & 6 个节点实现
│       │   ├── core/                # 状态模型 / 异常 / 结果封装
│       │   ├── infra/               # Reranker 容灾
│       │   ├── services/            # 检索 / 查询 / 综合服务
│       │   └── utils/               # LLM / JSON / 重试 / 文本工具
│       ├── rag/                     # Hybrid RAG（向量 + BM25 / QA 生成 / 文档加载）
│       ├── services/                # 多模态影像 / 画像抽取 / 后台任务执行
│       ├── config/                  # YAML 配置（专家 / 规则 / 模板 / Prompt / 限额）
│       └── utils/                   # 任务管理 / 上下文摘要 / Token 聚合
│
└── docs/                            # 项目文档
```

---

## 🤖 多智能体协同机制

### LangGraph 推理拓扑

```
                           用户输入
                              │
                    ┌──────── ▼ ────────┐
                    │   Intent Node     │
                    │ 意图分类 + 难度评分 │
                    └──────── ┬ ────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
         irrelevant        simple         complex
              │               │               │
              ▼               ▼               ▼
        ┌──────────┐   ┌──────────┐   ┌──────────────┐
        │  Reject  │   │  Fast    │   │  Analysis    │
        │  Node    │   │  Track   │   │  Node        │
        └──────────┘   └──────────┘   └──────┬───────┘
                                             │
                                    ┌──────── ▼ ────────┐
                                    │  Retrieve Node    │
                                    │ Hybrid RAG 证据检索│
                                    └──────── ┬ ────────┘
                                             │
                                    ┌──────── ▼ ────────┐
                                    │   Reason Node     │
                                    │ 多智能体推理+辩论  │
                                    └──────── ┬ ────────┘
                                             │
                                    ┌──────── ▼ ────────┐
                                    │  Validate Node    │
                                    │ 质量校验+退火反思  │ ──↺ 校验失败
                                    └──────── ┬ ────────┘
                                             │
                                    ┌──────── ▼ ────────┐
                                    │   Report Node     │
                                    │ 报告生成+学习激励  │
                                    └───────────────────┘
```

### 智能体角色矩阵

| 角色 | 优先级 | 适用意图 | 职责 |
|:---|:---:|:---|:---|
| 画像对话智能体 | 1 | 全场景 | 引导式对话，收集学生信息 |
| 特征抽取智能体 | 2 | profile / assessment | 自动抽取 8 维度画像特征 |
| 需求分析智能体 | 3 | resource / tutor / learning_path | 分析需求，拆解任务 |
| 文档撰写智能体 | 4 | resource | 生成专业课程讲解文档 |
| 题目生成智能体 | 5 | resource / assessment | 生成多类型练习题目 |
| 质量审核智能体 | 6 | resource / assessment / learning_path | 审核学术准确性与个性化匹配 |
| 学习激励智能体 | 7 | 全场景 | 情绪识别与激励反馈 |
| 仲裁智能体 | 8 | resource / tutor / assessment / learning_path | 依据证据链裁决辩论 |

### 辩论-仲裁机制

```
 ┌──────────────────────────────────────────────────────┐
 │  Step 1: 并行推理                                     │
 │  asyncio.gather → 各专家独立生成建议                    │
 ├──────────────────────────────────────────────────────┤
 │  Step 2: 多轮辩论                                     │
 │  各专家基于辩论上下文提出反驳或补充                       │
 │  （立场 + 论据 + 回应）                                │
 ├──────────────────────────────────────────────────────┤
 │  Step 3: 仲裁裁决                                     │
 │  仲裁智能体 → ARBITRATION 结论 + REASONING 推理过程     │
 ├──────────────────────────────────────────────────────┤
 │  Step 4: 意见综合                                     │
 │  加权合并专家意见与仲裁裁决 → 最终提案                   │
 └──────────────────────────────────────────────────────┘
```

### 动态退火反思

校验失败时自动触发：

| 机制 | 说明 |
|:---|:---|
| **驳回分类** | 5 类：事实错误 / 逻辑矛盾 / 个性化不足 / 医学专业性错误 / 内容不完整 |
| **针对性修正** | 每类驳回生成对应修正指引 |
| **权重衰减** | 发言权重按 0.5 因子衰减（最低 0.2），避免无效重试 |

### 动态编排

根据意图类型和难度评分动态裁剪参与智能体：

| 意图 | 专家数 | 参与角色 |
|:---|:---:|:---|
| `profile` | 3 | 画像对话 + 特征抽取 + 学习激励 |
| `resource` | 6 | 需求分析 + 文档撰写 + 题目生成 + 质量审核 + 学习激励 + 画像对话 |
| `tutor` | 4 | 画像对话 + 需求分析 + 质量审核 + 学习激励 |
| `assessment` | 5 | 特征抽取 + 需求分析 + 题目生成 + 质量审核 + 学习激励 |
| `learning_path` | 4 | 画像对话 + 需求分析 + 质量审核 + 学习激励 |

> 仲裁智能体在辩论启用且难度 ≥ 0.6 时自动加入。

---

## 🎯 功能模块

| 模块 | 功能 | 关键特性 |
|:---|:---|:---|
| **对话式学习画像** | 自然语言对话自动抽取特征，构建 8 维度动态画像 | 知识基础 · 认知风格 · 学习目标 · 易错点 · 学习节奏 · 资源偏好 · 临床经验 · 情绪状态 |
| **多智能体资源生成** | 8 种个性化资源类型 | 课程讲解文档 · 思维导图 · 练习题目 · 拓展阅读 · 临床案例 · 设计方案 · 评估报告 · 代码实操案例 |
| **学习路径规划** | 根据画像生成 5-15 步学习路径 | 前置步骤依赖 · 精准资源推送 · 路径动态调整 · 步骤进度追踪 |
| **智能辅导** | 即时多模态答疑 | 文字解答 · 图片识别(qwen-vl-max) · 上下文感知 · 偏好回答形式 |
| **学习效果评估** | 5 维度评估 + 闭环优化 | 知识掌握度 · 学习效率 · 技能应用 · 学习一致性 · 进度对齐度 |
| **多模态影像识别** | 自动识别图片类型并匹配分析策略 | 课件笔记 · 代码编程 · 通用医学影像 · 多图联合分析 |
| **代码辅助开发** | 医学数据分析编程助手 | 代码补全 · 错误诊断 · 优化建议 · 沙箱执行(python -I + 资源上限) |

> 所有资源生成与辅导接口均支持 **SSE 流式输出** 和 **图片输入**。

---

## 🚀 快速开始

### 方式一：Docker Compose 一键启动（推荐）

```bash
cp .env.example .env   # 填写 DASHSCOPE_API_KEY 等必需密钥
docker compose up -d --build
```

- 前端：`http://localhost:5173`（MySQL/Redis/后端/模型层自动编排启动）
- 课程 PDF 放入 `model/data/documents/` 后重启 model 服务即可自动构建向量库

### 方式二：本地手动启动

### 环境要求

| 依赖 | 版本 | 说明 |
|:---|:---|:---|
| Java | 21+ | 后端运行时 |
| Python | 3.11+ | 模型推理层 |
| Node.js | 18+ | 前端构建 |
| MySQL | 8.0+ | 数据存储 |
| Redis | 6.0+ | 缓存与限流 |
| DashScope API Key | — | 阿里云大模型服务（必需） |

### 启动步骤

**Step 1 — 初始化数据库**

```bash
mysql -u root -p < backend/ai/MyServer/learningo-agents.sql
```

**Step 2 — 启动模型推理服务**

```bash
cd model

# 推荐使用快速启动脚本
# Windows
start.bat
# Linux / macOS
chmod +x start.sh && ./start.sh

# 或手动启动
pip install -r requirements.txt
python -m app.main
```

- 服务地址：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`
- 首次启动自动加载 PDF 文献并构建向量库

**Step 3 — 启动后端服务**

```bash
cd backend/ai/MyServer
mvn spring-boot:run
```

- 服务地址：`http://localhost:8080`

**Step 4 — 启动前端服务**

```bash
cd frontend
npm install
npm run dev
```

- 前端地址：`http://localhost:5173`

---

## ⚙️ 配置说明

### 模型层环境变量（`model/.env`）

```bash
# 必需 - 阿里云 DashScope API Key
DASHSCOPE_API_KEY="sk-your-dashscope-api-key"

# 必需 - JWT 密钥（需与 Java 后端一致）
SECRET_KEY="your-jwt-secret-key"

# 可选 - DeepSeek API Key（备用 LLM）
DEEPSEEK-API-KEY="sk-your-deepseek-api-key"

# 可选 - 课程 PDF 目录（默认 model/data/documents/）
MEDICAL_DOCS_DIR="/path/to/your/pdf/documents"
```

### 模型层 YAML 配置

| 配置文件 | 说明 |
|:---|:---|
| `expert_config.yaml` | 8 个专家定义 · 辩论配置 · 动态编排规则 |
| `rules_config.yaml` | 质量校验规则 · 退火策略（5 类驳回分类与修正） |
| `report_templates.yaml` | 5 种报告模板（画像 / 资源 / 辅导 / 评估 / 路径） |
| `prompts.yaml` | 各场景 Prompt 模板库 |
| `limits_config.yaml` | 参数上限与关键词配置 |

### 后端配置

通过 `application-dev.yml`（开发）或 `application-prod.yml`（生产）配置数据库、Redis、AI 服务地址、JWT 共享密钥和阿里云 OSS。

---

## 📡 API 概览

### 全局约定

| 项目 | 说明 |
|:---|:---|
| Java 后端 | `http://localhost:8080/api` |
| Python 模型层 | `http://localhost:8000/model` |
| 认证方式 | 除登录/注册外，所有接口需携带 JWT Token |
| 响应体格式 | `{ code: 1, msg: "success", data: {} }` |

### SSE 流式事件

| 事件 | 说明 |
|:---|:---|
| `init` | 连接建立，返回任务 ID |
| `node_start` | 智能体节点开始推理 |
| `token` | 内容片段（增量） |
| `node_done` | 节点完成 |
| `done` | 流式结束 |
| `error` | 错误 |

### 核心 API

| 模块 | 接口 | 方法 | 说明 |
|:---|:---|:---|:---|
| 认证 | `/api/user/login` | POST | 用户登录 |
| 认证 | `/api/user/register` | POST | 用户注册 |
| 画像 | `/api/profile/conversation` | POST (SSE) | 对话式画像构建 |
| 画像 | `/api/profile` | GET | 获取当前画像 |
| 画像 | `/model/profile/extract` | POST | 抽取画像维度 |
| 资源 | `/api/resources/generate` | POST (SSE) | 综合资源生成 |
| 资源 | `/api/resources/generate/*` | POST (SSE) | 8 种资源类型独立生成 |
| 路径 | `/api/learning-path/generate` | POST | 生成学习路径 |
| 路径 | `/api/learning-path/recommend` | POST | 个性化资源推送 |
| 辅导 | `/api/tutor/chat` | POST (SSE) | 智能辅导对话 |
| 评估 | `/api/assessment/generate` | POST (SSE) | 生成评估报告 |
| 评估 | `/model/evaluation/optimize` | POST | 触发学习方案优化 |
| 代码 | `/api/code/assist` | POST (SSE) | 代码补全 / 诊断 / 优化 |
| 代码 | `/api/code/execute` | POST | 沙箱执行 Python 代码 |

### 前端路由

| 路由 | 页面 | 功能 |
|:---|:---|:---|
| `/login` | login.vue | 登录 / 注册 |
| `/profile` | profile.vue | 学习画像构建 |
| `/resources` | resources.vue | 资源生成 |
| `/learning-path` | learning-path.vue | 学习路径规划 |
| `/tutor` | tutor.vue | 智能辅导 |
| `/assessment` | assessment.vue | 学习效果评估 |
| `/code-assist` | code-assist.vue | 代码辅助开发 |

---

## 🛡️ 安全与防幻觉

### 防幻觉策略

| 策略 | 说明 |
|:---|:---|
| **证据溯源** | 强制引用来源文献与页码，杜绝无依据输出 |
| **双层校验** | 规则引擎学术审查 + LLM 反思逻辑审查 |
| **辩论-仲裁** | 多智能体辩论 + 证据链裁决，减少单一模型偏见 |
| **动态退火** | 校验失败自动分类修正，权重衰减避免无效重试 |
| **文献引用规范** | 强制使用《》书名号引用库内文献，严禁引用库外文献 |

### 系统安全

| 机制 | 说明 |
|:---|:---|
| **JWT 双向认证** | Java 与 Python 之间共享 JWT Secret 双向验证 |
| **分布式限流** | Redisson 信号量控制最大并发数，防止服务过载 |
| **SSE 断线续传** | 滑动窗口缓存 + Last-Event-ID 机制 |
| **Token 自动续期** | 即将过期时自动签发新 Token |

### 内容安全

- 意图分类拦截非教育相关输入
- 系统角色 Prompt 内置安全规则（禁止绝对性结论、标注不确定性、临床建议须提醒执业医师指导）

---

## 📄 开源声明

| 项目 | 用途 | 协议 |
|:---|:---|:---|
| LangChain & LangGraph | 多智能体编排框架 | MIT |
| FastAPI | Python 异步 Web 框架 | MIT |
| ChromaDB | 向量数据库 | Apache 2.0 |
| Qwen（通义千问） | 大语言模型 | 阿里云协议 |
| DashScope Embedding | 文本向量化 | 阿里云协议 |
| gte-rerank | 语义重排模型 | Apache 2.0 |
| Vue 3 | 前端框架 | MIT |
| Spring Boot 3 | 后端框架 | Apache 2.0 |
| MyBatis-Plus | ORM 框架 | Apache 2.0 |
| Redisson | 分布式锁与限流 | Apache 2.0 |
| 阿里云 OSS | 对象存储 | 阿里云协议 |

> 本项目开发过程中使用了 AI 辅助编程工具，所有 AI 生成内容均经过人工审核与测试验证。

---

## ⚠️ 免责声明

*本系统属于高等教育个性化学习辅助系统，系统生成的学习资源与建议仅供参考，不替代教师的专业教学判断。学生应结合自身实际情况与教师指导进行学习规划。*