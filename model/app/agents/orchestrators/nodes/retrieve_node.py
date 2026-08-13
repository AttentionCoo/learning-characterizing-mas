import logging
import asyncio
from typing import Dict, Optional
from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.constants import MAX_EVIDENCE_CHARS
from app.agents.utils.reasoning_trace import parse_retrieval_evidence
from app.agents.utils.text_utils import truncate_text

logger = logging.getLogger(__name__)

# 不适合 RAG 检索脑卒中知识库的功能前缀：
# - profile_build：画像构建，输入是学生背景信息而非医学知识
# - assessment：学习效果评估，分析学生学习状态
# - learning_path：路径规划，规划学习阶段/时间安排
# 这些功能分析的是「学生」而非「脑卒中医学知识」，检索知识库会引入无关 chunk 干扰推理。
_RAG_SKIP_REPORT_MODE_PREFIXES = ("profile_build", "assessment", "learning_path")


class RetrieveNode(BaseNode):

    def __init__(self, learning_assistant, shared_memory_system=None):
        self.learning_assistant = learning_assistant
        self.shared_memory_system = shared_memory_system

    async def run(self, state: LearningState) -> Dict:
        report_mode = state.get("report_mode", "")
        if report_mode.startswith(_RAG_SKIP_REPORT_MODE_PREFIXES):
            logger.info(
                f"[retrieve] 功能 {report_mode} 不适合 RAG 检索脑卒中知识库，跳过检索"
            )
            return {"evidence": "", "retrieval_sources": []}

        evidence = await self.learning_assistant.afast_parallel_retrieve(
            state["learning_questions"]
        )

        shared_memory_hits = []
        if self.shared_memory_system:
            shared_memory_hits = self._retrieve_shared_memory(state)
            if shared_memory_hits:
                memory_evidence = self._format_shared_memory_evidence(shared_memory_hits)
                if memory_evidence:
                    evidence = f"{evidence}\n\n--- 共享记忆 ---\n{memory_evidence}" if evidence else memory_evidence
                    logger.info(f"[retrieve] 融合共享记忆 | 命中={len(shared_memory_hits)} 条")

        result = {
            "evidence": truncate_text(evidence, MAX_EVIDENCE_CHARS),
            "retrieval_sources": parse_retrieval_evidence(evidence),
        }
        if shared_memory_hits:
            result["shared_memory_hits"] = shared_memory_hits
        return result

    def _retrieve_shared_memory(self, state: LearningState) -> list:
        try:
            query = state.get("case_text", "")
            intent_type = state.get("intent_type", "")
            if not query:
                return []
            memories = self.shared_memory_system.retrieve_relevant(
                query=query,
                top_k=3,
                intent_type=intent_type,
            )
            return memories
        except Exception as e:
            logger.warning(f"[retrieve] 共享记忆检索失败: {e}")
            return []

    @staticmethod
    def _format_shared_memory_evidence(memories: list) -> str:
        if not memories:
            return ""
        parts = []
        for mem in memories:
            source = mem.get("source_agent", "unknown")
            content = mem.get("content", "")
            relevance = mem.get("relevance", 0.0)
            parts.append(f"[{source} | 相关度={relevance:.2f}] {content}")
        return "\n".join(parts)
