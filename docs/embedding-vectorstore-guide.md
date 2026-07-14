# Embedding 与向量库维度指南

## 目录

- [1. 背景概念](#1-背景概念)
- [2. 项目中的两套向量库](#2-项目中的两套向量库)
- [3. Embedding 模型与维度](#3-embedding-模型与维度)
- [4. 维度不匹配的根因](#4-维度不匹配的根因)
- [5. 修复方案](#5-修复方案)
- [6. 日常运维](#6-日常运维)

---

## 1. 背景概念

### 1.1 Embedding（文本向量化）

Embedding 是将文本转换为固定长度浮点数数组（向量）的过程。语义相近的文本，向量在空间中的距离也相近。

```
"脑卒中急性期的溶栓治疗" → [0.023, -0.451, 0.789, ..., 0.312]  (1024 或 2560 个 float)
```

### 1.2 维度（Dimension）

向量数组的长度，由 Embedding 模型决定。**不同模型产出的向量维度不同，无法混用**：

| 模型 | 维度 | 来源 |
|------|------|------|
| 讯飞官方 Embedding API | 2560 | 云端 HTTP 接口 |
| BAAI/bge-large-zh-v1.5 | 1024 | 本地 CPU 推理 |
| all-MiniLM-L6-v2 (ONNX) | 384 | ChromaDB 内置默认 |

### 1.3 ChromaDB 向量库

ChromaDB 是一个向量数据库，语义检索的本质是：将用户查询转为向量，在库中找到距离最近的 K 个文档向量。

**关键约束**：一个 ChromaDB 集合（Collection）创建后，其维度就固定了。后续写入的任何向量必须与创建时的维度一致，否则报错：

```
Embedding dimension 1024 does not match collection dimensionality 2560
```

### 1.4 为什么维度会变

本项目的 Embedding 类 `XfyunEmbeddings` 封装了**自动降级**逻辑：

```
                 ┌─ 讯飞 API 正常 ──→ 2560d
                 │
XfyunEmbeddings ─┤
                 │                 ┌─ 成功 → BGE 1024d
                 └─ 讯飞 API 失败 ──┤
                                   └─ 失败 → ChromaDB 默认 ONNX 384d
```

一旦降级触发，产出的向量维度就变了，与旧数据冲突。

---

## 2. 项目中的两套向量库

本项目有 **两个独立的 ChromaDB 持久化集合**，用途不同但共享同一个 Embedding 类：

### 2.1 主知识库（RAG 文档检索）

| 属性 | 值 |
|------|-----|
| 代码位置 | `model/app/rag/retrievers.py` → `build_or_load_vectorstore()` |
| 持久化路径 | `model/data/vector_stores/chroma_db_unified` |
| 数据来源 | `model/data/documents/` 下的 PDF 文档 |
| 检索方式 | 三阶漏斗：向量检索 + BM25 → RRF 融合 → Reranker 精排 |
| Embedding 类 | `XfyunEmbeddings` |

**创建方式**（正确，显式传了 embedding_function）：

```python
# retrievers.py:404
vectordb = Chroma(
    persist_directory=persist_dir,
    embedding_function=embeddings,  # ← XfyunEmbeddings 实例，维度由 LangChain 管理
)
```

### 2.2 共享记忆库（Agent 经验持久化）

| 属性 | 值 |
|------|-----|
| 代码位置 | `model/app/agents/core/shared_memory.py` → `SharedMemoryStore` |
| 持久化路径 | `model/data/vector_stores/chroma_db_shared_memory` |
| 数据来源 | 多 Agent 推理过程中产生的高价值洞察 |
| 检索方式 | 向量相似度检索（余弦距离） |
| Embedding 类 | `XfyunEmbeddings` |

**创建方式**（修复前有 Bug，未传 embedding_function）：

```python
# shared_memory.py:202（修复前）
self._collection = client.get_or_create_collection(
    name=self.COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"}
    # ❌ 没有 embedding_function → ChromaDB 使用默认 ONNX 384d
)
```

### 2.3 两套库的数据流关系

```
PDF 文档                        Agent 推理
    │                               │
    ▼                               ▼
UnifiedSearchEngine            SharedMemoryStore
    │                               │
    ▼                               ▼
chroma_db_unified              chroma_db_shared_memory
(主知识检索)                   (跨会话经验复用)
    │                               │
    └───────────┬───────────────────┘
                ▼
         HybridRetriever
         (三阶漏斗检索)
                │
                ▼
           LLM 生成回答
```

---

## 3. Embedding 模型与维度

### 3.1 XfyunEmbeddings 的内部机制

```python
# retrievers.py:41-259
class XfyunEmbeddings(Embeddings):
    """讯飞文本向量化（官方 HTTP 接口，2560 维）。

    环境变量：
    - XFYUN_EMBEDDING_ENABLED=false  可直接跳过讯飞，全程使用本地 BGE
    - XFYUN_EMBEDDING_URL            覆盖默认服务地址
    """

    BASE_URL = "https://emb-cn-huabei-1.xf-yun.com/"  # 讯飞官方接口
    MAX_CHARS = 2500          # 单次输入上限
    _MIN_INTERVAL = 0.7       # QPS 节流间隔（免费档 ≈2 QPS）
```

**三种运行模式**：

| 模式 | 触发条件 | 维度 | 速度 | 稳定性 |
|------|----------|------|------|--------|
| 讯飞在线 | `XFYUN_EMBEDDING_ENABLED=true` 且 API 正常 | 2560 | 慢（网络+节流） | 低（QPS=2 极易限流） |
| BGE 降级 | 讯飞 API 连续失败 4 次后自动切换 | 1024 | 快（本地 CPU） | 高（无外部依赖） |
| BGE 直连 | `XFYUN_EMBEDDING_ENABLED=false` | 1024 | 快（本地 CPU） | 高 |

### 3.2 BGE 降级模型

```python
# retrieves.py:101-116
def _get_fallback_embeddings(self):
    self._fallback_embeddings = HuggingFaceBgeEmbeddings(
        model_name="BAAI/bge-large-zh-v1.5",  # 中文优化，1.3GB
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
```

### 3.3 ChromaDB 默认 ONNX 模型（all-MiniLM-L6-v2）

ChromaDB 内置了一个轻量 ONNX 模型作为默认 EmbeddingFunction。当 `get_or_create_collection` 没有收到 `embedding_function` 参数时，会自动使用它（384d）。

项目中 `retrievers.py:16-18` 尝试 monkey-patch 禁用它：

```python
import chromadb.utils.embedding_functions as ef_module
ef_module.DefaultEmbeddingFunction = lambda: None
```

但这个 patch 只在 `retrievers.py` 被导入后才生效，`shared_memory.py` 独立初始化时可能先于 patch 执行，导致 ChromaDB 仍使用默认 ONNX 模型。

---

## 4. 维度不匹配的根因

### 4.1 问题场景重现

```
时间线：

T1: 服务首次启动
    - XfyunEmbeddings 正常 → 讯飞 2560d
    - SharedMemoryStore.get_or_create_collection() 创建集合
    - ❌ 没传 embedding_function → ChromaDB 用默认 ONNX 决定维度？
    - 实际上：如果 monkey-patch 先生效，集合无默认 embedding
    - 第一条 add(embeddings=[2560d向量]) 成功，集合维度锁定为 2560

T2: 讯飞 QPS 限流（免费档只有 2 QPS，Agent 批量推理极易触发）
    - XfyunEmbeddings 降级 → BGE 1024d
    - store() 调用 embed_query() → 产出 1024d 向量
    - collection.add(embeddings=[1024d向量])
    - ❌ ERROR: Embedding dimension 1024 != collection dimensionality 2560

T3: 降级存储回退
    - 捕获异常，走"纯文档存储"路径
    - collection.add(documents=[...])  # 没传 embeddings
    - ChromaDB 尝试用默认 ONNX 模型自动 embedding
    - ❌ ERROR: Embedding dimension 384 != collection dimensionality 2560
```

### 4.2 三条错误日志的精确对应

从你的日志：

```
WARNING: ⚠️ 向量存储失败，降级为纯文档存储: Embedding dimension 1024 does not match collection dimensionality 2560
```
→ BGE-large-zh-v1.5（1024d）试图写入讯飞（2560d）创建的集合

```
ERROR: ❌ 存储完全失败: Embedding dimension 384 does not match collection dimensionality 2560
```
→ ChromaDB 默认 ONNX（384d）试图写入讯飞（2560d）创建的集合

```
ERROR: ❌ 检索完全失败: Embedding dimension 384 does not match collection dimensionality 2560
```
→ 检索时 query_embedding 降级为 BGE(1024d) 或 ONNX(384d)，与集合 2560d 冲突

### 4.3 Bug 本质

```
              ┌─────────────────────────────────┐
              │  同一个 XfyunEmbeddings 实例     │
              │  在不同时间点可能产出不同维度！   │
              │                                  │
              │  讯飞在线 → 2560d                │
              │  讯飞限流 → BGE 1024d            │
              │  默认回退 → ONNX 384d            │
              └─────────────────────────────────┘
                          │
                          ▼
              ┌─────────────────────────────────┐
              │  ChromaDB 集合维度一旦创建就锁定 │
              │  后续所有写入必须同维度          │
              └─────────────────────────────────┘
                          │
                          ▼
              ┌─────────────────────────────────┐
              │  维度不一致 → 全部读写失败       │
              └─────────────────────────────────┘
```

---

## 5. 修复方案

### 5.1 代码修复（已完成）

**文件 1：`model/app/agents/core/shared_memory.py`**

三处改动：

**① 新增 `_ChromaEmbeddingFunction` 包装器**（第 175-194 行）

```python
class _ChromaEmbeddingFunction:
    """将 LangChain 的 XfyunEmbeddings 包装为 ChromaDB 原生 EmbeddingFunction。

    ChromaDB 的 get_or_create_collection 在未传入 embedding_function 时会使用默认
    ONNX 模型（all-MiniLM-L6-v2, 384d），与讯飞 embedding（2560d）或 BGE 降级
    （1024d）维度冲突，导致后续写入/检索全量失败。

    此包装器确保 ChromaDB 集合的维度与 XfyunEmbeddings 当前有效模型一致，
    同时保证降级路径（add 时不传 embeddings）也能产出正确维度的向量。
    """

    def __init__(self, xfyun_embeddings):
        self._xfyun = xfyun_embeddings

    def __call__(self, texts):
        """ChromaDB 要求: (List[str]) -> List[List[float]]"""
        if isinstance(texts, str):
            return [self._xfyun.embed_query(texts)]
        return self._xfyun.embed_documents(texts)
```

**② `get_or_create_collection` 显式传入 `embedding_function`**（第 226-230 行）

```python
# 修复前
self._collection = client.get_or_create_collection(
    name=self.COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"},
)

# 修复后
self._collection = client.get_or_create_collection(
    name=self.COLLECTION_NAME,
    embedding_function=self._ef,        # ← 显式传入包装器
    metadata={"hnsw:space": "cosine"},
)
```

**③ 降级存储路径优化**（第 302-313 行）

维度冲突时跳过无效重试，直接给出修复指引：

```python
if "dimension" in err_msg.lower() or "dimensionality" in err_msg.lower():
    logger.error(
        f"[shared_memory] ❌ 向量维度冲突，无法存储: {err_msg}\n"
        f"   原因：ChromaDB 集合维度与当前 embedding 模型输出维度不一致。\n"
        f"   解决：删除向量库目录后重启服务，统一使用一种 embedding 模型。\n"
        f"   向量库路径: {self.persist_dir}\n"
        f"   建议：在 .env 中设置 XFYUN_EMBEDDING_ENABLED=false 全程使用本地 BGE（1024d）"
    )
    return None  # 直接返回，不浪费重试
```

**文件 2：`model/.env`**

新增配置项，主动关闭讯飞 embedding，避开 QPS=2 限制：

```bash
# 5. 文本向量化（embedding）模式
# false = 全程使用本地 BGE-large-zh-v1.5（1024d），无需讯飞额度，无 QPS 限制
# true  = 优先使用讯飞云端 embedding（2560d），失败时自动降级 BGE
# 讯飞免费档 QPS≈2，高并发下极易触发限流 → 建议 false
XFYUN_EMBEDDING_ENABLED=false
```

**文件 3：`.env.example`**

同步注释，默认推荐值改为 `false`。

### 5.2 为什么设置 `XFYUN_EMBEDDING_ENABLED=false`

| 对比维度 | 讯飞在线 (true) | 本地 BGE (false) |
|----------|-----------------|-------------------|
| 向量维度 | 2560 | 1024 |
| QPS 限制 | **≈2**（极易触发限流） | 无限制 |
| 延迟 | 网络 RTT + 节流等待(0.7s/条) | 纯本地 CPU 推理 |
| 依赖 | 需要讯飞 embedding 服务额度 | 仅需首次下载模型(~1.3GB) |
| 稳定性 | 低（网络/限流/欠费） | 高 |
| 中文语义质量 | 高 | 高（BGE 中文专项优化） |

**结论**：免费档 QPS=2 意味着每秒最多 2 次请求。而 Agent 多专家并行推理时，embedding 请求可能在短时间大量集中触发，瞬间超限。选择 `false` 用本地 BGE 是最稳定的方案。

### 5.3 部署前必须执行的步骤

旧的向量库已被讯飞 2560d "污染"，必须删除后重建：

```bash
# 在服务器上执行（路径相对于 model/ 目录）
rm -rf model/data/vector_stores/chroma_db_unified
rm -rf model/data/vector_stores/chroma_db_shared_memory
```

重启服务后，系统会自动：
1. 加载 BGE-large-zh-v1.5 模型（首次需下载 ~1.3GB）
2. 用 1024d 统一维度创建/重建两个 ChromaDB 集合
3. 重新从 PDF 文档构建主知识库向量
4. 共享记忆库从零开始积累

---

## 6. 日常运维

### 6.1 健康检查

```bash
# 检查向量库状态
ls -la model/data/vector_stores/chroma_db_unified/
ls -la model/data/vector_stores/chroma_db_shared_memory/

# 检查日志中的 embedding 初始化信息
grep "embedding_function" logs/app.log
# 预期看到: embedding_function=_ChromaEmbeddingFunction

grep "BGE 兜底" logs/app.log
# 如果 XFYUN_EMBEDDING_ENABLED=false，应该看到:
# "ℹ️ XFYUN_EMBEDDING_ENABLED=false，跳过讯飞 embedding，直接使用本地 BGE"
```

### 6.2 重建向量库

当文档更新后：

```bash
cd model
python scripts/build_vectorstore.py
```

### 6.3 切换回讯飞 Embedding

如果后续升级了讯飞 embedding 额度（QPS 提升），可以切回：

```bash
# .env 中修改
XFYUN_EMBEDDING_ENABLED=true

# 必须删除旧库重建（1024d → 2560d 维度变了）
rm -rf model/data/vector_stores/chroma_db_unified
rm -rf model/data/vector_stores/chroma_db_shared_memory

# 重启服务
```

### 6.4 维度冲突排查口诀

```
日志出现 "dimension" + "does not match" → 三件事：
1. 确认当前使用的 embedding 模型（grep XFYUN_EMBEDDING_ENABLED .env）
2. 删除两个向量库目录
3. 重启服务，让它用统一维度重建
```
