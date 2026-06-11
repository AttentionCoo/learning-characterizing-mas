import logging
import asyncio
from typing import Dict
from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode
from langchain_core.messages import HumanMessage, SystemMessage
from app.config.config_loader import get_expert_manager

logger = logging.getLogger(__name__)


class ReasonNode(BaseNode):

    def __init__(self, llm, expert_config=None):
        self.llm = llm
        self.expert_manager = expert_config or get_expert_manager()
        self.experts = self.expert_manager.get_experts()
        self.synthesis_config = self.expert_manager.get_synthesis_config()
        logger.info(f"[reason] 已加载 {len(self.experts)} 位专家配置")
        for expert in self.experts:
            logger.info(f"  - {expert.get('role')} (优先级: {expert.get('priority', 'N/A')})")

    async def run(self, state: LearningState) -> Dict:
        logger.info(f"[reason] 开始执行推理节点")
        logger.info(f"[reason] 输入文本长度: {len(state['case_text'])}")
        logger.info(f"[reason] 证据长度: {len(state['evidence']) if state['evidence'] else 0}")
        logger.info(f"[reason] 反思次数: {state['reflection_count']}")

        case_info = f"学生信息：{state['case_text']}\n上下文：{state['all_info']}\n参考证据：{state['evidence']}"

        if state['validation_feedback']:
            case_info += f"\n\n【之前被驳回的反馈，请反思】：{state['validation_feedback']}"
            logger.info(f"[reason] 存在校验反馈，进入反思模式")

        logger.info(f"[reason] 开启多专家并行推理 (Reflection Count: {state['reflection_count']})")

        tasks = []
        expert_roles = []

        for expert in self.experts:
            role = expert.get("role")
            instruction = expert.get("instruction")
            expert_roles.append(role)
            tasks.append(self._ask_expert(role, instruction, case_info))

        logger.info(f"[reason] 已创建 {len(tasks)} 个专家推理任务")

        results = await asyncio.gather(*tasks)

        logger.info(f"[reason] 专家推理完成，收到 {len(results)} 个结果")

        expert_advices = {}
        successful_experts = 0
        for role, advice in zip(expert_roles, results):
            expert_advices[f"{role}_advice"] = advice
            if advice and not advice.startswith("未能获取"):
                successful_experts += 1
                logger.info(f"[reason] {role} 推理成功，建议长度: {len(advice)}")
            else:
                logger.warning(f"[reason] {role} 推理失败或返回空结果")

        logger.info(f"[reason] 成功推理专家数: {successful_experts}/{len(expert_roles)}")

        logger.info("[reason] 进行多专家意见统筹汇总")

        expert_opinions_text = self._build_expert_opinions_text(expert_roles, results)
        logger.info(f"[reason] 专家意见文本长度: {len(expert_opinions_text)}")

        synthesis_prompt = self.synthesis_config.get(
            "prompt_template",
            "作为教学总监，请统筹以下各位智能体的意见，并给出最终综合提案(Proposal)和潜在问题批评(Critique)：\n{expert_opinions}\n请将输出分为两部分，用 \"### PROPOSAL ###\" 和 \"### CRITIQUE ###\" 隔开。"
        ).format(expert_opinions=expert_opinions_text)

        logger.info(f"[reason] 开始调用LLM进行意见综合")

        try:
            synthesis_res = await self.llm.ainvoke([HumanMessage(content=synthesis_prompt)])
            content = getattr(synthesis_res, "content", str(synthesis_res))
            logger.info(f"[reason] 意见综合完成，结果长度: {len(content)}")
        except Exception as e:
            logger.error(f"[reason] 意见综合失败: {type(e).__name__} - {str(e)}")
            content = "### PROPOSAL ###\n基于专家意见，建议进一步评估和个性化调整。\n\n### CRITIQUE ###\n由于意见综合失败，无法提供详细的风险批判。"

        proposal_separator = self.synthesis_config.get("proposal_separator", "### PROPOSAL ###")
        critique_separator = self.synthesis_config.get("critique_separator", "### CRITIQUE ###")

        parts = content.split(critique_separator)
        proposal_text = parts[0].replace(proposal_separator, "").strip()
        critique_text = parts[1].strip() if len(parts) > 1 else "无明显风险批判。"

        logger.info(f"[reason] 提案长度: {len(proposal_text)}, 批判长度: {len(critique_text)}")

        result = {
            "proposal": proposal_text,
            "critique": critique_text
        }

        result.update(expert_advices)

        logger.info(f"[reason] 推理节点执行完成，返回结果")
        return result

    def _build_expert_opinions_text(self, roles: list, results: list) -> str:
        separator = self.synthesis_config.get("opinion_separator", "【{role}建议】{opinion}\n")
        opinions = []
        for role, advice in zip(roles, results):
            opinions.append(separator.format(role=role, opinion=advice))
        return "\n".join(opinions)

    async def _ask_expert(self, role: str, instruction: str, case_info: str) -> str:
        expert_config = self.expert_manager.get_expert_by_role(role)
        system_prompt = expert_config.get("system_prompt", f"你是专业的{role}") if expert_config else f"你是专业的{role}"

        prompt = f"你目前扮演【{role}】。\n{instruction}\n\n【学习资料】\n{case_info}"

        try:
            res = await self.llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt)
            ])
            return getattr(res, "content", "")
        except Exception as e:
            logger.error(f"{role} 推理失败: {e}")
            return f"未能获取{role}建议。"