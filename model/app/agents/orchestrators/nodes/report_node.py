import logging
import json
from typing import Dict
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.constants import MAX_PROPOSAL_CHARS, MAX_CRITIQUE_CHARS
from app.agents.utils.text_utils import truncate_text

logger = logging.getLogger(__name__)


class ReportNode(BaseNode):

    def __init__(self, llm_proposer, report_manager):
        self.llm_proposer = llm_proposer
        self.report_manager = report_manager

    async def run(self, state: LearningState) -> Dict:
        logger.info(f"[report] 开始执行报告生成节点")
        logger.info(f"[report] 报告模式: {state['report_mode']}")
        logger.info(f"[report] 提案长度: {len(state['proposal']) if state['proposal'] else 0}")
        logger.info(f"[report] 批判长度: {len(state['critique']) if state['critique'] else 0}")
        logger.info(f"[report] 证据长度: {len(state['evidence']) if state['evidence'] else 0}")
        logger.info(f"[report] 校验状态: {state['validation_passed']}")
        logger.info(f"[report] 反思次数: {state['reflection_count']}")

        if state['user_questions']:
            logger.info(f"[report] 存在用户问题，直接返回提案")
            return {"report": state['proposal']}

        if not state['proposal']:
            logger.warning(f"[report] 没有提案，生成默认报告")
            default_report = f"""## 学习分析报告

### 学生情况
{state['case_text']}

### 分析结果
系统已完成初步分析，但未能生成具体的学习建议。

### 可能原因
- 需要进一步的学习信息
- 建议提供更详细的学习背景

### 建议
请提供更详细的学习信息，以便系统进行个性化分析。
"""
            return {"report": default_report}

        context_str = (
            json.dumps(state['context'], ensure_ascii=False, indent=2)
            if isinstance(state['context'], dict) else str(state['context'])
        )

        logger.info(f"[report] 上下文长度: {len(context_str)}")

        warning_text = ""
        if not state['validation_passed'] and state['validation_feedback']:
            warning_text = f"\n\n⚠️ **质量警告**: {state['validation_feedback']}\n\n"
            logger.info(f"[report] 添加质量警告到报告")

        report_template = self.report_manager.get_template(state['report_mode'])
        prompt_text = report_template.format(
            context=context_str,
            all_info=state['all_info'] or "无历史记录",
            evidence=state['evidence'] or "未检索到相关证据",
            proposal=truncate_text(state['proposal'], MAX_PROPOSAL_CHARS) or "无",
            critique=truncate_text(state['critique'], MAX_CRITIQUE_CHARS) or "无批判意见",
        )

        if warning_text:
            prompt_text = prompt_text.replace("### 个性化建议", f"### 质量警告{warning_text}### 个性化建议")

        logger.info(f"[report] Prompt长度: {len(prompt_text)}")
        logger.info(f"[report] 开始生成报告")

        messages = [
            SystemMessage(content=self.report_manager.system_role),
            HumanMessage(content=prompt_text),
        ]
        report = ""
        chunk_count = 0
        try:
            async for chunk in self.llm_proposer.astream(messages):
                c = chunk.content if hasattr(chunk, "content") else str(chunk)
                report += c
                chunk_count += 1
        except Exception as e:
            logger.error(f"[report] 报告生成失败: {type(e).__name__} - {str(e)}")
            report = f"## 学习分析报告\n\n{state['proposal']}\n\n{warning_text}"

        logger.info(f"[report] 报告生成完成，长度: {len(report)}, 块数: {chunk_count}")
        return {"report": report}