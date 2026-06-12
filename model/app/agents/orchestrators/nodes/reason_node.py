import logging
import asyncio
from typing import Dict, List
from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode
from langchain_core.messages import HumanMessage, SystemMessage
from app.config.config_loader import get_expert_manager

logger = logging.getLogger(__name__)


class ReasonNode(BaseNode):

    def __init__(self, llm, expert_config=None, llm_synthesis=None):
        self.llm = llm
        self.llm_synthesis = llm_synthesis or llm
        self.expert_manager = expert_config or get_expert_manager()
        self.experts = self.expert_manager.get_experts()
        self.synthesis_config = self.expert_manager.get_synthesis_config()
        self.debate_config = self.expert_manager.get_debate_config()
        self.debate_enabled = self.expert_manager.is_debate_enabled()
        self.debate_max_rounds = self.expert_manager.get_debate_max_rounds()
        self.arbitrator_role = self.expert_manager.get_arbitrator_role()
        self.dynamic_orchestration_enabled = self.expert_manager.is_dynamic_orchestration_enabled()
        logger.info(f"[reason] 已加载 {len(self.experts)} 位专家配置")
        logger.info(f"[reason] 专家推理模型: {getattr(self.llm, 'model_name', 'unknown')}")
        logger.info(f"[reason] 综合汇总模型: {getattr(self.llm_synthesis, 'model_name', 'unknown')}")
        logger.info(f"[reason] 辩论模式: {'启用' if self.debate_enabled else '禁用'} (最大轮数: {self.debate_max_rounds})")
        logger.info(f"[reason] 仲裁智能体: {self.arbitrator_role}")
        logger.info(f"[reason] 动态编排: {'启用' if self.dynamic_orchestration_enabled else '禁用'}")
        for expert in self.experts:
            logger.info(f"  - {expert.get('role')} (优先级: {expert.get('priority', 'N/A')}, 最低难度: {expert.get('min_difficulty', 0.0)})")

    async def run(self, state: LearningState) -> Dict:
        logger.info(f"[reason] 开始执行推理节点")
        logger.info(f"[reason] 输入文本长度: {len(state['case_text'])}")
        logger.info(f"[reason] 证据长度: {len(state['evidence']) if state['evidence'] else 0}")
        logger.info(f"[reason] 反思次数: {state['reflection_count']}")
        logger.info(f"[reason] 难度评分: {state.get('difficulty_score', 0.5)}")

        active_experts = self._resolve_active_experts(state)
        logger.info(f"[reason] 本轮参与专家: {active_experts}")

        case_info = f"学生信息：{state['case_text']}\n上下文：{state['all_info']}\n参考证据：{state['evidence']}"

        if state['validation_feedback']:
            correction_hint = self._build_correction_hint(state)
            case_info += f"\n\n【之前被驳回的反馈，请反思】：{state['validation_feedback']}"
            if correction_hint:
                case_info += f"\n\n【针对性修正指引】：{correction_hint}"
            logger.info(f"[reason] 存在校验反馈，进入反思模式（退火策略）")

        agent_weights = state.get('agent_weights', {})

        logger.info(f"[reason] 开启多专家并行推理 (Reflection Count: {state['reflection_count']})")

        tasks = []
        expert_roles = []

        for expert in self.experts:
            role = expert.get("role")
            if role not in active_experts:
                continue
            instruction = expert.get("instruction")
            expert_roles.append(role)
            weight = agent_weights.get(role, 1.0)
            tasks.append(self._ask_expert(role, instruction, case_info, weight))

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

        motivational_feedback = expert_advices.get("学习激励智能体_advice", "")

        debate_history = list(state.get('debate_history', []))

        if self.debate_enabled and len(expert_roles) > 1:
            logger.info(f"[reason] 启动辩论-仲裁模式")
            debate_results = await self._run_debate(
                expert_roles, results, case_info, state.get('evidence', ''), debate_history
            )
            debate_history = debate_results["debate_history"]
            arbitration_result = debate_results["arbitration_result"]
            logger.info(f"[reason] 辩论-仲裁完成，辩论轮数: {len(debate_history)}")
        else:
            arbitration_result = None

        logger.info("[reason] 进行多专家意见统筹汇总")

        expert_opinions_text = self._build_expert_opinions_text(expert_roles, results, agent_weights)
        logger.info(f"[reason] 专家意见文本长度: {len(expert_opinions_text)}")

        synthesis_input = expert_opinions_text
        if arbitration_result:
            synthesis_input += f"\n\n【仲裁裁决】\n{arbitration_result}"

        synthesis_prompt = self.synthesis_config.get(
            "prompt_template",
            "作为教学总监，请统筹以下各位智能体的意见，并给出最终综合提案(Proposal)和潜在问题批评(Critique)：\n{expert_opinions}\n请将输出分为两部分，用 \"### PROPOSAL ###\" 和 \"### CRITIQUE ###\" 隔开。"
        ).format(expert_opinions=synthesis_input)

        logger.info(f"[reason] 开始调用LLM进行意见综合 (模型: {getattr(self.llm_synthesis, 'model_name', 'unknown')})")

        try:
            synthesis_res = await self.llm_synthesis.ainvoke([HumanMessage(content=synthesis_prompt)])
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
            "critique": critique_text,
            "active_experts": active_experts,
            "debate_history": debate_history,
            "motivational_feedback": motivational_feedback,
        }

        result.update(expert_advices)

        logger.info(f"[reason] 推理节点执行完成，返回结果")
        return result

    def _resolve_active_experts(self, state: LearningState) -> List[str]:
        """根据意图类型和难度评分动态决定参与专家"""
        if not self.dynamic_orchestration_enabled:
            return [e.get("role") for e in self.experts]

        intent_type = state.get('intent_type', '')
        difficulty_score = state.get('difficulty_score', 0.5)

        active = self.expert_manager.get_experts_for_intent_and_difficulty(
            intent_type, difficulty_score
        )

        if self.debate_enabled and self.arbitrator_role not in active:
            if difficulty_score >= 0.6:
                active.append(self.arbitrator_role)

        logger.info(f"[reason] 动态编排: intent={intent_type}, difficulty={difficulty_score:.2f}, experts={active}")
        return active

    def _build_correction_hint(self, state: LearningState) -> str:
        """根据退火策略构建针对性修正提示"""
        from app.config.config_loader import get_validation_manager
        validation_mgr = get_validation_manager()

        if not validation_mgr.is_annealing_enabled():
            return ""

        feedback = state.get('validation_feedback', '')
        if not feedback:
            return ""

        category = validation_mgr.classify_rejection(feedback)
        correction_prompt = validation_mgr.get_correction_prompt_for_category(category)

        rejection_categories = list(state.get('rejection_categories', []))
        if category != "general":
            rejection_categories.append(category)

        logger.info(f"[reason] 退火策略: 驳回分类={category}, 修正提示长度={len(correction_prompt)}")

        return correction_prompt

    def _build_expert_opinions_text(self, roles: list, results: list, agent_weights: Dict) -> str:
        """构建带权重的专家意见文本"""
        separator = self.synthesis_config.get("opinion_separator", "【{role}建议】{opinion}\n")
        opinions = []
        for role, advice in zip(roles, results):
            weight = agent_weights.get(role, 1.0)
            weight_label = f"(权重: {weight:.1f})" if weight < 1.0 else ""
            opinions.append(separator.format(role=f"{role}{weight_label}", opinion=advice))
        return "\n".join(opinions)

    async def _run_debate(
        self,
        expert_roles: List[str],
        initial_results: List[str],
        case_info: str,
        evidence: str,
        existing_history: List[Dict],
    ) -> Dict:
        """执行多轮辩论-仲裁流程"""
        debate_history = list(existing_history)

        debate_roles = [r for r in expert_roles if r != self.arbitrator_role]
        debate_results_map = dict(zip(expert_roles, initial_results))

        round_num = 0
        for round_num in range(1, self.debate_max_rounds + 1):
            logger.info(f"[reason] 辩论第 {round_num}/{self.debate_max_rounds} 轮")

            debate_context = self._build_debate_context(debate_results_map, debate_history, case_info)

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

            logger.info(f"[reason] 辩论第 {round_num} 轮完成，{len(debate_round_results)} 位专家发言")

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
        """构建辩论上下文"""
        context_parts = [f"【学习资料】\n{case_info}\n"]

        context_parts.append("【各专家当前观点】")
        for role, opinion in debate_results_map.items():
            if role != self.arbitrator_role:
                context_parts.append(f"  {role}: {opinion[:500]}")

        if debate_history:
            context_parts.append("\n【历史辩论记录】")
            for record in debate_history[-6:]:
                context_parts.append(f"  第{record['round']}轮 {record['role']}: {record['content'][:300]}")

        return "\n".join(context_parts)

    async def _ask_debater(self, role: str, debate_context: str, round_num: int) -> str:
        """让专家参与辩论"""
        expert_config = self.expert_manager.get_expert_by_role(role)
        system_prompt = expert_config.get("system_prompt", f"你是专业的{role}") if expert_config else f"你是专业的{role}"

        debate_template = self.debate_config.get(
            "debate_prompt_template",
            "你目前参与第{round}轮辩论。以下是辩论上下文：\n{debate_context}\n请针对与你观点不同之处提出反驳或补充。"
        )

        prompt = debate_template.format(round=round_num, debate_context=debate_context)

        try:
            res = await self.llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt)
            ])
            return getattr(res, "content", "")
        except Exception as e:
            logger.error(f"[reason] {role} 辩论发言失败: {e}")
            return f"未能获取{role}辩论意见。"

    async def _run_arbitration(self, debate_history: List[Dict], evidence: str) -> str:
        """仲裁智能体裁决"""
        arbitrator_config = self.expert_manager.get_expert_by_role(self.arbitrator_role)
        system_prompt = arbitrator_config.get(
            "system_prompt", "你是公正严谨的教育仲裁专家。"
        ) if arbitrator_config else "你是公正严谨的教育仲裁专家。"

        history_text = "\n".join(
            f"第{r['round']}轮 {r['role']}: {r['content'][:500]}"
            for r in debate_history
        )

        arbitration_template = self.debate_config.get(
            "arbitration_prompt_template",
            "作为仲裁智能体，请根据以下辩论记录和证据链裁决。\n【辩论记录】\n{debate_history}\n【可用证据】\n{evidence}"
        )

        prompt = arbitration_template.format(
            debate_history=history_text,
            evidence=evidence[:2000] if evidence else "无"
        )

        try:
            res = await self.llm_synthesis.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt)
            ])
            content = getattr(res, "content", "")
            logger.info(f"[reason] 仲裁裁决完成，长度: {len(content)}")
            return content
        except Exception as e:
            logger.error(f"[reason] 仲裁裁决失败: {e}")
            return "仲裁失败，请基于专家意见自行判断。"

    async def _ask_expert(self, role: str, instruction: str, case_info: str, weight: float = 1.0) -> str:
        """让专家给出建议（支持权重衰减）"""
        expert_config = self.expert_manager.get_expert_by_role(role)
        system_prompt = expert_config.get("system_prompt", f"你是专业的{role}") if expert_config else f"你是专业的{role}"

        prompt = f"你目前扮演【{role}】。\n{instruction}\n\n【学习资料】\n{case_info}"

        if weight < 1.0:
            prompt += f"\n\n【注意】你在上一轮推理中部分建议被驳回，当前发言权重为{weight:.1f}，请更加谨慎地依据证据给出建议。"

        try:
            res = await self.llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt)
            ])
            return getattr(res, "content", "")
        except Exception as e:
            logger.error(f"{role} 推理失败: {e}")
            return f"未能获取{role}建议。"