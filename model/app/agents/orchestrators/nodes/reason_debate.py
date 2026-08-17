"""辩论-仲裁编排：从 ReasonNode 拆出的独立协作模块。

负责多专家多轮辩论与仲裁裁决，持有辩论配置、仲裁角色与模型引用。
ReasonNode 仅负责专家提案与意见统筹，辩论环节委托本类完成。
"""
import asyncio
import logging
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class DebateOrchestrator:

    def __init__(
        self,
        debate_config: Dict,
        arbitrator_role: str,
        expert_manager,
        llm,
        llm_synthesis,
        debate_max_rounds: int,
    ):
        self.debate_config = debate_config
        self.arbitrator_role = arbitrator_role
        self.expert_manager = expert_manager
        self.llm = llm
        self.llm_synthesis = llm_synthesis
        self.debate_max_rounds = debate_max_rounds

    async def run(
        self,
        expert_roles: List[str],
        initial_results: List[str],
        case_info: str,
        evidence: str,
        existing_history: List[Dict],
    ) -> Dict:
        """执行多轮辩论-仲裁流程。"""
        debate_history = list(existing_history)

        debate_roles = [r for r in expert_roles if r != self.arbitrator_role]
        debate_results_map = dict(zip(expert_roles, initial_results))

        logger.info("[debate] ══════════ 辩论开始 ══════════")
        for role, opinion in debate_results_map.items():
            if role != self.arbitrator_role:
                logger.info(f"[debate][辩论·初始观点] {role}:\n{opinion}")

        round_num = 0
        for round_num in range(1, self.debate_max_rounds + 1):
            logger.info(f"[debate] 辩论第 {round_num}/{self.debate_max_rounds} 轮")

            debate_context = self._build_debate_context(
                debate_results_map, debate_history, case_info
            )

            debate_tasks = []
            debate_task_roles = []
            for role in debate_roles:
                debate_tasks.append(self._ask_debater(role, debate_context, round_num))
                debate_task_roles.append(role)

            debate_round_results = await asyncio.gather(*debate_tasks)

            for role, response in zip(debate_task_roles, debate_round_results):
                debate_results_map[role] = response
                debate_history.append({
                    "round": round_num,
                    "role": role,
                    "content": response,
                })
                logger.info(f"[debate][辩论·第{round_num}轮] {role}:\n{response}")

            logger.info(
                f"[debate] 辩论第 {round_num} 轮完成，{len(debate_round_results)} 位专家发言"
            )

        arbitration_result = await self._run_arbitration(debate_history, evidence)

        return {
            "debate_history": debate_history,
            "arbitration_result": arbitration_result,
        }

    def _build_debate_context(
        self,
        debate_results_map: Dict[str, str],
        debate_history: List[Dict],
        case_info: str,
    ) -> str:
        """构建辩论上下文。"""
        context_parts = [f"【学习资料】\n{case_info}\n"]

        context_parts.append("【各专家当前观点】")
        for role, opinion in debate_results_map.items():
            if role != self.arbitrator_role:
                context_parts.append(f"  {role}: {opinion[:500]}")

        if debate_history:
            context_parts.append("\n【历史辩论记录】")
            for record in debate_history[-6:]:
                context_parts.append(
                    f"  第{record['round']}轮 {record['role']}: {record['content'][:300]}"
                )

        return "\n".join(context_parts)

    async def _ask_debater(self, role: str, debate_context: str, round_num: int) -> str:
        """让专家参与辩论。"""
        expert_config = self.expert_manager.get_expert_by_role(role)
        system_prompt = (
            expert_config.get("system_prompt", f"你是专业的{role}")
            if expert_config else f"你是专业的{role}"
        )

        debate_template = self.debate_config.get(
            "debate_prompt_template",
            "你目前参与第{round}轮辩论。以下是辩论上下文：\n{debate_context}\n"
            "请针对与你观点不同之处提出反驳或补充。"
        )

        prompt = debate_template.format(round=round_num, debate_context=debate_context)

        try:
            res = await self.llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt),
            ])
            return getattr(res, "content", "")
        except Exception as e:
            logger.error(f"[debate] {role} 辩论发言失败: {e}")
            return f"未能获取{role}辩论意见。"

    async def _run_arbitration(self, debate_history: List[Dict], evidence: str) -> str:
        """仲裁智能体裁决。"""
        arbitrator_config = self.expert_manager.get_expert_by_role(self.arbitrator_role)
        system_prompt = (
            arbitrator_config.get("system_prompt", "你是公正严谨的教育仲裁专家。")
            if arbitrator_config else "你是公正严谨的教育仲裁专家。"
        )

        history_text = "\n".join(
            f"第{r['round']}轮 {r['role']}: {r['content'][:500]}"
            for r in debate_history
        )

        arbitration_template = self.debate_config.get(
            "arbitration_prompt_template",
            "作为仲裁智能体，请根据以下辩论记录和证据链裁决。\n"
            "【辩论记录】\n{debate_history}\n【可用证据】\n{evidence}",
        )

        prompt = arbitration_template.format(
            debate_history=history_text,
            evidence=evidence[:2000] if evidence else "无",
        )

        try:
            res = await self.llm_synthesis.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt),
            ])
            content = getattr(res, "content", "")
            logger.info("[debate] ══════════ 仲裁裁决 ══════════")
            logger.info(f"[debate][仲裁·裁决] {self.arbitrator_role}:\n{content}")
            return content
        except Exception as e:
            logger.error(f"[debate] 仲裁裁决失败: {e}")
            return "仲裁失败，请基于专家意见自行判断。"
