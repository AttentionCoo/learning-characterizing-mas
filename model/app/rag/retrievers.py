import logging
import os
import sys
import hashlib
import time
from typing import List
from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from http import HTTPStatus
import dashscope
from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever

# Monkey-patch chromadb to prevent ONNX embedding function initialization
import sys
import chromadb.utils.embedding_functions as ef_module
original_default = ef_module.DefaultEmbeddingFunction
ef_module.DefaultEmbeddingFunction = lambda: None

from langchain_chroma import Chroma

from .data_loader import load_pdfs_from_dir, split_documents
from .qa_generator import QAGenerator


load_dotenv()
logger = logging.getLogger(__name__)

CONFIG = {
    "persist_dir": os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_db_unified"),
    "docs_dir": os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "documents"),
    "top_k_per_store": 4,
    "enable_qa_generation": True,
    # 三阶漏斗参数
    "recall_k": 20,         # 第一阶：每个检索器宽召回数量
    "rrf_top_k": 20,        # 第二阶：RRF 粗排后保留的候选数
    "top_k_final": 3,       # 第三阶：Reranker 精排后最终返回数
}


class DashScopeEmbeddings(Embeddings):
    def __init__(self, model: str = "text-embedding-v2"):
        self.model = model
        self.api_key = os.getenv("DASHSCOPE_API_KEY")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        result = []
        for i in range(0, len(texts), 25):
            batch = texts[i:i + 25]
            resp = dashscope.TextEmbedding.call(
                model=self.model,
                input=batch,
                api_key=self.api_key,
            )
            if resp.status_code == HTTPStatus.OK:
                for item in resp.output["embeddings"]:
                    result.append(item["embedding"])
            else:
                raise ValueError(f"DashScope embedding 失败: {resp.code} - {resp.message}")
        return result

    def embed_query(self, text: str) -> List[float]:
        resp = dashscope.TextEmbedding.call(
            model=self.model,
            input=text,
            api_key=self.api_key,
        )
        if resp.status_code == HTTPStatus.OK:
            return resp.output["embeddings"][0]["embedding"]
        else:
            raise ValueError(f"DashScope embedding 失败: {resp.code} - {resp.message}")


class BGEReranker:
    def __init__(self, top_k: int = 5):
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            logger.warning("⚠️ 未找到 DASHSCOPE_API_KEY，Rerank 功能已禁用")
        self.top_k = top_k
        self.candidate_models = [
            "qwen-rerank-v1",
            "gte-rerank-v2", 
            "qwen-rerank",
            "gte-rerank"
        ]
        self.enabled = bool(self.api_key)

    def rerank(self, query: str, docs: List[Document], top_k: int = None) -> List[Document]:
        if not docs:
            return []

        actual_top_k = top_k if top_k is not None else self.top_k

        if not self.enabled:
            logger.info(f"ℹ️  Rerank 功能已禁用，直接返回原始结果")
            return docs[:actual_top_k]

        for model in self.candidate_models:
            try:
                logger.info(f"🚀 尝试使用模型 {model} 进行 Rerank...")
                doc_contents = [doc.page_content for doc in docs]
                resp = dashscope.TextReRank.call(
                    model=model,
                    query=query,
                    documents=doc_contents,
                    top_n=actual_top_k,
                    return_documents=True,
                    api_key=self.api_key,
                )
                if resp.status_code == HTTPStatus.OK:
                    reranked = []
                    for item in resp.output.results:
                        original_doc = docs[item.index]
                        original_doc.metadata["relevance_score"] = item.relevance_score
                        reranked.append(original_doc)
                    logger.info(f"✅ Rerank 成功 (使用 {model})，{len(docs)} → {len(reranked)} 条")
                    return reranked
                else:
                    if "AccessDenied" in str(resp.code) or resp.code == "AccessDenied":
                        logger.warning(f"⚠️  模型 {model} 遭遇权限阻碍 (AccessDenied)，尝试切换下一个...")
                        continue
                    else:
                        logger.warning(f"⚠️  Rerank API 失败 ({model}, {resp.code}): {resp.message}，尝试切换下一个...")
                        continue
            except Exception as e:
                error_str = str(e)
                if "AccessDenied" in error_str:
                    logger.warning(f"⚠️  模型 {model} 遭遇混杂因素阻碍 (AccessDenied)，尝试切换下一个...")
                    continue
                else:
                    logger.warning(f"⚠️  模型 {model} 调用异常: {type(e).__name__} - {error_str}，尝试切换下一个...")
                    continue

        logger.error("❌ 所有百炼 Rerank 模型均鉴权失败或调用异常，启用原始结果兜底。")
        return docs[:actual_top_k]


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
    embeddings = DashScopeEmbeddings(model="text-embedding-v2")
    vectordb = Chroma(
        persist_directory=persist_dir,
        embedding_function=embeddings,
    )
    try:
        count = vectordb._collection.count()
        if count == 0 and chunks:
            docs_to_insert = chunks
            if enable_qa:
                logger.info(f"⚠️ 向量库为空，准备为 {len(chunks)} 条切片生成扩展QA对...")
                qa_gen = QAGenerator()
                qa_docs = qa_gen.generate_qa_for_chunks(chunks)
                docs_to_insert = chunks + qa_docs
                logger.info(f"入库总计：{len(chunks)}条原文 + {len(qa_docs)}条QA对 = {len(docs_to_insert)}条")
            else:
                logger.info(f"⚠️ 向量库为空，写入 {len(chunks)} 条...")

            batch_size = 32
            total_docs = len(docs_to_insert)
            for i in range(0, total_docs, batch_size):
                batch = docs_to_insert[i:i + batch_size]
                try:
                    vectordb.add_documents(documents=batch)
                    current_processed = min(i + batch_size, total_docs)
                    # 每 5 个批次或是最后一批时打印进度
                    if (i // batch_size + 1) % 5 == 0 or current_processed == total_docs:
                        logger.info(f"  ⏳ 正在写入向量库... 已完成: {current_processed} / {total_docs} 条")
                except Exception as e:
                    logger.error(f"❌ 批次写入失败 (起始索引 {i}): {e}")
            logger.info("✅ 向量库写入完成")
        else:
            logger.info(f"✅ 向量库已有 {count} 条数据")
    except Exception as e:
        logger.warning(f"⚠️ 检查向量库状态异常: {e}")
    return vectordb


class HybridRetriever:
    """
    三阶漏斗混合检索器

    第一阶（宽召回）: 向量检索 + BM25 各召回 recall_k 篇
    第二阶（粗排）  : RRF 倒数排名融合，快速选出 rrf_top_k 篇候选
    第三阶（精排）  : BGEReranker 深度语义重排序，选出 top_k_final 篇喂给 LLM

    优势：
    - RRF 零成本、零延迟，快速将 40 篇候选压缩到 20 篇
    - Reranker 只需处理 20 篇而非 40 篇，节省 API 开销
    - 精排结果质量远高于纯 RRF 或纯 Reranker
    """

    def __init__(self, vectordb, documents, recall_k=20, rrf_top_k=20):
        self.recall_k = recall_k
        self.rrf_top_k = rrf_top_k
        self.vector_retriever = vectordb.as_retriever(search_kwargs={"k": recall_k})
        self.reranker = BGEReranker(top_k=CONFIG.get("top_k_final", 3))

        if documents and len(documents) > 0:
            self.bm25 = BM25Retriever.from_documents(documents)
            self.bm25.k = recall_k
        else:
            self.bm25 = None
            logger.warning("⚠️ [HybridRetriever] 文档为空，BM25 未初始化")

        self._cache: dict = {}
        self._cache_ttl = 300

    def search(self, query: str, top_k_final: int = 3) -> List[Document]:
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
        v_docs = self.vector_retriever.invoke(query)
        b_docs = self.bm25.invoke(query) if self.bm25 else []

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

        # ═══════════════════════════════════════════════════════
        # 向量库持久化：已有数据则直接加载，避免重复构建
        # ═══════════════════════════════════════════════════════
        need_rebuild = self._check_vectorstore_empty(persist_dir)

        if need_rebuild:
            logger.info("🆕 向量库为空，开始首次构建...")
            try:
                raw_docs = load_pdfs_from_dir(self.docs_dir)
            except Exception as e:
                logger.error(f"❌ 加载文档失败: {e}")
                raw_docs = []

            logger.info("🔀 使用混合分块 (Hybrid Chunking): 规则边界保护→递归切分(512/128)→合并小块")
            self.chunks = split_documents(raw_docs)
        else:
            logger.info("✅ 向量库已存在，跳过文档加载与分块，直接加载已有数据")
            raw_docs = []
            self.chunks = []

        self.vectorstore = build_or_load_vectorstore(
            self.chunks,
            persist_dir,
            enable_qa=bool(CONFIG.get("enable_qa_generation", False))
        )
        self.retriever = HybridRetriever(
            self.vectorstore,
            raw_docs,
            recall_k=CONFIG.get("recall_k", 20),
            rrf_top_k=CONFIG.get("rrf_top_k", 20),
        )

    def _check_vectorstore_empty(self, persist_dir: str) -> bool:
        """检查 ChromaDB 向量库是否为空（不存在或无数据）"""
        if not os.path.exists(persist_dir) or not os.path.isdir(persist_dir):
            return True
        try:
            import chromadb
            client = chromadb.PersistentClient(path=persist_dir)
            collections = client.list_collections()
            for col in collections:
                if col.count() > 0:
                    return False
            return True
        except Exception:
            return True

    def search(self, query: str, top_k_final: int = 3) -> List[Document]:
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