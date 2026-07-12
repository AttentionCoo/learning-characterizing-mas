"""
Vision-RAG 桥接服务 — Vision-RAG Bridge

将医学影像分析的结构化发现自动转化为检索查询，
桥接视觉理解与本地 ChromaDB 知识库的循证检索。
"""

import logging
from typing import Dict, List, Any

from app.schemas.medical_image import MedicalImageFindings

logger = logging.getLogger(__name__)


class VisionRAGBridge:
    """视觉发现 → RAG 检索的桥接服务。

    将结构化的影像发现转化为：
    1. 本地 ChromaDB 向量检索查询字符串
    2. 综合证据包（注入多智能体推理流程）
    """

    def __init__(self, unified_search_engine=None):
        self._search_engine = unified_search_engine

    # ----------------------------------------------------------
    # 公开 API
    # ----------------------------------------------------------

    def search_local_knowledge(self, findings: MedicalImageFindings, top_k: int = 3) -> List[Dict[str, Any]]:
        """从本地 ChromaDB 知识库检索与影像发现相关的文档。

        Returns:
            List of document dicts with content and metadata
        """
        if not self._search_engine:
            logger.warning("[vision_rag] 检索引擎未初始化")
            return []

        # 构建综合查询文本
        query_parts = []
        if findings.anatomical_region:
            query_parts.append(findings.anatomical_region)
        query_parts.extend(findings.key_findings[:3])
        query_parts.extend(findings.differential_diagnosis[:2])
        query_text = " ".join(query_parts)

        if not query_text.strip():
            return []

        try:
            results = self._search_engine.search(query_text, top_k=top_k)
            logger.info(f"[vision_rag] 本地知识库检索 | 查询='{query_text[:80]}' | 结果={len(results)} 条")
            return results
        except Exception as e:
            logger.warning(f"[vision_rag] 本地知识库检索失败: {e}")
            return []

    def format_evidence_for_agent(
        self,
        findings: MedicalImageFindings,
        local_docs: List[Dict[str, Any]],
    ) -> str:
        """将视觉发现和检索证据格式化为适合多智能体推理的文本。

        这个文本会被注入到 LearningState.evidence 中，供 reason_node 使用。
        """
        parts = []

        # 1. 影像发现摘要
        parts.append("## 📷 医学影像分析结果")
        parts.append(f"- 影像类型：{findings.image_type}")
        parts.append(f"- 解剖区域：{findings.anatomical_region}")
        parts.append(f"- 关键发现：")
        for f in findings.key_findings:
            parts.append(f"  * {f}")
        if findings.abnormalities:
            parts.append(f"- 异常发现（{len(findings.abnormalities)} 处）：")
            for ab in findings.abnormalities:
                parts.append(f"  * {ab.location}：{ab.description}（临床意义：{ab.significance}）")
        if findings.differential_diagnosis:
            parts.append(f"- 鉴别诊断：{' > '.join(findings.differential_diagnosis)}")
        parts.append(f"- 紧急程度：{findings.urgency_level}")
        parts.append(f"- 置信度：{findings.confidence:.0%}")
        parts.append(f"- 建议确认性检查：{', '.join(findings.recommended_confirmatory_tests) if findings.recommended_confirmatory_tests else '无'}")
        if findings.limitations:
            parts.append(f"- 分析局限性：{findings.limitations}")

        # 2. 本地知识库
        if local_docs:
            parts.append("\n## 📖 本地卒中指南参考")
            for i, doc in enumerate(local_docs, 1):
                content = doc.get("content", "")[:200] if isinstance(doc, dict) else str(doc)[:200]
                source = doc.get("metadata", {}).get("source", "") if isinstance(doc, dict) else ""
                parts.append(f"{i}. [{source}] {content}...")

        # 3. 免责声明
        parts.append("\n---")
        parts.append("> ⚠️ **AI辅助教育说明**：以上影像分析由多模态AI模型自动生成，仅供医学教育参考。")
        parts.append("> 所有AI影像判读结果必须由具备资质的放射科医生或临床医生确认。")
        parts.append("> 请勿基于AI分析结果做出临床决策。")

        return "\n".join(parts)
