"""
医学证据评分重排 — Medical Evidence Reranker
=============================================

把"检索候选"按医学道理重新排序，而非纯 embedding 距离：

    final = 0.35×语义 + 0.25×证据类型 + 0.20×指南权威 + 0.10×时效 + 0.10×主题
            + 干预命中加分 + 淘汰惩罚

- 语义分：优先使用 BGEReranker API（dashscope TextReRank）返回的 relevance_score；
  调用失败或未配置时，降级为 RRF 分数 min-max 归一化 —— 绝不退化成"原始顺序"。
- 证据类型分：chunk 所在 collection 与查询证据类型一致 → 满分；相关库 → 半价。
- 权威分：指南/规范/共识(1.0) > 教材(0.8) > 其他(0.5)。
- 时效分：年份越新越高（线性插值，未知年份取中值）。
- 主题分：chunk 的 subtopic 与查询证据类型对应主题一致 → 满分。
- 干预命中加分：查询中的药物/操作与 chunk 的 intervention 标签一致时加分。
- 淘汰惩罚：主题明显不匹配（如治疗查询命中血脂预防 chunk）直接扣分，进入负分区间。

纯函数部分不依赖 langchain，方便离线单测；rerank 部分操作 Document。
"""

import logging
from typing import Dict, List, Optional

from .labels import SUBTOPIC_COLLECTION

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 1. 权重与常量
# ═══════════════════════════════════════════════════════════════

WEIGHTS: Dict[str, float] = {
    "semantic": 0.35,        # 语义相关性（BGEReranker 或 RRF 归一化）
    "evidence_type": 0.25,   # 证据类型匹配
    "authority": 0.20,       # 指南权威
    "recency": 0.10,         # 时效
    "topic": 0.10,           # 主题一致性
}
MISMATCH_PENALTY: float = -0.5   # 主题不匹配淘汰惩罚
INTERVENTION_BONUS: float = 0.15  # 干预命中加分（上限）

# 相关库（评分时半价，不淘汰）
_RELATED: Dict[str, tuple] = {
    "treatment": ("guideline",),
    "prevention": ("guideline",),
    "anatomy": (),
    "etiology": (),
    "guideline": (),
}

_REFERENCE_YEAR = 2024  # 时效评分参照年（可被 recency_score 参数覆盖）


def normalize_scores(values: List[float]) -> List[float]:
    """
    min-max 归一化到 [0, 1]。

    - 空列表 → []
    - 全部相等 → 全 1.0（无法区分时视为同权）
    """
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def authority_score(authority: Optional[str]) -> float:
    """权威等级 → 分数：指南/共识/规范 1.0，教材 0.8，其他 0.5。"""
    return {
        "guideline": 1.0,
        "textbook": 0.8,
        "generic": 0.5,
    }.get(authority, 0.5)


def recency_score(year: Optional[int], reference_year: int = _REFERENCE_YEAR) -> float:
    """
    时效分：从 2019（0.5）线性到 reference_year（1.0）；更早取 0.3；未知取 0.5。
    """
    if not year:
        return 0.5
    if year <= 2019:
        return 0.3
    if year >= reference_year:
        return 1.0
    return 0.5 + 0.5 * (year - 2019) / (reference_year - 2019)


def _get_meta(doc, key: str, default=None):
    """兼容 langchain Document 与普通 dict 的 metadata 读取。"""
    if hasattr(doc, "metadata") and isinstance(doc.metadata, dict):
        return doc.metadata.get(key, default)
    if isinstance(doc, dict):
        meta = doc.get("metadata", doc)
        return meta.get(key, default) if isinstance(meta, dict) else default
    return default


def evidence_type_score(doc, evidence_type: str) -> float:
    """证据类型匹配分：主库 1.0，相关库 0.5，其他 0.0。"""
    doc_collection = _get_meta(doc, "collection", "")
    if doc_collection == evidence_type:
        return 1.0
    if doc_collection in _RELATED.get(evidence_type, ()):
        return 0.5
    return 0.0


def topic_score(doc, evidence_type: str) -> float:
    """
    主题一致性分：chunk 的 subtopic 映射到主题库后与查询证据类型一致 → 1.0。
    subtopic 缺失时退回 collection 判断。
    """
    subtopic = _get_meta(doc, "subtopic", "")
    if subtopic:
        mapped = SUBTOPIC_COLLECTION.get(subtopic)
        if mapped:
            return 1.0 if mapped == evidence_type else 0.0
    subtopic_collection = _get_meta(doc, "collection", "")
    return 1.0 if subtopic_collection == evidence_type else 0.0


def intervention_bonus(query: str, doc) -> float:
    """
    干预命中加分：查询文本命中的干预类别与 chunk 的 intervention 标签有交集 → 加分。

    返回 0.0 或 INTERVENTION_BONUS。
    """
    if not query or not query.strip():
        return 0.0
    try:
        from .labels import extract_interventions
        query_hits = extract_interventions(query)
        if not query_hits:
            return 0.0
        doc_hits = _get_meta(doc, "interventions", []) or []
        if isinstance(doc_hits, str):
            # chromadb 中空列表序列化为空字符串
            doc_hits = [h for h in doc_hits.split(",") if h]
        if any(hit in doc_hits for hit in query_hits):
            return INTERVENTION_BONUS
    except Exception:
        pass
    return 0.0


def medical_evidence_score(
    query: str,
    doc,
    evidence_type: Optional[str] = None,
    semantic_score: float = 0.0,
) -> Dict:
    """
    计算单篇文档的医学评分。

    参数:
        query: 原始查询（用于干预命中加分）
        doc:   langchain Document 或带 metadata 的 dict
        evidence_type: 查询的证据类型（可空，空则跳过类型/主题项）
        semantic_score: 语义分（BGEReranker relevance_score 或 RRF 归一化），0~1

    返回:
        {"score": 总分, "breakdown": {各项得分}, "penalty": 惩罚, "bonus": 加分}
    """
    breakdown: Dict[str, float] = {}

    breakdown["semantic"] = max(0.0, min(1.0, float(semantic_score or 0.0)))

    if evidence_type:
        breakdown["evidence_type"] = evidence_type_score(doc, evidence_type)
        breakdown["topic"] = topic_score(doc, evidence_type)
    else:
        breakdown["evidence_type"] = 0.0
        breakdown["topic"] = 0.0

    breakdown["authority"] = authority_score(_get_meta(doc, "authority"))
    breakdown["recency"] = recency_score(_get_meta(doc, "year"))

    weighted = sum(WEIGHTS[key] * breakdown[key] for key in WEIGHTS)

    bonus = intervention_bonus(query, doc)

    # 淘汰惩罚：主题明显不匹配（治疗查询命中血脂预防 chunk）
    penalty = 0.0
    if evidence_type:
        doc_collection = _get_meta(doc, "collection", "")
        if (
            doc_collection
            and doc_collection != evidence_type
            and doc_collection not in _RELATED.get(evidence_type, ())
        ):
            penalty = MISMATCH_PENALTY

    total = weighted + bonus + penalty
    return {
        "score": round(total, 4),
        "breakdown": {k: round(v, 4) for k, v in breakdown.items()},
        "bonus": round(bonus, 4),
        "penalty": round(penalty, 4),
    }


# ═══════════════════════════════════════════════════════════════
# 2. BGEReranker（语义分来源，可降级）
# ═══════════════════════════════════════════════════════════════


class BGEReranker:
    """BGEReranker 语义精排：调 dashscope TextReRank API，失败抛异常由上层兜底。"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key
        self.model = model or "qwen3-rerank"
        self.enabled = bool(api_key)

    def rerank_scores(self, query: str, docs: List) -> Optional[List[float]]:
        """
        返回与 docs 等长的 relevance_score 列表（0~1）。

        未配置 key 或调用失败时返回 None（调用方走 RRF 归一化兜底）。
        """
        if not self.enabled or not docs:
            return None
        try:
            import dashscope
            from http import HTTPStatus

            response = dashscope.TextReRank.call(
                model=self.model,
                query=query,
                documents=[doc.page_content for doc in docs],
                top_n=len(docs),
                return_documents=True,
                api_key=self.api_key,
            )
            if response.status_code != HTTPStatus.OK:
                logger.warning("[scoring] BGEReranker 调用失败: %s", response.message)
                return None
            scores = [0.0] * len(docs)
            for item in response.output.results:
                scores[item.index] = item.relevance_score
            return scores
        except Exception as exc:
            logger.warning("[scoring] BGEReranker 异常，走 RRF 兜底: %s", exc)
            return None


# ═══════════════════════════════════════════════════════════════
# 3. 医学评分重排主类
# ═══════════════════════════════════════════════════════════════


class MedicalEvidenceReranker:
    """
    医学证据重排器：语义分（API 优先，RRF 归一化兜底）融合医学规则评分。

    排序依据是 medical_evidence_score，而非原始 embedding 顺序。
    """

    def __init__(
        self,
        top_k: int = 3,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.top_k = top_k
        self.model = model
        self.bge = BGEReranker(api_key=api_key, model=model)

    # ── 语义分获取 ──
    def _semantic_scores(self, query: str, docs: List) -> List[float]:
        """API 优先；失败/未配置 → RRF 分数归一化兜底。"""
        api_scores = self.bge.rerank_scores(query, docs)
        if api_scores is not None:
            return api_scores
        rrf_values = [
            float(_get_meta(doc, "rrf_score", 0.0) or 0.0)
            for doc in docs
        ]
        return normalize_scores(rrf_values)

    # ── 主重排 ──
    def rerank(
        self,
        query: str,
        docs: List,
        evidence_type: Optional[str] = None,
        top_k: Optional[int] = None,
        semantic_scores: Optional[List[float]] = None,
    ) -> List:
        """
        医学评分重排。

        参数:
            query: 查询（用于干预命中加分）
            docs: 候选 Document 列表（含 rrf_score / collection / subtopic 等 metadata）
            evidence_type: 查询证据类型（用于类型/主题分与淘汰惩罚）
            top_k: 返回条数
            semantic_scores: 外部语义分（测试注入用）；None 则内部获取

        返回:
            按 medical_score 降序的 top_k 文档，metadata 写入 medical_score / score_breakdown。
        """
        if not docs:
            return []
        actual_top_k = top_k or self.top_k
        sem_scores = (
            semantic_scores
            if semantic_scores is not None
            else self._semantic_scores(query, docs)
        )

        scored: List = []
        for doc, sem in zip(docs, sem_scores):
            result = medical_evidence_score(query, doc, evidence_type, semantic_score=sem)
            scored.append((doc, result))

        # 淘汰严重不匹配（负分）
        kept = [(doc, r) for doc, r in scored if r["score"] >= 0]
        if not kept:
            kept = scored  # 全部负分时保留相对最优，避免空结果

        kept.sort(key=lambda item: item[1]["score"], reverse=True)
        kept = kept[:actual_top_k]

        for doc, result in kept:
            if hasattr(doc, "metadata") and isinstance(doc.metadata, dict):
                doc.metadata["medical_score"] = result["score"]
                doc.metadata["medical_score_breakdown"] = result["breakdown"]
        return [doc for doc, _ in kept]

    # ── 显式兜底入口（测试与调用方可用）──
    def fallback_rerank(
        self,
        query: str,
        docs: List,
        evidence_type: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> List:
        """
        纯规则兜底重排：Rerank API 不可用时，用 RRF 归一化 + 医学评分排序。

        这是"rerank 失败不再退化为原始 embedding 顺序"的保证路径。
        """
        if not docs:
            return []
        actual_top_k = top_k or self.top_k
        rrf_values = [
            float(_get_meta(doc, "rrf_score", 0.0) or 0.0)
            for doc in docs
        ]
        sem_scores = normalize_scores(rrf_values)
        return self.rerank(
            query,
            docs,
            evidence_type=evidence_type,
            top_k=actual_top_k,
            semantic_scores=sem_scores,
        )
