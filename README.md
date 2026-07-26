<div align="center">

# LearnAgent

### 网址
https://8.141.124.251/login

### 多智能体个性化学习系统

**基于大模型技术体系的高等教育个性化学习智能体系统**

[![Java 21](https://img.shields.io/badge/Java-21+-ED8B00?style=flat-square&logo=openjdk&logoColor=white)](https://openjdk.org/)
[![Python 3.11](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Vue 3.5](https://img.shields.io/badge/Vue-3.5-4FC08D?style=flat-square&logo=vue.js&logoColor=white)](https://vuejs.org/)
[![Spring Boot 3.3](https://img.shields.io/badge/Spring%20Boot-3.3-6DB33F?style=flat-square&logo=springboot&logoColor=white)](https://spring.io/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2.9-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![LangChain](https://img.shields.io/badge/LangChain-1.3.13-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://www.langchain.com/)
[![RAGAS](https://img.shields.io/badge/RAGAS-0.4.x-6C5CE7?style=flat-square)](https://docs.ragas.io/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

</div>

---

## 🌟 项目背景

面向高等教育场景（**脑卒中方向医学生**）的个性化学习智能体系统。在传统医学教育中，学生面临以下挑战：

- 📚 **知识碎片化**：医学知识体系庞大、更新迅速，学生难以建立系统性的认知框架，知识点之间缺乏有效连接
- 👨‍⚕️ **个性化缺失**：统一的教学模式无法满足不同学生的学习节奏、基础差异和兴趣方向，优秀学生"吃不饱"、基础薄弱学生"跟不上"
- 🧩 **实践机会有限**：临床案例资源稀缺，尤其是典型病例的影像资料和诊疗方案，学生难以获得充分的实践训练
- 📊 **评估手段单一**：传统考试偏重记忆性知识考查，难以全面评估学生的临床推理能力、循证思维和综合应用能力
- 🔬 **循证医学教育滞后**：最新临床指南和研究成果难以快速融入教学，教学内容与临床实践存在脱节

LearnAgent 以高校专业课程知识库为底座，融合 **多智能体协同推理**、**Hybrid RAG**（混合检索增强生成）、**多模态影像识别** 与 **全栈响应式流式架构**，实现从学生画像构建到个性化资源生成、学习路径规划、智能辅导、学习效果评估的完整闭环。系统内置 10 个脑卒中专业领域的循证医学测试问答，支持递归分块与语义分块两种策略的 A/B 评测对比，确保检索质量可量化、可优化。

## 🎯 系统目标

| 目标 | 描述 |
|:---|:---|
| **个性化学习** | 根据学生画像提供量身定制的学习方案 |
| **智能辅导** | 24/7 全天候智能辅导，解答疑问 |
| **循证学习** | 基于权威医学文献的证据驱动学习 |
| **能力评估** | 全面、客观的学习效果评估体系 |
| **透明可解释** | 完整的思考过程展示，支持追溯验证 |

---

## ✦ 核心亮点

| 特性 | 说明 |
|:---|:---|
| 🧠 **三群协同多智能体架构** | 基于 LangGraph StateGraph 构建 9 个专家智能体，YAML 配置驱动，支持动态编排与辩论-仲裁机制，实现从画像构建到学习评估的完整闭环 |
| 🔍 **证据前置 Hybrid RAG** | 三阶漏斗检索：Qwen 向量 + BM25 宽召回 → RRF 倒数排名融合粗排 → Qwen Reranker 精排；QA 生成扩充向量库；强制文献溯源；支持递归分块与语义分块 A/B 评测 |
| 💾 **共享记忆系统** | 物理层（ChromaDB 向量存储）+ 逻辑层（信任加权投票共识）+ 元记忆过滤（四维信息熵计算），跨会话保留高价值洞察，实现学习连续性 |
| ⚡ **全栈响应式流式管道** | Java WebFlux + Python AsyncIO 深度流式融合，AI 思考过程完全透明可视化，SSE 断线续传，支持 100 并发稳定运行 |
| 🖼️ **医学多模态影像分析** | 10 类医学影像自动分类 + qwen-vl-max 结构化分析 + DICOM 元数据提取 + 多图对比 + Vision-RAG 桥接循证检索 |
| 🛡️ **防幻觉与质量保障** | 双层校验（规则引擎学术审查 + LLM 反思逻辑审查）+ 动态退火修正 + 辩论-仲裁 + 71 条自动化测试用例，确保输出可靠性 |
| 🩺 **医学 OCR 结构化提取** | 检验报告 + 处方 + 通用医学文档的 OCR 流式识别与结构化提取，支持多格式文档输入 |
| 💻 **代码执行与辅助** | 支持 Python 代码在线执行沙箱与 AI 编程辅助，适用于医学数据处理、统计分析与算法教学场景 |
| 📊 **学习风险评估** | 百炼平台集成，自动评估学生学习风险等级并生成个性化干预建议，支持知识点掌握度热力图与综合能力雷达图 |

---

## 🧠 多智能体编排架构

### 9 大专家智能体协同体系

系统基于 LangGraph StateGraph 构建 9 个领域专家智能体，通过 YAML 配置驱动，支持动态编排与辩论-仲裁机制。每个智能体拥有独立的系统提示词、知识边界和输出规范。

```
                           ┌──────────────────┐
                           │   学生输入/请求    │
                           └────────┬─────────┘
                                    │
                           ┌────────▼─────────┐
                           │   Orchestrator    │
                           │  (意图识别+路由)   │
                           └────────┬─────────┘
                                    │
            ┌───────────┬───────────┼───────────┬───────────┐
            │           │           │           │           │
     ┌──────▼──────┐ ┌──▼────┐ ┌───▼────┐ ┌───▼────┐ ┌───▼────┐
     │  Profile    │ │Resource│ │Learning│ │ Tutor  │ │Evaluate│
     │   Agent     │ │ Agent  │ │  Path  │ │ Agent  │ │ Agent  │
     │  画像构建    │ │ 资源生成│ │  Agent  │ │ 智能辅导│ │ 学习评估│
     └─────────────┘ └────────┘ │ 路径规划│ └────────┘ └────────┘
                                └────────┘
            ┌───────────┬───────────┬───────────┐
     ┌──────▼──────┐ ┌──▼────┐ ┌───▼────┐ ┌───▼────────┐
     │   Vision    │ │  OCR  │ │  Code  │ │   Bailian   │
     │   Agent     │ │ Agent │ │ Agent  │ │   Agent     │
     │  医学影像    │ │ 文档识别│ │ 代码执行│ │  学习风险    │
     └─────────────┘ └────────┘ └────────┘ └─────────────┘
```

| 智能体 | 职责 | 核心能力 |
|:---|:---|:---|
| **Profile Agent** | 学生画像构建 | 对话式信息采集、知识水平评估、学习风格分析、兴趣方向识别 |
| **Resource Agent** | 个性化资源生成 | 8 种资源类型独立生成（讲义/案例/习题/文献综述/思维导图/临床指南/视频脚本/交互式问答） |
| **Learning Path Agent** | 学习路径规划 | 知识图谱导航、先修关系推理、难度梯度设计、动态路径调整 |
| **Tutor Agent** | 智能辅导答疑 | 24/7 全天候辅导、多轮对话理解、循证解答、文献溯源 |
| **Evaluate Agent** | 学习效果评估 | 知识点掌握度热力图、综合能力雷达图、学习行为分析、优化方案生成 |
| **Vision Agent** | 医学影像分析 | 10 类影像自动分类、结构化报告生成、DICOM 元数据提取、多图对比 |
| **OCR Agent** | 医学文档识别 | 检验报告/处方/通用文档流式 OCR 识别与结构化提取 |
| **Code Agent** | 代码执行辅助 | Python 代码在线执行沙箱、AI 编程辅助、医学数据处理教学 |
| **Bailian Agent** | 学习风险分析 | 百炼平台集成、学习风险等级评估、干预建议生成 |

### 辩论-仲裁质量保障机制

当多个智能体对同一问题产生分歧时，系统自动启动辩论-仲裁流程：

1. **辩论阶段**：各相关智能体基于自身知识领域提出观点和证据链
2. **信任加权投票**：基于历史表现加权计算共识得分
3. **仲裁裁决**：由 Orchestrator 综合证据链和共识得分做出最终裁决
4. **元记忆沉淀**：高价值洞察通过四维信息熵计算后存入共享记忆，跨会话复用

---

## 📊 RAG 分块策略 A/B 评测

系统内置完整的 RAG 分块策略对比评测框架（`tests/compare_chunking.py`），支持递归字符分块与语义分块两种策略的量化对比。

### 评测指标（RAGAS）

| 指标 | 英文名 | 说明 |
|:---|:---|:---|
| 上下文精确度 | Context Precision | 检索到的上下文中有多少比例与问题相关 |
| 上下文召回率 | Context Recall | 标准答案所需信息是否都被检索到 |
| 答案忠实度 | Faithfulness | 生成的答案是否忠实于检索到的上下文 |
| 答案相关性 | Answer Relevancy | 生成的答案与问题的相关程度 |

### 两种分块策略

| 策略 | 算法 | 参数 | 优势 |
|:---|:---|:---|:---|
| **递归字符分块** | RecursiveCharacterTextSplitter | chunk_size=512, overlap=128 | 实现简单、速度快、适合通用场景 |
| **语义分块** | 基于 Embedding 相似度阈值切分 | similarity_threshold=0.80, overlap_ratio=0.25, chunk_size=100-800 | 保留语义完整性、适合专业领域长文档 |

### 评测测试集

系统内置 10 道脑卒中循证医学测试问答，覆盖以下核心知识点：

| # | 知识点 | 测试问题 |
|:---:|:---|:---|
| 1 | 出血转化 | 脑梗死后出血转化的主要危险因素有哪些？ |
| 2 | 静脉溶栓 | 急性脑梗死静脉溶栓的时间窗是多少？ |
| 3 | t-PA 用药 | 急性脑梗死 t-PA 静脉溶栓的剂量和用法是什么？ |
| 4 | 血管内治疗 | 急性大血管闭塞性脑梗死的血管内治疗适应症是什么？ |
| 5 | 血压管理 | 脑梗死急性期的血压管理目标是什么？ |
| 6 | 溶栓前血压 | 静脉溶栓前的血压控制目标是什么？ |
| 7 | NIHSS 评分 | NIHSS 评分的临床意义和分级标准是什么？ |
| 8 | 血糖管理 | 急性脑梗死患者血糖管理目标是什么？ |
| 9 | 抗血小板治疗 | 脑梗死二级预防的抗血小板治疗方案是什么？ |
| 10 | ECASS 分型 | 脑梗死后出血转化的 ECASS 分型标准是什么？ |

### 运行评测

```bash
cd model

# 构建向量库 + 评测（首次运行）
python -m tests.compare_chunking

# 跳过构建，仅运行评测（已有向量库）
python -m tests.compare_chunking --skip-build

# 强制重建向量库
python -m tests.compare_chunking --force-rebuild

# 输出结果到 JSON 文件
python -m tests.compare_chunking --output results.json
```

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
│   Python 3.11 · FastAPI · LangGraph · LangChain · Qwen             │
│   ChromaDB · qwen3.7-text-embedding · qwen3-rerank · qwen-vl-max   │
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
| **前端** | Vue · Vite · Pinia · marked · DOMPurify · pdfjs-dist | 3.5 · 7 · 3 · 17 · 3.3 · 3.11 | 流式渲染 · Markdown 展示 · 思考步骤折叠 · 学习路径可视化 · PDF 预览 · 医学影像查看器 |
| **后端** | Java · Spring Boot · WebFlux · Security · Redisson · MySQL · MyBatis-Plus | 21 · 3.3 · 6.1 · 6.3 · 3.27 · 8.0 · 3.5 | 响应式高并发 · JWT 认证 · 分布式限流 · WebClient 流式转发 · SSE 断线续传 · 阿里云 OSS 集成 |
| **模型** | Python · FastAPI · LangGraph · LangChain · Qwen · ChromaDB · qwen3-rerank | 3.11 · 0.128 · 1.2.9 · 1.3.13 · Max/Plus/Turbo · 0.5 · --- | 多智能体编排 · Hybrid RAG · 流式事件输出 · 多模态识别 · 文献检索 · RAGAS 评测 |

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
            │  RRF(d) = 1/(60+Rank_v)        │
            │         + 1/(60+Rank_b)       │
            │  40 篇 → 20 篇候选              │
            └───────────────┬───────────────┘
                            │
                            ▼
            ┌───────────────────────────────┐
            │     第三阶：Reranker 精排       │
            │  qwen3-rerank                  │
            │  失败时回退到 RRF 排序结果       │
            │  20 篇 → 3 篇最终结果           │
            └───────────────────────────────┘
```

| 阶段 | 技术 | 输入 → 输出 | 说明 |
|:---|:---|:---|:---|
| **宽召回** | Qwen Embedding (qwen3.7-text-embedding, 1024d) + BM25 | 各 20 篇 → 最多 40 篇 | 语义向量 + 关键词双路并行召回，互补覆盖 |
| **粗排** | RRF (Reciprocal Rank Fusion) | 40 篇 → 20 篇 | 零成本零延迟，纯排名融合，避开 Dense/Sparse 分值区间差异 |
| **精排** | QwenReranker (qwen3-rerank) | 20 篇 → 3 篇 | 深度语义重排序，失败时使用 RRF 结果兜底 |

#### 文档预处理流程

| 步骤 | 实现 | 参数 |
|:---|:---|:---|
| PDF 加载 | PyPDFLoader | --- |
| 文本清洗 | clean_text() 去除换行和多余空格 | --- |
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
├── backend/server/                  # 后端服务层（Java Spring Boot）
│   └── src/main/java/com/learnagent/
│       ├── controller/              # REST 控制器（15 个：画像/资源/路径/辅导/评估/医学影像/代码/监控/用户/课程/文档/题目/登录/上传/首页）  
│       ├── service/                 # 业务逻辑（AI 流式/对话持久化/OSS）
│       ├── cache/                   # SSE 事件缓存
│       ├── config/                  # 配置（Security/WebClient/Redisson/OSS/Jackson/MyBatisPlus）
│       ├── entity/                  # 实体类
│       ├── dto/                     # 数据传输对象
│       ├── param/                   # 请求参数
│       ├── vo/                      # 响应视图对象
│       ├── mapper/                  # MyBatis-Plus Mapper
│       └── utils/                   # JWT/OSS/IP 工具
│
├── model/                           # 模型推理层（Python FastAPI）
│   └── app/
│       ├── main.py                  # FastAPI 入口 & API 路由（9 大模块 30+ 接口）
│       ├── agents/                  # 多智能体核心
│       │   ├── orchestrators/       # LangGraph 图定义 & 8 个节点实现
│       │   │   ├── clinical_graph.py  # LearningGraphBuilder（含 Vision 节点分支）
│       │   │   ├── xf_xinghuo_agent.py # LearningAgent（顶层智能体入口）
│       │   │   └── nodes/             # 工作流节点（intent/analysis/vision/retrieve/reason/validate/report）
│       │   ├── core/                # 状态模型 / 共享记忆 / 异常 / 结果封装 / 装饰器
│       │   ├── infra/               # Reranker 容灾
│       │   ├── services/            # 检索 / 查询 / 综合服务
│       │   ├── pipelines/           # RAG 管道
│       │   ├── bailian/             # 百炼平台集成（学习风险分析）
│       │   ├── schemas/             # 数据结构定义
│       │   └── utils/               # LLM / JSON / 重试 / 文本工具
│       ├── rag/                     # Hybrid RAG（向量 + BM25 / QA 生成 / 文档加载）
│       ├── services/                # 多模态影像 & OCR
│       │   ├── medical_vision_service.py  # 10 类医学影像结构化分析
│       │   ├── medical_ocr_service.py     # 检验报告/处方/文档 OCR 提取
│       │   ├── vision_rag_bridge.py       # 影像发现 → 本地知识库桥接
│       │   ├── vision_service.py          # 通用视觉分析服务
│       ├── config/                  # YAML 配置（9 专家 / 规则 / 模板 / Prompt / 限额 / 共享记忆）
│       ├── evaluation/              # 评估模块
│       └── utils/                   # 任务管理 / 上下文摘要 / Token 聚合 / 错误码 / 命名模型 / 模型下载
│
├── tests/                           # 测试套件
│   ├── test_full_suite.py           # 全链路黑盒测试
│   └── locustfile.py                # Locust 并发压测脚本
├── docs/                            # 项目文档
│   ├── api/
│   │   └── LearnAgent系统接口文档.md      # 64 接口完整规范
│   └── architecture/
│       ├── 需求规格说明书.md              # 系统功能/非功能需求
│       ├── 系统设计说明书.md              # 架构设计/UML/ER/接口规范/安全/部署
│       ├── 系统测试报告.md                # 黑白盒测试+并发压测+量化指标
│       ├── 核心算法设计文档.md            # 6 核心算法流程图+伪代码
│       ├── 数据库设计手册.md              # 14 表DDL+索引+外键+数据字典
│       ├── 共享记忆系统.md                # 共享记忆实现细节
│       └── 医学影像识别与拦截系统.md       # 影像识别流水线细节
└── LICENSE                          # 许可证
```

---

## 📊 测试与质量保障

### 测试体系总览

| 测试类型 | 用例数 | 覆盖范围 | 文档位置 |
|:---|:---:|:---|:---|
| 黑盒功能测试 | 60 | 9 大功能模块（认证/画像/资源/路径/辅导/评估/影像/代码/文档） | [测试报告 §2](docs/architecture/系统测试报告.md) |
| 白盒路径覆盖 | 27 | 4 核心算法 100% 路径覆盖（多智能体/退火校验/RAG/意图路由） | [测试报告 §3](docs/architecture/系统测试报告.md) |
| 并发性能测试 | 5 级梯度 | 10/20/50/100/200 并发 SSE | [测试报告 §4](docs/architecture/系统测试报告.md) |
| 系统效果量化 | 4 类指标 | RAG 检索质量 / 资源生成质量 / 画像构建质量 / 路径效果 | [测试报告 §5](docs/architecture/系统测试报告.md) |

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

# RAG 分块策略 A/B 评测对比
cd model
python -m tests.compare_chunking
python -m tests.compare_chunking --skip-build
python -m tests.compare_chunking --output results.json

# API 客户端集成测试（需启动模型服务）
cd model
python -m pytest tests/test_api_client.py -v

# 全链路黑盒 + 并发压测（需启动完整服务）
cd tests
python -m pytest test_full_suite.py -v

# Locust 并发压测
cd tests
locust -f locustfile.py --host=http://localhost:8080
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
| DashScope API Key | --- | 阿里云大模型服务（必需） |

### 启动步骤

**Step 1 — 初始化数据库**

```bash
mysql -u root -p < backend/server/learningo-agents.sql
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
cd backend/server
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

### 一站式启动（Docker Compose）

```bash
# 确保已安装 Docker 和 Docker Compose
docker-compose up -d
```

---

## ⚙️ 配置说明

### 模型层环境变量（model/.env）

```bash
# 必需 - 阿里云 DashScope API Key
DASHSCOPE_API_KEY="sk-your-dashscope-api-key"

# 可选 - Qwen 模型覆盖
QWEN_MODEL_MAX="qwen-max"
QWEN_MODEL_PLUS="qwen-plus"
QWEN_MODEL_TURBO="qwen-turbo"
QWEN_EMBEDDING_MODEL="qwen3.7-text-embedding"
QWEN_EMBEDDING_DIMENSION="1024"
QWEN_RERANK_MODEL="qwen3-rerank"
QWEN_VISION_MODEL="qwen-vl-max"

# 必需 - JWT 密钥（需与 Java 后端一致）
SECRET_KEY="your-jwt-secret-key"

# 可选 - 课程 PDF 目录（默认 model/data/documents/）
MEDICAL_DOCS_DIR="/path/to/your/pdf/documents"

# 可选 - Redis 配置
REDIS_HOST="localhost"
REDIS_PORT="6379"
```

### 模型层 YAML 配置

| 配置文件 | 说明 |
|:---|:---|
| expert_config.yaml | 9 个专家定义 · 辩论配置 · 动态编排规则 |
| rules_config.yaml | 质量校验规则 · 退火策略（5 类驳回分类与修正） |
| report_templates.yaml | 6 种报告模板（画像 / 资源 / 辅导 / 评估 / 路径 / 知识问答） |
| prompts.yaml | 各场景 Prompt 模板库 |
| limits_config.yaml | 参数上限与关键词配置 |
| shared_memory_config.yaml | 共享记忆系统配置（熵值阈值 · 共识参数 · 持久化策略） |

### 后端配置

通过 application-dev.yml（开发）或 application-prod.yml（生产）配置数据库、Redis、AI 服务地址、JWT 共享密钥和阿里云 OSS。

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
| init | 连接建立，返回任务 ID |
| node_start | 智能体节点开始推理 |
| token | 内容片段（增量） |
| node_done | 节点完成 |
| done | 流式结束 |
| error | 错误 |

### 核心 API

| 模块 | 接口 | 方法 | 说明 |
|:---|:---|:---|:---|
| 认证 | /api/user/login | POST | 用户登录 |
| 认证 | /api/user/register | POST | 用户注册 |
| 画像 | /api/profile/conversation | POST (SSE) | 对话式画像构建 |
| 画像 | /api/profile | GET | 获取当前画像 |
| 画像 | /model/profile/extract | POST | 抽取画像维度 |
| 资源 | /api/resources/generate | POST (SSE) | 综合资源生成 |
| 资源 | /api/resources/generate/* | POST (SSE) | 8 种资源类型独立生成 |
| 路径 | /api/learning-path/generate | POST | 生成学习路径 |
| 路径 | /model/learning-path/recommend | POST | 个性化资源推送 |
| 路径 | /model/learning-path/{path_id}/adjust | POST | 动态调整学习路径 |
| 辅导 | /api/tutor/chat | POST (SSE) | 智能辅导对话 |
| 评估 | /api/evaluation/generate | POST (SSE) | 生成评估报告 |
| 评估 | /model/evaluation/optimize | POST | 触发学习方案优化 |
| 评估 | /model/evaluation/behavior | POST | 提交学习行为数据 |
| 评估 | /model/evaluation/mastery-heatmap | GET | 知识点掌握度热力图 |
| 医学影像 | /model/medical/analyze-image | POST | 医学影像结构化分析 |
| 医学影像 | /model/medical/analyze-case | POST (SSE) | 多模态病例综合分析 |
| 医学影像 | /model/medical/compare-images | POST | 多图对比分析 |
| 医学影像 | /model/medical/dicom-metadata | POST | DICOM 元数据提取 |
| 医学OCR | /model/medical/ocr/lab-report | POST | 检验报告 OCR 提取 |
| 医学OCR | /model/medical/ocr/prescription | POST | 处方 OCR 提取 |
| 医学OCR | /model/medical/ocr/text | POST (SSE) | 通用文档 OCR 流式识别 |
| 课程 | /model/courses | GET | 课程列表 |
| 课程 | /model/courses/{course_id}/knowledge-tree | GET | 课程知识体系树 |
| 代码 | /api/code/execute | POST | 代码执行沙箱 |
| 代码 | /api/code/assist | POST (SSE) | 代码补全 / 诊断 / 优化 |
| 任务 | /model/tasks/{task_id} | GET | 查询异步任务状态 |
| 任务 | /model/tasks/{task_id}/stream | GET (SSE) | SSE 流式重连 |
| 管理 | /admin/reload_config | POST | 配置热更新 |
| 管理 | /admin/report_modes | GET | 可用报告模式列表 |
| 分析 | /ai/analyze | POST | 学习风险快速分析 |

### 前端路由

| 路由 | 页面 | 功能 |
|:---|:---|:---|
| /login | login.vue | 登录 / 注册 |
| / | home.vue | 首页布局（导航栏 + 子路由） |
| /profile | profile.vue | 学习画像构建 |
| /resources | resources.vue | 资源生成 |
| /learning-path | learning-path.vue | 学习路径规划 |
| /tutor | tutor.vue | 智能辅导 |
| /assessment | assessment.vue | 学习效果评估 |
| /code-assist | code-assist.vue | 代码辅助开发 |

---

## 🔧 典型应用场景

### 场景一：个性化学习路径规划

**用户**：医学生小王，刚进入脑卒中专业学习，基础薄弱

**流程**：
1. 小王完成对话式画像构建，系统通过多轮对话了解其基础水平、学习目标和兴趣方向
2. 系统分析知识库中的知识图谱，结合先修关系推理，生成个性化学习路径
3. 小王按照路径学习，系统实时跟踪学习进度和行为数据
4. 根据学习行为数据（答题正确率、停留时间、重复学习次数等），动态调整路径难度和内容
5. 学习完成后，系统生成知识点掌握度热力图和综合能力雷达图

**涉及智能体**：Profile Agent → Learning Path Agent → Evaluate Agent

### 场景二：智能循证辅导答疑

**用户**：学生小李在学习过程中遇到疑难问题

**流程**：
1. 小李向智能辅导模块提问："脑梗死后出血转化的主要危险因素有哪些？"
2. 系统通过 Hybrid RAG 三阶漏斗检索相关文献（宽召回 → RRF 粗排 → Reranker 精排）
3. 多智能体协同分析，Tutor Agent 结合检索结果生成详细解答
4. 解答包含文献引用，支持证据溯源，双击引用可跳转至原文
5. 系统自动记录问答历史，丰富学生画像

**涉及智能体**：Tutor Agent + Orchestrator（辩论-仲裁）

### 场景三：医学影像分析学习

**用户**：学生小张需要分析临床影像案例，准备影像诊断考试

**流程**：
1. 小张上传 CT/MRI 等医学影像图片
2. Vision Agent 自动分类影像类型（CT 平扫/CTA/MRI-DWI/MRI-T2 等 10 类）
3. 系统进行结构化分析，标注关键解剖结构和异常发现
4. Vision-RAG 桥接本地知识库，检索相关文献和诊疗指南，提供循证支持
5. 生成详细的分析报告，包含影像学特征描述、鉴别诊断、相关知识点和学习建议

**涉及智能体**：Vision Agent → OCR Agent（如有文本标注）→ RAG 检索

### 场景四：学习效果综合评估

**用户**：学生小赵完成阶段性学习，需要评估学习效果

**流程**：
1. 系统收集小赵的学习行为数据（学习时长、答题记录、交互频率、知识点覆盖度等）
2. Evaluate Agent 生成知识点掌握度热力图，直观展示强项与薄弱环节
3. Bailian Agent 评估学习风险等级，识别可能掉队的知识点
4. 系统生成针对性学习方案优化建议，推荐补充学习资源
5. 教师可查看全班学生的评估报告，调整教学策略

**涉及智能体**：Evaluate Agent → Bailian Agent → Learning Path Agent（动态调整）

---

## 🛡️ 安全与防幻觉

### 防幻觉策略

| 策略 | 说明 |
|:---|:---|
| **证据溯源** | 强制引用来源文献与页码，杜绝无依据输出 |
| **双层校验** | 规则引擎学术审查 + LLM 反思逻辑审查 |
| **辩论-仲裁** | 多智能体辩论 + 证据链裁决，减少单一模型偏见 |
| **动态退火** | 校验失败自动分类修正，权重衰减避免无效重试 |
| **文献引用规范** | 强制使用书名号引用库内文献，严禁引用库外文献 |

### 系统安全

| 机制 | 说明 |
|:---|:---|
| **JWT 双向认证** | Java 与 Python 之间共享 JWT Secret 双向验证 |
| **分布式限流** | Redisson 信号量控制最大并发数，防止服务过载 |
| **SSE 断线续传** | 滑动窗口缓存 + Last-Event-ID 机制 + /model/tasks/{task_id}/stream 重连接口 |
| **Token 自动续期** | 即将过期时自动签发新 Token |
| **配置热更新** | /admin/reload_config 接口支持运行时热更新 YAML 配置，无需重启服务 |

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
| OSS 上传失败 | 重试 + 降级 | 本地临时存储 |
| SSE 连接中断 | Last-Event-ID | 缓存事件回放 |

---

## 🤝 贡献指南

欢迎贡献代码！请遵循以下流程：

### 贡献步骤

1. **Fork 仓库**
   ```bash
   git clone https://github.com/your-username/learning-multi-agent-system.git
   ```

2. **创建分支**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **开发代码**
   - 遵循项目代码规范
   - 添加必要的测试用例
   - 确保所有测试通过

4. **提交代码**
   ```bash
   git add .
   git commit -m "feat: add your feature"
   ```

5. **推送分支**
   ```bash
   git push origin feature/your-feature-name
   ```

6. **创建 Pull Request**
   - 描述清楚修改内容
   - 关联相关 issue

### 代码规范

| 语言 | 规范 |
|:---|:---|
| Python | 遵循 PEP 8 规范 |
| Java | 遵循 Google Java 风格指南 |
| Vue | 遵循 Vue 官方风格指南 |

### 提交信息规范

```
<type>: <description>

[optional body]

[optional footer]
```

**Type 类型**：
- feat：新功能
- fix：修复 bug
- docs：文档更新
- style：代码格式（不影响功能）
- refactor：重构（既不新增功能也不修复 bug）
- test：测试相关
- chore：构建/工具类更新

---

## ❓ FAQ

### Q1: 如何获取 DashScope API Key？

A: 访问 [阿里云 DashScope 控制台](https://dashscope.console.aliyun.com/)，注册账号并申请 API Key。

### Q2: 首次启动时向量库需要多长时间构建？

A: 取决于 PDF 文档数量和网络速度，通常需要 5-10 分钟。首次构建完成后会缓存，后续启动无需重新构建。

### Q3: SSE 连接断开后如何重连？

A: 系统支持 Last-Event-ID 机制，前端会自动尝试重连。也可以调用 /model/tasks/{task_id}/stream 接口手动重连。

### Q4: 如何添加新的医学文献？

A: 将 PDF 文件放入 model/data/documents/ 目录，重启模型服务即可自动加载。

### Q5: 如何自定义专家智能体配置？

A: 编辑 model/app/config/expert_config.yaml 文件，按照现有格式添加或修改专家定义，然后通过 /admin/reload_config 接口热更新配置，无需重启服务。

### Q6: 支持哪些 LLM 模型？

A: 系统统一使用阿里云百炼 Qwen 模型：`qwen-max/plus/turbo` 负责推理，`qwen3.7-text-embedding` 负责向量检索，`qwen3-rerank` 负责精排，`qwen-vl-max` 负责视觉理解。模型名可通过环境变量覆盖。

### Q7: 如何进行性能调优？

A:
- 调整 limits_config.yaml 中的并发参数（AI 信号量 permits）
- 优化 Redis 缓存配置（TTL、连接池大小）
- 根据实际情况调整 Reranker 模型切换策略
- 调整 ChromaDB 向量检索的 top_k 参数
- 使用 RAGAS 评测对比不同分块策略的效果

---

## 📚 文档导航

| 文档 | 说明 |
|:---|:---|
| [需求规格说明书](docs/architecture/需求规格说明书.md) | 10 章：功能/非功能需求 + UML 用例图 + 核心算法流程图与伪代码 |
| [系统设计说明书](docs/architecture/系统设计说明书.md) | 7 章：四层架构/Mermaid 图 + UML 用例模型 + ER 数据模型 + 64 接口规范 + 安全设计 + 部署拓扑 |
| [系统测试报告](docs/architecture/系统测试报告.md) | 6 章：黑盒 60 条 + 白盒 27 条 + 并发压测 5 级梯度 + 系统效果量化指标 |
| [核心算法设计文档](docs/architecture/核心算法设计文档.md) | 8 章：6 核心算法 Mermaid 流程图 + Python/Java 伪代码 + 性能对比 |
| [数据库设计手册](docs/architecture/数据库设计手册.md) | 7 章：14 表 DDL + ER 图 + 索引策略 + 外键级联 + 数据字典 |
| [接口文档](docs/api/LearnAgent系统接口文档.md) | 14 模块 64 接口完整规范（请求/响应/SSE 协议） |

---

## 📜 License

本项目基于 [MIT License](LICENSE) 开源。

---

*本系统属于高等教育个性化学习辅助系统，系统生成的学习资源与建议仅供参考，不替代教师的专业教学判断。学生应结合自身实际情况与教师指导进行学习规划。*
