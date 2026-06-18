# 模型层完整学习文档

> 本文档涵盖：文件架构、阅读顺序、数据模型详解、节点详解、LangGraph 机制详解

---

# 第一章：文件架构与阅读指南

## 1.1 模型层整体架构

```
model/
├── app/
│   ├── main.py                          ← ① 入口：FastAPI 应用
│   ├── config/                          ← ② 配置层
│   │   ├── config_loader.py               - PromptManager / ReportTemplateManager / 各种Manager
│   │   ├── prompts.yaml                   - 提示词模板
│   │   ├── report_templates.yaml          - 报告模板
│   │   ├── expert_config.yaml             - 专家配置
│   │   ├── limits_config.yaml             - 参数限制配置
│   │   └── rules_config.yaml              - 规则配置
│   ├── agents/                          ← ③ 核心智能体层（重点）
│   │   ├── assistant.py                   - LearningAssistant（快速通道）
│   │   ├── constants.py                   - 共享常量
│   │   ├── core/                          - 核心基础设施
│   │   │   ├── schema.py                  - LearningState / LearningContext 数据模型
│   │   │   ├── result.py                  - Result / RetrievalResult 统一结果封装
│   │   │   ├── exceptions.py              - 自定义异常体系
│   │   │   └── decorators.py              - retry / timeit 装饰器
│   │   ├── orchestrators/                 - 编排层（LangGraph 工作流）
│   │   │   ├── clinical_graph.py          - LearningGraphBuilder（图构建器）
│   │   │   ├── qwen_agent.py             - LearningAgent（顶层智能体，对外入口）
│   │   │   └── nodes/                     - 工作流节点
│   │   │       ├── base.py                - BaseNode 抽象基类
│   │   │       ├── intent_node.py         - 意图识别节点
│   │   │       ├── analysis_node.py       - 学习需求分析节点
│   │   │       ├── retrieve_node.py       - 证据检索节点
│   │   │       ├── reason_node.py         - 多智能体推理节点
│   │   │       ├── validate_node.py       - 质量校验节点
│   │   │       └── report_node.py         - 报告生成节点
│   │   ├── pipelines/                     - 管道层
│   │   │   └── rag_pipeline.py            - RAGPipeline（查询→检索→合成）
│   │   ├── services/                      - 服务层
│   │   │   ├── query_service.py           - QueryGenerationService（生成检索查询）
│   │   │   ├── retrieval_service.py       - EvidenceRetrievalService（证据检索）
│   │   │   └── synthesis_service.py       - EvidenceSynthesisService（证据合成）
│   │   ├── infra/                         - 基础设施层
│   │   │   ├── base_reranker.py           - BaseReranker 抽象基类
│   │   │   └── reranker.py                - DashScopeReranker 实现
│   │   ├── bailian/                       - 百炼平台集成
│   │   │   └── health_risk_analyzer.py    - LearningRiskAnalyzer
│   │   ├── schemas/                       - 数据结构
│   │   │   └── retrieval.py               - RerankResult 等
│   │   └── utils/                         - 工具层
│   │       ├── llm_helper.py              - LLMHelper（同步/异步调用）
│   │       ├── json_parser.py             - JSON 解析
│   │       ├── text_utils.py              - 文本处理
│   │       └── retry.py                   - 重试工具
│   ├── rag/                              ← ④ RAG 检索层
│   │   ├── __init__.py
│   │   ├── data_loader.py                 - PDF 加载 / 文本清洗 / 文档切分
│   │   ├── retrievers.py                  - 向量库构建 / HybridRetriever / UnifiedSearchEngine
│   │   ├── retrieve.py                    - 对外统一导出
│   │   └── qa_generator.py                - QA 对生成
│   ├── services/                         ← ⑤ 外部服务层
│   │   ├── pubmed_service.py              - PubMed 文献检索
│   │   └── vision_service.py              - 多模态影像分析
│   ├── utils/                            ← ⑥ 通用工具层
│   │   ├── context_summary.py             - 对话摘要
│   │   ├── error_codes.py                 - 错误码
│   │   ├── naming_model.py                - 命名模型
│   │   ├── task_manager.py                - 异步任务管理
│   │   ├── token_aggregator.py            - Token 聚合
│   │   └── download_models.py             - 模型下载
│   └── evaluation/                       ← ⑦ 评估层（空）
│       └── __init__.py
├── data/                                 ← 数据目录（PDF 指南文档）
├── tests/                                ← 测试目录
└── requirements.txt
```

## 1.2 推荐阅读顺序

### 第一阶段：理解入口和数据模型

| 顺序 | 文件 | 理由 |
|------|------|------|
| 1 | `app/main.py` | **FastAPI 入口**，所有 API 路由、请求/响应模型、资源初始化都在这里，是理解系统全貌的起点 |
| 2 | `app/agents/core/schema.py` | **核心数据模型** `LearningState` 和 `LearningContext`，整个 LangGraph 工作流的状态流转都依赖它 |
| 3 | `app/agents/constants.py` | **共享常量**，理解系统的参数限制和关键词分类 |

### 第二阶段：理解 LangGraph 工作流（核心）

| 顺序 | 文件 | 理由 |
|------|------|------|
| 4 | `app/agents/orchestrators/nodes/base.py` | **节点抽象基类**，只有10行，理解节点接口约定 |
| 5 | `app/agents/orchestrators/nodes/intent_node.py` | **意图识别节点**，工作流第一个节点，决定请求路由方向 |
| 6 | `app/agents/orchestrators/nodes/analysis_node.py` | **分析节点**，解析学习需求 |
| 7 | `app/agents/orchestrators/nodes/retrieve_node.py` | **检索节点**，调用 RAG 检索证据 |
| 8 | `app/agents/orchestrators/nodes/reason_node.py` | **推理节点**，多智能体辩论推理（核心逻辑） |
| 9 | `app/agents/orchestrators/nodes/validate_node.py` | **校验节点**，质量把关和反思循环 |
| 10 | `app/agents/orchestrators/nodes/report_node.py` | **报告节点**，最终输出 |
| 11 | `app/agents/orchestrators/clinical_graph.py` | **图构建器**，把所有节点组装成 LangGraph 状态图，定义路由和边 |
| 12 | `app/agents/orchestrators/qwen_agent.py` | **顶层智能体** `LearningAgent`，组装所有节点并暴露 `run_learning_reasoning()` 流式接口 |

### 第三阶段：理解 RAG 管道和服务层

| 顺序 | 文件 | 理由 |
|------|------|------|
| 13 | `app/agents/services/query_service.py` | 查询生成服务 |
| 14 | `app/agents/services/retrieval_service.py` | 证据检索服务 |
| 15 | `app/agents/services/synthesis_service.py` | 证据合成服务 |
| 16 | `app/agents/pipelines/rag_pipeline.py` | RAG 管道，串联上面三个服务 |
| 17 | `app/agents/assistant.py` | `LearningAssistant`，快速通道（不走完整工作流，直接检索+回答） |

### 第四阶段：理解底层基础设施

| 顺序 | 文件 | 理由 |
|------|------|------|
| 18 | `app/agents/core/result.py` | 统一结果封装 `Result<T>` |
| 19 | `app/agents/core/exceptions.py` | 异常体系 |
| 20 | `app/agents/core/decorators.py` | retry / timeit 装饰器 |
| 21 | `app/agents/infra/base_reranker.py` | 重排序抽象基类 |
| 22 | `app/agents/infra/reranker.py` | DashScope 重排序实现 |
| 23 | `app/agents/utils/llm_helper.py` | LLM 调用辅助 |
| 24 | `app/config/config_loader.py` | 配置管理器 |

### 第五阶段：理解 RAG 检索和外部服务

| 顺序 | 文件 | 理由 |
|------|------|------|
| 25 | `app/rag/data_loader.py` | PDF 文档加载和切分 |
| 26 | `app/rag/retrievers.py` | 向量库构建、混合检索器、统一搜索引擎 |
| 27 | `app/services/pubmed_service.py` | PubMed 文献检索 |
| 28 | `app/services/vision_service.py` | 多模态影像分析 |
| 29 | `app/agents/bailian/health_risk_analyzer.py` | 学习风险评估（百炼平台） |

---

# 第二章：核心数据模型详解

## 2.1 LearningContext — 学习上下文（Pydantic BaseModel）

这是一个**结构化的学生画像模型**，用于描述一个学生的完整学习状态：

```python
class LearningContext(BaseModel):
    基本信息: Dict = Field(default_factory=dict)       # 专业、年级、当前课程等
    学习需求: str = ""                                  # 学生表达的核心需求
    主要问题: List[str] = Field(default_factory=list)   # 学生面临的学习问题列表
    知识水平评估: Dict = Field(default_factory=dict)    # 各维度知识掌握程度
    认知风格: str = ""                                  # 视觉型/听觉型/动手型等
    学习目标: List[str] = Field(default_factory=list)   # 短期/长期学习目标
    易错点: List[str] = Field(default_factory=list)     # 常犯错误
    学习节奏: Dict = Field(default_factory=dict)        # 学习速度、时间安排偏好
    资源偏好: List[str] = Field(default_factory=list)   # 视频/文档/练习等偏好
```

它对应 `analysis_node.py` 中 `profile` 意图类型的 `structured_context` 模板结构，是分析节点输出的结构化画像数据。

## 2.2 LearningState — LangGraph 工作流状态（TypedDict）

这是整个系统的**核心状态对象**，在 LangGraph 的各个节点之间流转。每个节点读取部分字段、写入部分字段，形成完整的数据流。

```python
class LearningState(TypedDict):
    case_text: str               # 用户原始输入
    all_info: str                # 历史对话上下文
    report_mode: str             # 报告模板模式
    intent_type: str             # 意图分类结果
    context: Dict                # 结构化分析上下文
    learning_questions: List[str]# 检索用的子问题列表
    key_risks: List[str]         # 关键风险识别
    complexity: str              # 复杂度等级
    difficulty_score: float      # 难度评分(0~1)
    evidence: str                # RAG检索到的证据文本
    proposal: str                # 多专家综合提案
    critique: str                # 多专家批判意见
    user_questions: List[str]    # 用户明确提出的问题
    report: str                  # 最终输出报告
    expert_advices: Dict         # 各专家原始建议
    validation_passed: bool      # 校验是否通过
    validation_feedback: str     # 驳回理由/修正指引
    reflection_count: int        # 反思次数
    agent_weights: Dict          # 退火后的专家权重
    rejection_categories: List[str]  # 驳回原因分类
    debate_history: List[Dict]   # 辩论历史记录
    active_experts: List[str]    # 本轮参与的专家列表
    motivational_feedback: str   # 学习激励反馈
    profile_summary: str         # 学生画像摘要
```

### 状态字段与节点读写关系

| 字段名 | 类型 | 写入节点 | 读取节点 | 含义 |
|--------|------|---------|---------|------|
| `case_text` | str | 初始化(qwen_agent) | intent, analysis | 用户原始输入文本 |
| `all_info` | str | 初始化 | analysis, reason | 历史对话上下文 |
| `report_mode` | str | 初始化 | report | 报告模板模式 |
| `profile_summary` | str | 初始化 | reason | 学生画像摘要 |
| `intent_type` | str | intent | clinical_graph(路由决策) | 意图分类结果 |
| `difficulty_score` | float | intent | reason | 难度评分(0~1) |
| `context` | Dict | analysis | report | 结构化分析上下文 |
| `learning_questions` | List[str] | analysis | retrieve | 检索用的子问题列表 |
| `key_risks` | List[str] | analysis | — | 关键风险识别 |
| `complexity` | str | analysis | — | 复杂度等级 |
| `user_questions` | List[str] | analysis | report | 用户明确提出的问题 |
| `evidence` | str | retrieve | reason, report | RAG检索到的证据文本 |
| `proposal` | str | reason | validate, report | 多专家综合提案 |
| `critique` | str | reason | validate, report | 多专家批判意见 |
| `active_experts` | List[str] | reason | validate | 本轮参与的专家列表 |
| `debate_history` | List[Dict] | reason | reason | 辩论历史记录 |
| `motivational_feedback` | str | reason | report | 学习激励反馈 |
| `expert_advices` | Dict | reason | — | 各专家原始建议 |
| `validation_passed` | bool | validate | clinical_graph(路由决策) | 校验是否通过 |
| `validation_feedback` | str | validate | reason | 驳回理由/修正指引 |
| `reflection_count` | int | validate | clinical_graph(路由决策) | 反思次数 |
| `agent_weights` | Dict | validate | reason | 退火后的专家权重 |
| `rejection_categories` | List[str] | validate | reason | 驳回原因分类 |
| `report` | str | report/knowledge/reject | — | 最终输出报告 |

### 为什么用 TypedDict 而不是 BaseModel？

LangGraph 的状态图要求状态是**可变的字典类型**，每个节点返回的字典会自动**合并（merge）**到当前状态中，而非替换。例如 `IntentNode` 只返回 `{"intent_type": ..., "difficulty_score": ...}`，其他字段保持不变。`TypedDict` 只做类型提示，不阻止运行时的字典操作，正好满足这个需求。

---

# 第三章：节点详解（小白版）

> 把整个系统想象成一家**学习咨询公司**，每个节点就是公司里的一个部门，用户的问题就像一个"工单"，依次经过各部门处理。

## 3.1 IntentNode — 前台接待员

**文件**：`app/agents/orchestrators/nodes/intent_node.py`

**角色**：公司前台，第一个接待客户的人。

**做什么**：客户一进来，前台先判断"这个人要干什么"，然后把客户引导到对应的部门。

前台会问 LLM（大语言模型）一个问题："这个用户输入属于哪一类？"

| 分类 | 含义 | 后续走向 |
|------|------|---------|
| `profile` | 要构建/更新学生画像 | → 进入分析流程 |
| `resource` | 要生成学习资源（文档、题目等） | → 进入分析流程 |
| `tutor` | 要辅导答疑 | → 进入分析流程 |
| `assessment` | 要做学习评估 | → 进入分析流程 |
| `learning_path` | 要规划学习路径 | → 进入分析流程 |
| `knowledge` | 只是问个简单的通用知识问题 | → 直接回答，不走完整流程 |
| `irrelevant` | 跟学习完全无关 | → 拒绝 |

同时前台还会给这个请求打个"难度分"（0~1），后面决定派几位专家来处理。

**举例**：
- 客户说"帮我整理一下我的学习情况" → 前台说"这是画像需求，去分析师那里"
- 客户说"今天天气怎么样" → 前台说"这跟学习无关，请回"

**读写字段**：
- 读取：`case_text`
- 写入：`intent_type`, `difficulty_score`

---

## 3.2 AnalysisNode — 需求分析师

**文件**：`app/agents/orchestrators/nodes/analysis_node.py`

**角色**：需求分析师，把客户模糊的需求拆解成清晰的、可执行的任务。

**做什么**：前台把客户转过来后，分析师做三件事：

1. **结构化理解**：把客户说的话整理成结构化数据。比如客户说"我大二学计算机，数据结构学不好"，分析师会整理出：
   - 基本信息：大二、计算机专业
   - 学习需求：数据结构学习困难
   - 知识水平：基础薄弱

2. **生成检索问题**：把客户需求转化成适合去资料库搜索的问题。比如：
   - "数据结构常见易错点有哪些？"
   - "二叉树遍历方法教学"
   - "排序算法对比总结"

3. **识别关键风险**：标记最紧迫的问题，比如"该学生基础薄弱，容易放弃"。

**关键设计**：分析师会根据不同的意图类型（`profile`/`resource`/`tutor`等）使用**不同的分析模板**，就像医生看内科和外科用不同的检查单一样。

**读写字段**：
- 读取：`case_text`, `all_info`, `intent_type`
- 写入：`context`, `learning_questions`, `key_risks`, `complexity`, `user_questions`

---

## 3.3 RetrieveNode — 资料室检索员

**文件**：`app/agents/orchestrators/nodes/retrieve_node.py`

**角色**：资料室管理员，根据分析师给的检索问题，去知识库里找相关资料。

**做什么**：
- 拿到分析师生成的检索问题列表（如 `["数据结构易错点", "二叉树遍历方法"]`）
- 调用 `LearningAssistant` 的并行检索功能，同时搜索多个问题
- 把找到的所有资料合并成一段"证据文本"

**举例**：分析师说"去帮我找关于数据结构易错点和二叉树遍历的资料"，检索员就去书架上翻，把找到的相关章节都复印出来，整理成一叠资料交给专家们。

**代码非常简洁**，只有几行——因为实际的检索逻辑在 `LearningAssistant` 和 `RAGPipeline` 里。

**读写字段**：
- 读取：`learning_questions`
- 写入：`evidence`

---

## 3.4 ReasonNode — 专家会诊室（最核心、最复杂）

**文件**：`app/agents/orchestrators/nodes/reason_node.py`

**角色**：专家会诊，多个不同视角的专家一起讨论，给出综合意见。

**做什么**：这是整个系统最核心的节点，分三步走：

### 第一步：多专家并行推理

系统配置了多位"专家"（从 `expert_config.yaml` 读取），每位专家有不同的专业视角，比如：
- 知识诊断专家：分析知识薄弱点
- 学习方法专家：建议学习策略
- 学习激励专家：给出激励建议

每位专家**同时**（并行）看同一份资料，各自给出独立意见。难度越高，参与的专家越多。

### 第二步：辩论-仲裁（可选）

如果启用了辩论模式（`debate_enabled`），专家们不是各说各的，而是会**互相反驳**：

```
第1轮：专家A说"应该先补基础"，专家B说"应该直接做题"
第2轮：专家A反驳B"基础不牢做题没意义"，专家B反驳A"光看理论容易忘"
...
最后：仲裁专家出场，综合所有辩论，做出裁决
```

### 第三步：综合汇总

一位"教学总监"把所有专家意见（以及仲裁裁决）汇总成两份文档：
- **Proposal（提案）**：综合建议方案
- **Critique（批判）**：方案中可能存在的问题和风险

**反思模式**：如果这是被质检部退回来的（`validation_feedback` 不为空），专家们会看到之前的驳回理由，调整自己的意见。同时被驳回的专家权重会降低（退火策略），就像"上次你说错了，这次你的意见权重降低"。

**读写字段**：
- 读取：`case_text`, `all_info`, `evidence`, `intent_type`, `difficulty_score`, `validation_feedback`, `agent_weights`, `reflection_count`, `profile_summary`, `debate_history`
- 写入：`proposal`, `critique`, `active_experts`, `debate_history`, `motivational_feedback`, `expert_advices`

---

## 3.5 ValidateNode — 质检部

**文件**：`app/agents/orchestrators/nodes/validate_node.py`

**角色**：质检员，检查专家们的方案有没有严重问题。

**做什么**：两道检查关卡：

### 第一关：规则引擎检查

用预设的规则快速扫描。比如"方案中不能出现某些绝对性表述"、"不能推荐超出学生水平的资源"等。这是**确定性的规则匹配**，速度快。

### 第二关：LLM 反思检查

让另一个 LLM 扮演"严格审查员"，仔细阅读方案，判断有没有：
- 事实错误
- 逻辑矛盾
- 个性化不足
- 违背教育原则

### 三种检查结果

| 结果 | 含义 | 后续 |
|------|------|------|
| ✅ PASS | 没问题 | → 进入报告生成 |
| 🔄 RETRY | 有问题，但还能改 | → 退回 ReasonNode 重新推理 |
| ❌ FAIL | 有问题，且反思次数已用完 | → 强制进入报告生成（加警告） |

**退火策略**：每次驳回，出问题的专家权重会乘以一个衰减因子（比如 0.7），这样下一轮推理时，经常犯错的专家影响力越来越小，就像金属退火一样逐渐"冷静"。

**读写字段**：
- 读取：`proposal`, `case_text`, `active_experts`, `agent_weights`, `rejection_categories`
- 写入：`validation_passed`, `validation_feedback`, `reflection_count`, `agent_weights`, `rejection_categories`

---

## 3.6 ReportNode — 报告生成部

**文件**：`app/agents/orchestrators/nodes/report_node.py`

**角色**：报告撰写员，把专家方案整理成用户看得懂的最终报告。

**做什么**：

1. **选择报告模板**：根据 `report_mode` 选择不同的报告格式
2. **填充模板**：把上下文、证据、提案、批判等填入模板
3. **添加附加信息**：
   - 如果质检没通过 → 加上"⚠️ 质量警告"
   - 如果有激励反馈 → 加上"💡 学习激励"
4. **调用 LLM 生成最终报告**：用流式输出，用户可以逐字看到报告生成

**特殊情况**：如果用户明确提出了一组问题（`user_questions` 不为空），就跳过报告模板，直接把专家提案作为答案返回——因为用户要的是直接回答，不是长篇报告。

**读写字段**：
- 读取：`context`, `all_info`, `evidence`, `proposal`, `critique`, `validation_passed`, `validation_feedback`, `motivational_feedback`, `report_mode`, `user_questions`
- 写入：`report`

---

## 3.7 两个快捷节点

在 `clinical_graph.py` 中还定义了两个不走完整流程的快捷节点：

| 节点 | 触发条件 | 做什么 |
|------|---------|--------|
| `_reject_node` | 前台判断为 `irrelevant` | 直接返回"请提供教育学习相关的查询" |
| `_knowledge_node` | 前台判断为 `knowledge` | 直接让 LLM 回答通用知识问题，不需要检索和专家推理 |

---

## 3.8 完整流程示例

用一个具体例子走一遍：

```
用户输入："我是大二计算机专业的学生，数据结构学得很差，
          特别是树和图的部分，有什么好的学习方法吗？"

📍 IntentNode（前台）
  → 判断：这是 tutor（辅导答疑）类型，难度 0.6

📍 AnalysisNode（分析师）
  → 结构化：专业=计算机，薄弱点=树和图，需求=学习方法
  → 生成检索问题：["数据结构树图学习方法", "图论入门教学策略"]
  → 关键风险：基础薄弱可能导致后续课程困难

📍 RetrieveNode（检索员）
  → 去知识库搜索，找到3段相关教学资料

📍 ReasonNode（专家会诊）
  → 知识诊断专家："该学生树和图的基础概念可能没理解透"
  → 学习方法专家："建议从可视化工具入手，先理解再刷题"
  → 学习激励专家："数据结构确实难，但掌握后对就业很有帮助"
  → 综合提案：从可视化入手 → 理解核心概念 → 逐步刷题巩固
  → 批判意见：需注意不要推荐过难的题目，避免打击信心

📍 ValidateNode（质检）
  → 规则检查：通过 ✅
  → LLM审查：通过 ✅

📍 ReportNode（报告生成）
  → 用模板生成一份完整的学习辅导报告，流式输出给用户
```

---

# 第四章：LangGraph 机制详解

## 4.1 LangGraph 是什么？

LangGraph 是一个**状态图框架**，用来构建多步骤的 AI 工作流。你可以把它理解为：

> **一张流程图**，图上有"节点"（做事的地方）和"边"（流转的方向），数据像水一样沿着边从一个节点流向下一个节点，每经过一个节点，数据就被处理一次。

核心思想就三个：**状态（State）、节点（Node）、边（Edge）**。

## 4.2 状态（State）— 水管里的水

状态就是在节点之间流动的数据。在我们的项目中就是 `LearningState`。

**关键机制**：LangGraph 的状态是**累积合并**的，不是替换。每个节点只需要返回它想修改的字段，LangGraph 会自动把这些字段合并到当前状态里，其他字段保持不变。

比如 `IntentNode` 只返回：

```python
return {"intent_type": "tutor", "difficulty_score": 0.6}
```

LangGraph 会自动把这个结果合并进状态，`case_text`、`all_info` 等其他字段原样保留。

## 4.3 节点（Node）— 水管上的处理站

节点就是流程图上的**处理单元**，每个节点接收当前状态，做自己的事情，然后返回要更新的状态字段。

### 在项目中怎么定义节点的？

看 `clinical_graph.py` 中的 `build()` 方法：

```python
def build(self):
    graph = StateGraph(LearningState)          # 创建一张图，指定状态类型

    graph.add_node("intent", self.intent_node.run)        # 注册节点
    graph.add_node("reject", self._reject_node)
    graph.add_node("knowledge_answer", self._knowledge_node)
    graph.add_node("analysis", self.analysis_node.run)
    graph.add_node("retrieve", self.retrieve_node.run)
    graph.add_node("reason", self.reason_node.run)
    graph.add_node("validate", self.validate_node.run)
    graph.add_node("generate_report", self.report_node.run)
```

`add_node(名字, 函数)` 做了两件事：
1. 在图上放一个"处理站"，给它起个名字
2. 指定这个处理站要执行的函数

**节点函数的签名约定**：接收 `state: LearningState`，返回 `Dict`（只包含要更新的字段）。

## 4.4 边（Edge）— 连接水管的管道

边定义了数据从一个节点流向下一个节点的**方向和条件**。项目里有三种边：

### ① 固定边 — 直连

```python
graph.add_edge("analysis", "retrieve")    # analysis 完成后，一定去 retrieve
graph.add_edge("retrieve", "reason")      # retrieve 完成后，一定去 reason
graph.add_edge("generate_report", END)    # 报告生成后，流程结束
```

就像水管直连，没有分叉，水只能往一个方向流。

### ② 条件边 — 分叉路口

```python
graph.add_conditional_edges(
    "intent",                    # 从 intent 节点出发
    self._route_intent,          # 用这个函数决定走哪条路
    {
        "irrelevant": "reject",
        "knowledge": "knowledge_answer",
        "profile": "analysis",
        "resource": "analysis",
        "tutor": "analysis",
        ...
    }
)
```

条件边就像**红绿灯路口**：`_route_intent` 函数读取状态中的 `intent_type`，返回一个字符串（如 `"tutor"`），LangGraph 根据这个字符串查映射表，决定下一步去哪个节点。

```python
def _route_intent(self, state: LearningState) -> str:
    t = state['intent_type']
    if t in {"profile", "resource", "tutor", ...}:
        return t
    return "irrelevant"
```

### ③ 反思循环边 — 环路

```python
graph.add_conditional_edges(
    "validate",                   # 从 validate 节点出发
    self._route_validation,       # 用这个函数决定走哪条路
    {
        "pass": "generate_report",   # 通过 → 生成报告
        "retry": "reason",           # 驳回 → 回到推理节点重新来
        "fail": "generate_report"    # 超过反思次数 → 强制生成报告
    }
)
```

这是最有趣的边——它形成了一个**环路**（validate → reason → validate → ...），让系统可以"反思"和"自我修正"。

## 4.5 入口点 — 水从哪里进来

```python
graph.set_entry_point("intent")   # 所有请求都从 intent 节点开始
```

## 4.6 编译 — 把图纸变成可运行的程序

```python
return graph.compile(checkpointer=self.checkpointer)
```

`compile()` 把定义好的图"编译"成一个可执行的对象。就像把建筑设计图纸变成真正可以住的房子。`checkpointer` 是可选的，用来保存中间状态，支持断点续跑。

## 4.7 节点在 LangGraph 中的完整运行机制

用一个完整的执行过程来说明：

```
步骤1: 用户调用 graph.astream_events(initial_state)

步骤2: LangGraph 把 initial_state 送到入口节点 "intent"
       → 执行 intent_node.run(state)
       → 返回 {"intent_type": "tutor", "difficulty_score": 0.6}
       → LangGraph 自动合并: state["intent_type"] = "tutor"
                              state["difficulty_score"] = 0.6

步骤3: LangGraph 调用 _route_intent(state) → 返回 "tutor"
       → 查映射表: "tutor" → "analysis"
       → 把更新后的 state 送到 "analysis" 节点

步骤4: 执行 analysis_node.run(state)
       → 返回 {"context": {...}, "learning_questions": [...], ...}
       → 自动合并到 state

步骤5: 固定边 analysis → retrieve
       → 执行 retrieve_node.run(state)
       → 返回 {"evidence": "..."}

步骤6: 固定边 retrieve → reason
       → 执行 reason_node.run(state)
       → 返回 {"proposal": "...", "critique": "...", ...}

步骤7: 固定边 reason → validate
       → 执行 validate_node.run(state)
       → 假设返回 {"validation_passed": False, "validation_feedback": "..."}

步骤8: 条件边 _route_validation(state) → 返回 "retry"
       → 回到 "reason" 节点（反思循环！）

步骤9: 再次执行 reason_node.run(state)
       → 这次 state 中有 validation_feedback，专家会据此修正
       → 返回新的 {"proposal": "...", "critique": "..."}

步骤10: reason → validate → _route_validation → "pass"
        → 进入 "generate_report"

步骤11: 执行 report_node.run(state) → 返回 {"report": "最终报告..."}

步骤12: generate_report → END，流程结束
```

## 4.8 总结：节点在 LangGraph 中的本质作用

| 概念 | 比喻 | 在项目中的作用 |
|------|------|---------------|
| **State** | 流水线上的产品 | `LearningState`，所有节点共享的数据 |
| **Node** | 流水线上的工位 | 每个节点做一件事（识别意图/分析/检索/推理/校验/生成报告） |
| **Edge** | 流水线的传送带 | 决定产品从一个工位送到哪个工位 |
| **条件边** | 分拣员 | 根据产品特征决定走哪条线 |
| **循环边** | 返工通道 | 质检不合格就送回重做 |
| **compile** | 开机 | 把图纸变成可运行的流水线 |

**节点最核心的设计原则**：每个节点只关心自己需要读的字段，只返回自己负责写的字段，互不干扰，LangGraph 负责合并。这就是为什么 `LearningState` 用 `TypedDict` 而不是 `BaseModel`——它需要是可变的、可部分更新的字典。

---

# 第五章：关键设计模式总结

## 5.1 系统核心运行流程图

```
用户请求 → main.py (FastAPI)
    ├── 简单问题 → LearningAssistant (快速通道: 检索+回答)
    └── 复杂问题 → LearningAgent (LangGraph 工作流)
                      │
                      ▼
                  IntentNode (意图识别)
                      │
              ┌───────┼───────┐
              ▼       ▼       ▼
           reject  knowledge  analysis
                              │
                              ▼
                        AnalysisNode (需求分析)
                              │
                              ▼
                        RetrieveNode (RAG检索)
                              │
                              ▼
                        ReasonNode (多智能体推理)
                              │
                              ▼
                        ValidateNode (质量校验) ←── 反思循环
                              │
                              ▼
                        ReportNode (报告生成)
```

## 5.2 设计模式一览

| 模式 | 体现 | 说明 |
|------|------|------|
| **LangGraph 状态图** | `LearningState` + 各节点 | 通过 TypedDict 在节点间传递状态，自动合并部分更新 |
| **管道模式** | `RAGPipeline` | 串联查询生成→证据检索→证据合成 |
| **策略模式** | `BaseNode` / `BaseReranker` | 抽象基类定义接口，具体实现可替换 |
| **配置外置** | `config_loader.py` + YAML 文件 | 提示词、报告模板、专家配置等全部 YAML 化 |
| **退火策略** | `ValidateNode._apply_annealing()` | 驳回时衰减专家权重，逐步"冷静" |
| **辩论-仲裁** | `ReasonNode._run_debate()` | 多专家辩论 + 仲裁智能体裁决 |
| **反思循环** | `validate → reason → validate` | 质检不通过时退回重做，最多 N 次 |