# LearnAgent Model / 多智能体个性化学习模型服务

> **基于 LangGraph 多智能体协同推理 + Hybrid RAG 的高等教育个性化学习模型推理层**

本模块是 LearnAgent 多智能体个性化学习系统的 **模型推理层**，以 FastAPI 异步框架为服务底座，融合 LangGraph 状态图编排、多智能体协同推理与混合检索增强生成（Hybrid RAG），实现了从意图识别到画像构建、资源生成、智能辅导、学习评估的完整推理闭环。

系统强调 **"证据先行、过程可解释、结果可验证"**——所有生成内容强制溯源至课程文献与页码，通过规则引擎 + LLM 反思的双重校验机制保障输出质量，并通过全链路 SSE 流式推送让 AI 推理过程透明可见。

---

## 🌟 核心亮点

### 1. LangGraph 状态图驱动的推理拓扑

基于 LangGraph `StateGraph` 构建完整的推理状态机，通过意图路由将不同类型的请求分发至对应的处理管道，支持条件分支、反思循环与检查点恢复：

```
用户输入 → Intent(意图分类) → 路由决策
    ├── irrelevant → Reject → END
    ├── knowledge → KnowledgeAnswer → END
    └── profile/resource/tutor/assessment/learning_path
         → Analysis(需求分析) → Retrieve(证据检索) → Reason(多智能体推理)
         → Validate(质量校验) ── pass → Report(报告生成) → END
                           ├─ retry → Reason(反思重推理)
                           └─ fail → Report → END
```

### 2. 证据驱动的 Hybrid RAG

- **双路混合检索**：DashScope Embedding（语义向量）+ BM25（专业术语精准匹配）并发检索
- **AI QA 自建引擎**：自动精读课程 PDF 并批量衍生高质量 Q&A 对（附带原文页码标签），大幅提升学习场景检索召回率
- **深度重排与溯源**：整合 DashScope gte-rerank 进行深度语境打分与证据压缩，生成内容强制进行文献名称与精准页码溯源

### 3. 多智能体矩阵协同推理

6 个专家角色智能体并行推理，模拟真实教育团队协作：

| 智能体 | 职责 |
| --- | --- |
| 画像对话智能体 | 引导式对话，收集学生特征信息 |
| 特征抽取智能体 | 从对话中自动抽取结构化画像维度 |
| 需求分析智能体 | 分析学习需求，拆解生成任务 |
| 文档撰写智能体 | 生成专业课程讲解文档 |
| 题目生成智能体 | 生成多种类型练习题目 |
| 质量审核智能体 | 审查资源学术准确性与内容安全 |

### 4. 双重校验与反思循环

- **规则引擎检查**：快速匹配质量规则（资源相关性、难度匹配、维度覆盖等），硬规则拦截
- **LLM 反思校验**：深层次教育逻辑审查，检查教学原则违反与常识错误
- **反思循环**：校验未通过时自动触发重新推理，最多支持 3 次反思（可配置）

### 5. 全链路 SSE 流式推送

从 Python Agent 异步生成器 → asyncio.Queue → FastAPI EventSourceResponse，实现 Thinking Step 推理过程透明化展示，避免长时间白屏等待。

---

## 🏗️ 技术栈

| 类别 | 技术 | 说明 |
| --- | --- | --- |
| Web 框架 | FastAPI 0.128 + Uvicorn | 高性能异步 Web 服务 |
| 智能体编排 | LangGraph 0.2 + LangChain 0.2 | 状态图驱动的多智能体推理 |
| 大语言模型 | Qwen-Max / Qwen-Plus / Qwen-Turbo | 阿里云百炼平台多级模型 |
| 向量检索 | ChromaDB 0.5 + DashScope Embedding | 语义向量检索 |
| 关键词检索 | BM25 (rank-bm25) | 专业术语精准匹配 |
| 重排模型 | DashScope gte-rerank | 深度语境重排与证据压缩 |
| PDF 解析 | pdfplumber + pypdf | 课程文档加载与分块 |
| 视觉分析 | DashScope MultiModalConversation | 图片识别与多模态分析 |
| 文献检索 | PubMed NCBI API | 学术文献外部补充检索 |
| 配置管理 | PyYAML + 动态配置加载器 | 专家角色/规则/参数/Prompt 模板 |
| 认证安全 | PyJWT | JWT Token 双向认证 |

---

## 📂 项目目录结构

```
model/
├── app/
│   ├── main.py                     # FastAPI 服务入口（路由 + 资源初始化）
│   │
│   ├── agents/                     # 多智能体核心模块
│   │   ├── orchestrators/          # LangGraph 编排层
│   │   │   ├── clinical_graph.py   # LearningGraphBuilder 状态图构建
│   │   │   ├── qwen_agent.py       # LearningAgent 主入口（流式推理）
│   │   │   └── nodes/              # 推理节点
│   │   │       ├── base.py         # BaseNode 节点基类
│   │   │       ├── intent_node.py  # 意图分类节点（7 种意图路由）
│   │   │       ├── analysis_node.py # 需求分析节点
│   │   │       ├── retrieve_node.py # 证据检索节点
│   │   │       ├── reason_node.py  # 多智能体并行推理节点
│   │   │       ├── validate_node.py # 质量校验节点（规则+反思）
│   │   │       └── report_node.py  # 报告生成节点
│   │   ├── pipelines/              # 处理管道
│   │   │   └── rag_pipeline.py     # RAG 检索-重排-合成管道
│   │   ├── services/               # 智能体服务
│   │   │   ├── query_service.py    # 查询生成服务
│   │   │   ├── retrieval_service.py # 证据检索服务
│   │   │   └── synthesis_service.py # 证据合成服务
│   │   ├── core/                   # 核心定义
│   │   │   ├── schema.py           # LearningState / LearningContext 数据模型
│   │   │   ├── decorators.py       # 装饰器工具
│   │   │   ├── exceptions.py       # 异常定义
│   │   │   └── result.py           # 结果封装
│   │   ├── infra/                  # 基础设施
│   │   │   ├── reranker.py         # DashScope gte-rerank 重排器
│   │   │   └── base_reranker.py    # 重排器基类
│   │   ├── schemas/                # 数据模式
│   │   │   └── retrieval.py        # RerankResult 检索结果模式
│   │   ├── utils/                  # 工具函数
│   │   │   ├── llm_helper.py       # LLM 调用辅助
│   │   │   ├── json_parser.py      # JSON 解析器
│   │   │   ├── retry.py            # 重试装饰器
│   │   │   └── text_utils.py       # 文本处理工具
│   │   ├── assistant.py            # LearningAssistant 学习助手
│   │   └── constants.py            # 常量定义
│   │
│   ├── rag/                        # RAG 模块
│   │   ├── retrievers.py           # 混合检索引擎（DashScope Embedding + ChromaDB + BM25）
│   │   ├── data_loader.py          # PDF 文档加载与递归分块
│   │   ├── qa_generator.py         # AI Batch QA 自动衍生引擎
│   │   └── retrieve.py             # 统一检索入口
│   │
│   ├── config/                     # YAML 配置中心
│   │   ├── config_loader.py        # 动态配置加载器（支持热更新）
│   │   ├── prompts.yaml            # Prompt 模板库
│   │   ├── expert_config.yaml      # 专家角色配置（6 个智能体角色）
│   │   ├── report_templates.yaml   # 报告模板（画像/资源/辅导/评估等）
│   │   ├── rules_config.yaml       # 校验规则配置（质量规则 + 反思参数）
│   │   └── limits_config.yaml      # 参数限制配置（子问题数/证据长度/关键词等）
│   │
│   ├── services/                   # 外部服务
│   │   ├── vision_service.py       # 视觉分析服务（DashScope 多模态）
│   │   └── pubmed_service.py       # PubMed 学术文献检索服务
│   │
│   ├── evaluation/                 # 评估模块
│   │
│   └── utils/                      # 通用工具
│       ├── context_summary.py      # 对话上下文摘要与 all_info 更新
│       ├── error_codes.py          # 错误码定义与错误事件构建
│       ├── token_aggregator.py     # Token 聚合器
│       ├── naming_model.py         # 对话命名模型（自动生成对话标题）
│       └── download_models.py      # 模型下载脚本
│
├── data/
│   └── documents/                  # 课程 PDF 文档库（系统启动时自动索引）
│
├── tests/                          # 自动化测试
│   ├── test_api_client.py          # API 客户端测试
│   ├── test_rag.py                 # RAG 功能测试
│   └── ...
│
├── requirements.txt                # Python 依赖清单
├── main.py                         # 启动入口
├── start.bat                       # Windows 一键启动脚本
├── start.sh                        # Linux/macOS 一键启动脚本
└── .env.example                    # 环境变量示例
```

---

## 🔄 系统核心链路流程

### 1. 请求接入与鉴权

前端发来学习请求（可能附带图片），Java 后端鉴权通过后建立 SSE 长连接，WebClient 异步调用本模型服务。

### 2. 意图识别与智能路由

Intent Node 利用 Qwen-Turbo 对输入进行意图分类，支持 7 种路由：

| 意图类型 | 路由目标 | 说明 |
| --- | --- | --- |
| `irrelevant` | Reject Node → END | 非教育学习相关，拒绝处理 |
| `knowledge` | KnowledgeAnswer → END | 通用教育知识询问，直接回答 |
| `profile` | 完整推理链 | 学习画像构建/更新 |
| `resource` | 完整推理链 | 个性化学习资源生成 |
| `tutor` | 完整推理链 | 智能辅导问答 |
| `assessment` | 完整推理链 | 学习效果评估 |
| `learning_path` | 完整推理链 | 学习路径规划 |

### 3. 学习需求结构化分析

Analysis Node 对输入进行结构化分析，提取关键学习要素：
- 学生基本信息（专业、年级、当前课程）
- 知识基础与薄弱环节
- 认知风格与资源偏好
- 学习目标与易错点模式

### 4. Hybrid RAG 证据检索

Retrieve Node 调用混合检索引擎从课程知识库中检索相关内容：
- **语义向量检索**：基于 DashScope text-embedding-v2 向量化 + ChromaDB 存储
- **关键词精准检索**：基于 BM25 算法匹配专业术语
- **深度重排**：gte-rerank 对混合结果进行深度语境打分与证据压缩
- **明确溯源**：每条证据附带来源文献名称与页码

### 5. 多智能体并行推理

Reason Node 汇集精准证据片段，驱动 6 个专家智能体并行推理：
- 画像对话智能体 → 特征抽取智能体 → 需求分析智能体
- 文档撰写智能体 → 题目生成智能体 → 质量审核智能体

各专家独立产出建议后，按优先级加权综合生成 Proposal 和 Critique。

### 6. 双重校验与反思循环

Validate Node 对推理结果进行双重校验：
- **规则引擎检查**：快速匹配质量规则（内容相关性、难度匹配、维度覆盖等）
- **LLM 反思校验**：深层次教育逻辑审查，检查教学原则违反
- **反思循环**：校验失败时自动触发 Reason Node 重新推理，最多 3 次

### 7. 报告生成与流式输出

Report Node 根据 `report_mode` 选择对应模板，生成结构化学习分析报告，通过 SSE 流式推送至前端。

### 8. 上下文摘要更新

流式推送完成后，后台启动 Context Summary 模型总结本次对话重点，更新 `all_info` 为多轮对话做铺垫。

---

## 🚀 快速接入

### 1. 环境准备与依赖安装

建议通过 Anaconda 新建虚拟环境：

```bash
conda create -n learn-agent python=3.11
conda activate learn-agent
pip install -r requirements.txt
```

> **注意**：PyTorch 需根据本机 CUDA 版本手动安装，未在 requirements.txt 中固定版本。

### 2. 环境变量配置

在 `model/` 根目录下创建 `.env` 文件（参考 `.env.example`）：

```env
# 必需：阿里云百炼 API 密钥（用于 Qwen 模型调用 + Embedding + Rerank）
DASHSCOPE_API_KEY=sk-您的阿里云百炼平台密钥

# 必需：JWT 认证密钥（须与后端 application-dev.yml 中 shared-jwt-secret 一致）
SECRET_KEY=自定义防越权的JWT随机字符串

# 可选：HuggingFace 镜像加速（国内网络建议配置）
HF_ENDPOINT=https://hf-mirror.com

# 可选：日志级别
# LOG_LEVEL=INFO
```

### 3. 课程知识库建设（RAG 底座）

将课程相关的 PDF 文件统一放入 `data/documents/` 文件夹。系统首次启动时会自动执行以下操作：

1. **自动递归分块（Recursive Chunking）**
   - 采用 512 字长配 128 字重叠的规则
   - 跨层级用段落、句号作为自然分割符
   - 将 PDF 切分为上千条文本块

2. **AI Batch QA 衍生**
   - 系统将文本块每 10 条打包发送给 Qwen-Turbo
   - 利用模型归纳能力"反向做题"，提取高质量 Q&A 对
   - 自动打上原文页码标签

3. **混合双索引编织（Dual-Indexing）**
   - 将"原生块" + "QA 对"进行向量化存入 ChromaDB
   - 在内存挂载 BM25 关键词索引
   - 构建完整的课程知识底座

### 4. 启动服务

```bash
# Windows
start.bat

# Linux/macOS
bash start.sh

# 或直接运行
python main.py
```

服务默认监听 `0.0.0.0:8000`。

启动时系统会按顺序初始化 7 个步骤：
1. 加载环境变量与配置
2. 初始化 LLM 模型（Qwen-Max / Qwen-Plus / Qwen-Turbo）
3. 构建 RAG 检索引擎（文档加载 → 分块 → QA 衍生 → 向量化 → BM25 索引）
4. 加载 Prompt 模板与报告模板
5. 初始化 LearningAssistant 学习助手
6. 初始化 LearningAgent 推理智能体（含 LangGraph 状态图构建）
7. 初始化视觉分析服务与命名模型

---

## 📝 核心 API

### 全局约定

- **Base URL**：`http://localhost:8000`
- **认证方式**：部分接口需携带 JWT Token（`token` 字段），与 Java 后端共享密钥双向认证
- **流式协议**：SSE（Server-Sent Events），Content-Type: `text/event-stream`

### SSE 流式事件格式

| 事件类型 | 说明 | data 结构 |
| --- | --- | --- |
| `init` | 连接建立，返回会话 ID | `{"type":"init","talkId":"123","newTalk":true}` |
| `node_start` | 智能体节点开始推理 | `{"type":"node_start","node":"profiler","label":"正在分析学习特征..."}` |
| `token` | 内容片段（增量） | `{"type":"token","content":"..."}` |
| `done` | 流式结束 | `{"type":"done","talkId":"123","title":"学习画像构建"}` |
| `error` | 错误 | `{"type":"error","code":"E2001","message":"..."}` |

### API 列表

#### 对话式学习画像

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/model/profile/conversation` | 对话式画像构建（SSE 流式） |
| GET | `/model/profile` | 获取当前学习画像 |
| PUT | `/model/profile/dimensions` | 手动更新画像维度 |
| GET | `/model/profile/conversations` | 获取画像对话列表 |
| GET | `/model/profile/conversation/{talk_id}` | 获取画像对话历史 |
| DELETE | `/model/profile/conversation/{talk_id}` | 删除画像对话 |

#### 多智能体协同资源生成

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/model/resources/generate` | 综合资源生成（SSE 流式） |
| POST | `/model/resources/generate/document` | 生成课程讲解文档（SSE 流式） |
| POST | `/model/resources/generate/mindmap` | 生成知识点思维导图（SSE 流式） |
| POST | `/model/resources/generate/quiz` | 生成练习题目（SSE 流式） |
| POST | `/model/resources/generate/reading` | 生成拓展阅读材料（SSE 流式） |
| POST | `/model/resources/generate/video-script` | 生成教学视频脚本（SSE 流式） |
| POST | `/model/resources/generate/code-practice` | 生成代码实操案例（SSE 流式） |
| GET | `/model/resources` | 获取资源列表（分页/筛选） |
| GET | `/model/resources/{id}` | 获取资源详情 |
| GET | `/model/resources/{id}/download` | 下载资源文件 |
| DELETE | `/model/resources/{id}` | 删除资源 |

#### 个性化学习路径

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/model/learning-path/generate` | 生成个性化学习路径 |
| GET | `/model/learning-path` | 获取学习路径列表 |
| GET | `/model/learning-path/{path_id}` | 获取学习路径详情 |
| PUT | `/model/learning-path/{path_id}/steps/{step_id}/progress` | 更新步骤进度 |
| POST | `/model/learning-path/recommend` | 个性化资源推送 |
| POST | `/model/learning-path/{path_id}/adjust` | 动态调整学习路径 |

#### 智能辅导

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/model/tutor/ask` | 智能辅导问答（SSE 流式，支持图片） |
| GET | `/model/tutor/conversations` | 获取辅导对话列表 |
| GET | `/model/tutor/conversation/{talk_id}` | 获取辅导对话历史 |
| DELETE | `/model/tutor/conversation/{talk_id}` | 删除辅导对话 |

#### 学习效果评估

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/model/evaluation/behavior` | 提交学习行为数据 |
| GET | `/model/evaluation/report` | 获取学习效果评估报告 |
| POST | `/model/evaluation/quiz/{quiz_id}/submit` | 提交练习答案 |
| GET | `/model/evaluation/mastery-heatmap` | 获取知识点掌握度热力图 |
| POST | `/model/evaluation/optimize` | 触发学习方案动态优化 |

#### 课程与知识库

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/model/courses` | 获取课程列表 |
| GET | `/model/courses/{id}/knowledge-tree` | 获取课程知识体系 |
| POST | `/model/pubmed/search` | 学术文献检索 |

#### 辅助接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/model/get_result` | 兼容旧版推理接口（SSE 流式） |
| POST | `/ai/analyze` | 学习风险快速分析 |
| POST | `/admin/reload_config` | 配置热更新 |
| GET | `/admin/report_modes` | 获取可用报告模式 |

---

## ⚙️ 配置文件说明

系统支持通过 YAML 配置文件灵活调整各项参数，并支持运行时热更新（`/admin/reload_config`）。

### `config/expert_config.yaml` — 专家角色配置

定义多智能体协作系统中的智能体角色、职责和系统提示词：

```yaml
experts:
  - role: "画像对话智能体"
    instruction: "请与学生进行自然对话，引导其表达学习背景..."
    system_prompt: "你是专业的学习画像构建顾问..."
    priority: 1

  - role: "特征抽取智能体"
    instruction: "请从对话内容中抽取结构化特征..."
    priority: 2

  # ... 共 6 个智能体角色

synthesis:
  prompt_template: |
    作为教学总监，请统筹以下各位智能体的意见...
  opinion_separator: "【{role}建议】{opinion}\n"
```

### `config/rules_config.yaml` — 校验规则配置

定义质量规则与反思参数：

```yaml
contraindication_rules:
  资源生成:
    - 内容与知识点无关
    - 难度与学生水平不匹配
    - 缺少实例或练习
  画像构建:
    - 未覆盖核心维度
    - 描述不具体
  学习路径:
    - 阶段划分不合理
    - 时间估算不可行

validation_settings:
  max_reflection_count: 3       # 最大反思次数
  enable_rule_engine: true       # 启用规则引擎
  enable_llm_reflection: true    # 启用 LLM 反思
```

### `config/limits_config.yaml` — 参数限制配置

控制推理过程中的各项参数上限：

```yaml
limits:
  max_sub_questions: 3           # 最大子问题数
  max_evidence_chars: 2000       # 最大证据字符数
  max_proposal_chars: 3000       # 最大方案字符数
  max_question_length: 5000      # 最大问题长度
  temperature: 0.7               # 生成温度

keywords:
  diagnostic: ["知识水平", "认知风格", "学习目标", "薄弱点", "画像"]
  treatment: ["资源生成", "辅导", "学习路径", "推荐", "个性化"]
  prognosis: ["学习效果", "掌握度", "进度", "评估", "优化"]
```

### `config/prompts.yaml` — Prompt 模板库

包含所有节点的系统提示词模板：
- `extract_context`：学习特征结构化提取
- `generate_questions`：关键学习问题生成
- `complexity_evaluation`：需求复杂度评估
- 以及各节点的推理提示词

### `config/report_templates.yaml` — 报告模板

定义不同 `report_mode` 下的结构化输出模板：
- `profile_build`：学习画像构建报告（8 个维度）
- `resource_generate`：个性化资源生成报告
- `tutor`：智能辅导报告
- 以及其他模式模板

---

## 🔧 扩展与定制

### 添加新的专家角色

编辑 `config/expert_config.yaml`：

```yaml
experts:
  - role: "思维导图生成智能体"
    instruction: "请基于知识点结构生成可视化思维导图..."
    system_prompt: "你是专业的知识可视化专家..."
    priority: 7
```

### 添加新的质量规则

编辑 `config/rules_config.yaml`：

```yaml
contraindication_rules:
  智能辅导:
    - 解答缺乏步骤化推导
    - 未结合学生认知风格
```

### 添加新的报告模式

在 `config/report_templates.yaml` 中添加新模板，系统会自动识别并在 `/admin/report_modes` 中列出。

### 运行时热更新

无需重启服务即可更新配置：

```bash
curl -X POST http://localhost:8000/admin/reload_config
```

---

## 🛡️ 安全与防幻觉机制

### 防幻觉策略
- **证据溯源**：所有生成内容强制引用来源文献与页码，杜绝无依据输出
- **双层校验**：Validate Node 规则引擎进行快速质量审查 + LLM 反思机制深层逻辑审查
- **反思循环**：校验未通过时自动触发重新推理，最多 3 次反思机会
- **意图拦截**：Intent Node 自动识别并拦截非教育学习相关输入

### 系统安全
- **JWT 双向认证**：与 Java 后端共享 JWT Secret，保障服务间调用安全
- **内容安全过滤**：自动检测并过滤敏感违规信息
- **学术规范检查**：确保生成内容无事实性错误

---

## 📊 性能优化建议

### 向量数据库优化
- 定期清理无效向量
- 调整 chunk 大小（当前 512）和重叠度（当前 128）
- 调整 `top_k_per_store` 参数控制每路检索返回数量

### 检索优化
- 调整向量检索和关键词检索的权重
- 优化 gte-rerank 的 top_n 阈值
- 启用/禁用 QA 生成（`enable_qa_generation`）

### 推理优化
- 调整专家数量和优先级权重
- 优化 Prompt 模板
- 调整 `max_reflection_count` 反思次数
- 调整 `temperature` 生成温度

---

## 🧪 测试

```bash
# 测试核心多智能体和 RAG 推理的流式能力
python tests/test_api_client.py

# 测试本地向量数据库召回水平
python tests/test_rag.py
```

---

## ⚠️ 免责声明

本系统属于高等教育个性化学习辅助系统，系统生成的学习资源与建议仅供参考，不替代教师的专业教学判断。学生应结合自身实际情况与教师指导进行学习规划。