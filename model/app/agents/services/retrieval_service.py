import logging
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio

from app.rag.planner import plan_decision_nodes
from app.rag.router import (
    classify_evidence_type,
    translate_query,
)

logger = logging.getLogger(__name__)


class EvidenceRetrievalService:
    """
    决策驱动证据检索服务。

    单条查询链路：
        临床问题 → Clinical Decision Planner（决策节点）
                → Query Translator（同义词扩展/剔除患者变量）
                → Evidence Router（证据类型）
                → MultiCollectionSearchEngine（多库隔离检索 + 医学评分重排）
                → 带结构化标签的证据文本
    """

    def __init__(self, retriever, top_k=3):
        self.retriever = retriever
        self.top_k = top_k

    def retrieve_single(self, query: str) -> str:
        # 1. 决策规划
        decision_nodes = plan_decision_nodes(query)
        # 2. 查询翻译（临床语言 → 医学检索语言）
        translated = translate_query(query)
        #    纯患者变量查询（如 "NIHSS 12"）剔除后可能为空串 → 回退原始查询
        if not translated.strip():
            translated = query
        # 3. 证据类型（路由）
        evidence_type = classify_evidence_type(query, decision_nodes)

        try:
            docs = self.retriever.search(
                translated,
                self.top_k,
                evidence_type=evidence_type,
                decision_nodes=decision_nodes,
            )
        except TypeError:
            # 兼容旧引擎（UnifiedSearchEngine 不支持路由参数）
            docs = self.retriever.search(query, self.top_k)

        if not docs:
            return ""

        results = []
        for i, doc in enumerate(docs):
            source = doc.metadata.get("source", "未知")
            page = doc.metadata.get("page", "?")
            score = doc.metadata.get("medical_score")
            if score is None:
                score = doc.metadata.get("relevance_score", "N/A")
            subtopic = doc.metadata.get("subtopic_name") or doc.metadata.get(
                "subtopic", ""
            )
            interventions = doc.metadata.get("interventions", []) or []
            if isinstance(interventions, str):
                # chromadb 中空列表序列化为空字符串
                interventions = [h for h in interventions.split(",") if h]
            year = doc.metadata.get("year", "")
            authority = doc.metadata.get("authority", "")

            content = doc.page_content[:500]

            tags = []
            if subtopic:
                tags.append(f"主题:{subtopic}")
            if interventions:
                tags.append(f"干预:{','.join(interventions)}")
            if year:
                tags.append(f"年份:{year}")
            if authority:
                tags.append(f"权威:{authority}")
            tag_str = f"({')('.join(tags)})" if tags else ""

            results.append(
                f"【文献{i+1}】"
                f"[来源:{source} p.{page}]"
                f"(相关度:{score})"
                f"{tag_str}\n"
                f"{content}"
            )

        return "\n\n".join(results)

    async def aretrieve_single(self, query: str) -> str:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.retrieve_single, query)

    async def aparallel_retrieve(self, queries: List[str]) -> str:
        import asyncio
        tasks = [self.aretrieve_single(q) for q in queries]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        parts = []
        for i, (q, content) in enumerate(zip(queries, results_list)):
            if isinstance(content, Exception):
                logger.error(f"检索失败 {q}: {content}")
                content = ""
            if content:
                # 标注该查询的决策节点与证据类型，便于下游推理理解证据来源
                decision_nodes = plan_decision_nodes(q)
                evidence_type = classify_evidence_type(q, decision_nodes)
                parts.append(
                    f"### 检索维度{i+1}: {q}"
                    f" [证据类型:{evidence_type}"
                    f"| 决策节点:{','.join(decision_nodes) or '无'}]\n{content}"
                )

        return "\n\n---\n\n".join(parts)

    def parallel_retrieve(self, queries: List[str]) -> str:

        results = {}

        with ThreadPoolExecutor(
            max_workers=min(3, len(queries))
        ) as executor:

            future_map = {
                executor.submit(self.retrieve_single, q): q
                for q in queries
            }

            for future in as_completed(future_map):
                q = future_map[future]

                try:
                    results[q] = future.result()
                except Exception as e:
                    logger.error(f"检索失败 {q}: {e}")
                    results[q] = ""

        parts = []

        for i, q in enumerate(queries):
            content = results.get(q, "")

            if content:
                decision_nodes = plan_decision_nodes(q)
                evidence_type = classify_evidence_type(q, decision_nodes)
                parts.append(
                    f"### 检索维度{i+1}: {q}"
                    f" [证据类型:{evidence_type}"
                    f"| 决策节点:{','.join(decision_nodes) or '无'}]\n{content}"
                )

        return "\n\n---\n\n".join(parts)
