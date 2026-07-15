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


load_dotenv(override=True)
logger = logging.getLogger(__name__)

CONFIG = {
    "persist_dir": os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "vector_stores", "chroma_db_unified"),
    "docs_dir": os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "documents"),
    "top_k_per_store": 4,
    "enable_qa_generation": True,
    # 三阶漏斗参数
    "recall_k": 20,         # 第一阶：每个检索器宽召回数量
    "rrf_top_k": 20,        # 第二阶：RRF 粗排后保留的候选数
    "top_k_final": 3,       # 第三阶：Reranker 精排后最终返回数
}


class XfyunEmbeddings(Embeddings):
    """讯飞文本向量化（官方 HTTP 接口，2560 维）。

    基于讯飞官方 https://emb-cn-huabei-1.xf-yun.com/ 接口，通过 HMAC-SHA256 签名鉴权。
    通过 domain 参数区分文档入库（para）和查询（query），获得更好的语义检索召回效果。
    单次输入上限 2K token，免费档 QPS 较低（≈2 QPS），故逐条请求并内置节流。
    连续失败时自动降级到本地 BGE 模型兜底。

    环境变量：
    - XFYUN_EMBEDDING_ENABLED=false  可直接跳过讯飞，全程使用本地 BGE
    - XFYUN_EMBEDDING_URL            覆盖默认服务地址
    """

    # 官方 HTTP 接口地址（单一入口，通过 domain 参数区分 para/query）
    BASE_URL = os.getenv(
        "XFYUN_EMBEDDING_URL",
        "https://emb-cn-huabei-1.xf-yun.com/",
    )
    MAX_CHARS = 2500  # 2K token 输入上限的保守字符近似

    # 免费档 QPS ≈ 2，取保守值 1.5 QPS（即最小间隔 ≈ 0.7s）
    _MIN_INTERVAL = 0.7
    _last_request_time: float = 0.0

    # 不可恢复的错误码：重试无意义，应立刻终止
    _FATAL_ERROR_CODES: dict[int, str] = {
        11200: "应用未授权该服务或业务量超限",
        11201: "日流控超限 —— 超过当日最大访问量限制",
        11202: "秒级/并发流控超限，或 license 校验失败",
        11203: "并发流控超限 —— 并发路数超过授权限制",
        10001: "鉴权失败 —— APP_ID / API_KEY / API_SECRET 不正确",
        10002: "应用未授权该服务",
        10003: "未知的应用 ID",
        10163: "请求参数错误",
    }

    # 类级别 BGE 模型缓存：所有 XfyunEmbeddings 实例共享同一份模型，避免重复加载
    _fallback_embeddings_cache = None
    _fallback_embeddings_failed = False

    def __init__(self):
        from app.utils.xfyun_auth import get_xfyun_credentials
        self.app_id, self.api_key, self.api_secret = get_xfyun_credentials()

        # 环境变量开关：XFYUN_EMBEDDING_ENABLED=false 时跳过讯飞，直接走 BGE
        embedding_enabled = os.getenv("XFYUN_EMBEDDING_ENABLED", "true").strip().lower()
        self._xfyun_dead = embedding_enabled in ("false", "0", "no", "off")

        if self._xfyun_dead:
            logger.info("ℹ️  XFYUN_EMBEDDING_ENABLED=false，跳过讯飞 embedding，直接使用本地 BGE")
        elif not all([self.app_id, self.api_key, self.api_secret]):
            logger.warning("⚠️ 未配置 XFYUN_APP_ID/XFYUN_API_KEY/XFYUN_API_SECRET，向量化功能将不可用")
            self._xfyun_dead = True

    @classmethod
    def _throttle(cls):
        """确保连续两次请求间隔 ≥ _MIN_INTERVAL 秒，防止触发 QPS 限流。"""
        now = time.time()
        elapsed = now - cls._last_request_time
        if elapsed < cls._MIN_INTERVAL:
            time.sleep(cls._MIN_INTERVAL - elapsed)
        cls._last_request_time = time.time()

    @classmethod
    def _get_fallback_embeddings(cls):
        """懒加载本地 BGE-large-zh-v1.5 模型（1024 维），作为讯飞云端不可用时的兜底。

        模型缓存在类级别 _fallback_embeddings_cache 中，所有实例共享同一份，
        避免每次 XfyunEmbeddings() 实例化都重新加载 1.3GB 模型。
        """
        if cls._fallback_embeddings_cache is not None:
            return cls._fallback_embeddings_cache
        if cls._fallback_embeddings_failed:
            return None
        try:
            logger.info(
                "⏳ 正在加载本地 BGE 兜底模型 (bge-large-zh-v1.5, ~1.3GB)...\n"
                "   首次加载需从 HuggingFace 下载模型文件，可能需要 1~3 分钟，请耐心等待..."
            )
            from langchain_community.embeddings import HuggingFaceBgeEmbeddings
            cls._fallback_embeddings_cache = HuggingFaceBgeEmbeddings(
                model_name="BAAI/bge-large-zh-v1.5",
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
            logger.info("✅ 本地 BGE 兜底模型已加载 (bge-large-zh-v1.5, 1024d)")
            return cls._fallback_embeddings_cache
        except Exception as e:
            logger.error(f"❌ 本地 BGE 模型加载失败: {e}")
            cls._fallback_embeddings_failed = True
            return None

    @classmethod
    def preload_fallback(cls):
        """预加载 BGE 兜底模型（建议在系统初始化时调用，避免运行时静默下载导致"假死"）。

        直接使用类级别缓存，所有实例共享同一份模型。
        """
        logger.info("🔄 预加载 BGE 兜底模型（系统初始化）...")
        fallback = cls._get_fallback_embeddings()
        if fallback:
            logger.info("✅ BGE 兜底模型预加载完成，后续降级将瞬间切换")
        else:
            logger.warning("⚠️ BGE 兜底模型预加载失败，运行时降级可能较慢")

    def _embed_once(self, text: str, domain: str) -> List[float]:
        """调用讯飞官方文本向量化 HTTP 接口。

        参数:
            text:   待向量化的文本内容
            domain: "para"（文档入库）或 "query"（查询检索）
        """
        import base64 as _b64
        import json as _json
        import struct as _struct

        import requests as _requests

        from app.utils.xfyun_auth import assemble_auth_url

        content = text[: self.MAX_CHARS]

        # 按讯飞官方 Embedding HTTP 协议构造请求体
        # domain="para" 用于知识原文/段落, domain="query" 用于用户问题
        message_data = [{"role": "user", "content": content}]
        message_str = _json.dumps(message_data, ensure_ascii=False)

        body = {
            "header": {"app_id": self.app_id, "status": 3},
            "parameter": {
                "emb": {
                    "domain": domain,
                    "feature": {
                        "encoding": "utf8",
                        "compress": "raw",
                        "format": "plain",
                    },
                }
            },
            "payload": {
                "messages": {
                    "encoding": "utf8",
                    "compress": "raw",
                    "format": "json",
                    "status": 3,
                    "text": _b64.b64encode(message_str.encode("utf-8")).decode("utf-8"),
                }
            },
        }

        last_err = None
        for attempt in range(4):
            self._throttle()  # ← QPS 节流：确保请求间隔 ≥ 0.7s
            signed_url = assemble_auth_url(
                self.BASE_URL, self.api_key, self.api_secret, method="POST"
            )
            resp = _requests.post(
                signed_url,
                json=body,
                headers={"Content-Type": "application/json;charset=UTF-8"},
                timeout=30,
            )
            data = resp.json()
            code = data.get("header", {}).get("code", -1)
            if code == 0:
                # 官方接口返回字段为 text（base64 编码的 float32 字节流，2560 维）
                vec_b64 = data["payload"]["feature"]["text"]
                vec_bytes = _b64.b64decode(vec_b64)
                return list(_struct.unpack(f"{len(vec_bytes) // 4}f", vec_bytes))

            message = data.get("header", {}).get("message", "")
            last_err = f"code={code} message={message}"

            # 不可恢复错误（license/auth/参数）：立刻终止，不浪费重试时间
            if code in self._FATAL_ERROR_CODES:
                detail = self._FATAL_ERROR_CODES[code]
                raise ValueError(
                    f"讯飞 embedding 不可恢复错误: {last_err} — {detail}"
                )

            # 可恢复错误（限流/网络波动）：退避重试
            logger.warning(
                f"⚠️ 讯飞 embedding 可恢复错误（第 {attempt + 1}/4 次重试）: {last_err}"
            )
            time.sleep(1.5 * (attempt + 1))
        raise ValueError(f"讯飞 embedding 失败（已重试 4 次）: {last_err}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """文档入库 embedding（domain="para"），逐条处理，内置 QPS 节流。

        一旦某条讯飞调用失败，整批统一降级到本地 BGE 模型，
        避免同一批次内混用讯飞和 BGE 向量导致 ChromaDB 维度冲突。
        降级后整个会话生命周期内不再重试讯飞。
        """
        return self._embed_batch(texts, domain="para")

    def embed_query(self, text: str) -> List[float]:
        """查询 embedding（domain="query"），失败时降级到本地 BGE。"""
        if self._xfyun_dead:
            fallback = self._get_fallback_embeddings()
            if fallback:
                return fallback.embed_query(text)
            raise ValueError("讯飞不可用且 BGE 兜底加载失败，无法 embedding")

        try:
            return self._embed_once(text, domain="query")
        except ValueError as e:
            logger.warning(f"⚠️ 讯飞 embedding 查询失败: {e}")
            self._xfyun_dead = True
            fallback = self._get_fallback_embeddings()
            if fallback:
                logger.info("🔄 降级到本地 BGE 模型处理查询...")
                return fallback.embed_query(text)
            raise

    def _embed_batch(self, texts: List[str], domain: str) -> List[List[float]]:
        """批量 embedding 的通用实现，domain="para" 或 "query"。

        逐条调用讯飞 API，内置 QPS 节流。单条失败时整批降级到本地 BGE。
        每 10 条打印一次进度，避免大批量时长时间无日志输出（看起来像"死机"）。
        """
        # 已降级：直接走 BGE
        if self._xfyun_dead:
            fallback = self._get_fallback_embeddings()
            if fallback:
                return fallback.embed_documents(texts)
            raise ValueError("讯飞不可用且 BGE 兜底加载失败，无法 embedding")

        batch_total = len(texts)
        results = []
        for i, t in enumerate(texts):
            try:
                results.append(self._embed_once(t, domain))
                # 每 10 条或最后一条时打印进度，避免长时间静默
                if (i + 1) % 10 == 0 or i == batch_total - 1:
                    logger.debug(
                        f"  📝 embedding 批次内进度: {i + 1}/{batch_total} 条"
                    )
            except ValueError as e:
                err_msg = str(e)
                logger.warning(f"⚠️ 讯飞 embedding 第 {i + 1}/{batch_total} 条失败: {e}")
                # 打印排查指引
                if "11202" in err_msg:
                    logger.warning(
                        "💡 解决方案：前往讯飞开放平台控制台 → 我的应用 → 服务管理 → "
                        "开通「文本向量化」服务；或设置环境变量 XFYUN_EMBEDDING_ENABLED=false 直接使用本地 BGE"
                    )
                self._xfyun_dead = True
                fallback = self._get_fallback_embeddings()
                if fallback:
                    logger.info(
                        f"🔄 整批降级到本地 BGE 模型（本批 {len(texts)} 条，1024d），"
                        f"后续批次不再重试讯飞"
                    )
                    return fallback.embed_documents(texts)
                raise
        return results


class BGEReranker:
    def __init__(self, top_k: int = 5):
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            # 讯飞暂无公开 rerank 服务；不配 DashScope Key 时精排层自动关闭，
            # 检索质量由前两阶（混合检索 + RRF 融合）保障
            logger.info("ℹ️ 未配置 DASHSCOPE_API_KEY，Rerank 精排已禁用（可选功能）")
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
    embeddings = XfyunEmbeddings()
    import chromadb
    _client = chromadb.PersistentClient(path=persist_dir)
    vectordb = Chroma(
        client=_client,
        embedding_function=embeddings,
    )
    try:
        count = vectordb._collection.count()
        if count == 0 and chunks:
            docs_to_insert = chunks
            if enable_qa:
                logger.info(f"⚠️ 向量库为空，准备为 {len(chunks)} 条切片生成扩展QA对（使用 Lite 档模型）...")
                qa_gen = QAGenerator(tier="lite")
                qa_docs = qa_gen.generate_qa_for_chunks(chunks)
                docs_to_insert = chunks + qa_docs
                logger.info(f"入库总计：{len(chunks)}条原文 + {len(qa_docs)}条QA对 = {len(docs_to_insert)}条")
            else:
                logger.info(f"⚠️ 向量库为空，写入 {len(chunks)} 条...")

            batch_size = 32
            total_docs = len(docs_to_insert)
            xfyun_failed = False
            write_start = time.time()

            logger.info(f"  📝 开始写入向量库，共 {total_docs} 条，批次大小 {batch_size}")
            logger.info(f"{'─' * 50}")

            for i in range(0, total_docs, batch_size):
                batch = docs_to_insert[i:i + batch_size]
                try:
                    vectordb.add_documents(documents=batch)
                    current_processed = min(i + batch_size, total_docs)

                    # 每批次都打印进度（带进度条、百分比、速度、ETA）
                    elapsed = time.time() - write_start
                    pct = current_processed / total_docs * 100
                    speed = current_processed / elapsed if elapsed > 0 else 0

                    if speed > 0:
                        eta_sec = (total_docs - current_processed) / speed
                        eta_str = f"{eta_sec:.0f}s" if eta_sec < 120 else f"{eta_sec / 60:.1f}min"
                    else:
                        eta_str = "计算中..."

                    # 简单进度条（20 格）
                    bar_length = 20
                    filled = int(bar_length * current_processed / total_docs)
                    bar = "█" * filled + "░" * (bar_length - filled)

                    logger.info(
                        f"  [{bar}] {pct:5.1f}% | {current_processed}/{total_docs} 条 | "
                        f"耗时 {elapsed:.0f}s | 速度 {speed:.1f} 条/s | ETA {eta_str}"
                    )
                except ValueError as e:
                    # 讯飞 embedding 失败 → 后续批次已自动降级到 BGE
                    if "讯飞 embedding 失败" in str(e):
                        xfyun_failed = True
                        if i == 0:
                            # 第一批就失败，BGE 从零开始建库，无维度冲突
                            logger.warning("⚠️ 讯飞 embedding 首轮即失败，后续批次自动降级到本地 BGE")
                            # 重新尝试当前批次（此时 embedding 内部已触发 BGE 降级）
                            try:
                                vectordb.add_documents(documents=batch)
                                current_processed = min(i + batch_size, total_docs)
                                logger.info(f"  [BGE兜底] 已完成: {current_processed} / {total_docs} 条")
                            except Exception as e2:
                                logger.error(f"❌ BGE 兜底也失败 (起始索引 {i}): {e2}")
                        else:
                            # 中间批次失败：已有 Xfyun 2560d 数据入库，BGE 1024d 会维度冲突
                            logger.error(
                                f"❌ 讯飞 embedding 在第 {i} 条处失败，但前 {i} 条已用 2560d 入库。\n"
                                f"   BGE 兜底（1024d）与已有向量维度不兼容，无法继续。\n"
                                f"   建议：删除向量库目录后重新运行，或联系讯飞开通 embedding 服务额度。\n"
                                f"   向量库路径: {persist_dir}"
                            )
                    else:
                        logger.error(f"❌ 批次写入失败 (起始索引 {i}): {e}")
                except Exception as e:
                    error_msg = str(e)
                    # 检测 ChromaDB 维度不匹配错误
                    if "dimensionality" in error_msg.lower() or "dimension" in error_msg.lower():
                        logger.error(
                            f"❌ 向量维度冲突 (起始索引 {i}): {error_msg}\n"
                            f"   原因：前序批次使用讯飞 2560d，当前批次降级为 BGE 1024d。\n"
                            f"   解决：删除向量库目录后重新运行，统一使用一种 embedding 模型。\n"
                            f"   向量库路径: {persist_dir}"
                        )
                    else:
                        logger.error(f"❌ 批次写入失败 (起始索引 {i}): {e}")
            write_elapsed = time.time() - write_start
            logger.info(f"{'─' * 50}")
            logger.info(f"✅ 向量库写入完成！共 {total_docs} 条，总耗时 {write_elapsed:.1f}s")
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