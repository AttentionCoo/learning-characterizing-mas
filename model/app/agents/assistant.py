import logging
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, AsyncGenerator, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from app.config.config_loader import PromptManager, ReportTemplateManager
from app.agents.services.query_service import QueryGenerationService
from app.agents.services.retrieval_service import EvidenceRetrievalService
from app.agents.services.synthesis_service import EvidenceSynthesisService
from app.agents.pipelines.rag_pipeline import RAGPipeline
from app.rag.retrievers import CONFIG
from app.agents.constants import MAX_EVIDENCE_PER_QUESTION

logger = logging.getLogger(__name__)


class LearningAssistant:

    def __init__(
        self,
        llm_main=None,
        llm_fast=None,
        retriever=None,
        prompt_manager: PromptManager = None,
        report_manager: ReportTemplateManager = None,
        llm=None,
    ):
        if llm_main is None:
            llm_main = llm
        if llm_fast is None:
            llm_fast = llm_main

        self.llm = llm_main
        self.llm_fast = llm_fast
        self.retriever = retriever
        self.prompts = prompt_manager
        self.reports = report_manager

        query_gen = QueryGenerationService(llm_fast, prompt_manager)
        retrieval = EvidenceRetrievalService(retriever, CONFIG.get("top_k_final", 3))
        synthesis = EvidenceSynthesisService(llm_fast, prompt_manager)
        self.rag_pipeline = RAGPipeline(query_gen, retrieval, synthesis)

        logger.info("✅ LearningAssistant 初始化完成")

    async def afast_parallel_retrieve(self, sub_questions: List[str]) -> str:
        if not sub_questions:
            return ""

        logger.info(f"🔍 异步快速并行检索 {len(sub_questions)} 个子问题...")

        raw_evidence = await self.rag_pipeline.retrieval.aparallel_retrieve(sub_questions)

        logger.info(f"🔍 检索完成，总长度: {len(raw_evidence)} 字符")
        return raw_evidence

    async def stream_fast_response(
        self, case_text: str, evidence: str = ""
    ) -> AsyncGenerator[str, None]:
        try:
            prompt = (
                f"你是高等教育个性化学习顾问。\n\n"
                f"【学生信息】\n{case_text}\n\n"
                f"【参考证据】\n{evidence if evidence else '无'}\n\n"
                f"请简洁回答，禁止绝对性结论。"
            )

            if self.prompts:
                p = self.prompts.get(
                    "fast_track",
                    case_text=case_text,
                    evidence=evidence if evidence else "无"
                )
                if p:
                    prompt = p

            messages = [
                SystemMessage(content=self.reports.system_role),
                HumanMessage(content=prompt)
            ]

            async for chunk in self.llm_fast.astream(messages):
                if hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
                elif isinstance(chunk, str) and chunk:
                    yield chunk

        except Exception as e:
            logger.exception("❌ 快速通道响应失败")
            yield "⚠️ 系统异常，请稍后重试。"

    async def stream_final_report(
        self,
        context: Dict,
        proposal: str,
        critique: str,
        evidence: str,
        all_info: str = "",
        report_mode: str = "emergency"
    ) -> AsyncGenerator[str, None]:
        try:
            template_name = self.reports.get_template_name(report_mode)
            logger.info(f"📝 生成报告: {template_name} (模式={report_mode})")

            report_template = self.reports.get_template(report_mode)

            context_str = (
                json.dumps(context, ensure_ascii=False, indent=2)
                if isinstance(context, dict) else str(context)
            )

            prompt_text = report_template.format(
                context=context_str,
                all_info=all_info if all_info else "无历史记录",
                evidence=evidence if evidence else "未检索到相关证据",
                proposal=proposal if proposal else "无",
                critique=critique if critique else "无批判意见"
            )

            messages = [
                SystemMessage(content=self.reports.system_role),
                HumanMessage(content=prompt_text)
            ]

            async for chunk in self.llm.astream(messages):
                if hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
                elif isinstance(chunk, str) and chunk:
                    yield chunk

            logger.info("✅ 报告生成完成")

        except Exception as e:
            logger.exception("❌ 报告生成失败")
            yield "⚠️ 系统异常，请稍后重试。"