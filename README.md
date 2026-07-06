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
| 🧠 **三群协同多智能体架构** | 基于 LangGraph StateGraph 构建 9 个专家智能体，YAML 配置驱动，支持动态编排与辩论-仲裁机制 |
| 🔍 **证据前置 Hybrid RAG** | 三阶漏斗检索：向量 + BM25 宽召回 → RRF 倒数排名融合粗排 → Reranker 4 模型自动切换精排；QA 生成扩充向量库；强制文献溯源 |
| 💾 **共享记忆系统** | 物理层（ChromaDB 向量存储）+ 逻辑层（信任加权投票共识）+ 元记忆过滤（四维信息熵计算），跨会话保留高价值洞察 |
| ⚡ **全栈响应式流式管道** | Java WebFlux + Python Asyncio 深度流式融合，AI 思考过程完全透明可视化，SSE 断线续传 |
| 🖼️ **医学多模态影像分析** | 10 类医学影像自动分类 + qwen-vl-max 结构化分析 + DICOM 元数据提取 + 多图对比 + Vision-RAG 桥接循证检索 |
| 📚 **循证医学文献检索** | PubMed E-utilities 文献检索（8 级证据等级排序）+ 本地知识库联合检索，图文联合理解 |
| 🛡️ **防幻觉与质量保障** | 双层校验（规则引擎 + LLM 反思）+ 动态退火修正 + 辩论-仲裁 + 71 条自动化测试用例 |
| 🩺 **医学 OCR 结构化提取** | 检验报告 + 处方 + 通用医学文档的 OCR 流式识别与结构化提取 |
| 💻 **代码执行与辅助** | 支持 Python 代码在线执行与 AI 编程辅助，适用于医学数据处理与算法教学场景 |
| 📊 **学习风险评估** | 百炼平台集成，自动评估学生学习风险等级并给出干预建议 |

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
│   ChromaDB · gte-rerank · qwen-vl-max · PubMed E-utilities      │
└──────────────────────────────────────────────────────────────────┘
```

### 全链路流式数据管道

```
 学生输入                                                    前端渲染
    │                                                          ▲
    ▼                                                          │
┌─────────┐  WebClient   ┌─────────┐  AsyncTaskManager  ┌──────────┐
│  Java   │ ──────────►  │ FastAPI │ ─────────────────► │ Learning │
│ 鉴权限流 │   异步调用     │  接收    │    创建任务         │  Agent   │
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

| 层级 | 核心技术 | 版本 | 职责 |
|:---|:---|:---|:---|
| **前端** | Vue · Vite · Pinia · marked · DOMPurify · pdfjs-dist | 3.5 · 7 · 3 · 17 · 3.3 · 3.11 | 流式渲染 · Markdown 展示 · 思考步骤折叠 · 学习路径可视化 · PDF 预览 |
| **后端** | Java · Spring Boot · WebFlux · Security · Redisson · MySQL · MyBatis-Plus | 21 · 3.3 · 6.1 · 6.3 · 3.27 · 8.0 · 3.5 | 响应式高并发 · JWT 认证 · 分布式限流 · WebClient 流式转发 · SSE 断线续传 |
| **模型** | Python · FastAPI · LangGraph · LangChain · Qwen · ChromaDB · gte-rerank · qwen-vl-max | 3.11 · 0.128 · 0.2.20 · 0.2.16 · Max/Plus/Turbo · 0.5 · — · — | 多智能体编排 · Hybrid RAG · 流式事件输出 · 多模态识别 · 文献检索 |

### Hybrid RAG 检索架构（三阶漏斗）

```
                         用户查询
                            │
                            ▼
            ┌───────────────────────────────┐
            │     第一阶：宽召回              │
            │  ┌──────────┐  ┌──────────┐   │
            │  │ 向量检索   │  │  BM25    │   │
            │  │ (语义相似) │  │ (关键词)  │   │
            │  │ top-20    │  │ top-20   │   │
            │  └──────────┘  └──────────┘   │
            │        最多 40 篇候选            │
            └───────────────┬───────────────┘
                            │
                            ▼
            ┌───────────────────────────────┐
            │     第二阶：RRF 粗排            │
            │  倒数排名融合                    │
            │  RRF(d) = 1/(60+Rankᵥ)        │
            │         + 1/(60+Rank_b)       │
            │  40 篇 → 20 篇候选              │
            └───────────────┬───────────────┘
                            │
                            ▼
            ┌───────────────────────────────┐
            │     第三阶：Reranker 精排       │
            │  4 模型自动切换容灾：            │
            │  qwen-rerank-v1               │
            │    → gte-rerank-v2            │
            │    → qwen-rerank              │
            │    → gte-rerank               │
            │  20 篇 → 3 篇最终结果           │
            └───────────────────────────────┘
```

| 阶段 | 技术 | 输入 → 输出 | 说明 |
|:---|:---|:---|:---|
| **宽召回** | DashScope Embedding (text-embedding-v2) + BM25 | 各 20 篇 → 最多 40 篇 | 语义向量 + 关键词双路并行召回，互补覆盖 |
| **粗排** | RRF (Reciprocal Rank Fusion) | 40 篇 → 20 篇 | 零成本零延迟，纯排名融合，避开 Dense/Sparse 分值区间差异 |
| **精排** | BGEReranker (DashScope ReRank API) | 20 篇 → 3 篇 | 深度语义重排序，4 模型自动切换容灾，失败时原始结果兜底 |

#### 文档预处理流程

| 步骤 | 实现 | 参数 |
|:---|:---|:---|
| PDF 加载 | PyPDFLoader | — |
| 文本清洗 | `clean_text()` 去除换行和多余空格 | — |
| 文档切分 | RecursiveCharacterTextSplitter | chunk_size=512, overlap=128 |
| QA 扩充 | QAGenerator (qwen-turbo) | 每 10 个 chunk 合并，生成 3-5 个 QA 对 |

#### 检索优化

| 特性 | 实现 |
|:---|:---|
| 检索缓存 | MD5(query+top_k) 哈希，TTL 300 秒 |
| 去重 | 基于 page_content 内容去重，同一内容取最高排名 |

---

## 📁 项目结构

```
learning-multi-agent-system/
├── frontend/                        # 前端交互层（Vue 3）
│   └── src/
│       ├── api/                     # API 请求（画像/资源/路径/辅导/评估/用户/医学影像）
│       ├── components/              # 组件（表单/头像/加载/对话/SVG图标/医学影像查看器/图片上传）
│       ├── views/                   # 页面（首页/登录/画像/资源/路径/辅导/评估）
│       ├── stores/                  # Pinia 状态管理（用户/主题）
│       ├── styles/                  # 样式（变量/过渡动画/公共样式）
│       ├── utils/                   # 工具（请求封装/图片压缩/流式暂停）
│       └── router/                  # 路由配置
│
├── backend/ai/MyServer/             # 后端服务层（Java Spring Boot）
│   └── src/main/java/com/it/
│       ├── controller/              # REST 控制器（15 个：画像/资源/路径/辅导/评估/医学影像/代码/监控/用户/课程/文档/题目/登录/上传/首页）
│       ├── service/                 # 业务逻辑（AI 流式/对话持久化/OSS）
│       ├── cache/                   # SSE 事件缓存
│       ├── config/                  # 配置（Security/WebClient/Redisson/OSS/Jackson/MyBatisPlus）
│       ├── pojo/                    # 实体类
│       ├── po/                      # 请求参数 & 响应视图对象
│       ├── mapper/                  # MyBatis-Plus Mapper
│       └── utils/                   # JWT/OSS/IP 工具
│
├── model/                           # 模型推理层（Python FastAPI）
│   └── app/
│       ├── main.py                  # FastAPI 入口 & API 路由（9 大模块 30+ 接口）
│       ├── agents/                  # 多智能体核心
│       │   ├── orchestrators/       # LangGraph 图定义 & 8 个节点实现
│       │   │   ├── clinical_graph.py  # LearningGraphBuilder（含 Vision 节点分支）
│       │   │   ├── qwen_agent.py      # LearningAgent（顶层智能体入口）
│       │   │   └── nodes/             # 工作流节点（intent/analysis/vision/retrieve/reason/validate/report）
│       │   ├── core/                # 状态模型 / 共享记忆 / 异常 / 结果封装 / 装饰器
│       │   ├── infra/               # Reranker 容灾
│       │   ├── services/            # 检索 / 查询 / 综合服务
│       │   ├── pipelines/           # RAG 管道
│       │   ├── bailian/             # 百炼平台集成（学习风险分析）
│       │   ├── schemas/             # 数据结构定义
│       │   └── utils/               # LLM / JSON / 重试 / 文本工具
│       ├── rag/                     # Hybrid RAG（向量 + BM25 / QA 生成 / 文档加载）
│       ├── services/                # 多模态影像 & PubMed 文献检索 & OCR
│       │   ├── medical_vision_service.py  # 10 类医学影像结构化分析
│       │   ├── medical_ocr_service.py     # 检验报告/处方/文档 OCR 提取
│       │   ├── vision_rag_bridge.py       # 影像发现 → PubMed/本地知识库桥接
│       │   ├── vision_service.py          # 通用视觉分析服务
│       │   └── pubmed_service.py          # PubMed 文献检索
│       ├── config/                  # YAML 配置（9 专家 / 规则 / 模板 / Prompt / 限额 / 共享记忆）
│       ├── evaluation/              # 评估模块
│       └── utils/                   # 任务管理 / 上下文摘要 / Token 聚合 / 错误码 / 命名模型 / 模型下载
│
├── tests/                           # 自动化测试脚本
│   ├── test_full_suite.py           # 全链路黑盒 + 并发压测（33 条用例，支持断点续跑）
│   └── test_medical_multimodal_e2e.py # 医学多模态端到端测试
│
├── model/tests/                     # 模型层单元测试（38 条用例）
│   ├── test_new_architecture.py     # 白盒路径覆盖测试
│   ├── test_shared_memory.py        # 共享记忆系统测试
│   ├── test_rag.py                  # RAG 检索功能测试
│   ├── test_api_client.py           # API 客户端集成测试
│   ├── test_migration.py            # 架构迁移验证测试
│   ├── test_medical_multimodal.py   # 医学多模态功能测试
│   ├── compare_chunking.py          # 分块策略对比测试
│   └── ...                          # 其他专项测试
│
└── docs/                            # 项目文档
    ├── 需求规格说明书.md              # SRS（10章，含UML图/算法伪代码）
    ├── 测试文档.md                    # V3.0（10章，黑白盒+并发+安全+容灾）
    ├── 数据库设计文档.md              # 14张表设计 + Mermaid ER图
    ├── 共享记忆系统优势总结.md         # 物理层+逻辑层+元记忆过滤优势分析
    ├── 多智能体个性化学习系统接口文档.md # 14模块完整API规范
    ├── API_SPEC.md                   # API 规范补充文档
    └── RAG技术学习文档.md             # RAG 检索技术学习文档
```

---

## 🤖 多智能体协同机制

### LangGraph 推理拓扑

```
                           用户输入
                              │
                    ┌──────── ▼ ────────┐
                    │   Intent Node     │
                    │ 意图分类 + 难度评分  │
                    └──────── ┬ ────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
         irrelevant        simple         complex
              │               │               │
              ▼               ▼               ▼
        ┌──────────┐   ┌──────────┐   ┌──────────────┐
        │  Reject  │   │Knowledge │   │  Analysis    │
        │  Node    │   │  Node    │   │  Node        │
        └──────────┘   └──────────┘   └──────┬───────┘
                                             │
                              ┌──────────────┼──────────────┐
                              │ 有医学影像     │              │
                              ▼              │              │
                    ┌──────────────┐         │              │
                    │  Vision Node │         │              │
                    │ 影像分析+证据  │         │              │
                    └──────┬───────┘         │              │
                           │                 │              │
                           └────────┬────────┘              │
                                    │                       │
                                    ▼                       │
                           ┌──────────────┐                │
                           │ 视觉证据合并   │                │
                           └──────┬───────┘                │
                                    │                       │
                                    ▼                       ▼
                           ┌──────────────┐   ┌──────────────┐
                           │  Retrieve    │   │  Retrieve    │
                           │ Node (含视觉) │   │    Node     │
                           └──────┬───────┘   └──────┬───────┘
                                    │                │
                                    └───────┬────────┘
                                            │
                                    ┌─────── ▼ ────────┐
                                    │   Reason Node     │
                                    │ 多智能体推理+辩论    │
                                    └─────── ┬ ────────┘
                                            │
                                    ┌─────── ▼ ────────┐
                                    │  Validate Node    │
                                    │ 质量校验+退火反思    │ ──↺ 校验失败
                                    └─────── ┬ ────────┘
                                            │
                                    ┌─────── ▼ ────────┐
                                    │   Report Node     │
                                    │ 报告生成+学习激励    │
                                    └───────────────────┘
```

### 智能体角色矩阵

| 角色 | 优先级 | 适用意图 | 职责 |
|:---|:---:|:---|:---|
| 画像对话智能体 | 1 | 全场景 | 引导式对话，收集学生信息 |
| 特征抽取智能体 | 2 | profile / assessment | 自动抽取 8 维度画像特征 |
| 需求分析智能体 | 3 | resource / tutor / learning_path | 分析需求，拆解任务 |
| 医学影像分析智能体 | 3.5 | tutor / resource / assessment / learning_path | 基于影像结构化发现提供影像-临床关联分析 |
| 文档撰写智能体 | 4 | resource | 生成专业课程讲解文档 |
| 题目生成智能体 | 5 | resource / assessment | 生成多类型练习题目 |
| 质量审核智能体 | 6 | resource / assessment / learning_path | 审核学术准确性与个性化匹配 |
| 学习激励智能体 | 7 | 全场景 | 情绪识别与激励反馈 |
| 仲裁智能体 | 8 | resource / tutor / assessment / learning_path | 依据证据链裁决辩论 |

### 辩论-仲裁机制

```
 ┌──────────────────────────────────────────────────────┐
 │  Step 1: 并行推理                                      │
 │  asyncio.gather → 各专家独立生成建议                    │
 ├──────────────────────────────────────────────────────┤
 │  Step 2: 多轮辩论                                      │
 │  各专家基于辩论上下文提出反驳或补充                        │
 │  （立场 + 论据 + 回应）                                 │
 ├──────────────────────────────────────────────────────┤
 │  Step 3: 仲裁裁决                                     │
 │  仲裁智能体 → ARBITRATION 结论 + REASONING 推理过程     │
 ├──────────────────────────────────────────────────────┤
 │  Step 4: 意见综合                                      │
 │  加权合并专家意见与仲裁裁决 → 最终提案                     │
 └──────────────────────────────────────────────────────┘
```

### 动态退火反思

校验失败时自动触发：

| 机制 | 说明 |
|:---|:---|
| **驳回分类** | 5 类：事实错误 / 逻辑矛盾 / 个性化不足 / 专业性错误 / 内容不完整 |
| **针对性修正** | 每类驳回生成对应修正指引 |
| **权重衰减** | 发言权重按 0.7 因子衰减（最低 0.2），避免无效重试 |
| **反思上限** | 最大反思 3 次，超限则强制输出 |

### 动态编排

根据意图类型和难度评分动态裁剪参与智能体：

| 意图 | 专家数 | 参与角色 |
|:---|:---:|:---|
| `profile` | 3 | 画像对话 + 特征抽取 + 学习激励 |
| `resource` | 7 | 需求分析 + 医学影像分析 + 文档撰写 + 题目生成 + 质量审核 + 学习激励 + 画像对话 |
| `tutor` | 5 | 画像对话 + 需求分析 + 医学影像分析 + 质量审核 + 学习激励 |
| `assessment` | 6 | 特征抽取 + 需求分析 + 医学影像分析 + 题目生成 + 质量审核 + 学习激励 |
| `learning_path` | 5 | 画像对话 + 需求分析 + 医学影像分析 + 质量审核 + 学习激励 |
| `knowledge` | 1 | 直接 LLM 知识问答（不走完整工作流） |

> 仲裁智能体在辩论启用且难度 ≥ 0.6 时自动加入。

### 共享记忆系统

多智能体间通过共享记忆系统实现跨会话知识保留与冲突消解：

```
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│  物理层       │  │  逻辑层       │  │  元记忆过滤       │
│  向量库存储    │  │  信任加权投票  │  │  信息熵计算       │
│              │  │              │  │                  │
│ SharedMemory │  │ Consensus    │  │ MetaMemory      │
│ Store        │  │ Engine       │  │ Filter          │
└──────────────┘  └──────────────┘  └──────────────────┘
```

| 层次 | 核心类 | 说明 |
|:---|:---|:---|
| **物理层** | `SharedMemoryStore` | ChromaDB 向量存储，语义级检索，三级降级容错 |
| **逻辑层** | `ConsensusEngine` + `AgentReputationStore` | 信誉加权投票共识，跨会话信誉持久化 |
| **元记忆过滤** | `MetaMemoryFilter` | 四维熵值评分（Shannon 熵 · 关键词密度 · Token 密度 · 长度），低熵高价值信息才持久化 |

数据流闭环：`retrieve_node` 读取共享记忆 → `reason_node` 共识投票 + 熵值过滤写入 → `validate_node` 信誉反馈更新

---

## 🎯 功能模块

| 模块 | 功能 | 关键特性 |
|:---|:---|:---|
| **对话式学习画像** | 自然语言对话自动抽取特征，构建 8 维度动态画像 | 知识基础 · 认知风格 · 学习目标 · 易错点 · 学习节奏 · 资源偏好 · 临床经验 · 情绪状态 |
| **多智能体资源生成** | 7 种个性化资源类型 | 课程讲解文档 · 思维导图 · 练习题目 · 拓展阅读 · 视频脚本 · 代码实操 · 综合批量生成 |
| **学习路径规划** | 根据画像生成 5-15 步学习路径 | 前置步骤依赖 · 精准资源推送 · 路径动态调整 · 步骤进度追踪 |
| **智能辅导** | 即时多模态答疑 | 文字解答 · 图片识别(qwen-vl-max) · 上下文感知 · 偏好回答形式 |
| **学习效果评估** | 5 维度评估 + 闭环优化 | 知识掌握度 · 学习效率 · 技能应用 · 学习一致性 · 进度对齐度 |
| **医学多模态影像分析** | 10 类影像分类 + 结构化分析 | CT/MRI/DSA/病理/心电图/临床照片/检验报告/影像报告/医学图解/课件资料 |
| **医学影像对比** | 多图对比分析 | 同模态治疗前后对比 · 不同模态交叉对比（CT vs MRI） |
| **DICOM 元数据提取** | DICOM 文件技术参数提取 | 扫描参数 · 序列信息 · 不提取患者隐私 |
| **医学 OCR 提取** | 检验报告/处方/文档结构化 | 检验指标数值提取 · 处方药品信息解析 · 流式识别 |
| **Vision-RAG 桥接** | 影像发现 → 循证检索 | 自动从影像分析结果生成 PubMed + 本地知识库检索 |
| **PubMed 文献检索** | 集成 NCBI E-utilities API | 8 级证据等级排序 · 与本地 ChromaDB 知识库互补 |
| **代码辅助开发** | 面向医学生的代码工具 | 代码生成 · 在线执行 · 错误诊断 · 实操案例生成 |
| **学习风险评估** | 百炼平台集成 | 风险等级判定 · 学习干预建议 · 异步评估 |
| **系统监控** | 限流熔断器状态监控 | 登录失败/成功统计 · 熔断器状态查询 |

> 所有资源生成与辅导接口均支持 **SSE 流式输出** 和 **图片输入**。

---

## 🖼️ 医学多模态影像分析

### 10 类医学影像自动分类

系统基于 qwen-vl-max 多模态大模型，自动识别并分类 10 种医学影像类型，每类配有专用分析 Prompt：

| 影像类型 | 标识 | 专用分析策略 |
|:---|:---|:---|
| 神经影像 CT | `neuroimaging_ct` | 脑实质密度评估 · 出血/缺血征象识别 · 中线移位判断 |
| 神经影像 MRI | `neuroimaging_mri` | DWI/ADC 序列解读 · T1/T2 信号分析 · 梗死核心/半暗带评估 |
| DSA 血管造影 | `angiography_dsa` | 血管狭窄/闭塞评估 · 侧支循环分级 · 介入治疗指征 |
| 病理切片 | `pathology` | 细胞形态学分析 · 染色特征识别 · 病理分期辅助 |
| 心电图 | `ecg` | 心率/心律分析 · ST-T 改变识别 · 房颤/心梗征象 |
| 临床照片 | `clinical_photo` | 神经系统体征 · 皮肤病变 · 术后评估 |
| 检验报告 | `lab_report` | 血常规/生化/凝血功能指标提取 |
| 影像报告 | `radiology_report` | 报告文本结构化提取 |
| 医学图解 | `medical_illustration` | 解剖结构标注 · 病理机制图解 |
| 课件资料 | `courseware` | 教学内容提取 · 知识点归纳 |

### 影像分析 → 推理工作流集成

```
医学影像输入
      │
      ▼
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ 影像分类      │───►│ 结构化分析         │───►│ Vision-RAG 桥接  │
│ (10类自动)    │    │ (JSON Schema约束) │    │ PubMed+本地检索  │
└─────────────┘    └──────────────────┘    └────────┬────────┘
                                                     │
                    ┌────────────────────────────────┘
                    ▼
          ┌──────────────────┐
          │ 视觉证据注入 State │
          │ → retrieve → reason│
          │ → validate → report│
          └──────────────────┘
```

### 多图对比分析

支持同一模态不同时间点对比（如治疗前后 CT）或不同模态交叉对比（CT vs MRI），自动生成对比分析报告，包含变化描述、临床意义解读和鉴别诊断建议。

### DICOM 元数据提取

从 DICOM 文件中提取技术参数（扫描参数、序列信息等），不提取患者身份信息，符合医疗数据隐私保护要求。

### 医学 OCR 结构化提取

| 能力 | 说明 |
|:---|:---|
| **检验报告 OCR** | 自动提取检验指标名称、数值、参考范围、异常标记 |
| **处方 OCR** | 解析药品名称、剂量、用法、频次等结构化信息 |
| **通用文档 OCR** | 流式识别医学文档文本，支持实时输出 |

---

## 📊 学习风险评估

集成阿里云百炼平台，通过 `LearningRiskAnalyzer` 异步评估学生学习风险：

```
学生画像数据 ──► LearningRiskAnalyzer ──► 风险评估结果
                                           │
                        ┌──────────────────┼──────────────────┐
                        ▼                  ▼                  ▼
                   低风险              中风险              高风险
                 保持当前节奏        加强辅导关注        触发干预预警
```

| 评估维度 | 说明 |
|:---|:---|
| **风险等级** | 低风险 / 中风险 / 高风险 三级判定 |
| **学习建议** | 针对性、可执行的学习改进建议（50字以内） |
| **评估摘要** | 学习状况综合评估摘要（50字以内） |
| **异步执行** | 基于 `asyncio` 异步调用，不阻塞主流程 |

---

## 🚀 部署指南

项目支持多种部署方式，提供完整的部署文档：

| 文档 | 说明 |
|:---|:---|
| `backend/ai/MyServer/BAOTA_DEPLOY.md` | 宝塔面板部署指南（Java 项目 + 环境变量配置） |
| `backend/ai/MyServer/README_DEPLOY.md` | 通用部署文档 |
| `ARCHITECTURE.md` | 模型层完整学习文档（文件架构 / 阅读顺序 / 数据模型 / 节点详解 / LangGraph 机制） |

### 快速启动

```bash
# 1. 启动模型推理层
cd model && pip install -r requirements.txt && python -m app.main

# 2. 启动后端服务层
cd backend/ai/MyServer && mvn spring-boot:run

# 3. 启动前端交互层
cd frontend && npm install && npm run dev
```

---

## 📊 测试与质量保障

### 测试体系总览

| 测试类型 | 用例数 | 覆盖范围 | 文档位置 |
|:---|:---:|:---|:---|
| 黑盒功能测试 | 33 | 10 大功能模块（认证/画像/资源/辅导/路径/评估/代码/对话/并发/非AI） | [测试文档 §2](docs/测试文档.md) |
| 白盒路径覆盖 | 38 | 核心模块路径覆盖 + 共享记忆系统 + RAG + 迁移验证 | [测试文档 §3](docs/测试文档.md) |
| 并发性能测试 | 3 级梯度 | 10/50/100 并发 SSE | [测试文档 §4](docs/测试文档.md) |
| 安全测试 | 16 | JWT/注入/限流/越权/上传 | [测试文档 §5](docs/测试文档.md) |
| 容灾测试 | 7 | Rerank/PubMed/OSS/SSE 降级 | [测试文档 §6](docs/测试文档.md) |

### 并发性能实测数据

| 并发数 | 成功率 | 平均延迟 | P50 | P95 | 瓶颈 |
|:---:|:---:|:---:|:---:|:---:|:---|
| 10 | 100% | 12.4s | 11.8s | 18.3s | 无 |
| 50 | 98% | 19.7s | 18.2s | 28.6s | 模型层排队 |
| 100 | 94% | 26.3s | 24.1s | 42.7s | AI 信号量满 (permits=20) |

### 运行测试

```bash
# 白盒单元测试
cd model
python -m pytest tests/test_new_architecture.py -v

# 共享记忆系统测试
cd model
python -m pytest tests/test_shared_memory.py -v

# RAG 检索测试
cd model
python -m pytest tests/test_rag.py -v

# API 客户端集成测试（需启动模型服务）
cd model
python -m pytest tests/test_api_client.py -v

# 全链路黑盒 + 并发压测（需启动完整服务）
cd tests
python -m pytest test_full_suite.py -v
```

---

## 🚀 快速开始

### 环境要求

| 依赖 | 版本 | 说明 |
|:---|:---|:---|
| Java | 21+ | 后端运行时 |
| Python | 3.11+ | 模型推理层 |
| Node.js | 20+ | 前端构建 |
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
| `expert_config.yaml` | 9 个专家定义 · 辩论配置 · 动态编排规则 |
| `rules_config.yaml` | 质量校验规则 · 退火策略（5 类驳回分类与修正） |
| `report_templates.yaml` | 6 种报告模板（画像 / 资源 / 辅导 / 评估 / 路径 / 知识问答） |
| `prompts.yaml` | 各场景 Prompt 模板库 |
| `limits_config.yaml` | 参数上限与关键词配置 |
| `shared_memory_config.yaml` | 共享记忆系统配置（熵值阈值 · 共识参数 · 持久化策略） |

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
| 资源 | `/model/resources/generate/*` | POST (SSE) | 7 种资源类型独立生成 |
| 路径 | `/api/learning-path/generate` | POST | 生成学习路径 |
| 路径 | `/model/learning-path/recommend` | POST | 个性化资源推送 |
| 路径 | `/model/learning-path/{path_id}/adjust` | POST | 动态调整学习路径 |
| 辅导 | `/api/tutor/chat` | POST (SSE) | 智能辅导对话 |
| 评估 | `/api/evaluation/generate` | POST (SSE) | 生成评估报告 |
| 评估 | `/model/evaluation/optimize` | POST | 触发学习方案优化 |
| 评估 | `/model/evaluation/behavior` | POST | 提交学习行为数据 |
| 评估 | `/model/evaluation/mastery-heatmap` | GET | 知识点掌握度热力图 |
| 文献 | `/model/pubmed/search` | POST | PubMed 学术文献检索 |
| 医学影像 | `/model/medical/analyze-image` | POST | 医学影像结构化分析 |
| 医学影像 | `/model/medical/analyze-case` | POST (SSE) | 多模态病例综合分析 |
| 医学影像 | `/model/medical/compare-images` | POST | 多图对比分析 |
| 医学影像 | `/model/medical/dicom-metadata` | POST | DICOM 元数据提取 |
| 医学OCR | `/model/medical/ocr/lab-report` | POST | 检验报告 OCR 提取 |
| 医学OCR | `/model/medical/ocr/prescription` | POST | 处方 OCR 提取 |
| 医学OCR | `/model/medical/ocr/text` | POST (SSE) | 通用文档 OCR 流式识别 |
| 课程 | `/model/courses` | GET | 课程列表 |
| 课程 | `/model/courses/{course_id}/knowledge-tree` | GET | 课程知识体系树 |
| 代码 | `/api/code/execute` | POST | 代码执行沙箱 |
| 代码 | `/api/code/assist` | POST | 代码辅助开发 |
| 任务 | `/model/tasks/{task_id}` | GET | 查询异步任务状态 |
| 任务 | `/model/tasks/{task_id}/stream` | GET (SSE) | SSE 流式重连 |
| 管理 | `/admin/reload_config` | POST | 配置热更新 |
| 管理 | `/admin/report_modes` | GET | 可用报告模式列表 |
| 分析 | `/ai/analyze` | POST | 学习风险快速分析 |

### 前端路由

| 路由 | 页面 | 功能 |
|:---|:---|:---|
| `/login` | login.vue | 登录 / 注册 |
| `/` | home.vue | 首页布局（导航栏 + 子路由） |
| `/profile` | profile.vue | 学习画像构建 |
| `/resources` | resources.vue | 资源生成 |
| `/learning-path` | learning-path.vue | 学习路径规划 |
| `/tutor` | tutor.vue | 智能辅导 |
| `/assessment` | assessment.vue | 学习效果评估 |

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
| **SSE 断线续传** | 滑动窗口缓存 + Last-Event-ID 机制 + `/model/tasks/{task_id}/stream` 重连接口 |
| **Token 自动续期** | 即将过期时自动签发新 Token |
| **配置热更新** | `/admin/reload_config` 接口支持运行时热更新 YAML 配置，无需重启服务 |

### 内容安全

| 机制 | 说明 |
|:---|:---|
| **SQL 注入防护** | MyBatis-Plus 参数化查询 + 输入校验 |
| **XSS 防护** | DOMPurify 前端净化 + 后端 Content-Security-Policy |
| **文件上传安全** | 白名单扩展名校验 + 文件大小限制 + OSS 隔离存储 |
| **越权访问防护** | JWT Token 绑定用户 ID + 接口级权限校验 |

### 容灾策略

| 场景 | 策略 | 降级方案 |
|:---|:---|:---|
| Rerank 模型不可用 | 4 模型自动切换 | 原始检索结果兜底 |
| PubMed API 超时 | 超时熔断 | 仅使用本地 ChromaDB |
| OSS 上传失败 | 重试 + 降级 | 本地临时存储 |
| SSE 连接中断 | Last-Event-ID | 缓存事件回放 |

---

## 📚 文档导航

| 文档 | 说明 |
|:---|:---|
| [需求规格说明书](docs/需求规格说明书.md) | 10 章：功能/非功能需求 + UML 图（组件图/类图/时序图/部署图）+ 核心算法流程图与伪代码 |
| [测试文档](docs/测试文档.md) | V3.0 · 10 章：黑盒 33 条 + 白盒 38 条 + 并发压测 + 安全测试 + 容灾测试 + 系统效果量化评估 |
| [数据库设计文档](docs/数据库设计文档.md) | 14 张表详细设计 + Mermaid ER 图 + 索引策略 + 数据字典 |
| [接口文档](docs/多智能体个性化学习系统接口文档.md) | 14 模块完整 API 规范（请求/响应/状态码） |
| [API 规范补充](docs/API_SPEC.md) | API 补充规范文档 |

---

## 📜 License

本项目基于 [MIT License](LICENSE) 开源。

---

*本系统属于高等教育个性化学习辅助系统，系统生成的学习资源与建议仅供参考，不替代教师的专业教学判断。学生应结合自身实际情况与教师指导进行学习规划。*