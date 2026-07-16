# 向量库持久化打造 — 知识点总结

## 1. 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    向量库持久化体系                        │
├────────────────────────┬────────────────────────────────┤
│    主知识库 (RAG)        │     共享记忆库 (SharedMemory)    │
│  chroma_db_unified/     │  chroma_db_shared_memory/       │
│  ─────────────────      │  ────────────────────────       │
│  来源: PDF 文档解析       │  来源: 多 Agent 对话中提取的知识   │
│  构建: build_or_load()  │  构建: SharedMemoryStore.store()│
│  用途: 医学知识检索增强    │  用途: 跨会话知识沉淀与复用        │
│  触发: 系统启动/手动脚本   │  触发: 每次 Agent 产生有价值输出    │
├────────────────────────┴────────────────────────────────┤
│              底层: ChromaDB (PersistentClient)            │
│              Embedding: XfyunEmbeddings (1024d BGE)       │
│              过滤: MetaMemoryFilter (熵值 0.85)            │
│              共识: ConsensusEngine (冲突解决)              │
│              信誉: AgentReputationStore (JSON 持久化)      │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 核心类详解

### 2.1 XfyunEmbeddings (retrievers.py)

双通道 Embedding 引擎：讯飞云端 API 优先，本地 BGE 兜底。

```
调用链:
  embed_query / embed_documents
    → 讯飞 API (HMAC-SHA256 签名)
    → 失败? → _xfyun_dead = True
    → _get_fallback_embeddings()
    → 本地 BGE-large-zh-v1.5 (1024d, CPU)
```

**关键设计：**

| 机制 | 实现 |
|------|------|
| 签名鉴权 | `_embed_once()` 内 HMAC-SHA256，`X-App-Id` 等 4 个头 |
| QPS 节流 | `_throttle()` 类方法，`_last_request_time` 类变量，间隔 >= 0.7s |
| 错误分级 | `_FATAL_ERROR_CODES` 字典，11200/11201/10001 等不可重试 |
| 批量降级 | 单条失败 -> 整批统一降级，避免维度混用 |
| 重试策略 | 指数退避 `1.5 x (attempt + 1)`，最多 4 次 |

**BGE 模型类级缓存（本次优化）：**

```python
# 修复前：实例变量，每次 XfyunEmbeddings() 都重新加载 1.3GB
self._fallback_embeddings = None

# 修复后：类变量，全进程共享一份
_fallback_embeddings_cache = None   # 类级别
_fallback_embeddings_failed = False # 失败标记

@classmethod
def _get_fallback_embeddings(cls):
    if cls._fallback_embeddings_cache is not None:
        return cls._fallback_embeddings_cache  # 缓存命中，0ms
    if cls._fallback_embeddings_failed:
        return None                            # 已知失败，不重试
    # 首次加载...
    cls._fallback_embeddings_cache = HuggingFaceBgeEmbeddings(...)
    return cls._fallback_embeddings_cache
```

**效果：** 第 2 次 `XfyunEmbeddings()` 从 185s -> 0s。

---

### 2.2 SharedMemoryStore (shared_memory.py)

多 Agent 共享知识记忆库，实现跨会话的知识沉淀。

```
生命周期:
  store(content, agent_id, metadata) -> MetaMemoryFilter.should_persist()
    -> 通过? -> ChromaDB.add() -> 持久化到磁盘
    -> 过滤? -> 返回 None（噪音丢弃）

  retrieve(query, top_k) -> ChromaDB.query() -> 返回 top_k 条记忆
```

**关键组件：**

| 组件 | 类 | 职责 |
|------|-----|------|
| 过滤 | `MetaMemoryFilter` | 熵值打分，< 0.85 阈值才持久化 |
| 共识 | `ConsensusEngine` | 多 Agent 建议冲突时投票决议 |
| 信誉 | `AgentReputationStore` | 正确/错误计数，JSON 文件持久化 |
| 适配 | `_ChromaEmbeddingFunction` | 桥接 XfyunEmbeddings -> ChromaDB 接口 |

**ChromaDB 签名兼容问题（本次修复）：**

```python
# 修复前：ChromaDB 0.4.16+ 拒绝
def __call__(self, texts):  # ❌ 参数名不匹配

# 修复后：通过 ChromaDB 签名校验
def __call__(self, input):  # ✅ 参数名必须为 input
```

ChromaDB 0.4.16+ 使用 `inspect.signature()` 校验 `EmbeddingFunction.__call__` 的参数名，必须严格为 `input`。

---

### 2.3 MetaMemoryFilter (shared_memory.py)

基于信息熵的智能过滤器，决定哪些 Agent 输出值得持久化。

**熵值计算公式（4 维加权）：**

```
熵分 = 0.3 x keyword_score + 0.3 x density_score + 0.2 x shannon_score + 0.2 x length_score

其中:
  keyword_score  = 中文医学术语命中率（溶栓、卒中、NIHSS 等）
  density_score  = 信息密度（有效字符 / 总字符）
  shannon_score  = 字符分布的香农熵（归一化）
  length_score   = 文本长度归一化（0.165 ~ 0.77 区间）

阈值: 0.85（低于阈值 -> 有价值，持久化）
```

**实际效果：**

| 内容 | 熵分 | 结果 |
|------|------|------|
| "rtPA 静脉溶栓时间窗为发病 4.5 小时内..." | 0.7254 | ✅ 保留 |
| "NIHSS 评分是评估卒中严重程度的重要工具..." | 0.5215 | ✅ 保留 |
| "嗯嗯好的知道了谢谢老师" | 0.9023 | ❌ 丢弃 |

---

### 2.4 ConsensusEngine (shared_memory.py)

当多个 Agent 对同一问题给出不同建议时，通过投票机制解决冲突。

```python
advices = {
    "agent_a": "建议从 Willis 环解剖开始...",
    "agent_b": "建议从 Willis 环解剖开始...",  # 与 a 一致
    "agent_c": "跳过解剖，直接学指南...",       # 与 a/b 冲突
}

result = ConsensusEngine().resolve_conflict(advices)
# -> winning_agents: ["agent_a", "agent_b"]  (多数派)
# -> reached: False (未达 100% 共识)
# -> 阈值: 0.4 (40% 以上即可形成多数)
```

---

### 2.5 AgentReputationStore (shared_memory.py)

追踪每个 Agent 的信誉分数，JSON 文件持久化。

```python
store = AgentReputationStore(config={"reputation_file": "agent_reputation.json"})
store.update("agent_a", was_correct=True)   # 正确 +1
store.update("agent_a", was_correct=False)  # 错误 +1
score = store.get_score("agent_a")          # 0.5 (1/2)
```

**持久化格式：**
```json
{
  "agent_a": {"correct": 10, "incorrect": 5},
  "agent_b": {"correct": 8,  "incorrect": 2}
}
```

---

### 2.6 build_or_load_vectorstore (retrievers.py)

主知识库的构建与加载入口，自动判断是否需要重建。

```python
def build_or_load_vectorstore(chunks, persist_dir, enable_qa=True):
    """
    策略:
      1. 检查 persist_dir 是否存在
      2. 存在 -> 直接加载（ChromaDB PersistentClient）
      3. 不存在 -> 构建新库
         a. 文档 chunk -> embedding
         b. 可选: QA 对生成（增强检索召回）
         c. 持久化到磁盘
    """
```

---

## 3. 维度一致性保证

**核心原则：** 所有向量库必须使用同一份 Embedding 模型（1024d BGE），否则检索结果不可比。

```
XfyunEmbeddings (1024d BGE)
  ├── _ChromaEmbeddingFunction 包装
  │     ├── SharedMemoryStore -> chroma_db_shared_memory
  │     └── build_or_load_vectorstore -> chroma_db_unified
  └── 直接调用
        ├── embed_query() -> 检索用
        └── embed_documents() -> 入库用
```

**配置开关：** `.env` 中 `XFYUN_EMBEDDING_ENABLED=false` 跳过讯飞云端，全程走 BGE，保证维度统一。

---

## 4. 持久化目录结构

```
data/vector_stores/
├── chroma_db_unified/          # 主知识库
│   ├── chroma.sqlite3          # 元数据索引
│   └── {uuid}/                 # 向量数据
│       ├── data_level0.bin
│       ├── header.bin
│       ├── length.bin
│       └── link_lists.bin
│
├── chroma_db_shared_memory/    # 共享记忆库
│   ├── chroma.sqlite3
│   └── {uuid}/
│       └── ...
│
└── agent_reputation.json       # Agent 信誉数据
```

---

## 5. 测试体系

### 5.1 test_shared_memory.py（单元 + 集成）

| 测试 | 验证点 |
|------|--------|
| MetaMemoryFilter | 高价值保留、低价值丢弃、批量过滤 |
| ConsensusEngine | 冲突解决、多数派识别 |
| AgentReputationStore | 信誉评分、JSON 持久化 |
| BatchFilter | 批量过滤正确性 |
| FullIntegration | 端到端：存储 -> 检索 -> 共识 -> 信誉 |

### 5.2 test_vectorstore_persistence.py（持久化专项）

| 模块 | 验证点 |
|------|--------|
| 主知识库构建与加载 | 5 条文档 -> 构建 -> 持久化文件 -> 重新加载 count=5 -> 检索命中 |
| 共享记忆库存储与检索 | 存储 2 条 -> 语义检索命中 -> 噪音过滤 |
| 跨会话持久化 | 新会话加载旧数据 -> 检索旧数据 -> 写入新数据 |
| 维度一致性 | 所有向量库维度 = 1024 |
| 元记忆过滤器 | 熵值计算正确性 |
| 共识引擎与信誉存储 | 共识决议 + 信誉持久化 |

---

## 6. 常见问题与解决方案

| 问题 | 原因 | 解决 |
|------|------|------|
| ChromaDB 初始化失败 | `__call__(texts)` 参数名不匹配 | 改为 `__call__(input)` |
| BGE 模型重复加载 | 实例变量无缓存 | 改为类级别 `_fallback_embeddings_cache` |
| 向量维度不一致 | 旧库用 ONNX-384d，新库用 BGE-1024d | 删除旧库目录重建 |
| 运行时静默"假死" | BGE 首次下载 ~3 分钟无日志 | main.py 启动时 `preload_fallback()` |
| Windows 清理报 PermissionError | ChromaDB 文件锁 | 重启进程后清理，或忽略 |

---

## 7. 关键代码路径

| 文件 | 职责 |
|------|------|
| `app/rag/retrievers.py` | XfyunEmbeddings、build_or_load_vectorstore |
| `app/agents/core/shared_memory.py` | SharedMemoryStore、MetaMemoryFilter、ConsensusEngine、AgentReputationStore |
| `app/main.py` | 系统初始化，BGE 预加载 |
| `app/rag/qa_generator.py` | QA 对生成（增强检索召回） |
| `scripts/build_vectorstore.py` | 手动构建向量库脚本 |
| `tests/test_shared_memory.py` | 共享记忆单元测试 |
| `tests/test_vectorstore_persistence.py` | 持久化集成测试 |
| `data/vector_stores/` | 向量库持久化目录 |
| `.env` | `XFYUN_EMBEDDING_ENABLED` 等开关 |