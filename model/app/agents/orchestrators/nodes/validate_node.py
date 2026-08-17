import logging
from typing import Dict
from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode
from langchain_core.messages import HumanMessage, SystemMessage
from app.config.config_loader import get_validation_manager

logger = logging.getLogger(__name__)


class ValidateNode(BaseNode):

    def __init__(self, llm, validation_config=None, shared_memory_system=None):
        self.llm = llm
        self.shared_memory_system = shared_memory_system
        self.validation_manager = validation_config or get_validation_manager()
        self.contraindication_rules = self.validation_manager.get_contraindication_rules()
        self.max_reflection_count = self.validation_manager.get_max_reflection_count()
        self.enable_rule_engine = self.validation_manager.is_rule_engine_enabled()
        self.enable_llm_reflection = self.validation_manager.is_llm_reflection_enabled()
        self.annealing_enabled = self.validation_manager.is_annealing_enabled()
        self.weight_decay_factor = self.validation_manager.get_weight_decay_factor()
        logger.info(f"[validate] 已加载校验配置")
        logger.info(f"[validate] 共享记忆信誉更新: {'启用' if self.shared_memory_system else '禁用'}")
        logger.info(f"  - 质量规则: {len(self.contraindication_rules)} 个类别")
        logger.info(f"  - 最大反思次数: {self.max_reflection_count}")
        logger.info(f"  - 规则引擎: {'启用' if self.enable_rule_engine else '禁用'}")
        logger.info(f"  - LLM反思: {'启用' if self.enable_llm_reflection else '禁用'}")
        logger.info(f"  - 动态退火: {'启用' if self.annealing_enabled else '禁用'} (衰减因子: {self.weight_decay_factor})")

    async def run(self, state: LearningState) -> Dict:
        logger.info(f"[validate] 开始后层结果校验，当前已反思次数: {state['reflection_count']}")

        try:
            from langgraph.config import get_stream_writer
            writer = get_stream_writer()
        except Exception:
            writer = None

        def _emit(payload: dict):
            if writer is None:
                return
            try:
                writer(payload)
            except Exception as e:
                logger.debug(f"[validate] 推送校验事件失败: {e}")

        result = None
        if self.enable_rule_engine:
            logger.info(f"[validate] 开始规则引擎检查")
            rule_feedback = await self._rule_engine_check(state)
            if rule_feedback:
                logger.warning(f"[validate] 规则引擎检查失败: {rule_feedback}")
                self._update_reputation(state, passed=False)
                result = self._fail_state(state, rule_feedback)
            else:
                logger.info(f"[validate] 规则引擎检查通过")

        if result is None and self.enable_llm_reflection:
            logger.info(f"[validate] 开始LLM反思检查")
            result = await self._llm_reflection_check(state)
            if result.get("validation_passed"):
                self._update_reputation(state, passed=True)
            else:
                self._update_reputation(state, passed=False)

        if result is None:
            logger.info("[validate] LLM反思已禁用，默认通过")
            self._update_reputation(state, passed=True)
            result = {"validation_passed": True, "validation_feedback": ""}

        # 校验结论与反馈全文流式推送（推理链可审计）
        passed = result.get("validation_passed", True)
        feedback = result.get("validation_feedback", "") or ""
        if passed:
            _emit({
                "type": "thinking",
                "thinking": {
                    "step": "validate",
                    "title": "质量校验通过",
                    "content": feedback or "事实一致性、完整性与安全性检查通过。",
                },
            })
        else:
            _emit({
                "type": "thinking",
                "thinking": {
                    "step": "validate",
                    "title": f"质量校验未通过（第 {result.get('reflection_count', 1)} 次驳回）",
                    "content": feedback,
                },
            })
        return result

    def _update_reputation(self, state: LearningState, passed: bool):
        if not self.shared_memory_system:
            return
        active_experts = state.get("active_experts", [])
        agent_weights = state.get("agent_weights", {})
        if active_experts:
            self.shared_memory_system.update_reputation(
                active_experts, passed, agent_weights
            )

    async def _rule_engine_check(self, state: LearningState) -> str:
        rule_feedback = []
        for category, rules in self.contraindication_rules.items():
            category_mentioned = category in state['proposal'] or category in state['case_text']
            if category_mentioned:
                for rule in rules:
                    if rule in state['proposal']:
                        rule_feedback.append(
                            f"触发[{category}]质量规则拦截: 方案中存在【{rule}】的问题。"
                        )
        return " \n".join(rule_feedback) if rule_feedback else ""

    async def _llm_reflection_check(self, state: LearningState) -> Dict:
        reflection_prompt = f"""作为教育质量审查专家，请校验以下学习分析与建议是否存在严重错误或安全遗漏。只检查致命错误或明显的教育原则违反。

【学生输入】:
{state['case_text']}
【当前综合方案 Proposal】:
{state['proposal']}

判断要求：
如果没有严重问题，请回复 "PASS"。
如果存在严重错误或违背教育原则的建议，请回复 "REJECT: "，并紧接详细的驳回理由。驳回理由请明确指出问题类别（如：事实错误、逻辑矛盾、个性化不足、医学专业性错误、内容不完整等）。"""

        try:
            res = await self.llm.ainvoke([
                SystemMessage(content="你是严格的教育质量审查员。"),
                HumanMessage(content=reflection_prompt)
            ])
            verdict = getattr(res, "content", "PASS").strip()

            if verdict.startswith("REJECT"):
                return self._fail_state(state, verdict)
            elif "PASS" in verdict:
                logger.info("[validate] 方案已通过质控审查")
                return {"validation_passed": True, "validation_feedback": ""}
            else:
                logger.warning(f"[validate] 审查结果模糊: {verdict}. 默认PASS")
                return {"validation_passed": True, "validation_feedback": ""}

        except Exception as e:
            logger.error(f"[validate] Reflection 调用异常: {e}，默认放行")
            return {"validation_passed": True, "validation_feedback": ""}

    def _fail_state(self, state: LearningState, reason: str) -> Dict:
        new_reflection_count = state['reflection_count'] + 1
        logger.warning(f"[validate] 方案被驳回! 理由: {reason}")
        logger.warning(f"[validate] 当前反思次数: {state['reflection_count']} -> {new_reflection_count}")

        result = {
            "validation_passed": False,
            "validation_feedback": reason,
            "reflection_count": new_reflection_count
        }

        if state['proposal']:
            result["proposal"] = state['proposal']
        if state['critique']:
            result["critique"] = state['critique']

        if self.annealing_enabled:
            annealing_updates = self._apply_annealing(state, reason)
            result.update(annealing_updates)

        return result

    def _apply_annealing(self, state: LearningState, reason: str) -> Dict:
        """应用动态退火策略：分类驳回原因、衰减智能体权重"""
        category = self.validation_manager.classify_rejection(reason)
        correction_prompt = self.validation_manager.get_correction_prompt_for_category(category)

        logger.info(f"[validate] 退火策略: 驳回分类={category}")

        rejection_categories = list(state.get('rejection_categories', []))
        if category != "general":
            rejection_categories.append(category)

        agent_weights = dict(state.get('agent_weights', {}))
        active_experts = state.get('active_experts', [])

        decayed_roles = []
        for role in active_experts:
            current_weight = agent_weights.get(role, 1.0)
            if current_weight > 0.2:
                new_weight = round(current_weight * self.weight_decay_factor, 2)
                agent_weights[role] = new_weight
                if new_weight < current_weight:
                    decayed_roles.append(f"{role}: {current_weight:.1f}->{new_weight:.1f}")

        if decayed_roles:
            logger.info(f"[validate] 权重衰减: {', '.join(decayed_roles)}")

        enhanced_feedback = reason
        if correction_prompt:
            enhanced_feedback += f"\n\n【退火修正指引】{correction_prompt}"

        return {
            "agent_weights": agent_weights,
            "rejection_categories": rejection_categories,
            "validation_feedback": enhanced_feedback,
        }