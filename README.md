# 🎓 LearnAgent / 多智能体个性化学习系统

> **基于大模型技术体系的高等教育个性化学习智能体系统**
> 本项目是一套面向高等教育场景的个性化学习智能体系统。系统以高校专业课程知识库为底座，融合 **多智能体协同推理**、**Hybrid RAG（混合检索增强生成）** 与 **全栈响应式流式架构**，实现了从学生画像构建到个性化资源生成、学习路径规划、智能辅导、学习效果评估的完整闭环，真正实现因材施教的数字化落地。

---

## 🌟 项目核心亮点与创新

### 🛡️ 1. 三群协同多智能体架构（Tri-Cluster Multi-Agent Architecture）

系统摒弃了传统单模型问答的单点输出，构建了三大智能体群协同架构：

* **画像构建智能体群**：由 Profiler Agent、Extractor Agent、Portrait Builder Agent 组成，通过自然语言对话自动抽取学生特征，构建包含 8 个维度（知识基础、认知风格、学习目标、易错点偏好、学习节奏、资源偏好、临床经验、情绪状态）的动态学生画像，支持画像的随学随新。
* **资源生成智能体群**：由 Requirement Analyzer、Document Writer、Mindmap Generator、Quiz Creator、Reading Curator、Video Script Writer、Code Practice Agent、Quality Reviewer 等多角色智能体协作，完成 10 种类型的个性化资源生成（课程讲解文档、知识体系思维导图、练习题目、临床指南与文献、教学视频脚本、医学编程实操、临床实操案例、课程 PPT、资源设计方案、实践项目材料等）。
* **辅导评估智能体群**：由 Question Analyzer、Text Tutor、Diagram Generator、Code Tutor、Video Explainer、Evaluator Agent 组成，提供多模态智能辅导与学习效果精准评估。

### 🔎 2. 证据前置的深度定制 Hybrid RAG

* **双路混合检索**：基于 ChromaDB + DashScope Embedding（语义向量）+ BM25（专业术语精准匹配）的双路并发检索引擎，优先召回权威教材与课程文献。
* **高级 QA 自建引擎**：系统精读课程 PDF 并自动批量衍生提炼高质量 Q&A 对（附带原文页码标签），大幅提升学习场景下的检索召回率。
* **深度重排与溯源**：整合 DashScope gte-rerank 进行深度语境打分与证据压缩，在生成内容中强制进行**文献名称与精准页码**的明确溯源，有效防止学术幻觉。

### ⚡ 3. 全栈响应式流式数据管道（Reactive Stream Pipeline）

底座采用 **Java WebFlux 响应式高并发框架** 与 **Python Asyncio 异步队列** 深度流式融合，打通了从底层智能体组装到前端 Vue3 ReadableStream 实时渲染的链路，使得 AI 的 **Thinking Step（思考过程）** 完全透明可视化，提供生成进度追踪与流式呈现机制，避免长时间白屏等待。支持 SSE 断线续传（Last-Event-ID），确保网络波动时内容不丢失。

### 🎯 4. 动态学习路径与精准资源推送

依托多智能体协同工作机制，整合系统生成的个性化资源，结合大模型对学生专业、学习进度、知识掌握情况及学习偏好的深度分析，为学生规划科学、动态的个性化学习路径，明确学习步骤和顺序；同时基于画像实现学习资源的精准推送，涵盖文档、视频、题库、实操案例等多类型内容，并根据评估结果动态调整。

---

## 🏗️ 全栈系统架构与技术矩阵

本项目采用典型的前端交互、后端业务、模型推理三层解耦架构，各层之间通过高并发、低延迟的响应式流进行数据穿透。

### 🛠️ 全栈技术矩阵

| 架构层级 | 核心技术栈 | 核心设计职责 |
| --- | --- | --- |
| 🎨 前端交互层<br>(Frontend) | Vue 3.5 (Composition API) <br>• Vite 7 • Pinia 3 • SCSS <br>• Fetch / ReadableStream <br>• marked • DOMPurify | 以用户体验为核心，持续接收后端流式推送并实时打字机渲染。支持 Markdown 渲染、多模态内容卡片化展示、ThinkingPanel 思考步骤折叠展示、学习路径可视化、PDF 在线预览、图片压缩上传。 |
| ☕ 后端服务层<br>(Backend) | Java 21 • Spring Boot 3.3 <br>• Spring WebFlux • Redis <br>• Redisson • MySQL 8.0 <br>• MyBatis-Plus • Aliyun OSS | 采用响应式编程模型支持高并发吞吐。通过 JWT 实现身份认证与安全控制，利用 Redisson 分布式限流与并发信号量控制，通过 WebClient 对底层 Python 模型服务进行流式非阻塞调用与转发，SSEEventCache 支持断线续传。 |
| 🐍 模型推理层<br>(Model) | Python 3.11+ • FastAPI <br>• LangGraph • LangChain <br>• Qwen-Max/Plus/Turbo <br>• ChromaDB • gte-rerank | 统一入口加载大语言模型、混合检索引擎与多智能体推理模块。通过异步生成器持续输出标准事件格式（thinking, token, done），实现高效流式通信。JWT 双向认证保障服务间调用安全。 |

### 🔄 全链路流式数据管道 (SSE Pipeline)

```
学生学习输入 ──► Java 鉴权与限流隔离 ──► WebClient 异步非阻塞调用 ──► FastAPI 接收请求
  ──► Python Agent 多状态流式产出 (yield) ──► asyncio.Queue 队列 ──► Java (Flux 持续转发)
  ──► Vue3 (ReadableStream 接收与实时打字机渲染)
```

---

## 🧠 多智能体矩阵协同推理机制（Multi-Agent System）

系统基于 **LangGraph** 创新设计了业务功能轴（纵向） × 决策行为轴（横向）的双轴矩阵多智能体协同架构，高度模拟真实教育场景中的多角色协作与多级质量把关流程。

### 1. LangGraph 推理拓扑架构

系统核心推理流程基于 LangGraph StateGraph 构建，通过意图路由将不同类型的请求分发至对应的处理管道：

```
用户输入
    ↓
[Intent Node] ←── 意图分类（profile / resource / tutor / assessment / learning_path / knowledge / irrelevant）
    ↓
[路由决策]
    ├── irrelevant ──► [Reject Node] ──► END
    ├── knowledge  ──► [Knowledge Answer Node] ──► END
    └── profile / resource / tutor / assessment / learning_path / consultation
         ↓
    [Analysis Node] ── 分析学习需求与问题拆解
         ↓
    [Retrieve Node] ── Hybrid RAG 证据检索
         ↓
    [Reason Node]  ── 多智能体协同推理
         ↓
    [Validate Node] ── 质量校验与反思循环（最多 3 次）
         ├── pass  ──► [Report Node] ──► END
         ├── retry ──► [Reason Node]（反思重推理）
         └── fail  ──► [Report Node] ──► END
```

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

摒弃传统繁琐表单，支持通过自然语言对话自动抽取特征，构建包含 8 个维度的动态学生画像：

* **知识基础**：当前专业、已掌握知识点、薄弱环节
* **认知风格**：视觉型/听觉型/动手型等学习偏好
* **学习目标**：短期目标与长期规划
* **易错点偏好**：常见错误模式与知识盲区
* **学习节奏**：每周可投入时长、偏好学习时段
* **资源偏好**：文档/视频/代码/图解等偏好类型
* **临床经验**：临床实践经历与技能水平
* **情绪状态**：学习动力与心理状态评估

画像支持随学随新，系统根据学习行为数据自动更新画像维度。支持对话历史管理与多轮对话上下文摘要。

### 2. 📄 多智能体协同资源生成

不同角色智能体协作完成 10 种类型的个性化资源生成：

| 资源类型 | 说明 |
| --- | --- |
| 📄 课程讲解文档 | 结构化知识点讲解，附带文献溯源 |
| 🧠 知识体系思维导图 | 可视化知识体系与关联（Mermaid 格式） |
| ✏️ 练习题目 | 选择题/填空题/简答题/代码题等 |
| 📖 临床指南与文献 | 关联文献与延伸学习资源 |
| 🎬 教学视频脚本 | 可视化讲解脚本生成 |
| 💻 医学编程实操 | 编程实践案例与运行环境 |
| 🏥 临床实操案例 | 临床场景实操案例 |
| 📊 课程 PPT | 结构化演示文稿 |
| 📋 资源设计方案 | 个性化学习资源规划方案 |
| 🔬 实践项目材料 | 综合实践项目配套材料 |

### 3. 🗺️ 个性化学习路径规划与资源推送

* **动态路径规划**：根据画像生成阶段性学习路径，明确学习步骤和顺序
* **精准资源推送**：基于画像维度综合计算，推送匹配的学习资源
* **路径动态调整**：根据学习效果评估结果或学生反馈，动态调整路径难度与资源推荐策略
* **步骤进度追踪**：支持标记步骤完成状态、实际投入时长与自评反馈

### 4. 🤖 智能辅导

当学生在学习过程中遇到问题时，系统提供即时、多模态的答疑解惑服务：

* **文字解答**：详细的步骤化文字讲解
* **图解说明**：自动生成示意图/流程图辅助理解
* **短视频讲解**：生成可视化讲解脚本
* **代码辅助**：编程问题的代码级辅导与调试
* **图片识别**：支持上传图片进行视觉分析辅助解答

### 5. 📊 学习效果评估

* **多维度评估**：综合评估、知识掌握、技能水平、学习进度等维度
* **实时跟踪**：学习行为、练习测试、资源使用反馈等数据采集
* **闭环优化**：评估结果自动触发学习路径调整和资源推送策略更新

---

## 📂 项目目录结构

```
learning-multi-agent-system/
├── frontend/                        # 前端项目 (Vue 3 + Vite 7)
│   ├── src/
│   │   ├── api/                     # API 接口层
│   │   │   ├── ai.js                # AI 通用接口
│   │   │   ├── profile.js           # 画像接口（SSE 流式）
│   │   │   ├── resources.js         # 资源生成接口
│   │   │   ├── learningPath.js      # 学习路径接口
│   │   │   ├── tutor.js             # 智能辅导接口
│   │   │   ├── assessment.js        # 学习评估接口
│   │   │   ├── code.js              # 代码执行接口
│   │   │   ├── documents.js         # 文档管理接口
│   │   │   ├── talk.js              # 对话管理接口
│   │   │   ├── patient.js           # 患者管理接口
│   │   │   └── user.js              # 用户认证接口
│   │   ├── components/              # 组件
│   │   │   ├── workspace/           # 工作区组件
│   │   │   │   ├── ChatWorkspace.vue      # 通用对话工作区
│   │   │   │   ├── LearningWorkspace.vue  # 学习工作区
│   │   │   │   ├── ThinkingPanel.vue      # AI 思考步骤面板
│   │   │   │   ├── WorkspaceTabs.vue      # 工作区标签页
│   │   │   │   └── PapersSidebar.vue      # 文献侧边栏
│   │   │   ├── form/                # 表单组件（登录/注册/编辑）
│   │   │   ├── svg/                 # SVG 图标组件
│   │   │   ├── PdfPreviewModal.vue  # PDF 在线预览弹窗
│   │   │   ├── AvatarUpload.vue     # 头像上传组件
│   │   │   └── LoadingModel.vue     # 加载动画组件
│   │   ├── views/                   # 页面视图
│   │   │   ├── login.vue            # 登录页
│   │   │   ├── home.vue             # 主页（侧边导航布局）
│   │   │   ├── profile.vue          # 学习画像页
│   │   │   ├── resources.vue        # 资源生成页
│   │   │   ├── learning-path.vue    # 学习路径页
│   │   │   ├── tutor.vue            # 智能辅导页
│   │   │   ├── assessment.vue       # 学习评估页
│   │   │   └── talk.vue             # 通用对话页
│   │   ├── stores/                  # Pinia 状态管理
│   │   │   ├── user.js              # 用户状态（含 Token 持久化）
│   │   │   └── theme.js             # 主题状态
│   │   ├── router/                  # 路由配置（含鉴权守卫）
│   │   ├── utils/                   # 工具函数
│   │   │   ├── request.js           # Axios 请求封装
│   │   │   ├── referenceParser.js   # 文献引用解析
│   │   │   ├── imageCompress.js     # 图片压缩
│   │   │   └── pause.js             # 流式暂停控制
│   │   └── styles/                  # 全局样式（SCSS 变量/过渡动画）
│   └── package.json
│
├── backend/                         # 后端项目 (Spring Boot 3.3)
│   └── ai/MyServer/
│       └── src/main/java/com/it/
│           ├── controller/          # 控制层（15 个控制器）
│           │   ├── ProfileController.java       # 画像对话（SSE）
│           │   ├── ResourceController.java      # 资源生成（SSE）
│           │   ├── LearningPathController.java  # 学习路径
│           │   ├── TutorController.java         # 智能辅导（SSE）
│           │   ├── AssessmentController.java    # 学习评估（SSE）
│           │   ├── CodeController.java          # 代码执行
│           │   ├── CourseController.java        # 课程管理
│           │   ├── DocumentController.java      # 文档管理
│           │   ├── LoginController.java         # 登录注册
│           │   └── ...
│           ├── service/             # 业务逻辑层
│           │   ├── AIStreamingService.java      # AI 流式服务接口
│           │   ├── impl/
│           │   │   ├── AIStreamingServiceImpl.java  # 流式核心实现
│           │   │   └── ConversationPersistenceService.java  # 对话持久化
│           │   └── OssDocumentService.java      # OSS 文档服务
│           ├── mapper/              # MyBatis-Plus Mapper（14 个）
│           ├── po/                  # 持久化对象
│           │   ├── dto/             # 数据传输对象
│           │   ├── uo/              # 请求参数对象（15 个）
│           │   └── vo/              # 响应视图对象（11 个）
│           ├── pojo/                # 实体类
│           │   ├── StudentProfile.java           # 学生画像
│           │   ├── LearningPath.java             # 学习路径
│           │   ├── LearningPathStepEntity.java   # 学习步骤
│           │   ├── LearningResource.java         # 学习资源
│           │   ├── LearningBehaviorRecord.java   # 学习行为记录
│           │   ├── EvalReport.java               # 评估报告
│           │   └── ...
│           ├── config/              # 配置类
│           │   ├── SecurityConfig.java           # 安全配置
│           │   ├── WebClientConfig.java          # WebClient 配置
│           │   ├── RedissonConfig.java           # Redisson 配置
│           │   └── ...
│           ├── cache/               # SSEEventCache（SSE 事件缓存与断线续传）
│           ├── interceptor/         # JWT 拦截器（Token 校验 + 自动续期）
│           ├── handler/             # 全局异常处理
│           └── utils/               # 工具类（JWT / OSS / IP 等）
│
├── model/                           # 模型推理层 (Python FastAPI)
│   ├── app/
│   │   ├── main.py                  # FastAPI 服务入口（路由 + 资源初始化）
│   │   ├── agents/                  # 多智能体核心模块
│   │   │   ├── orchestrators/       # LangGraph 编排器
│   │   │   │   ├── clinical_graph.py      # StateGraph 构建与路由
│   │   │   │   ├── qwen_agent.py          # LearningAgent 主入口
│   │   │   │   └── nodes/                 # 各功能节点
│   │   │   │       ├── intent_node.py     # 意图分类节点
│   │   │   │       ├── analysis_node.py   # 需求分析节点
│   │   │   │       ├── retrieve_node.py   # 证据检索节点
│   │   │   │       ├── reason_node.py     # 多智能体推理节点
│   │   │   │       ├── validate_node.py   # 质量校验节点
│   │   │   │       └── report_node.py     # 报告生成节点
│   │   │   ├── pipelines/           # RAG 管道
│   │   │   │   └── rag_pipeline.py       # 检索-重排-合成管道
│   │   │   ├── services/            # 智能体服务
│   │   │   │   ├── query_service.py      # 查询生成服务
│   │   │   │   ├── retrieval_service.py  # 证据检索服务
│   │   │   │   └── synthesis_service.py  # 证据合成服务
│   │   │   ├── core/                # 核心定义
│   │   │   │   ├── schema.py            # LearningState 数据模型
│   │   │   │   ├── decorators.py        # 装饰器
│   │   │   │   ├── exceptions.py        # 异常定义
│   │   │   │   └── result.py            # 结果封装
│   │   │   ├── infra/               # 基础设施
│   │   │   │   ├── reranker.py          # DashScope gte-rerank 重排器
│   │   │   │   └── base_reranker.py     # 重排器基类
│   │   │   ├── schemas/             # 数据模式
│   │   │   │   └── retrieval.py         # 检索结果模式
│   │   │   ├── utils/               # 工具函数
│   │   │   │   ├── llm_helper.py        # LLM 调用辅助
│   │   │   │   ├── json_parser.py       # JSON 解析器
│   │   │   │   ├── retry.py             # 重试装饰器
│   │   │   │   └── text_utils.py        # 文本处理工具
│   │   │   ├── assistant.py         # LearningAssistant 学习助手
│   │   │   └── constants.py         # 常量定义
│   │   ├── rag/                     # RAG 模块
│   │   │   ├── retrievers.py        # 混合检索引擎（DashScope Embedding + ChromaDB + BM25）
│   │   │   ├── data_loader.py       # PDF 文档加载与分块
│   │   │   ├── qa_generator.py      # QA 自动衍生引擎
│   │   │   └── retrieve.py          # 统一检索入口
│   │   ├── config/                  # YAML 配置文件
│   │   │   ├── prompts.yaml         # Prompt 模板库
│   │   │   ├── expert_config.yaml   # 专家角色配置
│   │   │   ├── report_templates.yaml # 报告模板
│   │   │   ├── rules_config.yaml    # 校验规则配置
│   │   │   ├── limits_config.yaml   # 参数限制配置
│   │   │   └── config_loader.py     # 配置加载器
│   │   ├── services/                # 外部服务
│   │   │   ├── vision_service.py    # 视觉分析服务
│   │   │   └── pubmed_service.py    # 文献检索服务
│   │   ├── evaluation/              # 评估模块
│   │   └── utils/                   # 工具函数
│   │       ├── context_summary.py   # 对话上下文摘要
│   │       ├── error_codes.py       # 错误码定义
│   │       ├── token_aggregator.py  # Token 聚合器
│   │       ├── naming_model.py      # 模型命名工具
│   │       └── download_models.py   # 模型下载脚本
│   ├── data/
│   │   └── documents/               # 课程 PDF 文档库
│   ├── tests/                       # 自动化测试
│   ├── requirements.txt
│   ├── main.py                      # 启动入口
│   ├── start.bat / start.sh         # 一键启动脚本
│   └── .env.example                 # 环境变量示例
│
├── sql表/                           # 数据库建表脚本
│   └── learningo-agents.sql         # 完整数据库初始化脚本
├── docs/                            # 项目文档
│   └── 多智能体个性化学习系统接口文档.md
└── scripts/                         # 辅助脚本
    └── fill_test_results.py         # 测试数据填充脚本
```

---

## 🚀 快速接入与本地部署

### 1. 环境依赖要求

| 依赖项 | 版本要求 | 说明 |
| --- | --- | --- |
| JDK | 21+ | 后端运行环境 |
| Maven | 3.8+ | 后端构建工具 |
| MySQL | 8.0+ | 数据库 |
| Redis | 6.0+ | 缓存与分布式锁 |
| Node.js | ^20.19.0 或 >=22.12.0 | 前端运行环境 |
| Python | 3.11+ | 模型服务运行环境 |
| 阿里云百炼 API Key | - | 大模型调用凭证 |

### 2. 基础环境配置

#### 模型层环境配置

```bash
cd model
conda create -n learn-agent python=3.11
conda activate learn-agent
pip install -r requirements.txt
```

在 `model/` 根目录下创建 `.env` 文件（参考 `.env.example`）：

```env
# 必需：阿里云百炼 API 密钥
DASHSCOPE_API_KEY=sk-您的阿里云百炼平台密钥

# 必需：JWT 密钥（须与后端 application-dev.yml 中 shared-jwt-secret 一致）
SECRET_KEY=自定义防越权的JWT随机字符串

# 可选：HuggingFace 镜像加速
HF_ENDPOINT=https://hf-mirror.com
```

#### 后端服务配置

修改 `backend/ai/MyServer/src/main/resources/application-dev.yml`，配置数据库、Redis 和模型服务地址：

```yaml
aiserver:
  datasource:
    driver-class-name: com.mysql.cj.jdbc.Driver
    host: localhost
    port: 3306
    database: medai
    username: your_username
    password: your_password
  redis:
    host: localhost
    port: 6379
    password: your_redis_password
  ai-api:
    url: http://localhost:8000
    shared-jwt-secret: ${AI_JWT_SECRET:dev-local-secret}
```

#### 数据库初始化

导入 `sql表/learningo-agents.sql` 到 MySQL 数据库（数据库名 `medai`）：

```bash
mysql -u root -p medai < sql表/learningo-agents.sql
```

### 3. 初始化启动

#### 第一步：启动模型服务 (Model)

将课程相关的 PDF 文件统一放入 `model/data/documents/` 文件夹，然后启动服务。系统首次运行会自动触发递归分块并进行 **AI Batch QA 衍生**，自动构建 BM25 内存索引和 ChromaDB 向量索引。

```bash
cd model
python main.py
# 或使用一键脚本
start.bat    # Windows
./start.sh   # Linux/macOS
```

模型服务默认在 `http://localhost:8000` 启动。

#### 第二步：启动后端服务 (Backend)

使用 IDE（如 IntelliJ IDEA）运行 `MyServerApplication.java`，或者使用 Maven 编译启动：

```bash
cd backend/ai/MyServer
mvn spring-boot:run
```

后端服务默认在 `http://localhost:8080` 启动。

#### 第三步：启动前端服务 (Frontend)

```bash
cd frontend
npm install
npm run dev
```

前端默认在 `http://localhost:5173` 启动，并自动代理请求至后端。

---

## 📝 核心 API 契约

### 全局约定

* **Base URL**：开发环境 `http://localhost:8080/api`
* **认证方式**：除登录/注册外，所有接口需携带 JWT Token（`Authorization: Bearer <token>` 或 `token: <token>`）
* **统一响应体**：`{ code: 1, msg: "success", data: {} }`（1=成功，0=失败）

### SSE 流式事件格式

流式接口采用 SSE（Server-Sent Events）协议：

| 事件类型 | 说明 | data 结构 |
| --- | --- | --- |
| `init` | 连接建立，返回会话 ID | `{"type":"init","talkId":"123","newTalk":true}` |
| `node_start` | 智能体节点开始推理 | `{"type":"node_start","node":"profiler","label":"正在分析学习特征..."}` |
| `token` | 内容片段（增量） | `{"type":"token","content":"..."}` |
| `thinking` | 思考过程展示 | `{"type":"thinking","step":1,"title":"知识基础分析","content":"..."}` |
| `done` | 流式结束 | `{"type":"done","talkId":"123","title":"学习画像构建"}` |
| `error` | 错误 | `{"type":"error","code":"E2001","message":"..."}` |
| `resume` | 断线续传恢复 | `{"type":"resume","talkId":"123","content":"..."}` |

### 核心 API 列表

| 模块 | 接口 | 方法 | 说明 |
| --- | --- | --- | --- |
| 用户认证 | `/api/user/login` | POST | 用户登录 |
| | `/api/user/register` | POST | 用户注册 |
| 学习画像 | `/api/profile/conversation` | POST (SSE) | 对话式画像构建 |
| | `/api/profile` | GET | 获取当前画像 |
| | `/api/profile/dimensions` | PUT | 更新画像维度 |
| | `/api/profile/conversations` | GET | 获取画像对话列表 |
| 资源生成 | `/api/resources/generate` | POST (SSE) | 多类型资源生成 |
| | `/api/resources` | GET | 获取资源列表 |
| 学习路径 | `/api/learning-path/generate` | POST (SSE) | 生成学习路径 |
| | `/api/learning-path` | GET | 获取当前路径 |
| | `/api/learning-path/step/progress` | PUT | 更新步骤进度 |
| 智能辅导 | `/api/tutor/chat` | POST (SSE) | 智能辅导对话 |
| | `/api/tutor/conversations` | GET | 获取辅导对话列表 |
| 学习评估 | `/api/assessment/generate` | POST (SSE) | 生成评估报告 |
| | `/api/assessment/reports` | GET | 获取评估报告列表 |
| 代码执行 | `/api/code/execute` | POST | 代码执行与调试 |
| 文档管理 | `/api/documents/upload` | POST | 文档上传（OSS） |
| | `/api/documents/match` | POST | 文献引用匹配 |

---

## 🛡️ 安全与防幻觉机制

### 防幻觉策略
* **证据溯源**：所有生成内容强制引用来源文献与页码，杜绝无依据输出
* **双层校验**：Validate Node 规则引擎进行学术准确性审查 + LLM 反思机制深层逻辑审查
* **反思循环**：校验未通过时自动触发重新推理，最多 3 次反思机会
* **规则引擎**：关键知识点设置硬性校验规则，校验失败自动拦截

### 系统安全
* **JWT 双向认证**：Java 后端与 Python 模型层之间通过共享 JWT Secret 进行双向认证
* **分布式限流**：Redisson 信号量控制最大并发数（默认 20），防止模型服务过载
* **SSE 断线续传**：SSEEventCache 滑动窗口缓存 + Last-Event-ID 机制，网络波动时自动恢复
* **Token 自动续期**：RefreshTokenInterceptor 在 Token 即将过期时自动签发新 Token

### 内容安全过滤
* **敏感信息过滤**：自动检测并过滤敏感违规信息
* **学术规范检查**：确保生成内容无事实性错误
* **意图分类拦截**：Intent Node 自动识别并拦截非教育学习相关输入

---

## 📊 开源项目与工具声明

| 项目/工具 | 用途 | 协议 |
| --- | --- | --- |
| LangChain & LangGraph | 多智能体编排框架 | MIT |
| FastAPI | Python 异步 Web 框架 | MIT |
| ChromaDB | 向量数据库 | Apache 2.0 |
| Qwen（通义千问） | 大语言模型（Max/Plus/Turbo） | 阿里云协议 |
| DashScope Embedding | 文本向量化（text-embedding-v2） | 阿里云协议 |
| gte-rerank | 语义重排模型 | Apache 2.0 |
| Vue 3 | 前端框架 | MIT |
| Spring Boot 3 | 后端框架 | Apache 2.0 |
| MyBatis-Plus | ORM 框架 | Apache 2.0 |
| Redisson | 分布式锁与限流 | Apache 2.0 |
| 阿里云 OSS | 对象存储服务 | 阿里云协议 |
| 阿里云百炼平台 | 大模型 API 服务 | 阿里云协议 |

> **AI Coding 工具说明**：本项目开发过程中使用了 AI 辅助编程工具进行代码生成与优化，所有 AI 生成内容均经过人工审核与测试验证。

---

## ⚠️ 免责声明

*本系统属于高等教育个性化学习辅助系统，系统生成的学习资源与建议仅供参考，不替代教师的专业教学判断。学生应结合自身实际情况与教师指导进行学习规划。*