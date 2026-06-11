# 🎓 LearnAgent / 多智能体个性化学习系统

> **基于大模型技术体系的高等教育个性化学习智能体系统**
> 本项目是一套面向高等教育场景的个性化学习智能体系统。系统以高校专业课程知识库为底座，融合 **多智能体协同推理**、**Hybrid RAG（混合检索增强生成）** 与 **全栈响应式流式架构**，实现了从学生画像构建到个性化资源生成、学习路径规划、智能辅导、学习效果评估的完整闭环，真正实现 因材施教的数字化落地。

---

## 🌟 项目核心亮点与创新

### 🛡️ 1. 三群协同多智能体架构（Tri-Cluster Multi-Agent Architecture）

系统摒弃了传统单模型问答的单点输出，构建了三大智能体群协同架构：

* **画像构建智能体群**：由 Profiler Agent、Extractor Agent、Portrait Builder Agent 组成，通过自然语言对话自动抽取学生特征，构建包含不少于6个维度（知识基础、认知风格、学习目标、易错点偏好、学习节奏、资源偏好等）的动态学生画像，支持画像的随学随新。
* **资源生成智能体群**：由 Requirement Analyzer、Document Writer、Mindmap Generator、Quiz Creator、Reading Curator、Video Script Writer、Code Practice Agent、Quality Reviewer 等多角色智能体协作，完成至少5种类型的个性化资源生成（课程讲解文档、思维导图、练习题目、拓展阅读、视频/动画脚本、代码实操案例等）。
* **辅导评估智能体群**：由 Question Analyzer、Text Tutor、Diagram Generator、Code Tutor、Video Explainer、Evaluator Agent 组成，提供多模态智能辅导与学习效果精准评估。

### 🔎 2. 证据前置的深度定制 Hybrid RAG

* **双路混合检索**：基于 ChromaDB（语义向量）+ BM25（专业术语精准匹配）的双路并发检索引擎，优先召回权威教材与课程文献。
* **高级 QA 自建引擎**：系统精读课程 PDF 并自动批量衍生提炼高质量 Q:A 对（附带原文页码标签），大幅提升学习场景下的检索召回率。
* **深度重排与溯源**：整合 gte-rerank 进行深度语境打分与证据压缩，在生成内容中强制进行**文献名称与精准页码**的明确溯源，有效防止学术幻觉。

### ⚡ 3. 全栈响应式流式数据管道（Reactive Stream Pipeline）

底座采用 **Java WebFlux 响应式高并发框架** 与 **Python Asyncio 异步队列** 深度流式融合，打通了从底层智能体组装到前端 Vue3 ReadableStream 实时渲染的链路，使得 AI 的 **Thinking Step（思考过程）** 完全透明可视化，提供生成进度追踪与流式呈现机制，避免长时间白屏等待。

### 🎯 4. 动态学习路径与精准资源推送

依托多智能体协同工作机制，整合系统生成的个性化资源，结合大模型对学生专业、学习进度、知识掌握情况及学习偏好的深度分析，为学生规划科学、动态的个性化学习路径，明确学习步骤和顺序；同时基于画像实现学习资源的精准推送，涵盖文档、视频、题库、实操案例等多类型内容，并根据评估结果动态调整。

---

## 🏗️ 全栈系统架构与技术矩阵

本项目采用典型的前端交互、后端业务、模型推理三层解耦架构，各层之间通过高并发、低延迟的响应式流进行数据穿透。

### 🛠️ 全栈技术矩阵

| 架构层级 | 核心技术栈 | 核心设计职责 |
| --- | --- | --- |
| 🎨 前端交互层<br>(Frontend) | Vue 3 (Composition API) <br>• Vite 7 • Pinia • SCSS <br>• Fetch / ReadableStream | 以用户体验为核心，持续接收后端流式推送并实时打字机渲染。支持 Markdown 渲染、多模态内容卡片化展示、多 Agent 思考步骤折叠展示、学习路径可视化。 |
| ☕ 后端服务层<br>(Backend) | Java 17 • Spring Boot 3 <br>• Spring WebFlux • Redis 6.0 <br>• Redisson • MySQL 8.0 | 采用响应式编程模型支持高并发吞吐。通过 JWT 实现身份认证与安全控制，利用 Redisson 分布式锁控制并发，通过 WebClient 对底层 Python 模型服务进行流式非阻塞调用与转发。 |
| 🐍 模型推理层<br>(Model) | Python 3.11+ • FastAPI <br>• LangGraph • LangChain <br>• Qwen-Max • gte-rerank | 统一入口加载大语言模型、混合检索引擎与多智能体推理模块。通过异步生成器持续输出标准事件格式（	hinking, chunk, done），实现高效流式通信。 |

### 🔄 全链路流式数据管道 (SSE Pipeline)

`	ext
学生学习输入 ──► Java 鉴权与限流隔离 ──► WebClient 异步非阻塞调用 ──► FastAPI 接收请求
  ──► Python Agent 多状态流式产出 (yield) ──► asyncio.Queue 队列 ──► Java (Flux 持续转发)
  ──► Vue3 (ReadableStream 接收与实时打字机渲染)
`

---

## 🧠 多智能体矩阵协同推理机制（Multi-Agent System）

系统基于 **LangGraph** 创新设计了业务功能轴（纵向） × 决策行为轴（横向）的双轴矩阵多智能体协同架构，高度模拟真实教育场景中的多角色协作与多级质量把关流程。

### 1. 三群协同拓扑架构图

`	ext
                     【 决策行为轴 (横向 LangGraph 拓扑演进) 】

                      Generator 阶段         Reviewer 阶段        Integrator 阶段
                     (内容生成智能体)       (质量审查智能体)       (整合反思智能体)
                     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  画像构建群 ────────►│ 特征抽取生成 │ ───►│ 画像合理性   │ ───►│              │
                     └──────────────┘     └──────────────┘     │              │
                     ┌──────────────┐     ┌──────────────┐     │ 最终结构化输出│
  资源生成群 ────────►│ 多类型资源   │ ───►│ 学术准确性   │ ───►│              │
                     └──────────────┘     └──────────────┘     │ (合规学习内容)│
                     ┌──────────────┐     ┌──────────────┐     │              │
  辅导评估群 ────────►│ 辅导/评估    │ ───►│ 教学有效性   │ ───►│              │
                     └──────────────┘     └──────────────┘     └──────────────┘
                            │                    │                    ▲
                            └────────────────────┴─── [校验失败拦截] ──┘
                                                     (触发异步自愈反思流)
`

### 2. 智能体角色矩阵

| 智能体群 | 角色名称 | 职责说明 |
| --- | --- | --- |
| 🎭 画像构建群 | Profiler Agent | 引导式对话，收集学生专业、学习目标等信息 |
| | Extractor Agent | 从对话中自动抽取画像特征维度 |
| | Portrait Builder Agent | 聚合特征构建/更新动态学生画像 |
| 📚 资源生成群 | Requirement Analyzer | 分析资源需求，拆解生成任务 |
| | Document Writer | 生成专业课程讲解文档 |
| | Mindmap Generator | 生成知识点思维导图 |
| | Quiz Creator | 生成不同类型练习题目 |
| | Reading Curator | 筛选并生成拓展阅读材料 |
| | Video Script Writer | 生成多模态教学视频/动画脚本 |
| | Code Practice Agent | 生成代码类实操案例 |
| | Quality Reviewer | 审查资源学术准确性与内容安全 |
| 💡 辅导评估群 | Question Analyzer | 分析学生问题类型与知识薄弱点 |
| | Text Tutor | 提供详细文字解答 |
| | Diagram Generator | 生成图解说明 |
| | Code Tutor | 代码辅助辅导 |
| | Video Explainer | 生成短视频讲解脚本 |
| | Evaluator Agent | 多维度学习效果评估 |

---

## ⚙️ 系统整体功能模块

### 1. 💬 对话式学习画像自主构建

摒弃传统繁琐表单，支持通过自然语言对话自动抽取特征，构建包含不少于6个维度的动态学生画像：

* **知识基础**：当前专业、已掌握知识点、薄弱环节
* **认知风格**：视觉型/听觉型/动手型等学习偏好
* **学习目标**：短期目标与长期规划
* **易错点偏好**：常见错误模式与知识盲区
* **学习节奏**：每周可投入时长、偏好学习时段
* **资源偏好**：文档/视频/代码/图解等偏好类型

画像支持随学随新，系统根据学习行为数据自动更新画像维度。

### 2. 📄 多智能体协同资源生成

不同角色智能体协作完成至少5种类型的个性化资源生成：

* **专业课程讲解文档**：结构化知识点讲解，附带文献溯源
* **知识点思维导图**：可视化知识体系与关联
* **不同类型练习题目**：选择题/填空题/简答题/代码题等
* **拓展阅读材料**：关联文献与延伸学习资源
* **多模态教学视频/动画脚本**：可视化讲解脚本生成
* **代码类实操案例**：编程实践案例与运行环境

### 3. 🗺️ 个性化学习路径规划与资源推送

* **动态路径规划**：根据画像生成阶段性学习路径，明确学习步骤和顺序
* **精准资源推送**：基于画像维度综合计算，推送匹配的学习资源
* **路径动态调整**：根据学习效果评估结果或学生反馈，动态调整路径难度与资源推荐策略

### 4. 🤖 智能辅导（可选加分项）

当学生在学习过程中遇到问题时，系统提供即时、多模态的答疑解惑服务：

* **文字解答**：详细的步骤化文字讲解
* **图解说明**：自动生成示意图/流程图辅助理解
* **短视频讲解**：生成可视化讲解脚本
* **代码辅助**：编程问题的代码级辅导与调试

### 5. 📊 学习效果评估（可选加分项）

* **多维度评估**：知识掌握度、学习效率、技能应用能力等维度
* **实时跟踪**：学习行为、练习测试、资源使用反馈等数据采集
* **闭环优化**：评估结果自动触发学习路径调整和资源推送策略更新

---

## 📂 项目目录结构

`	ext
learning-multi-agent-system/
├── frontend/                    # 前端项目 (Vue 3 + Vite)
│   ├── src/
│   │   ├── api/                 # API 接口定义
│   │   ├── components/          # 组件（含 workspace 工作区组件）
│   │   ├── views/               # 页面视图
│   │   │   ├── profile.vue      # 学习画像页
│   │   │   ├── resources.vue    # 资源中心页
│   │   │   ├── learning-path.vue# 学习路径页
│   │   │   ├── tutor.vue        # 智能辅导页
│   │   │   ├── assessment.vue   # 学习评估页
│   │   │   └── talk.vue         # 对话页
│   │   ├── stores/              # Pinia 状态管理
│   │   └── router/              # 路由配置
│   └── package.json
├── backend/                     # 后端项目 (Spring Boot 3)
│   └── ai/MyServer/
│       └── src/main/java/com/it/
│           ├── controller/      # 控制层
│           ├── service/         # 业务逻辑层
│           ├── mapper/          # MyBatis Mapper
│           ├── po/              # 持久化对象
│           ├── config/          # 配置类
│           ├── interceptor/     # 拦截器（鉴权）
│           └── utils/           # 工具类
├── model/                       # 模型推理层 (Python FastAPI)
│   ├── app/
│   │   ├── agents/              # 多智能体核心模块
│   │   │   ├── orchestrators/   # LangGraph 编排器
│   │   │   │   └── nodes/       # 各功能节点
│   │   │   ├── pipelines/       # RAG 管道
│   │   │   ├── services/        # 智能体服务
│   │   │   └── infra/           # 重排器等基础设施
│   │   ├── rag/                 # RAG 模块
│   │   ├── config/              # 配置文件
│   │   └── services/            # 外部服务
│   ├── data/                    # 数据目录（课程文档等）
│   ├── tests/                   # 自动化测试
│   ├── requirements.txt
│   └── main.py                  # FastAPI 服务入口
├── sql表/                       # 数据库建表脚本
├── docs/                        # 项目文档
│   └── 多智能体个性化学习系统接口文档.md
└── scripts/                     # 辅助脚本
`

---

## 🚀 快速接入与本地部署

### 1. 环境依赖要求

* **后端环境**：MySQL 8.0+、Redis 6.0+、JDK 17+、Maven 3.8+
* **前端环境**：Node.js >= 20.19.0 (推荐使用 ^22.12.0)
* **模型服务**：Python 3.11+、Anaconda/Miniconda 环境

### 2. 基础环境配置

#### 模型层环境配置

`ash
cd model
conda create -n learn-agent python=3.11
conda activate learn-agent
pip install -r requirements.txt
`

在 model/ 根目录下创建 .env 文件：

`env
DASHSCOPE_API_KEY=sk-您的阿里云百炼平台密钥
SECRET_KEY=自定义防越权的JWT随机字符串
`

#### 后端服务配置

修改 ackend/ai/MyServer/src/main/resources/application.yml：

`yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/learning_agents?useSSL=false&serverTimezone=UTC
    username: your_username
    password: your_password
  data:
    redis:
      host: localhost
      port: 6379
model:
  server:
    url: http://localhost:8000
`

#### 数据库初始化

导入 sql表/learningo-agents.sql 到 MySQL 数据库。

### 3. 初始化启动

#### 第一步：启动模型服务 (Model)

将课程相关的 PDF 文件统一放入 model/data/documents/ 文件夹，然后启动服务。系统首次运行会自动触发递归分块并进行 **AI Batch QA 衍生**，自动构建高频词 BM25 内存索引和 ChromaDB 向量索引。

`ash
cd model
python main.py
# 或者执行一键脚本
start.bat
`

#### 第二步：启动后端服务 (Backend)

使用编译工具（如 IntelliJ IDEA）运行 MyServerApplication.java，或者使用 Maven 编译启动：

`ash
cd backend/ai/MyServer
mvn spring-boot:run
`

#### 第三步：启动前端服务 (Frontend)

`ash
cd frontend
fnm use 22
npm install
npm run dev
`

*前端默认在 localhost:5173 启动，并自动代理请求至后端的响应端口。*

---

## 📝 核心 API 契约

### 1. 对话式学习画像构建（SSE流式）：/api/profile/chat

* **协议**：SSE (Server-Sent Events)
* **请求类型**：POST
* **Payload**：
`json
{
  message: 我是计算机专业大二学生，想学人工智能，Python基础还行但数学比较弱,
  conversationId: optional-existing-id,
  token: your-jwt-token
}
`

* **响应格式**：流式输出，包含画像特征抽取过程与画像维度更新结果。

### 2. 多智能体协同资源生成（SSE流式）：/api/resources/generate

* **请求类型**：POST
* **Payload**：
`json
{
  courseName: 人工智能导论,
  topic: 梯度下降算法,
  resourceTypes: [document, mindmap, quiz, code_practice],
  difficulty: intermediate,
  token: your-jwt-token
}
`

* **响应格式**：流式输出，包含各智能体协作生成过程与最终资源内容。

### 3. 个性化学习路径规划：/api/learning-path/generate

* **请求类型**：POST
* **Payload**：
`json
{
  courseName: 人工智能导论,
  goalDescription: 掌握机器学习基础算法并能够独立实现,
  weeklyHours: 18,
  token: your-jwt-token
}
`

### 4. 智能辅导（SSE流式）：/api/tutor/chat

* **请求类型**：POST
* **Payload**：
`json
{
  question: 梯度下降中学习率太大或太小分别会有什么问题？,
  responseMode: multimodal,
  token: your-jwt-token
}
`

### 5. 学习效果评估：/api/evaluation/report

* **请求类型**：GET
* **查询参数**：pathId, period (week/month/all)

---

## 🛡️ 安全与防幻觉机制

### 防幻觉策略
* **证据溯源**：所有生成内容强制引用来源文献与页码，杜绝无依据输出
* **双层校验**：Quality Reviewer 智能体进行学术准确性审查 + LLM 反思机制深层逻辑审查
* **规则引擎**：关键知识点设置硬性校验规则，校验失败自动拦截

### 内容安全过滤
* **敏感信息过滤**：自动检测并过滤敏感违规信息
* **学术规范检查**：确保生成内容无事实性错误
* **人工干预节点**：关键内容生成节点支持人工审核

---

## 📊 开源项目与工具声明

| 项目/工具 | 用途 | 协议 |
| --- | --- | --- |
| LangChain & LangGraph | 多智能体编排框架 | MIT |
| FastAPI | Python 异步 Web 框架 | MIT |
| ChromaDB | 向量数据库 | Apache 2.0 |
| Qwen（通义千问） | 大语言模型 | 阿里云协议 |
| gte-rerank | 语义重排模型 | Apache 2.0 |
| Vue 3 | 前端框架 | MIT |
| Spring Boot 3 | 后端框架 | Apache 2.0 |
| 阿里云百炼平台 | 大模型 API 服务 | 阿里云协议 |

> **AI Coding 工具说明**：本项目开发过程中使用了 Claude Code 等 AI 辅助编程工具进行代码生成与优化，所有 AI 生成内容均经过人工审核与测试验证。

---

## ⚠️ 免责声明

*本系统属于高等教育个性化学习辅助系统，系统生成的学习资源与建议仅供参考，不替代教师的专业教学判断。学生应结合自身实际情况与教师指导进行学习规划。*
