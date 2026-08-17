"""检索结果融合：RRF（倒数排名融合）。

从 rag/retrievers.py 中拆出的纯函数模块，负责把多路召回结果
（向量 + BM25）融合为单一排序，并在 metadata 写入 rrf_score。
"""
from typing import List

from langchain_core.documents import Document


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
