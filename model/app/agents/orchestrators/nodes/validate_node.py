import logging
from typing import Dict
from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode
from langchain_core.messages import HumanMessage, SystemMessage
from app.config.config_loader import get_validation_manager

logger = logging.getLogger(__name__)

class ValidateNode(BaseNode):

    def __init__(self, llm, validation_config=None):
        self.llm = llm
        self.validation_manager = validation_config or get_validation_manager()
        self.contraindication_rules = self.validation_manager.get_contraindication_rules()
        self.max_reflection_count = self.validation_manager.get_max_reflection_count()
        self.enable_rule_engine = self.validation_manager.is_rule_engine_enabled()
        self.enable_llm_reflection = self.validation_manager.is_llm_reflection_enabled()
        logger.info(f"[validate] 已加载校验配置")
        logger.info(f"  - 质量规则: {len(self.contraindication_rules)} 个类别")
        logger.info(f"  - 最大反思次数: {self.max_reflection_count}")
        logger.info(f"  - 规则引擎: {'启用' if self.enable_rule_engine else '禁用'}")
        logger.info(f"  - LLM反思: {'启用' if self.enable_llm_reflection else '禁用'}")

    async def run(self, state: LearningState) -> Dict:
        logger.info(f"[validate] 开始后层结果校验，当前已反思次数: {state['reflection_count']}")

        if self.enable_rule_engine:
            logger.info(f"[validate] 开始规则引擎检查")
            rule_feedback = await self._rule_engine_check(state)
            if rule_feedback:
                logger.warning(f"[validate] 规则引擎检查失败: {rule_feedback}")
                return self._fail_state(state, rule_feedback)
            logger.info(f"[validate] 规则引擎检查通过")

        if self.enable_llm_reflection:
            logger.info(f"[validate] 开始LLM反思检查")
            return await self._llm_reflection_check(state)
        else:
            logger.info("[validate] LLM反思已禁用，默认通过")
            return {"validation_passed": True, "validation_feedback": ""}

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
如果存在严重错误或违背教育原则的建议，请回复 "REJECT: "，并紧接详细的驳回理由。"""

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

        return result