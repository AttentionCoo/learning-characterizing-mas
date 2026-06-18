# LearnAgent / 多智能体个性化学习系统

> 基于大模型技术体系的高等教育个性化学习智能体系统

面向高等教育场景（脑卒中方向医学生）的个性化学习智能体系统。以高校专业课程知识库为底座，融合 **多智能体协同推理**、**Hybrid RAG**、**多模态影像识别** 与 **全栈响应式流式架构**，实现从学生画像构建到个性化资源生成、学习路径规划、智能辅导、学习效果评估的完整闭环。

---

## 目录

- [核心亮点](#核心亮点)
- [系统架构](#系统架构)
- [项目结构](#项目结构)
- [多智能体协同机制](#多智能体协同机制)
- [功能模块](#功能模块)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [API 概览](#api-概览)
- [安全与防幻觉](#安全与防幻觉)
- [开源声明](#开源声明)
- [免责声明](#免责声明)

---

## 核心亮点

### 三群协同多智能体架构

基于 **LangGraph StateGraph** 构建三大智能体群协同架构，8 个专家智能体通过 YAML 配置驱动，支持动态编排与辩论-仲裁机制：

- **画像构建智能体群**：画像对话 + 特征抽取 + 学习激励，构建 8 维度动态学生画像（知识基础、认知风格、学习目标、易错点偏好、学习节奏、资源偏好、临床经验、情绪状态）
- **资源生成智能体群**：需求分析 + 文档撰写 + 题目生成 + 质量审核 + 学习激励，完成 7 种个性化资源生成
- **辅导评估智能体群**：需求分析 + 质量审核 + 学习激励，提供智能辅导与精准评估

### 证据前置的 Hybrid RAG

- **双路混合检索**：ChromaDB + DashScope 语义向量检索 + BM25 精准匹配，Reranker 深度重排
- **多模型 Rerank 容灾**：4 个候选模型自动切换，全部失败时原始结果兜底
- **QA 自建引擎**：自动从课程 PDF 批量衍生高质量 Q&A 对，提升检索召回率
- **深度溯源**：强制文献名称与精准页码溯源，防止学术幻觉

### 全栈响应式流式管道

Java WebFlux + Python Asyncio 深度流式融合，打通底层智能体到前端 Vue3 ReadableStream 实时渲染链路，AI 思考过程完全透明可视化，支持 SSE 断线续传。

### 多模态与循证扩展

- **qwen-vl-max 视觉理解**：自动识别图片类型并匹配分析策略，实现图文联合理解
- **PubMed 文献检索**：集成 NCBI E-utilities API，内置 8 级证据等级排序，扩展循证医学证据来源

---

## 系统架构

### 三层解耦架构

```
┌─────────────────────────────────────────────────────────┐
│                   前端交互层 (Frontend)                   │
│    Vue 3.5 · Vite · Pinia · ReadableStream · marked     │
├─────────────────────────────────────────────────────────┤
│                   后端服务层 (Backend)                    │
│   Java 21 · Spring Boot 3.3 · WebFlux · Security ·      │
│   Redis/Redisson · MySQL · MyBatis-Plus · OSS            │
├─────────────────────────────────────────────────────────┤
│                   模型推理层 (Model)                      │
│   Python 3.11 · FastAPI · LangGraph · LangChain ·        │
│   Qwen · ChromaDB · gte-rerank · qwen-vl-max · PubMed   │
└─────────────────────────────────────────────────────────┘
```

### 全链路流式数据管道

```
学生学习输入 → Java 鉴权与限流 → WebClient 异步调用 → FastAPI 接收
  → AsyncTaskManager 创建任务 → LearningAgent 推理
  → LangGraph astream_events → _translate_event 翻译标准事件
  → asyncio.Queue → Java Flux 转发 → Vue3 ReadableStream 实时渲染
```

### 技术矩阵

| 层级 | 核心技术 | 职责 |
| --- | --- | --- |
| 前端 | Vue 3.5 · Vite 7.1 · Pinia 3.0 · marked 17 · DOMPurify · pdfjs-dist | 流式渲染、Markdown 展示、思考步骤折叠、学习路径可视化、PDF 预览 |
| 后端 | Java 21 · Spring Boot 3.3 · WebFlux · Security · Redisson 3.27 · MySQL 8.0 · MyBatis-Plus 3.5 | 响应式高并发、JWT 认证、分布式限流、WebClient 流式转发、SSE 断线续传 |
| 模型 | Python 3.11 · FastAPI 0.128 · LangGraph 0.2.20 · Qwen-Max/Plus/Turbo · ChromaDB 0.5 · gte-rerank · qwen-vl-max | 多智能体编排、Hybrid RAG、流式事件输出、多模态识别、文献检索 |

---

## 项目结构

```
learning-multi-agent-system/
├── frontend/                    # 前端交互层（Vue 3）
│   └── src/
│       ├── api/                 # API 请求模块（AI/画像/资源/路径/辅导/评估等）
│       ├── components/          # 组件（工作区/表单/PDF预览/思考面板等）
│       ├── views/               # 页面视图（登录/画像/资源/路径/辅导/评估等）
│       ├── stores/              # Pinia 状态管理
│       ├── utils/               # 工具函数（请求封装/图片压缩/引用解析等）
│       └── router/              # 路由配置
│
├── backend/ai/MyServer/         # 后端服务层（Java Spring Boot）
│   └── src/main/java/com/it/
│       ├── controller/          # REST 控制器
│       ├── service/             # 业务逻辑（AI流式/对话持久化/OSS文档）
│       ├── cache/               # SSE 事件缓存
│       ├── config/              # 配置类（Security/WebClient/Redisson/OSS）
│       ├── pojo/                # 实体类
│       ├── po/                  # 请求参数 & 响应视图对象
│       ├── mapper/              # MyBatis-Plus Mapper
│       └── utils/               # JWT/OSS/IP 工具
│
├── model/                       # 模型推理层（Python FastAPI）
│   └── app/
│       ├── main.py              # FastAPI 入口
│       ├── agents/              # 多智能体核心
│       │   ├── orchestrators/   # LangGraph 图定义 & 节点实现
│       │   ├── core/            # 状态模型/异常/结果封装
│       │   ├── infra/           # Reranker 容灾
│       │   ├── services/        # 检索/查询/综合服务
│       │   └── utils/           # LLM/JSON/重试/文本工具
│       ├── rag/                 # Hybrid RAG（向量+BM25检索/QA生成/文档加载）
│       ├── services/            # 多模态影像 & PubMed 文献检索
│       ├── config/              # YAML 配置（专家/规则/模板/Prompt/限额）
│       └── utils/               # 任务管理/上下文摘要/Token聚合等
│
└── docs/                        # 项目文档
```

---

## 多智能体协同机制

### LangGraph 推理拓扑

```
用户输入
    │
[Intent Node] ← 意图分类 + 难度评分（0.0-1.0）
    │
    ├── irrelevant → [Reject Node] → 结束
    ├── simple → [Fast Track] → 直接生成回答
    └── complex → [Analysis Node] → 结构化需求分析
                      │
                 [Retrieve Node] → Hybrid RAG 证据检索
                      │
                 [Reason Node] → 多智能体协同推理 + 辩论仲裁
                      │
                 [Validate Node] → 质量校验 + 退火反思
                      │              ↺ 校验失败 → 回到 Reason Node
                 [Report Node] → 报告生成 + 学习激励
```

### 智能体角色矩阵

| 角色 | 优先级 | 适用意图 | 职责 |
| --- | --- | --- | --- |
| 画像对话智能体 | 1 | 全场景 | 引导式对话，收集学生信息 |
| 特征抽取智能体 | 2 | profile/resource/assessment | 自动抽取 8 维度画像特征 |
| 需求分析智能体 | 3 | resource/tutor/learning_path | 分析需求，拆解任务 |
| 文档撰写智能体 | 4 | resource | 生成专业课程讲解文档 |
| 题目生成智能体 | 5 | resource/assessment | 生成多类型练习题目 |
| 质量审核智能体 | 6 | resource/assessment/learning_path | 审核学术准确性与个性化匹配 |
| 学习激励智能体 | 7 | 全场景 | 情绪识别与激励反馈 |
| 仲裁智能体 | 8 | resource/tutor/assessment/learning_path | 依据证据链裁决辩论 |

### 辩论-仲裁机制

1. **并行推理**：参与专家通过 `asyncio.gather` 并行生成建议
2. **多轮辩论**：各专家基于辩论上下文提出反驳或补充（立场 + 论据 + 回应）
3. **仲裁裁决**：仲裁智能体输出结构化裁决（`ARBITRATION` 结论 + `REASONING` 推理过程）
4. **意见综合**：加权合并专家意见与仲裁裁决，生成最终提案

### 动态退火反思

校验失败时自动触发：
- **驳回分类**：5 类（事实错误 / 逻辑矛盾 / 个性化不足 / 医学专业性错误 / 内容不完整）
- **针对性修正**：每类驳回生成对应修正指引
- **权重衰减**：发言权重按 0.5 因子衰减（最低 0.2），避免无效重试

### 动态编排

根据意图类型和难度评分动态裁剪参与智能体：

| 意图 | 参与专家数 | 说明 |
| --- | --- | --- |
| profile | 3 | 画像对话 + 特征抽取 + 学习激励 |
| resource | 6 | 画像对话 + 需求分析 + 文档撰写 + 题目生成 + 质量审核 + 学习激励 |
| tutor | 4 | 画像对话 + 需求分析 + 质量审核 + 学习激励 |
| assessment | 5 | 特征抽取 + 需求分析 + 题目生成 + 质量审核 + 学习激励 |
| learning_path | 4 | 画像对话 + 需求分析 + 质量审核 + 学习激励 |

> 仲裁智能体在辩论启用且难度 ≥ 0.6 时自动加入。

---

## 功能模块

### 对话式学习画像构建

通过自然语言对话自动抽取特征，构建 8 维度动态画像（知识基础、认知风格、学习目标、易错点偏好、学习节奏、资源偏好、临床经验、情绪状态），支持随学随新。

### 多智能体协同资源生成

7 种个性化资源类型：课程讲解文档、知识体系思维导图、练习题目、拓展阅读材料、教学视频脚本、代码实操案例、综合资源批量生成。所有接口均支持 SSE 流式输出和图片输入。

### 个性化学习路径规划

根据画像生成 5-15 步学习路径，支持前置步骤依赖、精准资源推送、路径动态调整和步骤进度追踪。

### 智能辅导

即时多模态答疑，支持文字解答、图片识别（qwen-vl-max）、上下文感知和偏好回答形式。

### 学习效果评估

5 维度评估（知识掌握度、学习效率、技能应用、学习一致性、进度对齐度），知识点掌握热力图，练习自动批改，评估结果闭环优化学习路径。

### 多模态影像识别

自动识别图片类型（课件笔记/代码编程/通用医学影像），匹配分析策略，流式输出分析结果，支持多图联合分析。

### PubMed 文献检索

集成 NCBI E-utilities API，8 级证据等级排序，与本地 ChromaDB 知识库互补。

### 代码辅助开发

面向医学生的代码生成、执行沙箱、错误诊断与实操案例生成。

---

## 快速开始

### 环境要求

| 依赖 | 版本 |
| --- | --- |
| Java | 21+ |
| Python | 3.11+ |
| Node.js | 18+ |
| MySQL | 8.0+ |
| Redis | 6.0+ |
| DashScope API Key | 必需 |

### 1. 初始化数据库

```bash
mysql -u root -p < backend/ai/MyServer/learningo-agents.sql
```

### 2. 启动模型推理服务

```bash
cd model

# 使用快速启动脚本（推荐）
# Windows
start.bat
# Linux / macOS
chmod +x start.sh && ./start.sh

# 或手动启动
pip install -r requirements.txt
python -m app.main
```

服务默认在 `http://localhost:8000` 启动，首次启动自动加载 PDF 文献并构建向量库。API 文档：`http://localhost:8000/docs`

### 3. 启动后端服务

```bash
cd backend/ai/MyServer
mvn spring-boot:run
```

服务默认在 `http://localhost:8080` 启动。

### 4. 启动前端服务

```bash
cd frontend
npm install
npm run dev
```

前端默认在 `http://localhost:5173` 启动。

---

## 配置说明

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
| --- | --- |
| `expert_config.yaml` | 8 个专家定义、辩论配置、动态编排规则 |
| `rules_config.yaml` | 质量校验规则、退火策略（5 类驳回分类与修正） |
| `report_templates.yaml` | 5 种报告模板（画像/资源/辅导/评估/路径） |
| `prompts.yaml` | 各场景 Prompt 模板库 |
| `limits_config.yaml` | 参数上限与关键词配置 |

### 后端配置

通过 `application-dev.yml`（开发）或 `application-prod.yml`（生产）配置数据库、Redis、AI 服务地址、JWT 共享密钥和阿里云 OSS。

---

## API 概览

### 全局约定

- **Java 后端**：`http://localhost:8080/api`
- **Python 模型层**：`http://localhost:8000/model`
- **认证**：除登录/注册外，所有接口需携带 JWT Token
- **响应体**：`{ code: 1, msg: "success", data: {} }`

### SSE 流式事件

| 事件 | 说明 |
| --- | --- |
| `init` | 连接建立，返回任务 ID |
| `node_start` | 智能体节点开始推理 |
| `token` | 内容片段（增量） |
| `node_done` | 节点完成 |
| `done` | 流式结束 |
| `error` | 错误 |

### 核心 API

| 模块 | 接口 | 方法 | 说明 |
| --- | --- | --- | --- |
| 认证 | `/api/user/login` | POST | 用户登录 |
| 认证 | `/api/user/register` | POST | 用户注册 |
| 画像 | `/api/profile/conversation` | POST (SSE) | 对话式画像构建 |
| 画像 | `/api/profile` | GET | 获取当前画像 |
| 画像 | `/model/profile/extract` | POST | 抽取画像维度 |
| 资源 | `/api/resources/generate` | POST (SSE) | 综合资源生成 |
| 资源 | `/model/resources/generate/*` | POST (SSE) | 7 种资源类型独立生成 |
| 路径 | `/api/learning-path/generate` | POST | 生成学习路径 |
| 路径 | `/model/learning-path/recommend` | POST | 个性化资源推送 |
| 辅导 | `/api/tutor/chat` | POST (SSE) | 智能辅导对话 |
| 评估 | `/api/assessment/generate` | POST (SSE) | 生成评估报告 |
| 评估 | `/model/evaluation/optimize` | POST | 触发学习方案优化 |

> 完整 API 文档见 [docs/API_SPEC.md](docs/API_SPEC.md) 和 [docs/多智能体个性化学习系统接口文档.md](docs/多智能体个性化学习系统接口文档.md)。

### 前端路由

| 路由 | 页面 | 功能 |
| --- | --- | --- |
| `/login` | login.vue | 登录/注册 |
| `/profile` | profile.vue | 学习画像构建 |
| `/resources` | resources.vue | 资源生成 |
| `/learning-path` | learning-path.vue | 学习路径规划 |
| `/tutor` | tutor.vue | 智能辅导 |
| `/assessment` | assessment.vue | 学习效果评估 |

---

## 安全与防幻觉

### 防幻觉策略

- **证据溯源**：强制引用来源文献与页码，杜绝无依据输出
- **双层校验**：规则引擎学术审查 + LLM 反思逻辑审查
- **辩论-仲裁**：多智能体辩论 + 证据链裁决，减少单一模型偏见
- **动态退火**：校验失败自动分类修正，权重衰减避免无效重试
- **文献引用规范**：强制使用《》书名号引用库内文献，严禁引用库外文献

### 系统安全

- **JWT 双向认证**：Java 与 Python 之间共享 JWT Secret 双向验证
- **分布式限流**：Redisson 信号量控制最大并发数，防止服务过载
- **SSE 断线续传**：滑动窗口缓存 + Last-Event-ID 机制
- **Token 自动续期**：即将过期时自动签发新 Token

### 内容安全

- 意图分类拦截非教育相关输入
- 系统角色 Prompt 内置安全规则（禁止绝对性结论、标注不确定性、临床建议须提醒执业医师指导）

---

## 开源声明

| 项目 | 用途 | 协议 |
| --- | --- | --- |
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
| PubMed E-utilities | 医学文献检索 API | NLM 公共 API |

> 本项目开发过程中使用了 AI 辅助编程工具，所有 AI 生成内容均经过人工审核与测试验证。

---

## 免责声明

*本系统属于高等教育个性化学习辅助系统，系统生成的学习资源与建议仅供参考，不替代教师的专业教学判断。学生应结合自身实际情况与教师指导进行学习规划。*