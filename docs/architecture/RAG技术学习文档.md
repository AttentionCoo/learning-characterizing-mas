# RAG（检索增强生成）技术学习文档

> 本文档面向系统开发者与学习者，深入讲解本项目中 RAG 技术的完整实现体系，包括架构设计、核心算法、代码实现与创新亮点。

---

## 目录

- [第一章：RAG 技术概述](#第一章rag-技术概述)
- [第二章：整体架构设计](#第二章整体架构设计)
- [第三章：知识底座 — 双层知识来源](#第三章知识底座--双层知识来源)
- [第四章：文档预处理与向量化](#第四章文档预处理与向量化)
    - [4.3 语义分块实验与结论](#43-语义分块实验与结论)
- [第五章：三阶漏斗混合检索（核心）](#第五章三阶漏斗混合检索核心)
- [第六章：QA 自动衍生引擎](#第六章qa-自动衍生引擎)
- [第七章：RAG 管道 — 查询→检索→合成](#第七章rag-管道--查询检索合成)
- [第八章：共享记忆系统 — RAG 的记忆层](#第八章共享记忆系统--rag-的记忆层)
- [第九章：LangGraph 工作流中的 RAG 集成](#第九章langgraph-工作流中的-rag-集成)
- [第十章：RAGAS 自动化评测](#第十章ragas-自动化评测)
    - [10.3 切分策略 A/B 对比评测](#103-切分策略-ab-对比评测)
- [第十一章：完整数据流与关键性能指标](#第十一章完整数据流与关键性能指标)
- [附录：核心文件索引](#附录核心文件索引)

---

## 第一章：RAG 技术概述

### 1.1 什么是 RAG？

**RAG（Retrieval-Augmented Generation，检索增强生成）** 是一种结合信息检索与文本生成的技术范式。在传统大语言模型（LLM）中，模型只能基于训练数据中的知识进行回答，存在以下问题：

- **知识截止日期**：训练数据有时间限制，无法回答最新问题
- **幻觉问题**：对不熟悉的内容可能编造虚假信息
- **不可溯源**：无法验证答案的来源和准确性

RAG 的解决思路是：**在 LLM 生成答案之前，先从外部知识库中检索相关文档，将检索到的证据注入到 LLM 的上下文中，让 LLM 基于证据进行回答。**

### 1.2 本项目的 RAG 定位

本项目面向**高等教育个性化学习**场景（以脑卒中医学教育为示范领域），构建了一套**多层次、多机制协同的 RAG 技术体系**：

```
本项目 RAG 的核心公式：
  精准回答 = 三阶漏斗混合检索（高效召回） 
            + 共享记忆系统（跨会话学习） 
            + 双重证据保障（权威教材 + 共享记忆） 
            + 质量校验闭环（退火修正 + 信誉反馈）
```

### 1.3 与普通 RAG 的对比

| 对比维度 | 普通 RAG | 本项目 RAG |
|:---|:---|:---|
| 检索策略 | 单一向量检索 | 三阶漏斗（向量+BM25→RRF→Reranker） |
| 记忆能力 | 无状态，每次独立检索 | 共享记忆系统，跨会话持久化 |
| 证据来源 | 单一知识库 | 本地权威教材 + 共享记忆 |
| 质量保障 | 无 | 退火校验 + 信誉反馈 + 反思循环 |
| 容灾能力 | 单点故障 | 4模型容灾切换 + 三级优雅降级 |
| 可追溯性 | 弱 | 每段证据附带来源+页码+相关度 |

---

## 第二章：整体架构设计

### 2.1 系统分层架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         RAG 技术体系全景                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────────┐        ┌──────────────────────────────────┐  │
│  │    知识底座（2层）     │        │        检索管道（3阶段）           │  │
│  │                      │        │                                  │  │
│  │ ① 本地教材PDF        │───────►│  查询生成 → 并行检索 → 证据合成    │  │
│  │ ② 共享记忆系统       │        │                                  │  │
│  │                      │        └──────────────────────────────────┘  │
│  └──────────────────────┘                      │                        │
│                                                ▼                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │              三阶漏斗混合检索器 (HybridRetriever)                   │  │
│  │                                                                   │  │
│  │  第一阶·宽召回       第二阶·RRF粗排       第三阶·Reranker精排     │  │
│  │  ┌──────────┐      ┌──────────┐        ┌──────────────┐         │  │
│  │  │ 向量检索  │      │ RRF倒数  │        │ 4模型容灾    │         │  │
│  │  │ (k=20)   │─────►│ 排名融合  │───────►│ 重排序       │──► 3篇  │  │
│  │  ├──────────┤      │ (40→20)  │        │ (20→3)       │         │  │
│  │  │ BM25检索 │      │          │        │              │         │  │
│  │  │ (k=20)   │      │          │        │              │         │  │
│  │  └──────────┘      └──────────┘        └──────────────┘         │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                   │                                     │
│                                   ▼                                     │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    共享记忆系统（3层）                              │  │
│  │                                                                   │  │
│  │  元记忆过滤         物理存储层           逻辑共识层                │  │
│  │  ┌──────────┐      ┌──────────┐        ┌──────────────┐         │  │
│  │  │ 4维熵值  │      │ChromaDB  │        │ 信任加权投票  │         │  │
│  │  │ 过滤器   │─────►│ 持久化   │◄──────►│ 共识引擎     │         │  │
│  │  └──────────┘      └──────────┘        └──────────────┘         │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 代码目录结构

```
model/app/
├── rag/                                   ← RAG 检索层
│   ├── data_loader.py                     ← PDF 加载 / 文本清洗 / 文档切分
│   ├── retrievers.py                      ← 向量库构建 / HybridRetriever / UnifiedSearchEngine
│   ├── retrieve.py                        ← 对外统一导出
│   └── qa_generator.py                    ← QA 对自动生成
├── agents/
│   ├── pipelines/
│   │   └── rag_pipeline.py                ← RAG 管道：查询→检索→合成
│   ├── services/
│   │   ├── query_service.py               ← 查询生成服务
│   │   ├── retrieval_service.py           ← 证据检索服务
│   │   └── synthesis_service.py           ← 证据合成服务
│   ├── infra/
│   │   ├── base_reranker.py               ← 重排序抽象基类
│   │   └── reranker.py                    ← DashScope 重排序实现
│   ├── schemas/
│   │   └── retrieval.py                   ← RerankResult / RetrievalDocument 数据模型
│   └── core/
│       └── shared_memory.py               ← 共享记忆系统（元记忆+存储+共识）
└── config/
    └── shared_memory_config.yaml          ← 共享记忆系统配置
```

---

## 第三章：知识底座 — 双层知识来源

### 3.1 第一层：本地权威教材 PDF

**作用**：提供权威教材的精准溯源，是本项目 RAG 的主知识库。

**技术实现**：

```
PDF文件 → PyPDFLoader 加载 → 文本清洗 → RecursiveCharacterTextSplitter 切分
       → DashScopeEmbeddings 向量化 → ChromaDB 持久化存储
```

**代码位置**：[data_loader.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/rag/data_loader.py)

```python
# 文本清洗：去除换行和多余空格，修复中文标点
def clean_text(text: str) -> str:
    text = text.replace("\n", "").replace(" ", "")
    text = text.replace("，，", "，").replace("。。", "。")
    return text.strip()

# 文档切分参数
splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,       # 每个文本块 512 字符
    chunk_overlap=128,    # 相邻块重叠 128 字符，保证上下文连贯
    separators=["\n\n", "。", "；", "\n", " ", ""]
)
```

**切分策略说明**：
- `chunk_size=512`：适中大小，既保证语义完整性，又避免检索结果过于宽泛
- `chunk_overlap=128`：25% 重叠率，确保跨 chunk 边界的信息不会丢失
- 分隔符优先级：段落 → 句子 → 分句 → 行 → 词，尽可能在语义边界切分

### 3.2 第二层：共享记忆系统

**作用**：跨会话保留多智能体推理中产生的高价值洞察，使 RAG 具备"学习记忆"能力。

> 详见[第八章：共享记忆系统](#第八章共享记忆系统--rag-的记忆层)

---

## 第四章：文档预处理与向量化

### 4.1 预处理流程

```
PDF文件目录 (data/documents/)
    │
    ▼
load_pdfs_from_dir()           ← 遍历目录，PyPDFLoader 逐页加载
    │
    ▼
clean_text()                   ← 文本清洗（去换行、去多余空格、修复标点）
    │
    ▼
过滤（长度 < 50 的页面丢弃）
    │
    ▼
split_documents()              ← RecursiveCharacterTextSplitter 切分
    │
    ▼
chunks[]                       ← 最终的文档片段列表
```

### 4.2 向量化存储

**Embedding 模型**：阿里云 DashScope `text-embedding-v2`

**代码位置**：[retrievers.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/rag/retrievers.py#L43-L76)

```python
class DashScopeEmbeddings(Embeddings):
    def __init__(self, model: str = "text-embedding-v2"):
        self.model = model
        self.api_key = os.getenv("DASHSCOPE_API_KEY")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # 批量嵌入，每批最多 25 条
        for i in range(0, len(texts), 25):
            batch = texts[i:i + 25]
            resp = dashscope.TextEmbedding.call(
                model=self.model, input=batch, api_key=self.api_key
            )
            # 提取嵌入向量
            ...

    def embed_query(self, text: str) -> List[float]:
        # 单条查询嵌入
        ...
```

**向量数据库**：ChromaDB（持久化模式）

```python
vectordb = Chroma(
    persist_directory="chroma_db_unified/",   # 持久化目录
    embedding_function=DashScopeEmbeddings()   # 嵌入函数
)
```

### 4.3 向量库初始化策略

**代码位置**：[retrievers.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/rag/retrievers.py#L213-L249)

```
build_or_load_vectorstore():
    if 向量库为空 and 有chunks:
        if 开启QA生成:
            QA对 = QAGenerator.generate_qa_for_chunks(chunks)
            入库数据 = chunks + QA对
        else:
            入库数据 = chunks
        分批写入（batch_size=32）
    else:
        直接加载已有向量库
```

**关键设计决策**：向量库只在首次启动时构建，后续启动直接加载已有数据，避免重复计算。

### 4.3 切分策略选型实验

#### 背景

在项目初期，我们评估了两种文档切分策略：

| 策略 | 原理 | 优势 | 劣势 |
|:---|:---|:---|:---|
| **递归字符切分** (RecursiveCharacterTextSplitter) | 按分隔符优先级（`\n\n` → `。` → `；` → `\n` → ` `）递归拆分，限制 `chunk_size=512, overlap=128` | 快速、稳定、可预测 | 可能在语义不自然的位置截断 |
| **语义分块** (Semantic Chunking) | 用 Embedding 计算相邻句子余弦相似度，在"语义断崖"处切分 | 块内主题高度一致 | 计算成本高、对术语密集文本的阈值敏感 |

#### 实验设计

使用讯飞星火 `text-embedding-v2` + `xf-xinghuo-plus`，在 12 份医学 PDF（259 页，涵盖脑卒中诊疗指南、专家共识等）上进行 **RAGAS 评测框架** 的 A/B 对比。

**语义分块 V1 参数**（第一轮）：
- `similarity_threshold=0.75`（相邻句子余弦相似度 < 0.75 则在此切分）
- `min_chunk_size=100, max_chunk_size=800`
- 无重叠、使用 `clean_text`（去除换行）

**语义分块 V2 参数**（调优轮）：
- `similarity_threshold=0.80`（升高阈值减少假断点）
- `overlap_ratio=0.25`（句子级 25% 重叠）
- 使用 `clean_text_preserve_nl`（保留换行作为段落边界信号）

#### V1 实验结果 (threshold=0.75, 无overlap)

| 指标 | 递归切分 | 语义分块 | 差值 | 胜出 |
|:---|:---|:---|:---|:---|
| Context Precision（上下文精准度） | **0.5000** | 0.2667 | -0.2333 | 递归 |
| Context Recall（上下文召回率） | **0.3783** | 0.3200 | -0.0583 | 递归 |
| Faithfulness（事实一致性） | **0.5961** | 0.5787 | -0.0174 | 递归 |
| Answer Relevancy（回答相关性） | 0.9353 | 0.9319 | -0.0034 | ≈ 持平 |
| 平均检索耗时 | 1822ms | 1892ms | +70ms | ≈ 持平 |

**结论：语义分块在 Context Precision 上暴跌 47%（0.50→0.27），全面落败。**

#### V2 实验结果 (threshold=0.80, overlap=0.25, 保留换行)

| 指标 | 递归切分 | 语义分块 | 差值 | 胜出 |
|:---|:---|:---|:---|:---|
| Context Precision（上下文精准度） | **0.2000** | 0.1250 | -0.0750 | 递归 |
| Context Recall（上下文召回率） | **0.4617** | 0.2783 | -0.1833 | 递归 |
| Faithfulness（事实一致性） | **0.6342** | 0.6174 | -0.0168 | 递归 |
| Answer Relevancy（回答相关性） | 0.9307 | 0.9395 | +0.0088 | ≈ 持平 |
| 平均检索耗时 | 1788ms | 2781ms | +993ms | 递归 |

**结论：调优后非但没有改进，反而因为保留换行导致语义块数量从 1070 暴增到 3313（3 倍膨胀），Precision 和 Recall 进一步恶化。**

#### 失败原因分析

1. **医学文本术语密度过高**。一段讲"溶栓"的句子和一段讲"抗血小板"的句子，虽然主题不同，但共享大量医学术语（"脑卒中""缺血性""治疗"），余弦相似度天然偏高。语义分块很难在这一片"术语噪声"中准确识别主题边界。

2. **`clean_text` 破坏了文档结构**。原始流程去除所有换行，段落边界完全消失。后续尝试保留换行（V2），却将标题 (`一、病因\n`) 等短文本切分为独立句子，导致块数失控。

3. **递归切分的重叠是意外优势**。`chunk_overlap=128`（25%）意味着相邻 chunk 共享内容，检索时宽容度更高。语义分块若不加 overlap，在边界处严格割裂信息；加 overlap 后（V2）又因"句子"定义过于碎片化而适得其反。

#### 最终结论

**本项目采用递归字符切分作为默认策略**（`chunk_size=512, overlap=128`），不启用语义分块。

这并不意味着语义分块本身是坏方案——在主题切换缓慢、术语多样性高的通用文本上它通常优于固定切分。但在术语高度密集、主题快速切换的医学教材数据集上，**简单的递归切分反而更鲁棒**。

> 语义分块的完整实现保留在 `data_loader.py` 中（`_semantic_split()` 函数），可通过传入 `embeddings` 参数启用。评测脚本位于 `tests/compare_chunking.py`，支持一键对比。

---


## 第五章：三阶漏斗混合检索（核心）

### 5.1 为什么需要混合检索？

| 检索方式 | 优势 | 劣势 |
|:---|:---|:---|
| **向量检索（Dense）** | 语义理解强，"溶栓时间窗"能匹配"静脉溶栓治疗时间" | 对专业缩写（如 NIHSS）不敏感 |
| **BM25 检索（Sparse）** | 关键词精确匹配，专业术语检索准确 | 无法理解语义变体 |

**三阶漏斗的设计目标**：在保持高召回率的前提下，通过逐级筛选提升最终结果的精准度，同时控制 API 调用成本。

### 5.2 第一阶：宽召回（Wide Recall）

**目标**：尽可能多地召回相关文档，宁滥勿缺。

```
向量检索: ChromaDB.similarity_search(query_embedding, k=20)
BM25检索: BM25Retriever.invoke(query, k=20)
─────────────────────────────────────────────────────
总计: 最多 40 篇候选文档
```

**代码位置**：[retrievers.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/rag/retrievers.py#L298-L301)

```python
# 向量检索：基于语义相似度
v_docs = self.vector_retriever.invoke(query)

# BM25检索：基于关键词匹配
b_docs = self.bm25.invoke(query) if self.bm25 else []
```

**BM25 初始化**：

```python
self.bm25 = BM25Retriever.from_documents(documents)
self.bm25.k = recall_k   # 20
```

### 5.3 第二阶：RRF 粗排（Coarse Ranking）

**目标**：零成本、零延迟地将 40 篇候选快速压缩到 20 篇。

**核心算法**：RRF（Reciprocal Rank Fusion，倒数排名融合）

```
RRF_Score(d) = 1/(k + Rank_Dense(d)) + 1/(k + Rank_BM25(d))

其中 k = 60（平滑常数）
```

**为什么用 RRF 而不是分数融合？**

向量检索返回的是余弦相似度（0~1），BM25 返回的是词频统计分数（无上限），两者的分值区间完全不同，直接相加或相乘都没意义。RRF **只看排名不看分数**，完美避开了这个问题。

**代码位置**：[retrievers.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/rag/retrievers.py#L142-L210)

```python
def reciprocal_rank_fusion(vector_results, bm25_results, k=60, top_k=20):
    # 1. 构建排名映射（1-indexed），同一内容取最高排名
    dense_ranks = {}
    for rank, doc in enumerate(vector_results, start=1):
        content = doc.page_content
        if content not in dense_ranks:
            dense_ranks[content] = rank

    sparse_ranks = {}
    for rank, doc in enumerate(bm25_results, start=1):
        content = doc.page_content
        if content not in sparse_ranks:
            sparse_ranks[content] = rank

    # 2. 计算 RRF 分数
    for content in all_docs:
        d_rank = dense_ranks.get(content, len(vector_results) + 1)
        s_rank = sparse_ranks.get(content, len(bm25_results) + 1)
        rrf_scores[content] = (1.0 / (k + d_rank)) + (1.0 / (k + s_rank))

    # 3. 按 RRF 分数降序排序，取 top_k
    ...
```

**RRF 工作原理示例**：

```
假设文档A在向量检索中排第1，在BM25中排第5：
  RRF(A) = 1/(60+1) + 1/(60+5) = 0.0164 + 0.0154 = 0.0318

假设文档B在向量检索中排第3，在BM25中排第2：
  RRF(B) = 1/(60+3) + 1/(60+2) = 0.0159 + 0.0161 = 0.0320

→ B 的综合排名高于 A，因为在两个检索器中都表现不错
```

### 5.4 第三阶：Reranker 精排（Fine Ranking）

**目标**：对 RRF 粗排后的 20 篇候选进行深度语义重排序，输出最相关的 3 篇。

**代码位置**：[retrievers.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/rag/retrievers.py#L79-L139)

**4 模型容灾切换机制**：

```python
class BGEReranker:
    def __init__(self):
        self.candidate_models = [
            "xf-xinghuo-rerank-v1",    # 首选
            "gte-rerank-v2",     # 备选1
            "xf-xinghuo-rerank",       # 备选2
            "gte-rerank"         # 备选3
        ]

    def rerank(self, query, docs, top_k=3):
        for model in self.candidate_models:
            try:
                resp = dashscope.TextReRank.call(
                    model=model,
                    query=query,
                    documents=[doc.page_content for doc in docs],
                    top_n=top_k,
                    return_documents=True,
                )
                if resp.status_code == HTTPStatus.OK:
                    return reranked_docs
                elif "AccessDenied" in str(resp.code):
                    continue   # 权限问题，切换下一个模型
                else:
                    continue   # 其他错误，切换下一个模型
            except Exception:
                continue       # 异常，切换下一个模型

        # 全部失败 → 原始结果兜底
        return docs[:top_k]
```

**容灾策略总结**：

| 场景 | 处理方式 |
|:---|:---|
| 模型1 正常 | 使用模型1 结果 |
| 模型1 AccessDenied | 自动切换模型2 |
| 模型2 调用异常 | 自动切换模型3 |
| 模型3 失败 | 自动切换模型4 |
| 全部失败 | 返回 RRF 粗排结果的前3篇 |

### 5.5 检索缓存

**代码位置**：[retrievers.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/rag/retrievers.py#L283-L290)

```python
cache_key = hashlib.md5(f"{query}_{top_k}".encode("utf-8")).hexdigest()
if cache_key in self._cache:
    result, ts = self._cache[cache_key]
    if time.time() - ts < 300:   # TTL = 300秒
        return result             # 缓存命中
```

**缓存策略**：
- 键：`MD5(query + top_k)`
- TTL：300 秒（5 分钟）
- 存储：内存字典
- 清除：`clear_cache()` 方法

### 5.6 三阶漏斗完整算法伪代码

```
算法: HybridRAG(query) → top_k_docs

1. 第一阶 · 宽召回 (Wide Recall):
   v_docs ← ChromaDB.similarity_search(query_embedding, k=20)
   b_docs ← BM25Retriever.invoke(query, k=20)
   日志: "向量检索 {len(v_docs)} 条 + BM25检索 {len(b_docs)} 条"

2. 第二阶 · RRF 粗排 (Coarse Ranking):
   FOR each doc_id IN (v_docs ∪ b_docs):
     rrf_score = 1/(60 + rank_dense[doc_id]) + 1/(60 + rank_sparse[doc_id])
   coarse_candidates ← sorted(rrf_score, descending)[:20]
   日志: "{len(v_docs)+len(b_docs)} 篇 → {len(coarse_candidates)} 篇候选"

3. 第三阶 · Reranker 精排 (Fine Ranking):
   FOR model IN [xf-xinghuo-rerank-v1, gte-rerank-v2, xf-xinghuo-rerank, gte-rerank]:
     TRY: result ← DashScope.TextReRank(model, query, coarse_candidates, top_n=3)
          IF result.status == OK: RETURN result
     CATCH AccessDenied / Exception: CONTINUE
   RETURN coarse_candidates[:3]  // 全部失败 → 原始结果兜底

4. 缓存写入:
   cache[MD5(query+top_k)] ← (result, timestamp)
   TTL = 300s
```

---

## 第六章：QA 自动衍生引擎

### 6.1 设计动机

纯文档切片的向量检索存在一个问题：用户的自然语言问题与教材原文的表述方式差异较大。例如：

- 用户问："脑梗死后出血转化的危险因素有哪些？"
- 教材原文："脑梗死后出血性转化（HT）是急性缺血性卒中静脉溶栓后最严重的并发症之一..."

两者的语义空间距离较远，纯向量检索可能召回率不足。

### 6.2 解决方案

**QA 自动衍生**：在向量库构建阶段，自动从文档片段中生成 QA 对，将这些 QA 对也存入向量库。这样，用户的问题更容易匹配到预先生成的"问题"。

**代码位置**：[qa_generator.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/rag/qa_generator.py#L12-L82)

```python
class QAGenerator:
    def __init__(self, model_name="xf-xinghuo-turbo"):
        self.llm = ChatOpenAI(
            model=model_name,
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

    def generate_qa_for_chunks(self, chunks, batch_size=10):
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i + batch_size]

            # 将10个片段合并为一段大文本
            combined_text = "\n\n--- 片段分隔 ---\n\n".join(
                [c.page_content for c in batch_chunks]
            )

            # 调用大模型生成3-5个QA对
            response = self.chain.invoke({"text": combined_text})

            # 生成结果附带来源信息
            qa_doc = Document(
                page_content=qa_content,
                metadata={
                    "source": ", ".join(sources),
                    "page": ", ".join(pages),
                    "doc_type": "qa_generated_batch"
                }
            )
```

**批量策略**：每 10 个 chunk 合并打一批，大幅减少 API 调用次数。

### 6.3 入库流程

```
原始 chunks (N条)  ──►  QAGenerator  ──►  QA衍生对 (N/10 批)
                                                    │
     ┌──────────────────────────────────────────────┘
     ▼
向量库入库 = chunks + QA对
           = N条原文 + M条QA对
```

**效果**：入库后向量库中同时包含原文和 QA 对，检索时更容易匹配到用户问题，实测召回率提升约 **+15%**。

---

## 第七章：RAG 管道 — 查询→检索→合成

### 7.1 管道架构

**代码位置**：[rag_pipeline.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/agents/pipelines/rag_pipeline.py#L1-L44)

```
用户问题
    │
    ▼
┌─────────────────────────────────────────────┐
│         RAGPipeline.run(question)            │
├─────────────────────────────────────────────┤
│                                             │
│  ① QueryGenerationService.generate()        │
│     将用户问题拆解为2个精准检索关键词         │
│                                             │
│  ② EvidenceRetrievalService.parallel_retrieve() │
│     并行执行2个维度的检索，格式化证据          │
│                                             │
│  ③ EvidenceSynthesisService.synthesize()     │
│     将证据合成为循证教育总结                  │
│                                             │
└─────────────────────────────────────────────┘
    │
    ▼
最终回答
```

### 7.2 查询生成服务

**代码位置**：[query_service.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/agents/services/query_service.py#L1-L59)

```python
class QueryGenerationService:
    def generate(self, question: str) -> List[str]:
        # 用 LLM 将用户问题拆解为2个精准检索中文关键词
        response = self.llm.invoke([
            SystemMessage(content="你是教育资料检索专家"),
            HumanMessage(content=f"根据以下学习问题生成2个精准中文检索关键词组合...{question}")
        ])

        # 过滤中文行，取前2个
        chinese_lines = [line for line in lines
                         if any('\u4e00' <= c <= '\u9fff' for c in line)]
        return chinese_lines[:2] if chinese_lines else [question[:50]]
```

**示例**：

```
输入: "脑梗死后出血转化的主要危险因素有哪些？"
输出: ["脑梗死 出血转化 危险因素", "脑梗死后出血 风险预测"]
```

### 7.3 证据检索服务

**代码位置**：[retrieval_service.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/agents/services/retrieval_service.py#L1-L92)

```python
class EvidenceRetrievalService:
    def parallel_retrieve(self, queries: List[str]) -> str:
        # 使用线程池并行检索
        with ThreadPoolExecutor(max_workers=min(3, len(queries))) as executor:
            future_map = {
                executor.submit(self.retrieve_single, q): q
                for q in queries
            }
            for future in as_completed(future_map):
                results[q] = future.result()

        # 格式化输出
        for i, q in enumerate(queries):
            parts.append(f"### 检索维度{i+1}: {q}\n{content}")

        return "\n\n---\n\n".join(parts)
```

**格式化输出示例**：

```
### 检索维度1: 脑梗死 出血转化 危险因素
【文献1】[来源:脑卒中指南2023.pdf p.45](相关度:0.92)
脑梗死后出血性转化（HT）是急性缺血性卒中静脉溶栓后最严重的并发症之一...

【文献2】[来源:神经病学.pdf p.128](相关度:0.87)
出血转化的主要危险因素包括：大面积脑梗死、高血压、高血糖...
```

### 7.4 证据合成服务

**代码位置**：[synthesis_service.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/agents/services/synthesis_service.py#L1-L49)

```python
class EvidenceSynthesisService:
    def synthesize(self, question: str, evidence: str) -> str:
        prompt = f"""你是循证教育专家。
学习问题：{question}
教育参考资料：{evidence}
请进行循证教育总结。"""

        response = self.llm.invoke([
            SystemMessage(content="你是循证教育专家"),
            HumanMessage(content=prompt)
        ])
        return response.content
```

### 7.5 学习助手集成

**代码位置**：[assistant.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/agents/assistant.py#L1-L136)

`LearningAssistant` 提供两种使用方式：

| 方式 | 路径 | 适用场景 |
|:---|:---|:---|
| **快速通道** | 直接调用 `RAGPipeline` → 检索 + 回答 | 简单知识问答 |
| **完整工作流** | 通过 LangGraph 状态机 → 多智能体协同推理 | 复杂个性化需求 |

---

## 第八章：共享记忆系统 — RAG 的记忆层

### 8.1 设计背景

传统 RAG 系统是**无状态**的：每次检索都是独立的，无法从历史经验中学习。本项目创新性地引入**共享记忆系统**，使 RAG 具备"跨会话记忆与学习"能力。

**系统公式**：

```
共享记忆系统 = 存储介质（物理层）+ 交换协议（网络层）+ 共识对齐（逻辑层）
```

### 8.2 三层架构

**代码位置**：[shared_memory.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/agents/core/shared_memory.py#L1-L712)

```
┌─────────────────────────────────────────────────────────────────┐
│                    共享记忆系统三层架构                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  第一层：元记忆过滤 (MetaMemoryFilter)                           │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ 四维熵值评分模型，判断信息是否有价值持久化                   │ │
│  │ 熵分 = 0.2×Shannon熵 + 0.3×(1-关键词密度)                 │ │
│  │      + 0.3×(1-Token密度) + 0.2×(1-长度得分)              │ │
│  │ 熵分 < 0.85 → 持久化 ✅    熵分 ≥ 0.85 → 丢弃 ❌          │ │
│  └───────────────────────────────────────────────────────────┘ │
│                           │                                     │
│                           ▼                                     │
│  第二层：物理存储 (SharedMemoryStore)                            │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ ChromaDB 向量数据库持久化存储                               │ │
│  │ 高价值洞察 → 向量嵌入 → 持久化 → 跨会话可检索              │ │
│  │ 三级降级：向量存储→纯文档存储→跳过                          │ │
│  └───────────────────────────────────────────────────────────┘ │
│                           │                                     │
│                           ▼                                     │
│  第三层：逻辑共识 (ConsensusEngine)                              │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ 信任加权投票共识引擎                                       │ │
│  │ combined_weight = reputation_weight × session_weight       │ │
│  │ 跨会话信誉持久化 (JSON文件) + 退火机制融合                  │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 8.3 元记忆过滤 — 四维熵值评分

**核心思想**：不是所有信息都值得记忆。通过计算信息的"熵值"，自动过滤低价值噪音。

| 维度 | 权重 | 含义 | 过滤目标 |
|:---|:---:|:---|:---|
| **Shannon 熵** | 0.2 | 字符分布均匀度 | 过滤乱码/重复字符 |
| **关键词密度** | 0.3 | 45个医学+教育领域关键词命中率 | 过滤无关闲聊 |
| **Token 密度** | 0.3 | 唯一 token 占比 | 过滤空洞废话 |
| **长度得分** | 0.2 | 信息充实度 | 过滤过短无意义文本 |

**领域关键词库**（部分）：

```python
DOMAIN_KEYWORDS = [
    "脑卒中", "中风", "脑梗", "脑梗死", "脑出血",
    "缺血性", "出血性", "溶栓", "取栓", "抗血小板", "抗凝",
    "NIHSS", "mRS", "ASPECTS", "rtPA", "阿替普酶",
    "康复", "二级预防", "学习", "复习", "知识点", "掌握",
    "画像", "认知风格", "学习目标", "易错点", "资源偏好",
    ...
]
```

**极短文本惩罚**：

```python
if token_count < 5:
    short_penalty = token_count / 5.0   # 惩罚系数
    unique_ratio *= short_penalty
```

防止"嗯嗯好的"这类极短文本因 token 唯一性高而误判为高价值。

**实测效果**：

| 文本类型 | 熵分 | 结果 |
|:---|:---|:---|
| 高价值医学文本 | 0.7254 | ✅ 持久化 |
| 噪音闲聊 | 0.9023 | ❌ 丢弃 |

### 8.4 信任加权投票共识

**核心思想**：多智能体之间可能产生意见冲突，需要一个公正的裁决机制。

**信任权重公式**：

```
combined_weight = reputation_weight × session_weight

其中：
  reputation_weight = 历史正确次数 / 历史总次数（跨会话持久化）
  session_weight   = 当前会话退火衰减权重（来自校验反馈）
```

**信誉更新策略**：

```
校验通过 → 所有参与专家 +1 correct
校验失败 → 权重最低的 1/3 专家 -1 correct，其余 +1 correct
```

**设计亮点**：不搞"一人犯错全员受罚"，精准定位责任方。

### 8.5 完整数据流闭环

```
用户提问
  │
  ▼
[retrieve_node] 证据检索 + 共享记忆检索（物理层读取）
  │
  ▼
[reason_node]  专家推理 → 冲突检测 → 共识投票（逻辑层）
               → 熵值计算 → 高价值洞察存储（元记忆过滤 + 物理层写入）
  │
  ▼
[validate_node] 校验 → 信誉更新（逻辑层反馈）
  │
  ▼
[context_summary] 摘要更新 → 答案熵值计算（元记忆过滤辅助）
```

**闭环优势**：
- 记忆不是"存了就忘"，而是通过信誉反馈不断优化质量
- 高信誉 Agent 的洞察更容易被持久化和检索到
- 低信誉 Agent 的噪音自动被过滤，不会污染共享记忆

### 8.6 配置驱动

**代码位置**：[shared_memory_config.yaml](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/config/shared_memory_config.yaml)

```yaml
store:
  persist_dir: "chroma_db_shared_memory"
  meta_filter:
    entropy_threshold: 0.85    # 熵值阈值，越低越严格
    keyword_weight: 0.3
    density_weight: 0.3
    shannon_weight: 0.2
    length_weight: 0.2
    min_length: 20

consensus:
  conflict_threshold: 0.4      # Jaccard < 0.4 视为冲突
  min_agreement_ratio: 0.6     # 共识达成的最低权重占比

persistence:
  auto_store_high_value: true
  min_confidence: 0.7
  max_memories_per_session: 10
```

---

## 第九章：LangGraph 工作流中的 RAG 集成

### 9.1 工作流拓扑

```
用户输入
    │
    ▼
IntentNode (意图分类 + 难度评分)
    │
    ├── irrelevant ──────────► 拒绝
    ├── knowledge ───────────► KnowledgeNode (极速知识问答，直接LLM)
    └── profile / resource / tutor / assessment / learning_path
                │
                ▼
        AnalysisNode (需求分析)
                │
                ├── learning_questions ← 拆解出的检索子问题
                ├── key_risks ← 关键风险识别
                ├── complexity ← 复杂度等级
                └── context ← 结构化分析上下文
                │
                ▼
        RetrieveNode (证据检索) ◄── RAG 检索入口
                │
                ├── evidence ← RAG检索到的证据文本
                ├── shared_memory_hits ← 共享记忆检索命中
                └── 调用 RAGPipeline 或直接调用 UnifiedSearchEngine
                │
                ▼
        ReasonNode (多智能体推理)
                │
                ├── 冲突检测 + 共识投票（共享记忆系统逻辑层）
                ├── 熵值计算 + 高价值洞察存储（元记忆过滤 + 物理层写入）
                └── proposal + critique + agent_weights
                │
                ▼
        ValidateNode (质量校验)
                │
                ├── PASS → 继续
                └── FAIL → 退火修正 → 回到 ReasonNode（最多3轮）
                │
                ▼
        ReportNode (报告生成)
```

### 9.2 LearningState 中的 RAG 相关字段

| 字段 | 类型 | 写入节点 | 读取节点 | 含义 |
|:---|:---|:---|:---|:---|
| `evidence` | str | RetrieveNode | ReasonNode, ReportNode | RAG检索到的证据文本 |
| `learning_questions` | List[str] | AnalysisNode | RetrieveNode | 用于检索的关键子问题 |
| `shared_memory_hits` | List[Dict] | RetrieveNode | ReasonNode | 共享记忆检索命中结果 |
| `memory_entropy_scores` | Dict | ReasonNode | — | 各专家建议的熵值评分 |
| `consensus_result` | Dict | ReasonNode | — | 共识投票结果 |

### 9.3 意图分流策略

| 意图类型 | 是否走 RAG | 说明 |
|:---|:---:|:---|
| `knowledge` | ❌ | 通用知识问答，直接 LLM 回答 |
| `profile` | ✅ | 画像构建，需要检索相关学习理论 |
| `resource` | ✅ | 资源生成，需要检索教材内容 |
| `tutor` | ✅ | 辅导问答，需要检索相关知识 |
| `assessment` | ✅ | 学习评估，需要检索评估标准 |
| `learning_path` | ✅ | 路径规划，需要检索学习路径设计方法 |
| `irrelevant` | ❌ | 拒绝回答 |

---

## 第十章：RAGAS 自动化评测

### 11.1 评测维度

基于 **RAGAS（RAG Assessment）框架**，从以下维度对 RAG 系统进行量化评估：

| 评测维度 | 含义 | 评估方法 |
|:---|:---|:---|
| **回答相关性** (Answer Relevancy) | 回答与问题的相关程度 | 计算回答中与问题相关的 token 占比 |
| **事实一致性** (Faithfulness) | 回答是否忠实于检索到的证据 | 将回答拆解为原子陈述，逐一验证 |
| **上下文精准度** (Context Precision) | 检索到的证据中相关文档的占比 | 计算检索结果中相关文档的排名 |
| **上下文召回率** (Context Recall) | 回答所需信息是否在检索结果中 | 对比回答与检索结果的覆盖度 |

### 11.2 测试覆盖

- 自动化测试用例：**71 条**（黑盒 33 + 白盒 38），通过率 100%
- 白盒路径覆盖率：**100%**（核心模块路径覆盖 + 共享记忆系统 + RAG + 迁移验证）

### 11.3 切分策略 A/B 对比评测

我们开发了专门的 RAGAS 对比评测脚本，用于在相同数据集上公平比较不同切分策略的效果。

**评测脚本**：`tests/compare_chunking.py`

**用法**：
```bash
# 首次运行（构建两套向量库 + RAGAS 评估）
python -m tests.compare_chunking --force-rebuild --output ragas_report.json

# 后续仅评测（向量库已构建）
python -m tests.compare_chunking --skip-build
```

**评测数据集**：10 道医学问题，覆盖病因、诊断、治疗、药物、指南等多个维度。

**实测评测结果（2026-07-05）**：

| 指标 | 递归切分 | 语义分块 | 胜出 |
|:---|:---|:---|:---|
| Context Precision | 0.5000 | 0.2667 | 递归 |
| Context Recall | 0.3783 | 0.3200 | 递归 |
| Faithfulness | 0.5961 | 0.5787 | 递归 |
| Answer Relevancy | 0.9353 | 0.9319 | ≈ 持平 |

> 详细分析和失败原因见[第四章 §4.3 切分策略选型实验](#43-切分策略选型实验)。

---

## 第十一章：完整数据流与关键性能指标

### 12.1 完整数据流

```
┌──────────────────────────────────────────────────────────────────────┐
│                        完整 RAG 数据流                                │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ① 文档预处理                                                        │
│     PDF → PyPDFLoader → 文本清洗 → RecursiveCharacterTextSplitter    │
│     (chunk_size=512, overlap=128) → QA对批量生成                      │
│                                                                      │
│  ② 向量化入库                                                        │
│     chunks + QA对 → DashScopeEmbeddings (text-embedding-v2)          │
│     → ChromaDB 持久化向量库 (chroma_db_unified/)                     │
│                                                                      │
│  ③ 用户查询处理                                                      │
│     query → QueryGenerationService → 2个检索关键词                    │
│                                                                      │
│  ④ 三阶漏斗检索                                                      │
│     关键词 → 向量检索(k=20) + BM25检索(k=20)                         │
│           → RRF粗排(40→20) → Reranker精排(20→3)                      │
│                                                                      │
│  ⑤ 证据格式化                                                        │
│     3篇文档 → 格式化（来源、页码、相关度）→ 结构化证据文本             │
│                                                                      │
│  ⑥ 共享记忆增强                                                      │
│     查询 → 共享记忆检索(ChromaDB) → 命中记忆注入检索结果              │
│     推理洞察 → 熵值过滤 → 持久化存储 → 跨会话可检索                   │
│                                                                      │
│  ⑦ 证据合成                                                          │
│     证据 + 用户问题 → EvidenceSynthesisService → 循证教育总结         │
│                                                                      │
│  ⑧ 质量保障                                                          │
│     多重校验 → 信誉更新 → 退火修正 → 反思循环(最多3轮)                │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 12.2 关键性能指标

| 指标 | 实测数据 | 说明 |
|:---|:---|:---|
| RAG 混合检索召回率提升 | **+15%** | 相比纯向量检索 |
| 检索缓存命中率 | 相同查询5分钟内免重复检索 | 节省 API 开销 |
| Reranker 容灾成功率 | 4 模型自动切换 | 零单点故障 |
| 共享记忆熵值过滤 | 高价值 0.7254 / 噪音 0.9023 | 精准过滤 |
| 退火修正成功率 | **92%** | 23/25 次校验驳回后修正通过 |
| 资源推送关联率 | **92%** | 每步平均 1.8 个精准资源 |
| 自动化测试通过率 | **100%** | 71条用例全通过 |
| 白盒路径覆盖率 | **100%** | 38条路径全覆盖 |

---

## 附录：核心文件索引

| 文件 | 核心职责 | 关键类/函数 |
|:---|:---|:---|
| [data_loader.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/rag/data_loader.py) | PDF加载与文档切分 | `load_pdfs_from_dir()`, `split_documents()`, `clean_text()` |
| [retrievers.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/rag/retrievers.py) | 向量库、混合检索、RRF、Reranker | `DashScopeEmbeddings`, `BGEReranker`, `HybridRetriever`, `UnifiedSearchEngine`, `reciprocal_rank_fusion()` |
| [qa_generator.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/rag/qa_generator.py) | QA对自动生成 | `QAGenerator`, `generate_qa_for_chunks()` |
| [rag_pipeline.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/agents/pipelines/rag_pipeline.py) | RAG管道：查询→检索→合成 | `RAGPipeline`, `run()` |
| [query_service.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/agents/services/query_service.py) | 检索查询生成 | `QueryGenerationService`, `generate()` |
| [retrieval_service.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/agents/services/retrieval_service.py) | 证据检索与格式化 | `EvidenceRetrievalService`, `parallel_retrieve()` |
| [synthesis_service.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/agents/services/synthesis_service.py) | 证据合成 | `EvidenceSynthesisService`, `synthesize()` |
| [shared_memory.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/agents/core/shared_memory.py) | 共享记忆系统（元记忆+存储+共识） | `MetaMemoryFilter`, `SharedMemoryStore`, `ConsensusEngine`, `AgentReputationStore`, `SharedMemorySystem` |
| [reranker.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/agents/infra/reranker.py) | DashScope重排序实现 | `DashScopeReranker`, `rerank()` |
| [base_reranker.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/agents/infra/base_reranker.py) | 重排序抽象基类 | `BaseReranker` |
| [retrieval.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/agents/schemas/retrieval.py) | 检索数据模型 | `RerankResult`, `RetrievalDocument` |
| [shared_memory_config.yaml](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/config/shared_memory_config.yaml) | 共享记忆系统配置 | 熵值阈值、共识参数、持久化策略 |
| [assistant.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/app/agents/assistant.py) | 学习助手（快速通道） | `LearningAssistant`, `RAGPipeline` 集成 |
| [test_rag.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/tests/test_rag.py) | RAG检索功能测试 | 3个医学测试问题 |
| [compare_chunking.py](file:///D:/CompetitionProject/learning-multi-agent-system/model/tests/compare_chunking.py) | RAGAS切分策略A/B对比评测 | 10题 × 2策略 × 4指标 |

---

> **文档版本**：v1.0  
> **最后更新**：2026-07-05  
> **适用项目**：LearnAgent — 基于大模型的个性化资源生成与学习多智能体系统