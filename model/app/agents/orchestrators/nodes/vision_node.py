"""
VisionAnalysisNode — LangGraph 医学影像分析节点

将医学多模态影像分析深度集成到多智能体推理工作流中。
影像分析结果作为"视觉证据"参与后续的检索、推理和辩论环节。

工作流位置：
  intent → vision → retrieve → reason → validate → generate_report
  (当 state 中存在 images 且非空时)
"""

import logging
from typing import Dict, List, Optional

from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode

logger = logging.getLogger(__name__)


class VisionAnalysisNode(BaseNode):
    """医学影像分析节点。

    职责：
    1. 接收包含医学影像的 state，调用 MedicalVisionService 进行结构化分析
    2. 通过 VisionRAGBridge 将影像发现转化为 PubMed + 本地知识库检索
    3. 将影像分析结果和循证证据写入 state，供后续节点使用

    节点输出字段：
    - vision_findings: 结构化的 MedicalImageFindings（dict）
    - vision_evidence: 格式化的影像分析+证据文本（str）
    - evidence: 在原有 evidence 基础上追加视觉证据
    """

    # 节点输出键名（用于 LangGraph state 更新）
    OUTPUT_FINDINGS_KEY = "vision_findings"
    OUTPUT_EVIDENCE_KEY = "vision_evidence"

    def __init__(
        self,
        medical_vision_service=None,
        vision_rag_bridge=None,
        llm_fast=None,
    ):
        """
        Args:
            medical_vision_service: MedicalVisionService 实例
            vision_rag_bridge: VisionRAGBridge 实例
            llm_fast: 快速LLM（用于生成检索查询等轻量任务）
        """
        self._vision = medical_vision_service
        self._bridge = vision_rag_bridge
        self._llm = llm_fast

    async def run(self, state: LearningState) -> Dict:
        """执行影像分析节点。

        从 state 中提取 images 和 case_text，执行完整的：
        影像分类 → 结构化分析 → PubMed检索 → 本地知识库检索 → 证据融合
        """
        images = state.get("images", [])
        if not images:
            logger.info("[vision_node] 无图片输入，跳过影像分析")
            return {
                self.OUTPUT_FINDINGS_KEY: None,
                self.OUTPUT_EVIDENCE_KEY: "",
            }

        question = state.get("case_text", "")
        all_info = state.get("all_info", "")
        existing_evidence = state.get("evidence", "")

        logger.info(f"[vision_node] 开始处理 {len(images)} 张医学影像 | 问题: {question[:80]}")

        # Step 1: 结构化影像分析
        findings = None
        vision_evidence_text = ""

        if self._vision:
            try:
                findings = await self._vision.analyze_structured(
                    images=images,
                    question=question,
                    all_info=all_info,
                )
                logger.info(
                    f"[vision_node] 影像分析完成 | 类型: {findings.image_type} | "
                    f"发现: {len(findings.key_findings)} 条 | 置信度: {findings.confidence:.0%}"
                )
            except Exception as e:
                logger.error(f"[vision_node] 影像分析失败: {e}", exc_info=True)
                findings = None
        else:
            logger.warning("[vision_node] MedicalVisionService 未初始化")

        # Step 2: Vision → RAG 桥接
        pubmed_papers = []
        local_docs = []

        if findings and self._bridge:
            # 并行检索 PubMed 和本地知识库
            import asyncio
            pubmed_task = asyncio.create_task(
                self._bridge.search_pubmed_from_findings(findings, max_results=3)
            )
            local_docs = self._bridge.search_local_knowledge(findings, top_k=3)
            try:
                pubmed_papers = await pubmed_task
            except Exception as e:
                logger.warning(f"[vision_node] PubMed检索失败: {e}")

        # Step 3: 格式化证据文本
        if findings and self._bridge:
            vision_evidence_text = self._bridge.format_evidence_for_agent(
                findings=findings,
                pubmed_papers=pubmed_papers,
                local_docs=local_docs,
            )

        # Step 4: 合并 evidence
        merged_evidence = existing_evidence
        if vision_evidence_text:
            if merged_evidence:
                merged_evidence = f"{vision_evidence_text}\n\n---\n\n{merged_evidence}"
            else:
                merged_evidence = vision_evidence_text

        # Step 5: 生成影像相关的学习子问题（供后续 retrieval_service 使用）
        vision_questions = self._generate_vision_questions(findings) if findings else []

        # 合并到 learning_questions
        existing_questions = list(state.get("learning_questions", []))
        merged_questions = vision_questions + existing_questions

        result = {
            self.OUTPUT_FINDINGS_KEY: findings.model_dump() if findings else None,
            self.OUTPUT_EVIDENCE_KEY: vision_evidence_text,
            "evidence": merged_evidence,
            "learning_questions": merged_questions,
        }

        logger.info(
            f"[vision_node] 节点完成 | 影像证据长度: {len(vision_evidence_text)} | "
            f"新增子问题: {len(vision_questions)} | PubMed文献: {len(pubmed_papers)}"
        )
        return result

    def _generate_vision_questions(self, findings) -> List[str]:
        """从影像发现生成学习子问题，引导后续的检索和推理。

        Returns:
            List of question strings for LearningAssistant to retrieve against
        """
        questions = []

        if not findings:
            return questions

        # 基于异常发现生成问题
        for ab in findings.abnormalities[:3]:
            if ab.description and ab.location:
                questions.append(f"{ab.location}{ab.description}的脑卒中影像学特征和临床处理")
            elif ab.description:
                questions.append(f"{ab.description}的脑卒中相关知识")

        # 基于鉴别诊断生成问题
        for dd in findings.differential_diagnosis[:2]:
            if dd:
                questions.append(f"{dd}的诊断标准和影像学鉴别要点")

        # 基于建议检查生成问题
        for test in findings.recommended_confirmatory_tests[:2]:
            if test:
                questions.append(f"脑卒中患者{test}的适应症和临床意义")

        # 基于影像类型生成通用问题
        img_type_name = findings.image_type.replace("neuroimaging_", "").replace("_", " ").upper()
        if img_type_name:
            questions.append(f"{img_type_name}在脑卒中诊断中的价值和典型表现")

        return questions

    @staticmethod
    def has_images(state: LearningState) -> bool:
        """检查 state 中是否包含需要分析的医学影像。

        供 clinical_graph.py 中的条件路由使用。
        """
        images = state.get("images", [])
        return bool(images)
