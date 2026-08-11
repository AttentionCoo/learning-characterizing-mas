import hashlib
import logging
import os
import re
import time
from http import HTTPStatus
from typing import List

import chromadb.utils.embedding_functions as ef_module
import dashscope
from dotenv import load_dotenv
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

# 阻止 ChromaDB 自动初始化内置 ONNX 向量模型，所有向量统一由 Qwen 生成。
original_default = ef_module.DefaultEmbeddingFunction
ef_module.DefaultEmbeddingFunction = lambda: None

from langchain_chroma import Chroma

from app.config.qwen import (
    get_qwen_api_key,
    get_qwen_embedding_dimension,
    get_qwen_embedding_model,
    get_qwen_rerank_model,
)

from .data_loader import load_pdfs_from_dir, split_documents
from .qa_generator import QAGenerator
from .labels import COLLECTIONS, partition_chunks_by_collection
from .router import classify_evidence_type, route_collections
from .scoring import MedicalEvidenceReranker


load_dotenv(override=True)
logger = logging.getLogger(__name__)

_QWEN_EMBEDDING_MODEL = get_qwen_embedding_model()
_QWEN_EMBEDDING_DIMENSION = get_qwen_embedding_dimension()
_QWEN_VECTORSTORE_SUFFIX = re.sub(
    r"[^a-zA-Z0-9_-]+", "_", _QWEN_EMBEDDING_MODEL
)
QWEN_COLLECTION_NAME = "medical-guides-qwen"

CONFIG = {
    "persist_dir": os.getenv("QWEN_VECTORSTORE_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data",
        "vector_stores",
        f"chroma_qwen_{_QWEN_VECTORSTORE_SUFFIX}_{_QWEN_EMBEDDING_DIMENSION}",
    ),
    "multi_persist_dir": os.getenv("QWEN_MULTI_VECTORSTORE_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data",
        "vector_stores",
        f"chroma_multi_{_QWEN_VECTORSTORE_SUFFIX}_{_QWEN_EMBEDDING_DIMENSION}",
    ),
    "docs_dir": os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data",
        "documents",
    ),
    "top_k_per_store": 4,
    "enable_qa_generation": True,
    "recall_k": 20,
    "rrf_top_k": 20,
    "top_k_final": 3,
}


class QwenEmbeddings(Embeddings):
    """百炼文本向量模型，文档与查询固定使用同一模型和维度。"""

    def __init__(
        self,
        *,
        model: str | None = None,
        dimension: int | None = None,
        batch_size: int = 10,
        max_retries: int = 3,
    ):
        self.api_key = get_qwen_api_key()
        self.model = model or get_qwen_embedding_model()
        self.dimension = dimension or get_qwen_embedding_dimension()
        self.batch_size = batch_size
        self.max_retries = max_retries
        logger.info(
            "✅ Qwen Embedding 初始化完成: %s (%sd)",
            self.model,
            self.dimension,
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embed(texts, text_type="document")

    def embed_query(self, text: str) -> List[float]:
        return self._embed([text], text_type="query")[0]

    def _embed(self, texts: List[str], *, text_type: str) -> List[List[float]]:
        if not texts:
            return []

        vectors: List[List[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = [
                text if text.strip() else " "
                for text in texts[start:start + self.batch_size]
            ]
            response = self._call_with_retry(batch, text_type=text_type)
            items = list(response.output["embeddings"])
            items.sort(key=lambda item: item.get("text_index", 0))

            batch_vectors = [item["embedding"] for item in items]
            if len(batch_vectors) != len(batch):
                raise RuntimeError(
                    f"Qwen Embedding 返回数量异常: 期望 {len(batch)}，"
                    f"实际 {len(batch_vectors)}"
                )
            for vector in batch_vectors:
                if len(vector) != self.dimension:
                    raise RuntimeError(
                        f"Qwen Embedding 维度异常: 期望 {self.dimension}，"
                        f"实际 {len(vector)}"
                    )
            vectors.extend(batch_vectors)

        return vectors

    def _call_with_retry(self, texts: List[str], *, text_type: str):
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = dashscope.TextEmbedding.call(
                    model=self.model,
                    input=texts,
                    dimension=self.dimension,
                    text_type=text_type,
                    api_key=self.api_key,
                )
                if response.status_code == HTTPStatus.OK:
                    return response
                last_error = RuntimeError(
                    f"{getattr(response, 'code', '')}: "
                    f"{getattr(response, 'message', '')}"
                )
            except Exception as exc:
                last_error = exc

            if attempt < self.max_retries:
                logger.warning(
                    "⚠️ Qwen Embedding 调用失败（%s/%s），准备重试: %s",
                    attempt,
                    self.max_retries,
                    last_error,
                )
                time.sleep(attempt)

        raise RuntimeError(f"Qwen Embedding 调用失败: {last_error}") from last_error


class QwenReranker:
    def __init__(self, top_k: int = 5):
        self.api_key = get_qwen_api_key(required=False)
        self.model = get_qwen_rerank_model()
        self.top_k = top_k
        self.enabled = bool(self.api_key)
        if not self.enabled:
            logger.info("ℹ️ 未配置 QWEN_API_KEY/DASHSCOPE_API_KEY，Rerank 精排已禁用")

    def rerank(
        self,
        query: str,
        docs: List[Document],
        top_k: int | None = None,
    ) -> List[Document]:
        if not docs:
            return []

        actual_top_k = top_k if top_k is not None else self.top_k
        if not self.enabled:
            return docs[:actual_top_k]

        try:
            logger.info(f"🚀 使用模型 {self.model} 进行 Rerank...")
            response = dashscope.TextReRank.call(
                model=self.model,
                query=query,
                documents=[doc.page_content for doc in docs],
                top_n=actual_top_k,
                return_documents=True,
                api_key=self.api_key,
            )
            if response.status_code != HTTPStatus.OK:
                raise RuntimeError(f"{response.code}: {response.message}")

            reranked = []
            for item in response.output.results:
                original_doc = docs[item.index]
                original_doc.metadata["relevance_score"] = item.relevance_score
                reranked.append(original_doc)
            logger.info(
                f"✅ Rerank 成功 (使用 {self.model})，"
                f"{len(docs)} → {len(reranked)} 条"
            )
            return reranked
        except Exception as exc:
            # 兜底修复：rerank API 失败时不再退化为原始 embedding 顺序，
            # 而是走 RRF 归一化 + 医学评分规则排序，保住医学排序。
            logger.error(
                f"❌ Qwen Rerank 调用失败，使用 RRF 归一化 + 医学评分兜底: {exc}"
            )
            fallback = MedicalEvidenceReranker(top_k=actual_top_k, api_key=None)
            return fallback.fallback_rerank(query, docs, top_k=actual_top_k)


def reciprocal_rank_fusion(
    vector_results: List[Document],
    bm25_results: List[Document],
    k: int = 60,
    top_k: int = 5,
) -> List[Document]:
    """
    倒数排名融合（RRF, Reciprocal Rank Fusion）

    完全不看原始相似度分数，只看文档在各自列表中的排名。
    完美避开了 Dense 向量分值 和 BM25 分值区间不同的问题。

    公式:
        RRF_Score(d) = 1/(k + Rank_Dense(d)) + 1/(k + Rank_BM25(d))

    参数:
        vector_results: 向量检索结果列表（按相似度降序）
        bm25_results:  BM25 检索结果列表（按得分降序）
        k:             平滑常数，默认 60
        top_k:         最终返回的文档数量

    返回:
        按 RRF 分数降序排列的 top_k 文档，每篇文档的 metadata 中写入 rrf_score
    """
    if not vector_results and not bm25_results:
        return []

    # 构建排名映射（1-indexed），同一内容取最高排名
    dense_ranks: dict[str, int] = {}
    for rank, doc in enumerate(vector_results, start=1):
        content = doc.page_content
        if content not in dense_ranks:
            dense_ranks[content] = rank

    sparse_ranks: dict[str, int] = {}
    for rank, doc in enumerate(bm25_results, start=1):
        content = doc.page_content
        if content not in sparse_ranks:
            sparse_ranks[content] = rank

    # 收集所有唯一文档
    all_docs: dict[str, Document] = {}
    for doc in vector_results + bm25_results:
        content = doc.page_content
        if content not in all_docs:
            all_docs[content] = doc

    # 未在某个列表中出现的文档，给予一个较大的默认排名
    dense_fallback = len(vector_results) + 1
    sparse_fallback = len(bm25_results) + 1

    # 计算 RRF 分数
    rrf_scores: dict[str, float] = {}
    for content in all_docs:
        d_rank = dense_ranks.get(content, dense_fallback)
        s_rank = sparse_ranks.get(content, sparse_fallback)
        rrf_scores[content] = (1.0 / (k + d_rank)) + (1.0 / (k + s_rank))

    # 按 RRF 分数降序排序
    sorted_contents = sorted(rrf_scores, key=lambda c: rrf_scores[c], reverse=True)

    # 构建结果
    result = []
    for content in sorted_contents[:top_k]:
        doc = all_docs[content]
        score = round(rrf_scores[content], 6)
        doc.metadata["rrf_score"] = score
        doc.metadata["relevance_score"] = score  # 向后兼容
        result.append(doc)

    return result


def build_or_load_vectorstore(chunks, persist_dir: str, enable_qa: bool = False):
    logger.info(f"🔌 [VectorStore] 连接: {persist_dir}")
    embeddings = QwenEmbeddings()
    expected_metadata = {
        "embedding_provider": "qwen",
        "embedding_model": embeddings.model,
        "embedding_dimension": embeddings.dimension,
    }

    import chromadb

    client = chromadb.PersistentClient(path=persist_dir)
    vectordb = Chroma(
        client=client,
        collection_name=QWEN_COLLECTION_NAME,
        collection_metadata=expected_metadata,
        embedding_function=embeddings,
    )
    count = vectordb._collection.count()
    actual_metadata = vectordb._collection.metadata or {}

    if count > 0:
        incompatible = {
            key: (actual_metadata.get(key), value)
            for key, value in expected_metadata.items()
            if actual_metadata.get(key) != value
        }
        if incompatible:
            raise RuntimeError(
                "向量库模型标识不一致，请使用与当前 Qwen Embedding 配置匹配的"
                f"独立目录。差异: {incompatible}"
            )
        logger.info(f"✅ Qwen 向量库已有 {count} 条数据")
        return vectordb

    if not chunks:
        logger.warning("⚠️ Qwen 向量库为空，且没有可供入库的文档")
        return vectordb

    docs_to_insert = chunks
    if enable_qa:
        logger.info(
            f"⚠️ Qwen 向量库为空，准备为 {len(chunks)} 条切片生成扩展 QA 对..."
        )
        qa_docs = QAGenerator(tier="turbo").generate_qa_for_chunks(chunks)
        docs_to_insert = chunks + qa_docs
        logger.info(
            f"入库总计：{len(chunks)} 条原文 + {len(qa_docs)} 条 QA 对 "
            f"= {len(docs_to_insert)} 条"
        )

    batch_size = 32
    total_docs = len(docs_to_insert)
    write_start = time.time()
    logger.info(f"📝 开始写入 Qwen 向量库，共 {total_docs} 条")

    for start in range(0, total_docs, batch_size):
        batch = docs_to_insert[start:start + batch_size]
        try:
            vectordb.add_documents(documents=batch)
        except Exception as exc:
            raise RuntimeError(
                f"Qwen 向量库写入失败（起始索引 {start}）: {exc}"
            ) from exc

        processed = min(start + batch_size, total_docs)
        elapsed = time.time() - write_start
        speed = processed / elapsed if elapsed > 0 else 0
        logger.info(
            f"  Qwen Embedding 进度: {processed}/{total_docs} | "
            f"耗时 {elapsed:.1f}s | 速度 {speed:.1f} 条/s"
        )

    logger.info(
        f"✅ Qwen 向量库写入完成，共 {vectordb._collection.count()} 条，"
        f"耗时 {time.time() - write_start:.1f}s"
    )
    return vectordb


class HybridRetriever:
    """
    三阶漏斗混合检索器

    第一阶（宽召回）: 向量检索 + BM25 各召回 recall_k 篇
    第二阶（粗排）  : RRF 倒数排名融合，快速选出 rrf_top_k 篇候选
    第三阶（精排）  : QwenReranker 深度语义重排序，选出 top_k_final 篇喂给 LLM

    优势：
    - RRF 零成本、零延迟，快速将 40 篇候选压缩到 20 篇
    - Reranker 只需处理 20 篇而非 40 篇，节省 API 开销
    - 精排结果质量远高于纯 RRF 或纯 Reranker
    """

    def __init__(
        self,
        vectordb,
        documents,
        recall_k=20,
        rrf_top_k=20,
        top_k_final=3,
    ):
        self.recall_k = recall_k
        self.rrf_top_k = rrf_top_k
        self.top_k_final = top_k_final
        self.vector_retriever = (
            vectordb.as_retriever(search_kwargs={"k": recall_k})
            if vectordb is not None
            else None
        )
        self.reranker = QwenReranker(top_k=top_k_final)

        if documents and len(documents) > 0:
            self.bm25 = BM25Retriever.from_documents(documents)
            self.bm25.k = recall_k
        else:
            self.bm25 = None
            logger.warning("⚠️ [HybridRetriever] 文档为空，BM25 未初始化")

        self._cache: dict = {}
        self._cache_ttl = 300

    def search(self, query: str, top_k_final: int | None = None) -> List[Document]:
        top_k_final = top_k_final or self.top_k_final
        cache_key = hashlib.md5(f"{query}_{top_k_final}".encode("utf-8")).hexdigest()
        if cache_key in self._cache:
            result, ts = self._cache[cache_key]
            if time.time() - ts < self._cache_ttl:
                logger.info(f"⚡ [Cache Hit] 跳过重复检索: {query[:50]}...")
                return result
            del self._cache[cache_key]

        logger.info(f"🔍 [HybridRetriever] 三阶漏斗检索: {query[:60]}...")

        # ═══════════════════════════════════════════
        # 第一阶：宽召回 (Wide Recall)
        # ═══════════════════════════════════════════
        try:
            v_docs = (
                self.vector_retriever.invoke(query)
                if self.vector_retriever is not None
                else []
            )
        except Exception as exc:
            logger.error(f"❌ Qwen 向量检索失败，继续尝试 BM25: {exc}")
            v_docs = []

        try:
            b_docs = self.bm25.invoke(query) if self.bm25 else []
        except Exception as exc:
            logger.error(f"❌ BM25 检索失败: {exc}")
            b_docs = []

        if not v_docs and not b_docs:
            logger.warning("⚠️ 检索结果为空")
            self._cache[cache_key] = ([], time.time())
            return []

        logger.info(
            f"📥 [第一阶·宽召回] 向量检索 {len(v_docs)} 条 + BM25检索 {len(b_docs)} 条"
        )

        # ═══════════════════════════════════════════
        # 第二阶：RRF 粗排 (Coarse Ranking)
        # ═══════════════════════════════════════════
        coarse_candidates = reciprocal_rank_fusion(
            v_docs, b_docs, k=60, top_k=self.rrf_top_k
        )

        logger.info(
            f"🎯 [第二阶·RRF粗排] {len(v_docs) + len(b_docs)} 篇 → {len(coarse_candidates)} 篇候选"
        )

        # 日志：RRF 粗排前三
        for i, doc in enumerate(coarse_candidates[:3]):
            score = doc.metadata.get("rrf_score", "?")
            logger.info(
                f"  RRF #{i+1}: score={score} | {doc.page_content[:60]}..."
            )

        # ═══════════════════════════════════════════
        # 第三阶：Reranker 精排 (Fine Ranking)
        # ═══════════════════════════════════════════
        result = self.reranker.rerank(query, coarse_candidates, top_k=top_k_final)

        logger.info(
            f"🏆 [第三阶·Reranker精排] {len(coarse_candidates)} 篇 → {len(result)} 篇最终结果"
        )

        # 日志：最终精排结果
        for i, doc in enumerate(result):
            score = doc.metadata.get("relevance_score", "?")
            rrf_score = doc.metadata.get("rrf_score", "?")
            source = doc.metadata.get("source", "?")
            logger.info(
                f"  Final #{i+1}: rerank={score} | rrf={rrf_score} "
                f"| {source} | {doc.page_content[:60]}..."
            )

        self._cache[cache_key] = (result, time.time())
        return result

    def clear_cache(self):
        count = len(self._cache)
        self._cache.clear()
        if count > 0:
            logger.info(f"🗑️ [HybridRetriever] 清空 {count} 条检索缓存")


class UnifiedSearchEngine:
    def __init__(self, persist_dir: str, top_k: int, docs_dir=None):
        logger.info("🔧 初始化 UnifiedSearchEngine...")

        self.docs_dir = (
            docs_dir
            or os.getenv("MEDICAL_DOCS_DIR")
            or CONFIG.get("docs_dir", "./data/documents")
        )
        logger.info(f"📂 文档目录: {self.docs_dir}")

        try:
            raw_docs = load_pdfs_from_dir(self.docs_dir)
        except Exception as exc:
            logger.error(f"❌ 加载文档失败: {exc}")
            raw_docs = []

        logger.info(
            "🔀 使用混合分块: 规则边界保护 → 递归切分(512/128) → 合并小块"
        )
        self.chunks = split_documents(raw_docs) if raw_docs else []

        if self._check_vectorstore_empty(persist_dir):
            logger.info("🆕 Qwen 向量库为空，开始构建...")
        else:
            logger.info("✅ Qwen 向量库已存在；原始文档仍用于初始化 BM25")

        try:
            self.vectorstore = build_or_load_vectorstore(
                self.chunks,
                persist_dir,
                enable_qa=bool(CONFIG.get("enable_qa_generation", False)),
            )
        except Exception as exc:
            self.vectorstore = None
            logger.error(
                "❌ Qwen 向量库初始化失败，检索引擎将继续使用 BM25: %s",
                exc,
            )
        self.retriever = HybridRetriever(
            self.vectorstore,
            self.chunks,
            recall_k=CONFIG.get("recall_k", 20),
            rrf_top_k=CONFIG.get("rrf_top_k", 20),
            top_k_final=top_k,
        )

    def _check_vectorstore_empty(self, persist_dir: str) -> bool:
        """检查 ChromaDB 向量库是否为空（不存在或无数据）"""
        if not os.path.exists(persist_dir) or not os.path.isdir(persist_dir):
            return True
        try:
            import chromadb
            client = chromadb.PersistentClient(path=persist_dir)
            collection = client.get_collection(QWEN_COLLECTION_NAME)
            return collection.count() == 0
        except Exception:
            return True

    def search(self, query: str, top_k_final: int | None = None) -> List[Document]:
        try:
            logger.info(f"🔍 执行检索: {query[:60]}...")
            docs = self.retriever.search(query, top_k_final=top_k_final)
            logger.info(f"🏆 检索完成，命中 {len(docs)} 条")
            return docs
        except Exception as e:
            logger.error(f"❌ 检索失败: {e}")
            return []

    def clear_cache(self):
        self.retriever.clear_cache()


# ═══════════════════════════════════════════════════════════════
# Multi-Collection 物理隔离检索引擎（v2.7）
#
# 链路：
#   问题 → Clinical Decision Planner（决策节点）
#        → Evidence Router（证据类型）
#        → 路由到隔离 collection（anatomy/guideline/etiology/treatment/prevention）
#            → 各库内 向量+BM25 混合检索
#                → 跨库 RRF 融合
#                    → BGEReranker 医学评分重排（语义+类型+权威+时效+主题+干预+惩罚）
#                        → Mismatch Filter → 输出
#
# 核心收益：把"事后过滤"变成"入口约束"——血脂指南 chunk 物理上不在
# anatomy collection 里，连候选集都进不了。
# ═══════════════════════════════════════════════════════════════


def build_multi_collection_vectorstore(
    chunks_by_collection: dict,
    persist_dir: str,
    client=None,
    embeddings=None,
):
    """
    按主题把带标签的 chunks 写入 5 个隔离 collection。

    每个 collection 使用独立 collection_name（anatomy/guideline/etiology/
    treatment/prevention），共享同一个 PersistentClient 目录。
    已有数据的 collection 跳过写入（幂等重建）。
    """
    import chromadb

    embeddings = embeddings or QwenEmbeddings()
    expected_metadata = {
        "embedding_provider": "qwen",
        "embedding_model": embeddings.model,
        "embedding_dimension": embeddings.dimension,
    }
    client = client or chromadb.PersistentClient(path=persist_dir)

    created = {}
    for collection_name in COLLECTIONS:
        chunks = chunks_by_collection.get(collection_name, [])
        vectordb = Chroma(
            client=client,
            collection_name=collection_name,
            collection_metadata=expected_metadata,
            embedding_function=embeddings,
        )
        count = vectordb._collection.count()
        if count > 0:
            logger.info(
                f"✅ collection[{collection_name}] 已有 {count} 条，跳过写入"
            )
            created[collection_name] = vectordb
            continue
        if not chunks:
            logger.info(f"ℹ️ collection[{collection_name}] 为空且无候选 chunk")
            created[collection_name] = vectordb
            continue

        batch_size = 32
        total = len(chunks)
        logger.info(
            f"📝 collection[{collection_name}] 写入 {total} 条 chunk..."
        )
        for start in range(0, total, batch_size):
            batch = chunks[start:start + batch_size]
            try:
                vectordb.add_documents(documents=batch)
            except Exception as exc:
                raise RuntimeError(
                    f"collection[{collection_name}] 写入失败（起始索引 {start}）: {exc}"
                ) from exc
            processed = min(start + batch_size, total)
            logger.info(
                f"  collection[{collection_name}] 进度: {processed}/{total}"
            )
        created[collection_name] = vectordb
    return created


class MultiCollectionSearchEngine:
    """
    决策驱动路由 + 物理隔离知识库 + 医学规则重排 的统一检索入口。

    对外保持与 UnifiedSearchEngine 兼容的接口：
        - .chunks         所有带标签的 chunk（main.py 统计文档列表用）
        - .search(query, top_k_final=None, top_k=None) -> List[Document]
        - .clear_cache()
        - .get_collection_stats() -> dict  （每库数量，诊断/测试用）
    """

    def __init__(
        self,
        persist_dir: str | None = None,
        top_k: int = 3,
        docs_dir=None,
        enable_qa: bool = False,
    ):
        logger.info("🔧 初始化 MultiCollectionSearchEngine（5 库物理隔离）...")
        self.top_k = top_k
        self.docs_dir = (
            docs_dir
            or os.getenv("MEDICAL_DOCS_DIR")
            or CONFIG.get("docs_dir", "./data/documents")
        )
        self.persist_dir = persist_dir or CONFIG.get("multi_persist_dir")
        self.recall_k = CONFIG.get("recall_k", 20)
        self.rrf_top_k = CONFIG.get("rrf_top_k", 20)
        logger.info(f"📂 文档目录: {self.docs_dir}")
        logger.info(f"🗄️  向量库目录: {self.persist_dir}")

        # 1. 加载 + 分块
        try:
            raw_docs = load_pdfs_from_dir(self.docs_dir)
        except Exception as exc:
            logger.error(f"❌ 加载文档失败: {exc}")
            raw_docs = []
        self.chunks = split_documents(raw_docs) if raw_docs else []
        logger.info(f"🔀 分块完成: {len(self.chunks)} 个 chunk")

        # 2. chunk 级结构化标签 + 分库
        self.collection_chunks = partition_chunks_by_collection(self.chunks)

        # 3. 构建/加载各库（Chroma + BM25）
        self.stores: dict = {}
        self._init_stores(enable_qa=enable_qa)

        # 4. 医学评分重排器（BGEReranker API 优先，RRF 归一化兜底）
        self.reranker = MedicalEvidenceReranker(
            top_k=top_k,
            api_key=get_qwen_api_key(required=False),
            model=get_qwen_rerank_model(),
        )

        self._cache: dict = {}
        self._cache_ttl = 300
        logger.info("✅ MultiCollectionSearchEngine 初始化完成")
        self.log_collection_stats()

    # ── 构建 ──
    def _init_stores(self, enable_qa: bool = False):
        """每个 collection 一个 Chroma + BM25。空库自动写入（幂等）。"""
        try:
            vectorstores = build_multi_collection_vectorstore(
                self.collection_chunks,
                self.persist_dir,
            )
        except Exception as exc:
            logger.error(
                f"❌ 多库向量库初始化失败，检索将仅使用 BM25: {exc}"
            )
            vectorstores = {c: None for c in COLLECTIONS}

        for collection in COLLECTIONS:
            chunks = self.collection_chunks.get(collection, [])
            bm25 = None
            if chunks:
                try:
                    bm25 = BM25Retriever.from_documents(chunks)
                    bm25.k = self.recall_k
                except Exception as exc:
                    logger.warning(
                        f"⚠️ collection[{collection}] BM25 初始化失败: {exc}"
                    )
            self.stores[collection] = {
                "vectorstore": vectorstores.get(collection),
                "bm25": bm25,
                "chunks": chunks,
            }

    def log_collection_stats(self):
        for collection in COLLECTIONS:
            store = self.stores.get(collection, {})
            chunks = store.get("chunks", [])
            vectorstore = store.get("vectorstore")
            vec_count = (
                vectorstore._collection.count()
                if vectorstore is not None
                else 0
            )
            logger.info(
                f"  📚 collection[{collection}]: {len(chunks)} chunks | "
                f"向量 {vec_count} 条"
            )

    def get_collection_stats(self) -> dict:
        """每库 chunk 数（测试与诊断用）。"""
        return {
            collection: len(self.stores.get(collection, {}).get("chunks", []))
            for collection in COLLECTIONS
        }

    # ── 检索 ──
    def search(
        self,
        query: str,
        top_k_final: int | None = None,
        evidence_type: str | None = None,
        decision_nodes=None,
        top_k: int | None = None,
    ) -> List[Document]:
        """
        决策驱动检索主入口。

        参数:
            query: 用户查询（临床语言）
            top_k_final / top_k: 最终返回条数（兼容两种调用方）
            evidence_type: 证据类型；None 时自动路由（Evidence Router）
            decision_nodes: Clinical Decision Planner 输出的决策节点（可空）

        返回:
            按 medical_score 降序的 top-k 文档
        """
        actual_top_k = top_k_final or top_k or self.top_k
        cache_key = hashlib.md5(
            f"{query}_{actual_top_k}_{evidence_type or ''}_{(decision_nodes or [])}"
            .encode("utf-8")
        ).hexdigest()
        if cache_key in self._cache:
            result, ts = self._cache[cache_key]
            if time.time() - ts < self._cache_ttl:
                logger.info(f"⚡ [MultiCollection] 缓存命中: {query[:50]}...")
                return result
            del self._cache[cache_key]

        logger.info(f"🔍 [MultiCollection] 检索: {query[:60]}...")

        # 1. Evidence Router：判定证据类型
        if evidence_type is None:
            evidence_type = classify_evidence_type(query, decision_nodes)
        # 2. 路由到隔离 collection（入口约束）
        #    主库 + 相关库（如 treatment+guideline），实现"跨 collection RRF 融合"；
        #    anatomy 等无相关库的类型仍严格隔离——血脂 chunk 物理上进不了候选集。
        collections = route_collections(evidence_type, strict=False)
        logger.info(
            f"🚦 [路由] evidence_type={evidence_type} → collections={collections}"
        )

        # 3. 各库内 向量 + BM25 混合检索（宽召回）
        v_docs: List[Document] = []
        b_docs: List[Document] = []
        for collection in collections:
            store = self.stores.get(collection)
            if store is None:
                continue
            vectorstore = store.get("vectorstore")
            if vectorstore is not None:
                try:
                    v_docs.extend(
                        vectorstore.as_retriever(
                            search_kwargs={"k": self.recall_k}
                        ).invoke(query)
                    )
                except Exception as exc:
                    logger.error(
                        f"❌ collection[{collection}] 向量检索失败: {exc}"
                    )
            bm25 = store.get("bm25")
            if bm25 is not None:
                try:
                    b_docs.extend(bm25.invoke(query))
                except Exception as exc:
                    logger.error(
                        f"❌ collection[{collection}] BM25 检索失败: {exc}"
                    )

        if not v_docs and not b_docs:
            logger.warning("⚠️ 所有目标 collection 检索结果为空")
            self._cache[cache_key] = ([], time.time())
            return []

        logger.info(
            f"📥 [宽召回] 向量 {len(v_docs)} 条 + BM25 {len(b_docs)} 条"
        )

        # 4. 跨库 RRF 粗排
        coarse = reciprocal_rank_fusion(
            v_docs, b_docs, k=60, top_k=self.rrf_top_k
        )
        logger.info(f"🎯 [RRF 粗排] {len(v_docs) + len(b_docs)} → {len(coarse)} 条")

        # 5. Mismatch Filter：剔除主题不匹配的 chunk（防御性，入口约束已兜底）
        filtered = [
            doc for doc in coarse
            if doc.metadata.get("collection") in collections
        ]
        if filtered:
            coarse = filtered

        # 6. BGEReranker 医学评分重排
        result = self.reranker.rerank(
            query,
            coarse,
            evidence_type=evidence_type,
            top_k=actual_top_k,
        )

        for i, doc in enumerate(result):
            logger.info(
                f"  Final #{i+1}: medical={doc.metadata.get('medical_score', '?')} "
                f"| {doc.metadata.get('source', '?')} "
                f"p.{doc.metadata.get('page', '?')} "
                f"[{doc.metadata.get('subtopic_name', doc.metadata.get('subtopic', '?'))}] "
                f"{doc.page_content[:50]}..."
            )

        self._cache[cache_key] = (result, time.time())
        return result

    def clear_cache(self):
        count = len(self._cache)
        self._cache.clear()
        if count > 0:
            logger.info(f"🗑️ [MultiCollection] 清空 {count} 条检索缓存")
