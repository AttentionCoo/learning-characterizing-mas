# LearnAgent / 多智能体个性化学习系统

> **基于大模型技术体系的高等教育个性化学习智能体系统**
> 本项目是一套面向高等教育场景（脑卒中方向医学生）的个性化学习智能体系统。系统以高校专业课程知识库为底座，融合 **多智能体协同推理**、**Hybrid RAG（混合检索增强生成）**、**多模态影像识别** 与 **全栈响应式流式架构**，实现了从学生画像构建到个性化资源生成、学习路径规划、智能辅导、学习效果评估的完整闭环，真正实现因材施教的数字化落地。

---

## 项目核心亮点与创新

### 1. 三群协同多智能体架构（Tri-Cluster Multi-Agent Architecture）

系统摒弃了传统单模型问答的单点输出，基于 **LangGraph StateGraph** 构建了三大智能体群协同架构。8 个专家智能体通过 YAML 配置驱动（[expert_config.yaml](model/app/config/expert_config.yaml)），支持动态编排与辩论-仲裁机制：

* **画像构建智能体群**：由画像对话智能体、特征抽取智能体、学习激励智能体组成，通过自然语言对话自动抽取学生特征，构建包含 8 个维度（知识基础、认知风格、学习目标、易错点偏好、学习节奏、资源偏好、临床经验、情绪状态）的动态学生画像，支持画像的随学随新。
* **资源生成智能体群**：由需求分析智能体、文档撰写智能体、题目生成智能体、质量审核智能体、学习激励智能体等多角色智能体协作，完成 7 种类型的个性化资源生成（课程讲解文档、知识体系思维导图、练习题目、临床指南与文献、教学视频脚本、医学编程实操等）。
* **辅导评估智能体群**：由需求分析智能体、质量审核智能体、学习激励智能体等提供智能辅导、学习效果精准评估与情感激励陪伴。
* **辩论-仲裁机制**：不同智能体就争议性知识点提出对立观点，经多轮辩论（默认 1 轮，可配置）后由仲裁智能体依据证据链裁决，输出包含 `### ARBITRATION ###`（裁决结论）和 `### REASONING ###`（裁决推理过程）的结构化裁决结果，减少单一模型偏见，尤其适用于争议性医学问题。
* **动态退火反思**：校验失败后根据驳回原因自动分类为 5 种类型（事实错误 `factual_error`、逻辑矛盾 `logical_contradiction`、个性化不足 `personalization_insufficient`、医学专业性错误 `medical_inaccuracy`、内容不完整 `completeness_issue`），生成针对性修正提示词，并按 `weight_decay_factor=0.5` 衰减不通过智能体的发言权重（最低至 0.2），避免无效重试。
* **智能体动态编排**：根据意图类型和难度评分（0.0-1.0）动态裁剪参与智能体的数量和类型。难度阈值分三档（low ≤ 0.3, medium ≤ 0.6, high ≤ 1.0），每个意图类型映射不同的专家组合，简单任务精简参与，复杂任务全量协同，减少 Token 消耗与延迟。

### 2. 证据前置的深度定制 Hybrid RAG

* **双路混合检索**：基于 ChromaDB + DashScope `text-embedding-v2` 语义向量检索 + BM25（专业术语精准匹配）的双路并发检索引擎，去重合并后交由 Reranker 深度重排，优先召回权威教材与课程文献。
* **多模型 Rerank 容灾**：整合 DashScope gte-rerank 进行深度语境打分与证据压缩，内置 `qwen-rerank-v1`、`gte-rerank-v2`、`qwen-rerank`、`gte-rerank` 四个候选模型自动切换，遇 `AccessDenied` 自动降级至下一模型，全部失败时启用原始结果兜底。
* **高级 QA 自建引擎**：系统精读课程 PDF 并通过 `QAGenerator`（基于 qwen-turbo）自动批量衍生提炼高质量 Q&A 对（每 10 个 chunk 合并为一批次生成 3-5 个 QA 对，附带原文页码标签与来源信息），大幅提升学习场景下的检索召回率。
* **并行检索管道**：`EvidenceRetrievalService` 支持对多个子问题进行异步并行检索（`aparallel_retrieve`），每个检索结果标注 `[来源:xxx p.xx]` 和 `(相关度:xx)`，最终按维度拼接为结构化证据文本。
* **检索缓存**：`HybridRetriever` 内置 MD5 键 + 300 秒 TTL 的内存缓存，避免重复检索相同查询。
* **深度重排与溯源**：在生成内容中强制进行**文献名称与精准页码**的明确溯源，有效防止学术幻觉。

### 3. 全栈响应式流式数据管道（Reactive Stream Pipeline）

底座采用 **Java WebFlux 响应式高并发框架** 与 **Python Asyncio 异步队列** 深度流式融合，打通了从底层智能体组装到前端 Vue3 ReadableStream 实时渲染的链路，使得 AI 的 **Thinking Step（思考过程）** 完全透明可视化，提供生成进度追踪与流式呈现机制，避免长时间白屏等待。支持 SSE 断线续传（Last-Event-ID），确保网络波动时内容不丢失。

**流式事件翻译机制**：`LearningAgent` 通过 `_translate_event` 方法将 LangGraph 的 `astream_events` 原始事件翻译为前端可理解的标准事件格式：
- `on_chain_start` → `node_start`（节点开始，附带中文标签如"正在分析学习需求..."）
- `on_chain_end` → `node_done`（节点完成，附带摘要如"检索到 3 个参考片段"）
- `on_chat_model_stream` → `token`（流式内容片段，仅对 `knowledge_answer` 和 `generate_report` 节点流式输出）

**后台任务管理**：`AsyncTaskManager` 管理所有 SSE 流式任务的生命周期，支持任务创建、事件追加、完成/失败状态管理，以及新事件等待机制（`wait_for_new_event`），确保事件按序推送。

### 4. 动态学习路径与精准资源推送

依托多智能体协同工作机制，整合系统生成的个性化资源，结合大模型对学生专业、学习进度、知识掌握情况及学习偏好的深度分析，为学生规划科学、动态的个性化学习路径，明确学习步骤和顺序；同时基于画像实现学习资源的精准推送，涵盖文档、视频、题库、实操案例等多类型内容，并根据评估结果动态调整。

### 5. 多模态影像识别与循证扩展

* **qwen-vl-max 视觉理解**：集成阿里云多模态大模型，支持学生上传医学影像、课件截图、代码截图等图片，系统自动识别图片类型（课件笔记/代码编程/通用医学影像）并匹配对应分析策略，实现图文联合理解与答疑。
* **PubMed 国际文献检索**：集成 NCBI E-utilities API，支持自动检索 PubMed 国际医学文献数据库，内置 8 级证据等级排序体系（指南 > 荟萃分析 > 系统综述 > RCT > 临床试验 > 综述 > 病例报告），与本地 ChromaDB 知识库互补，扩展循证医学证据来源覆盖面。

---

## 项目目录结构

```
learning-multi-agent-system/
├── frontend/                          # 前端交互层（Vue 3）
│   ├── src/
│   │   ├── api/                       # API 请求模块
│   │   │   ├── ai.js                  # AI 流式对话接口
│   │   │   ├── profile.js             # 学习画像接口
│   │   │   ├── resources.js           # 资源生成接口
│   │   │   ├── learningPath.js        # 学习路径接口
│   │   │   ├── tutor.js               # 智能辅导接口
│   │   │   ├── assessment.js          # 学习评估接口
│   │   │   ├── code.js                # 代码辅助接口
│   │   │   ├── documents.js           # 文档管理接口
│   │   │   ├── patient.js             # 患者管理接口
│   │   │   ├── talk.js                # 对话管理接口
│   │   │   ├── learning.js            # 学习行为接口
│   │   │   └── user.js                # 用户认证接口
│   │   ├── components/
│   │   │   ├── workspace/             # 工作区组件
│   │   │   │   ├── ChatWorkspace.vue  # 对话工作区
│   │   │   │   ├── LearningWorkspace.vue # 学习工作区
│   │   │   │   ├── ThinkingPanel.vue  # 思考步骤折叠面板
│   │   │   │   ├── PapersSidebar.vue  # 文献侧边栏
│   │   │   │   ├── PatientWorkspace.vue # 患者工作区
│   │   │   │   └── WorkspaceTabs.vue  # 工作区标签页
│   │   │   ├── form/                  # 表单组件
│   │   │   │   ├── LoginForm.vue      # 登录表单
│   │   │   │   ├── RegisterForm.vue   # 注册表单
│   │   │   │   └── EditForm.vue       # 编辑表单
│   │   │   ├── PdfPreviewModal.vue    # PDF 预览弹窗
│   │   │   ├── AvatarUpload.vue       # 头像上传
│   │   │   └── LoadingModel.vue       # 模型加载动画
│   │   ├── views/                     # 页面视图
│   │   │   ├── login.vue              # 登录页
│   │   │   ├── home.vue               # 主页布局
│   │   │   ├── profile.vue            # 学习画像页
│   │   │   ├── resources.vue          # 资源生成页
│   │   │   ├── learning-path.vue      # 学习路径页
│   │   │   ├── tutor.vue              # 智能辅导页
│   │   │   ├── assessment.vue         # 学习评估页
│   │   │   └── talk.vue               # 对话页
│   │   ├── stores/                    # Pinia 状态管理
│   │   │   ├── user.js                # 用户状态（Token/认证）
│   │   │   └── theme.js               # 主题状态
│   │   ├── utils/                     # 工具函数
│   │   │   ├── request.js             # Axios 请求封装
│   │   │   ├── imageCompress.js       # 图片压缩
│   │   │   ├── referenceParser.js     # 文献引用解析
│   │   │   └── pause.js               # 流式暂停控制
│   │   └── router/index.js            # 路由配置
│   └── package.json
│
├── backend/ai/MyServer/               # 后端服务层（Java Spring Boot）
│   ├── src/main/java/com/it/
│   │   ├── controller/                # REST 控制器
│   │   │   ├── LoginController.java   # 登录注册
│   │   │   ├── ProfileController.java # 学习画像
│   │   │   ├── ResourceController.java # 资源生成
│   │   │   ├── LearningPathController.java # 学习路径
│   │   │   ├── TutorController.java   # 智能辅导
│   │   │   ├── AssessmentController.java # 学习评估
│   │   │   ├── CodeController.java    # 代码辅助
│   │   │   ├── DocumentController.java # 文档管理
│   │   │   ├── CourseController.java  # 课程管理
│   │   │   ├── QuesController.java    # 题目管理
│   │   │   ├── UploadController.java  # 文件上传
│   │   │   ├── MonitorController.java # 系统监控
│   │   │   └── InitialPageController.java # 首页数据
│   │   ├── service/                   # 业务逻辑层
│   │   │   ├── AIStreamingService.java    # AI 流式调用接口
│   │   │   ├── impl/AIStreamingServiceImpl.java # WebClient 流式转发实现
│   │   │   ├── impl/ConversationPersistenceService.java # 对话持久化
│   │   │   └── OssDocumentService.java    # OSS 文档服务
│   │   ├── cache/
│   │   │   └── SSEEventCache.java     # SSE 事件缓存（断线续传）
│   │   ├── config/                    # 配置类
│   │   │   ├── SecurityConfig.java    # Spring Security 配置
│   │   │   ├── WebClientConfig.java   # WebClient 流式调用配置
│   │   │   ├── RedissonConfig.java    # Redisson 分布式限流
│   │   │   └── OssConfig.java         # 阿里云 OSS 配置
│   │   ├── pojo/                      # 实体类
│   │   ├── po/uo/                     # 请求参数对象
│   │   ├── po/vo/                     # 响应视图对象
│   │   ├── mapper/                    # MyBatis-Plus Mapper
│   │   └── utils/                     # JWT、OSS、IP 工具
│   ├── src/main/resources/
│   │   ├── application.yml            # 主配置
│   │   ├── application-dev.yml        # 开发环境配置
│   │   ├── application-prod.yml       # 生产环境配置
│   │   └── db/schema_additions.sql    # 数据库增量脚本
│   ├── learningo-agents.sql           # 完整数据库初始化脚本
│   └── pom.xml
│
├── model/                             # 模型推理层（Python FastAPI）
│   ├── app/
│   │   ├── main.py                    # FastAPI 入口（所有 API 端点定义）
│   │   ├── agents/
│   │   │   ├── orchestrators/
│   │   │   │   ├── clinical_graph.py  # LangGraph StateGraph 图定义
│   │   │   │   ├── qwen_agent.py      # LearningAgent 主推理入口
│   │   │   │   └── nodes/             # 图节点实现
│   │   │   │       ├── intent_node.py     # 意图分类 + 难度评分
│   │   │   │       ├── analysis_node.py   # 结构化需求分析
│   │   │   │       ├── retrieve_node.py   # Hybrid RAG 证据检索
│   │   │   │       ├── reason_node.py     # 多智能体协同推理 + 辩论仲裁
│   │   │   │       ├── validate_node.py   # 质量校验 + 退火反思
│   │   │   │       └── report_node.py     # 报告生成 + 学习激励
│   │   │   ├── assistant.py           # LearningAssistant（RAG 检索封装）
│   │   │   ├── core/
│   │   │   │   ├── schema.py          # LearningState 状态模型（22 字段）
│   │   │   │   ├── decorators.py      # 装饰器
│   │   │   │   ├── exceptions.py      # 自定义异常
│   │   │   │   └── result.py          # 结果封装
│   │   │   ├── infra/
│   │   │   │   ├── reranker.py        # 多模型 Rerank 容灾
│   │   │   │   └── base_reranker.py   # Reranker 基类
│   │   │   ├── services/
│   │   │   │   ├── retrieval_service.py   # 证据检索服务
│   │   │   │   ├── query_service.py       # 查询服务
│   │   │   │   └── synthesis_service.py   # 意见综合服务
│   │   │   ├── pipelines/
│   │   │   │   └── rag_pipeline.py    # RAG 管道
│   │   │   └── utils/
│   │   │       ├── llm_helper.py      # LLM 调用辅助
│   │   │       ├── json_parser.py     # JSON 解析
│   │   │       ├── retry.py           # 重试机制
│   │   │       └── text_utils.py      # 文本工具
│   │   ├── rag/
│   │   │   ├── retrievers.py          # HybridRetriever（向量 + BM25）
│   │   │   ├── retrieve.py            # UnifiedSearchEngine 统一检索
│   │   │   ├── qa_generator.py        # QA 对自建引擎
│   │   │   └── data_loader.py         # PDF 文档加载
│   │   ├── services/
│   │   │   ├── vision_service.py      # 多模态影像识别服务
│   │   │   └── pubmed_service.py      # PubMed 文献检索服务
│   │   ├── config/
│   │   │   ├── expert_config.yaml     # 8 专家智能体配置
│   │   │   ├── rules_config.yaml      # 校验规则 + 退火策略
│   │   │   ├── report_templates.yaml  # 5 种报告模板
│   │   │   ├── prompts.yaml           # Prompt 模板库
│   │   │   ├── limits_config.yaml     # 参数上限配置
│   │   │   └── config_loader.py       # 配置加载器（单例管理）
│   │   └── utils/
│   │       ├── task_manager.py        # AsyncTaskManager 后台任务管理
│   │       ├── context_summary.py     # ConversationSummaryService
│   │       ├── naming_model.py        # 对话命名模型
│   │       ├── token_aggregator.py    # Token 聚合
│   │       └── error_codes.py         # 错误码定义
│   ├── data/documents/                # 课程 PDF 文献库（12 篇脑卒中指南）
│   ├── tests/                         # 测试用例
│   ├── requirements.txt               # Python 依赖
│   ├── start.bat                      # Windows 快速启动脚本
│   └── start.sh                       # Linux 快速启动脚本
│
└── docs/                              # 项目文档
    ├── API_SPEC.md                    # 接口规范文档
    └── 多智能体个性化学习系统接口文档.md  # 中文接口文档
```

---

## 全栈系统架构与技术矩阵

本项目采用典型的前端交互、后端业务、模型推理三层解耦架构，各层之间通过高并发、低延迟的响应式流进行数据穿透。

### 全栈技术矩阵

| 架构层级 | 核心技术栈 | 核心设计职责 |
| --- | --- | --- |
| 前端交互层<br>(Frontend) | Vue 3.5 (Composition API) <br>• Vite 7.1 • Pinia 3.0 • SCSS <br>• Fetch / ReadableStream <br>• marked 17 • DOMPurify • morphdom <br>• pdfjs-dist • vue-pdf-embed • NProgress | 以用户体验为核心，持续接收后端流式推送并实时打字机渲染。支持 Markdown 渲染、多模态内容卡片化展示、ThinkingPanel 思考步骤折叠展示、学习路径可视化、PDF 在线预览、图片压缩上传。 |
| 后端服务层<br>(Backend) | Java 21 • Spring Boot 3.3.13 <br>• Spring WebFlux • Spring Security <br>• Redis • Redisson 3.27 <br>• MySQL 8.0 • MyBatis-Plus 3.5.5 <br>• Aliyun OSS • Hutool • JWT | 采用响应式编程模型支持高并发吞吐。通过 JWT 实现身份认证与安全控制，利用 Redisson 分布式限流与并发信号量控制，通过 WebClient 对底层 Python 模型服务进行流式非阻塞调用与转发，SSEEventCache 支持断线续传。 |
| 模型推理层<br>(Model) | Python 3.11+ • FastAPI 0.128 <br>• LangGraph 0.2.20 • LangChain 0.2.16 <br>• Qwen-Max/Plus/Turbo <br>• ChromaDB 0.5 • gte-rerank <br>• DashScope SDK • PyJWT <br>• qwen-vl-max（多模态视觉） <br>• PubMed E-utilities（文献检索） | 统一入口加载大语言模型、混合检索引擎与多智能体推理模块。通过异步生成器持续输出标准事件格式（node_start, token, node_done, done），实现高效流式通信。JWT 双向认证保障服务间调用安全。集成多模态影像识别与 PubMed 文献检索扩展能力。 |

### 全链路流式数据管道 (SSE Pipeline)

```
学生学习输入 ──► Java 鉴权与限流隔离 ──► WebClient 异步非阻塞调用 ──► FastAPI 接收请求
  ──► AsyncTaskManager 创建后台任务 ──► LearningAgent.run_learning_reasoning()
  ──► LangGraph StateGraph astream_events ──► _translate_event 翻译为标准事件
  ──► asyncio.Queue 队列 ──► Java (Flux 持续转发)
  ──► Vue3 (ReadableStream 接收与实时打字机渲染)
```

---

## 多智能体矩阵协同推理机制（Multi-Agent System）

系统基于 **LangGraph** 创新设计了业务功能轴（纵向） × 决策行为轴（横向）的双轴矩阵多智能体协同架构，高度模拟真实教育场景中的多角色协作与多级质量把关流程。

### 1. LangGraph 推理拓扑架构

系统核心推理流程基于 LangGraph StateGraph 构建，通过意图路由将不同类型的请求分发至对应的处理管道。完整图定义位于 [clinical_graph.py](model/app/agents/orchestrators/clinical_graph.py)，状态模型定义于 [schema.py](model/app/agents/core/schema.py)：

```
用户输入
    |
[Intent Node] <-- 意图分类 + 难度评分（0.0-1.0）
    |                基于 ChatPromptTemplate + LLM + StrOutputParser 链
    |                输出 JSON: { type, reason, difficulty_score }
    v
[路由决策] _route_intent()
    |
    +-- irrelevant --> [Reject Node] --> END
    |                   返回: "请提供教育学习相关的查询"
    |
    +-- knowledge  --> [Knowledge Answer Node] --> END
    |                   直接调用 LLM 回答通用教育问题
    |
    +-- profile / resource / tutor / assessment / learning_path / consultation
         |
    [Analysis Node] -- 结构化分析学习需求
    |                  输出: structured_context, learning_questions(最多3个),
    |                        key_risks, complexity, user_questions
    v
    [Retrieve Node] -- Hybrid RAG 并行证据检索
    |                  调用 LearningAssistant.afast_parallel_retrieve()
    |                  对每个子问题异步检索，结果截断至 MAX_EVIDENCE_CHARS(2000)
    v
    [Reason Node]  -- 动态编排 -> 八智能体协同推理
    |                  1. _resolve_active_experts(): 根据意图+难度选择参与专家
    |                  2. asyncio.gather 并行推理（支持权重衰减提示）
    |                  3. 辩论-仲裁（_run_debate + _run_arbitration）
    |                  4. 统筹汇总 -> Proposal + Critique
    v
    [Validate Node] -- 质量校验与动态退火反思循环
    |                   1. 规则引擎检查（contraindication_rules）
    |                   2. LLM 反思检查（PASS / REJECT）
    |                   3. 退火策略：分类驳回 + 权重衰减 + 修正提示词
    |
    +-- pass  --> [Report Node]（含学习激励反馈）--> END
    +-- retry --> [Reason Node]（权重衰减 + 针对性修正提示词）
    +-- fail  --> [Report Node] --> END（强制输出，附质量警告）
```

**LearningState 状态模型**（[schema.py](model/app/agents/core/schema.py)）贯穿整个图执行流程，包含 22 个字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `case_text` | str | 用户原始输入 |
| `all_info` | str | 历史对话上下文摘要 |
| `report_mode` | str | 报告模式（profile_build/resource_generate/tutor/assessment/learning_path） |
| `intent_type` | str | 意图分类结果 |
| `difficulty_score` | float | 难度评分（0.0-1.0） |
| `context` | Dict | 结构化学习上下文 |
| `learning_questions` | List[str] | 检索子问题列表 |
| `evidence` | str | RAG 检索证据文本 |
| `proposal` | str | 综合提案 |
| `critique` | str | 潜在问题批判 |
| `validation_passed` | bool | 校验是否通过 |
| `validation_feedback` | str | 校验反馈/驳回理由 |
| `reflection_count` | int | 反思次数 |
| `agent_weights` | Dict | 智能体权重映射（退火衰减） |
| `rejection_categories` | List[str] | 驳回原因分类历史 |
| `debate_history` | List[Dict] | 辩论历史记录 |
| `active_experts` | List[str] | 本轮参与专家列表 |
| `motivational_feedback` | str | 学习激励反馈 |
| `report` | str | 最终生成报告 |

### 2. 智能体角色矩阵

以下 8 个专家智能体均通过 [expert_config.yaml](model/app/config/expert_config.yaml) 配置驱动，每个智能体定义了 `role`、`instruction`、`system_prompt`、`priority`、`applicable_intents`、`min_difficulty` 六个核心属性：

| 角色名称 | 优先级 | 适用意图 | 最低难度 | 职责说明 |
| --- | --- | --- | --- | --- |
| 画像对话智能体 | 1 | profile, resource, tutor, assessment, learning_path | 0.0 | 引导式对话，收集学生专业、学习目标、脑卒中知识水平等信息 |
| 特征抽取智能体 | 2 | profile, resource, assessment | 0.2 | 从对话中自动抽取结构化画像特征维度（8 维度） |
| 需求分析智能体 | 3 | resource, tutor, learning_path | 0.3 | 分析学习需求，拆解生成任务，确定资源类型和难度级别 |
| 文档撰写智能体 | 4 | resource | 0.4 | 生成脑卒中专业课程讲解文档，涵盖脑血管解剖、病理机制、诊疗规范等 |
| 题目生成智能体 | 5 | resource, assessment | 0.4 | 生成选择题、病例分析题、简答题等多种类型练习题目 |
| 质量审核智能体 | 6 | resource, assessment, learning_path | 0.5 | 审核资源学术准确性、医学专业性、个性化匹配度和教学有效性 |
| 学习激励智能体 | 7 | profile, resource, tutor, assessment, learning_path | 0.0 | 识别学生情绪状态，提供鼓励、阶段性反馈和节奏调整建议 |
| 仲裁智能体 | 8 | resource, tutor, assessment, learning_path | 0.6 | 依据证据链和逻辑一致性裁决辩论中的对立观点，确保输出稳健无偏见 |

### 3. 动态编排规则

动态编排通过 `intent_expert_mapping` 和 `difficulty_thresholds` 联合决定每个请求的参与专家：

| 意图类型 | 参与专家 | 说明 |
| --- | --- | --- |
| profile | 画像对话智能体、特征抽取智能体、学习激励智能体 | 画像构建场景，3 个专家协作 |
| resource | 画像对话智能体、需求分析智能体、文档撰写智能体、题目生成智能体、质量审核智能体、学习激励智能体 | 资源生成场景，6 个专家协作 |
| tutor | 画像对话智能体、需求分析智能体、质量审核智能体、学习激励智能体 | 辅导场景，4 个专家协作 |
| assessment | 特征抽取智能体、需求分析智能体、题目生成智能体、质量审核智能体、学习激励智能体 | 评估场景，5 个专家协作 |
| learning_path | 画像对话智能体、需求分析智能体、质量审核智能体、学习激励智能体 | 路径规划场景，4 个专家协作 |

> 仲裁智能体在辩论启用且难度评分 ≥ 0.6 时自动加入参与列表。

### 4. 辩论-仲裁机制详解

辩论-仲裁流程在 [reason_node.py](model/app/agents/orchestrators/nodes/reason_node.py) 中实现：

1. **首轮并行推理**：所有参与专家（除仲裁智能体外）通过 `asyncio.gather` 并行调用 LLM 生成各自建议
2. **多轮辩论**：每轮辩论中，各专家基于辩论上下文（包含其他专家当前观点和历史辩论记录）提出反驳或补充，输出格式为：立场（支持/反对/修正）、论据与证据、对反方观点的回应
3. **仲裁裁决**：仲裁智能体接收完整辩论记录和可用证据，输出结构化裁决结果（`### ARBITRATION ###` 裁决结论 + `### REASONING ###` 裁决推理过程）
4. **意见综合**：将专家意见（带权重标签）和仲裁裁决合并，由 `llm_synthesis`（qwen-max）生成最终 Proposal + Critique

### 5. 动态退火反思机制详解

退火策略在 [validate_node.py](model/app/agents/orchestrators/nodes/validate_node.py) 和 [rules_config.yaml](model/app/config/rules_config.yaml) 中实现：

**校验流程**：
1. **规则引擎检查**：遍历 `contraindication_rules` 中的质量规则（资源生成/画像构建/学习路径三类），检测提案中是否包含违规内容
2. **LLM 反思检查**：调用 LLM 作为教育质量审查员，判断提案是否存在严重错误，输出 `PASS` 或 `REJECT: <详细理由>`
3. **最大反思次数**：默认 1 次（`max_reflection_count: 1`），超过后强制输出

**退火策略**（校验失败时触发）：
1. **驳回分类**：根据关键词匹配将驳回原因分为 5 类：
   - `factual_error`（事实错误）：关键词"事实错误""数据不准确""信息有误""与证据不符"
   - `logical_contradiction`（逻辑矛盾）：关键词"逻辑矛盾""前后不一致""自相矛盾""推理不成立"
   - `personalization_insufficient`（个性化不足）：关键词"个性化不足""未结合画像""缺乏针对性""通用化"
   - `medical_inaccuracy`（医学专业性错误）：关键词"医学错误""诊疗不规范""不符合指南""专业性不足"
   - `completeness_issue`（内容不完整）：关键词"不完整""遗漏""缺少关键""覆盖不全"
2. **针对性修正提示词**：每类驳回生成对应的修正指引，如"你的上一次输出存在事实性错误，请严格依据提供的参考证据重新推理，禁止编造未在证据中出现的数据或结论。"
3. **权重衰减**：所有参与专家的发言权重按 `weight_decay_factor=0.5` 衰减（最低至 0.2），被衰减的专家在下一轮推理中会收到提示"你在上一轮推理中部分建议被驳回，当前发言权重为 x.x，请更加谨慎地依据证据给出建议。"

---

## 系统整体功能模块

### 1. 对话式学习画像自主构建

摒弃传统繁琐表单，支持通过自然语言对话自动抽取特征，构建包含 8 个维度的动态学生画像：

* **知识基础**（knowledgeBase）：level（beginner/intermediate/advanced）、已掌握知识点、薄弱知识点
* **认知风格**（cognitiveStyle）：type（visual/auditory/kinesthetic/reading）、偏好描述
* **学习目标**（learningGoal）：短期目标、长期目标、当前课程
* **易错点偏好**（errorPattern）：errorType（conceptual/careful/procedural）、高频错误点
* **学习节奏**（learningPace）：speed（slow/moderate/fast）、每周可投入时长
* **资源偏好**（resourcePreference）：偏好资源类型列表（video/document/quiz 等）
* **临床经验**（clinicalExperience）：level（none/basic/moderate/extensive）、脑卒中相关临床经验描述
* **情绪状态**（emotionState）：status（motivated/anxious/confident/overwhelmed）、情绪描述

画像支持随学随新：
- 对话结束后，系统自动调用 `_extract_profile_from_conversation` 从师生对话中提取画像维度（通过 qwen-turbo + 结构化 JSON Prompt）
- 支持手动更新画像维度（`PUT /model/profile/dimensions`）
- 支持对话历史管理与多轮对话上下文摘要（`ConversationSummaryService`，保留率 0.4）

### 2. 多智能体协同资源生成

不同角色智能体协作完成 7 种类型的个性化资源生成，每种资源均有独立的 API 端点和请求模型：

| 资源类型 | API 端点 | 请求模型 | 说明 |
| --- | --- | --- | --- |
| 课程讲解文档 | `/model/resources/generate/document` | `SingleDocumentRequest` | 结构化知识点讲解，支持难度/风格/画像感知配置 |
| 知识体系思维导图 | `/model/resources/generate/mindmap` | `SingleMindmapRequest` | Mermaid 格式，可配置展开层级（默认 3 层） |
| 练习题目 | `/model/resources/generate/quiz` | `SingleQuizRequest` | 选择题/填空题/简答题等，可配置题目类型/数量/是否含答案 |
| 拓展阅读材料 | `/model/resources/generate/reading` | `SingleReadingRequest` | 关联文献与延伸学习资源，可配置类型/语言/数量 |
| 教学视频脚本 | `/model/resources/generate/video-script` | `SingleVideoScriptRequest` | 可视化讲解脚本，可配置时长/风格/是否含旁白和画面描述 |
| 代码实操案例 | `/model/resources/generate/code-practice` | `SingleCodePracticeRequest` | 编程实践案例，可配置语言/项目类型/是否含测试用例和注释 |
| 综合资源生成 | `/model/resources/generate` | `ResourceGenerateRequest` | 多类型资源批量生成，支持课程名/知识点/难度/图片输入 |

所有资源生成接口均支持 SSE 流式输出和图片输入（通过 `VisionAnalysisService` 调用 qwen-vl-max 多模态模型进行视觉分析）。

### 3. 个性化学习路径规划与资源推送

* **动态路径规划**：根据画像生成阶段性学习路径（5-15 步），每步包含 2-5 个知识点，难度循序渐进，支持前置步骤依赖（prerequisites）
* **精准资源推送**：基于画像维度综合计算，推送匹配的学习资源，返回推荐理由和相关性评分
* **路径动态调整**：根据学习效果评估结果或学生反馈，动态调整路径难度与资源推荐策略（支持插入步骤/更新资源/调整难度三种调整类型）
* **步骤进度追踪**：支持标记步骤完成状态（not_started/in_progress/completed）、实际投入时长与自评反馈

### 4. 智能辅导

当学生在学习过程中遇到问题时，系统提供即时、多模态的答疑解惑服务：

* **文字解答**：详细的步骤化文字讲解
* **图片识别**：支持上传图片进行视觉分析辅助解答（基于 qwen-vl-max 多模态模型，自动检测图片类型：课件/代码/通用）
* **上下文感知**：支持传入课程名、当前知识点、学习路径 ID 等上下文信息
* **偏好回答形式**：可指定期望的回答形式（text/diagram/code/video）

### 5. 学习效果评估

* **多维度评估**：5 个维度（知识掌握度、学习效率、技能应用、学习一致性、进度对齐度），每个维度包含评分、等级和详细信息
* **知识点掌握热力图**：按知识点树状结构展示掌握程度（0.0-1.0 四档：未掌握/初步了解/基本掌握/熟练掌握）
* **练习/测验提交**：支持答案提交与自动批改，返回知识点薄弱分析和推荐资源
* **闭环优化**：评估结果自动触发学习路径调整和资源推送策略更新（`/model/evaluation/optimize`）
* **学习行为采集**：支持提交学习行为数据（学习时长、资源使用、练习结果等）

### 6. 多模态影像识别与辅助分析

系统集成 **qwen-vl-max** 多模态视觉大模型，支持学生在对话中上传医学影像、课件截图、代码截图等图片，实现多模态辅助分析：

* **图片类型自动识别**：`VisionAnalysisService` 根据用户问题关键词自动判断图片类型（`image_report` 课件笔记类 / `image_drug` 代码编程类 / `image_general` 通用医学影像类），匹配不同的分析 Prompt 策略
* **流式影像分析**：通过 DashScope `MultiModalConversation` API 流式输出分析结果，实时呈现影像解读过程
* **多图联合分析**：支持单次请求上传多张图片进行联合分析，图片以 Base64 编码传输
* **与对话流式融合**：影像分析结果无缝融入主对话流式管道，前端通过 `ThinkingPanel` 展示"正在分析图片..."进度

### 7. PubMed 文献检索与循证扩展

系统集成 **PubMed E-utilities API**，支持自动检索国际医学文献数据库，为学习资源生成提供循证医学证据扩展：

* **智能检索**：`PubMedService` 封装 NCBI E-utilities API（esearch + efetch），支持关键词检索与摘要获取
* **证据等级排序**：内置 8 级证据等级体系（Practice Guideline > Guideline > Meta-Analysis > Systematic Review > RCT > Clinical Trial > Review > Case Reports），自动按证据强度排序
* **API Key 加速**：配置 PubMed API Key 提升请求速率限制（从 3 次/秒提升至 10 次/秒）
* **与 RAG 互补**：PubMed 检索结果与本地 ChromaDB 知识库检索结果互补，扩展证据来源覆盖面

### 8. 代码辅助开发

系统提供面向医学生的代码辅助开发能力，支持医学数据分析编程、临床决策支持代码生成与医学 AI 模型实操：

* **代码生成**：根据学习需求生成 Python/SQL 等语言的医学数据分析代码
* **代码执行**：后端 `CodeController` 提供代码执行沙箱接口（`/api/code/execute`），支持代码运行与调试
* **代码辅助**：`/api/code/assist` 接口提供代码补全、错误诊断与优化建议
* **实操案例生成**：资源生成模块支持 `code-practice` 类型，自动生成含测试用例和注释的编程实践案例

---

## 模型层初始化流程

FastAPI 服务启动时通过 `lifespan` 上下文管理器执行 7 步资源初始化（[main.py](model/app/main.py)）：

| 步骤 | 初始化内容 | 说明 |
| --- | --- | --- |
| 1/7 | 配置管理器 | PromptManager、ReportTemplateManager、ExpertManager、ValidationManager、LimitsManager |
| 2/7 | 大语言模型 | qwen-max（提案生成）、qwen-plus（推理校验）、qwen-turbo（意图分类/快速通道） |
| 3/7 | 上下文摘要服务 | ConversationSummaryService（基于 qwen-turbo） |
| 4/7 | 向量检索引擎 | UnifiedSearchEngine（ChromaDB + DashScope Embedding + BM25 + Reranker） |
| 5/7 | 学习助手 | LearningAssistant（RAG Pipeline 组装） |
| 6/7 | 学习推理智能体 | LearningAgent（LangGraph 图编译 + 6 个节点注入） |
| 7/7 | 其他服务 | VisionAnalysisService（qwen-vl-max）、NamingModel（对话命名） |

---

## 核心 API 契约

### 全局约定

* **Java 后端 Base URL**：开发环境 `http://localhost:8080/api`
* **Python 模型层 Base URL**：`http://localhost:8000/model`
* **认证方式**：除登录/注册外，所有接口需携带 JWT Token（`Authorization: Bearer <token>` 或 `token: <token>`）
* **统一响应体**：`{ code: 1, msg: "success", data: {} }`（1=成功，0=失败）
* **JWT 双向认证**：Java 后端转发请求至 Python 模型层时，携带 JWT Token 进行双向验证

### SSE 流式事件格式

流式接口采用 SSE（Server-Sent Events）协议，由 `AsyncTaskManager` 管理事件推送：

| 事件类型 | 说明 | data 结构 |
| --- | --- | --- |
| `init` | 连接建立，返回任务 ID 和会话 ID | `{"type":"init","taskId":"...","talkId":"123","newTalk":true}` |
| `node_start` | 智能体节点开始推理 | `{"type":"node_start","node":"analysis","label":"正在分析学习需求..."}` |
| `token` | 内容片段（增量） | `{"type":"token","content":"..."}` |
| `node_done` | 节点完成，附带摘要 | `{"type":"node_done","node":"retrieve","summary":"检索到 3 个参考片段"}` |
| `done` | 流式结束 | `{"type":"done","taskId":"...","talkId":"123","title":"学习画像构建"}` |
| `error` | 错误 | `{"type":"error","code":"E2001","message":"..."}` |

### 核心 API 列表

#### 用户认证

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/user/login` | POST | 用户登录 |
| `/api/user/register` | POST | 用户注册 |

#### 学习画像

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/profile/conversation` | POST (SSE) | 对话式画像构建（流式） |
| `/api/profile` | GET | 获取当前画像（含 8 维度 JSON） |
| `/api/profile/dimensions` | PUT | 手动更新画像维度 |
| `/api/profile/conversations` | GET | 获取画像对话列表 |
| `/model/profile/extract` | POST | 从对话内容抽取画像维度（8 维度结构化 JSON 输出） |

#### 资源生成

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/resources/generate` | POST (SSE) | 综合多类型资源生成 |
| `/model/resources/generate/document` | POST (SSE) | 课程讲解文档生成 |
| `/model/resources/generate/mindmap` | POST (SSE) | 知识体系思维导图生成 |
| `/model/resources/generate/quiz` | POST (SSE) | 练习题目生成 |
| `/model/resources/generate/reading` | POST (SSE) | 拓展阅读材料生成 |
| `/model/resources/generate/video-script` | POST (SSE) | 教学视频脚本生成 |
| `/model/resources/generate/code-practice` | POST (SSE) | 代码实操案例生成 |
| `/api/resources` | GET | 获取资源列表 |

#### 学习路径

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/learning-path/generate` | POST | 生成学习路径（5-15 步，含前置依赖） |
| `/api/learning-path` | GET | 获取当前路径 |
| `/api/learning-path/{path_id}/steps/{step_id}/progress` | PUT | 更新步骤进度 |
| `/model/learning-path/recommend` | POST | 个性化资源推送 |
| `/model/learning-path/{path_id}/adjust` | POST | 动态调整学习路径 |

#### 智能辅导

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/tutor/chat` | POST (SSE) | 智能辅导对话（支持图片输入） |
| `/api/tutor/conversations` | GET | 获取辅导对话列表 |

#### 学习评估

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/assessment/generate` | POST (SSE) | 生成评估报告 |
| `/model/evaluation/report` | GET | 获取学习效果评估报告（5 维度） |
| `/model/evaluation/mastery-heatmap` | GET | 知识点掌握度热力图 |
| `/model/evaluation/quiz/{quiz_id}/submit` | POST | 提交练习答案 |
| `/model/evaluation/behavior` | POST | 提交学习行为数据 |
| `/model/evaluation/optimize` | POST | 触发学习方案动态优化 |

#### 其他

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/code/execute` | POST | 代码执行与调试 |
| `/api/documents/upload` | POST | 文档上传（OSS） |
| `/api/documents/match` | POST | 文献引用匹配 |

### 前端页面路由映射

| 路由路径 | 页面组件 | 功能说明 |
| --- | --- | --- |
| `/login` | `login.vue` | 用户登录/注册 |
| `/profile` | `profile.vue` | 对话式学习画像构建（8 维度动态画像） |
| `/resources` | `resources.vue` | 多智能体协同资源生成（7 种资源类型） |
| `/learning-path` | `learning-path.vue` | 个性化学习路径规划与资源推送 |
| `/tutor` | `tutor.vue` | 智能辅导（支持图片输入 + 多模态答疑） |
| `/assessment` | `assessment.vue` | 学习效果评估与反馈 |

> 所有页面均需登录后访问（路由守卫 `router.beforeEach` 校验 Token），未登录自动重定向至 `/login`。

### 数据库表结构概览

系统使用 MySQL 8.0 数据库（库名 `medai`），核心数据表如下：

| 表名 | 说明 | 关键字段 |
| --- | --- | --- |
| `user` | 用户信息表 | id, username, password, major, grade, specialty |
| `student_profile` | 学习画像表 | id, user_id, dimensions(JSON), update_time |
| `talk` | 对话会话表 | id, user_id, title, create_time |
| `cont` | 对话消息表 | id, talk_id, content, role(user/assistant), images(Base64 JSON) |
| `learning_path` | 学习路径表 | id, user_id, course_name, goal, status, total_steps |
| `learning_path_step` | 学习路径步骤表 | id, path_id, step_order, title, status, actual_hours |
| `learning_resource` | 学习资源表 | id, title, type, url, content |
| `step_resource_rel` | 步骤-资源关联表 | id, step_id, resource_id |
| `learning_behavior_record` | 学习行为记录表 | id, user_id, path_id, step_id, behavior_type, behavior_data |
| `eval_report` | 评估报告表 | id, user_id, path_id, report_content, create_time |
| `patient` | 患者信息表 | id, name, history, notes, doctor_id |
| `ai_opinion` | AI 分析意见表 | id, patient_id, risk_level, suggestions, analysis_details |
| `health_data` | 健康数据表 | id, patient_id, data_content(JSON) |
| `learning_material` | 学习资料表 | id, title, category, type, url, content |
| `ques` | 题目表 | id, course_id, type, content, answer |

> 完整建表脚本见 [learningo-agents.sql](backend/ai/MyServer/learningo-agents.sql)，增量脚本见 [schema_additions.sql](backend/ai/MyServer/src/main/resources/db/schema_additions.sql)。

---

## 安全与防幻觉机制

### 防幻觉策略

* **证据溯源**：所有生成内容强制引用来源文献与页码（`[来源:xxx p.xx]`），杜绝无依据输出
* **双层校验**：Validate Node 规则引擎进行学术准确性审查（`contraindication_rules` 关键词匹配）+ LLM 反思机制深层逻辑审查（PASS/REJECT 判定）
* **辩论-仲裁模式**：不同智能体就争议观点进行多轮辩论，仲裁智能体依据证据链裁决（输出 `### ARBITRATION ###` + `### REASONING ###`），减少单一模型偏见
* **动态退火反思**：校验未通过时自动分类驳回原因为 5 类（事实错误/逻辑矛盾/个性化不足/医学专业性错误/内容不完整），生成针对性修正提示词，同时按 0.5 因子衰减不通过智能体的发言权重（最低 0.2），避免无效重试
* **智能体动态编排**：根据意图类型和难度评分动态裁剪参与智能体数量，简单任务 3 个专家，复杂任务 6 个专家 + 仲裁
* **规则引擎**：3 类质量规则（资源生成/画像构建/学习路径）设置硬性校验规则，校验失败自动拦截
* **文献引用规范**：系统角色 Prompt 强制要求使用《》书名号引用库内文献，严禁自行创造或引用库外文献名称

### 系统安全

* **JWT 双向认证**：Java 后端与 Python 模型层之间通过共享 JWT Secret 进行双向认证（`verify_token` 函数校验每个模型层请求）
* **分布式限流**：Redisson 信号量控制最大并发数（默认 20），防止模型服务过载
* **SSE 断线续传**：SSEEventCache 滑动窗口缓存 + Last-Event-ID 机制，网络波动时自动恢复
* **Token 自动续期**：RefreshTokenInterceptor 在 Token 即将过期时自动签发新 Token

### 内容安全过滤

* **敏感信息过滤**：自动检测并过滤敏感违规信息
* **学术规范检查**：确保生成内容无事实性错误
* **意图分类拦截**：Intent Node 自动识别并拦截非教育学习相关输入（`irrelevant` 类型路由至 Reject Node）
* **安全卫栏**：系统角色 Prompt 内置安全规则——禁止绝对性结论、建议需标注不确定性、关键信息缺失须标注"不足以支持"、临床诊疗建议须提醒在执业医师指导下实践

---

## 配置文件说明

模型层采用 YAML 配置驱动，所有配置通过 `config_loader.py` 统一加载为单例管理器：

| 配置文件 | 管理器 | 核心配置项 |
| --- | --- | --- |
| [expert_config.yaml](model/app/config/expert_config.yaml) | ExpertManager | 8 个专家定义（role/instruction/system_prompt/priority/applicable_intents/min_difficulty）、辩论配置（enabled/max_rounds/arbitrator_role/辩论模板/仲裁模板）、综合汇总配置（prompt_template/opinion_separator）、动态编排配置（difficulty_thresholds/intent_expert_mapping）、启用专家列表 |
| [rules_config.yaml](model/app/config/rules_config.yaml) | ValidationManager | 3 类禁忌规则（资源生成/画像构建/学习路径）、校验设置（max_reflection_count/enable_rule_engine/enable_llm_reflection）、退火策略（enabled/weight_decay_factor/5 类驳回分类关键词/5 类针对性修正提示词） |
| [report_templates.yaml](model/app/config/report_templates.yaml) | ReportTemplateManager | system_role（20 年教学经验顾问角色 + 三步逻辑主线 + 画像驱动原则 + 安全卫栏）、5 种报告模板（profile_build/resource_generate/tutor/assessment/learning_path） |
| [prompts.yaml](model/app/config/prompts.yaml) | PromptManager | 各场景 Prompt 模板库 |
| [limits_config.yaml](model/app/config/limits_config.yaml) | LimitsManager | 参数上限（max_sub_questions=3/max_evidence_chars=2000/max_proposal_chars=3000 等）、3 类关键词（diagnostic/treatment/prognosis）、拒绝关键词（reject） |

---

## 报告模板体系

系统通过 [report_templates.yaml](model/app/config/report_templates.yaml) 定义了 5 种报告模式，每种模式对应不同的输出结构：

| 报告模式 | 名称 | 输出结构 |
| --- | --- | --- |
| `profile_build` | 学习画像构建 | 9 节结构：基本信息分析 → 知识基础 → 认知风格 → 学习目标 → 易错点 → 学习节奏 → 资源偏好 → 临床经验 → 个性化建议 |
| `resource_generate` | 个性化学习资源内容生成 | 学习目标 → 核心知识点详解（定义/要点/临床意义） → 知识关联图谱 → 重点难点突破 → 拓展阅读 → 自测清单 → 实践应用案例 |
| `tutor` | 智能辅导 | 解答 → 关键概念 → 易错提示 → 拓展思考 → 下一步建议 |
| `assessment` | 学习评估报告 | 综合评估 → 各维度分析 → 优势分析 → 薄弱环节 → 改进建议 |
| `learning_path` | 学习路径规划 | 学生需求 → 历史上下文 → 参考证据 → 初步规划 → 审查意见 |

---

## 快速开始

### 环境要求

* **Java 21+** + Maven 3.8+
* **Python 3.11+** + pip
* **Node.js 18+** + npm
* **MySQL 8.0+**
* **Redis 6.0+**
* **阿里云 DashScope API Key**（用于 Qwen 大模型、Embedding、Rerank 服务）

### 环境变量

模型层环境变量配置文件为 `model/.env`，需配置以下变量：

```bash
# 必需 - 阿里云 DashScope API Key（用于 Qwen 大模型、Embedding、Rerank、多模态服务）
DASHSCOPE_API_KEY="sk-your-dashscope-api-key"

# 必需 - JWT 密钥（需与 Java 后端 application-dev.yml 中的 shared-jwt-secret 保持一致）
SECRET_KEY="your-jwt-secret-key"

# 可选 - DeepSeek API Key（备用 LLM 服务）
DEEPSEEK-API-KEY="sk-your-deepseek-api-key"

# 可选 - 课程 PDF 文档目录（默认使用 model/data/documents/）
MEDICAL_DOCS_DIR="/path/to/your/pdf/documents"
```

后端服务环境变量通过 `application-dev.yml`（开发环境）或 `application-prod.yml`（生产环境）配置，主要包括：
- 数据库连接（`aiserver.datasource.*`）
- Redis 连接（`aiserver.redis.*`）
- AI 服务地址与 JWT 共享密钥（`aiserver.ai-api.*`）
- 阿里云 OSS 配置（`aiserver.alioss.*`）

### 第一步：初始化数据库

```bash
mysql -u root -p < backend/ai/MyServer/learningo-agents.sql
```

### 第二步：启动模型推理服务 (Model)

**方式一：使用快速启动脚本（推荐）**

```bash
cd model

# Windows
start.bat

# Linux / macOS
chmod +x start.sh && ./start.sh
```

启动脚本会自动检测 Python 环境、虚拟环境、依赖包和 `.env` 配置文件，一键完成环境准备与服务启动。

**方式二：手动启动**

```bash
cd model
pip install -r requirements.txt
python -m app.main
```

模型服务默认在 `http://localhost:8000` 启动，首次启动会自动加载 `data/documents/` 目录下的 12 篇脑卒中 PDF 指南并构建 ChromaDB 向量库。启动完成后可访问 `http://localhost:8000/docs` 查看完整 API 文档。

### 第三步：启动后端服务 (Backend)

使用 IDE（如 IntelliJ IDEA）运行 `MyServerApplication.java`，或者使用 Maven 编译启动：

```bash
cd backend/ai/MyServer
mvn spring-boot:run
```

后端服务默认在 `http://localhost:8080` 启动。

### 第四步：启动前端服务 (Frontend)

```bash
cd frontend
npm install
npm run dev
```

前端默认在 `http://localhost:5173` 启动，并自动代理请求至后端。

---

## 开源项目与工具声明

| 项目/工具 | 用途 | 协议 |
| --- | --- | --- |
| LangChain & LangGraph | 多智能体编排框架（StateGraph 构建 + astream_events 流式输出） | MIT |
| FastAPI | Python 异步 Web 框架（SSE 流式响应 + lifespan 生命周期管理） | MIT |
| ChromaDB | 向量数据库（持久化存储 + DashScope Embedding 索引） | Apache 2.0 |
| Qwen（通义千问） | 大语言模型（Max/Plus/Turbo 三级模型 + qwen-vl-max 多模态） | 阿里云协议 |
| DashScope Embedding | 文本向量化（text-embedding-v2，25 条/批次） | 阿里云协议 |
| gte-rerank | 语义重排模型（4 模型容灾切换） | Apache 2.0 |
| Vue 3 | 前端框架 | MIT |
| Spring Boot 3 | 后端框架（WebFlux 响应式 + Security 安全控制） | Apache 2.0 |
| MyBatis-Plus | ORM 框架 | Apache 2.0 |
| Redisson | 分布式锁与限流 | Apache 2.0 |
| 阿里云 OSS | 对象存储服务 | 阿里云协议 |
| 阿里云百炼平台 | 大模型 API 服务 | 阿里云协议 |
| PubMed E-utilities | 国际医学文献检索 API（NCBI esearch + efetch） | NLM 公共 API |

> **AI Coding 工具说明**：本项目开发过程中使用了 AI 辅助编程工具进行代码生成与优化，所有 AI 生成内容均经过人工审核与测试验证。

---

## 免责声明

*本系统属于高等教育个性化学习辅助系统，系统生成的学习资源与建议仅供参考，不替代教师的专业教学判断。学生应结合自身实际情况与教师指导进行学习规划。*