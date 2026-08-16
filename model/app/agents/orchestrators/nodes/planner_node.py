"""PlannerNode — LLM 规划器。

接收意图门控后的状态，用轻量模型（qwen-turbo）生成结构化执行计划：
- 首选 with_structured_output(ExecutionPlan)（JSON Schema 约束）
- 失败则降级为 JSON 提示词 + JsonParser 解析
- 再失败则回退默认计划（等价于升级前固定管线）

计划通过 normalize_plan 保证白名单步骤类型、合法依赖并以 finalize 结尾。
"""
import json
import logging
from typing import Dict

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.schemas.plan import (
    ExecutionPlan,
    build_default_plan,
    normalize_plan,
    plan_to_dict,
)
from app.agents.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)

_PLANNER_SYSTEM_PROMPT = """你是学习任务规划器。根据学生的需求分析结果，把本轮任务编排为可执行的步骤序列。

步骤类型白名单（step_type 只能取以下值之一）：
- analyze: 拆解学习需求与子问题
- retrieve: 检索脑卒中指南证据（循证资料）
- expert_reason: 召集多学科专家并行推理、辩论仲裁、统筹汇总
- finalize: 汇总生成最终报告（必须是最后一个步骤）

要求：
1. 步骤数 1~6，按依赖顺序排列
2. 简单问题可以只用 expert_reason + finalize；需要循证依据的问题应先 retrieve
3. 每个步骤给出简短 title 和 goal（中文）
4. depends_on 填前置步骤的序号（0 开始），无依赖填 []
5. rationale 用一句话说明规划理由"""


class PlannerNode(BaseNode):

    def __init__(self, llm, enabled: bool = True):
        self.llm = llm
        self.enabled = enabled
        self.structured_llm = None
        if enabled:
            try:
                self.structured_llm = llm.with_structured_output(ExecutionPlan)
                logger.info("[planner] 结构化输出已启用 (with_structured_output)")
            except Exception as e:
                logger.warning(f"[planner] with_structured_output 初始化失败，降级 JSON 解析: {e}")

    def _build_user_prompt(self, state: LearningState) -> str:
        intent = state.get("intent_type", "")
        evidence_len = len(state.get("evidence", "") or "")
        questions = state.get("learning_questions", []) or []
        feedback = state.get("validation_feedback", "") or ""

        prompt = (
            f"意图类型：{intent}\n"
            f"学生问题：{state['case_text']}\n"
            f"已拆解子问题：{questions if questions else '（尚未分析）'}\n"
            f"可用循证材料：{evidence_len} 字符\n"
        )
        if feedback:
            prompt += f"\n【上一轮计划被驳回的反馈，请据此重新规划】：{feedback}\n"
        return prompt

    async def run(self, state: LearningState) -> Dict:
        intent = state.get("intent_type", "")

        if not self.enabled:
            logger.info("[planner] 规划器已禁用，使用默认计划")
            return self._default_result(intent, "规划器已禁用")

        messages = [
            SystemMessage(content=_PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=self._build_user_prompt(state)),
        ]

        # 1) 结构化输出
        if self.structured_llm is not None:
            try:
                plan = await self.structured_llm.ainvoke(messages)
                if plan and getattr(plan, "steps", None):
                    plan = normalize_plan(plan, intent)
                    logger.info(f"[planner] 规划成功（结构化输出）: {len(plan.steps)} 步 | {plan.rationale[:60]}")
                    return {"plan": plan_to_dict(plan), "plan_rationale": plan.rationale}
            except Exception as e:
                logger.warning(f"[planner] 结构化输出失败，降级 JSON 解析: {type(e).__name__}: {e}")

        # 2) JSON 提示词解析
        try:
            raw = await self.llm.ainvoke(messages)
            content = getattr(raw, "content", str(raw))
            parsed = JsonParser.parse(content, None)
            if parsed:
                plan = ExecutionPlan.model_validate(parsed)
                plan = normalize_plan(plan, intent)
                logger.info(f"[planner] 规划成功（JSON 解析）: {len(plan.steps)} 步")
                return {"plan": plan_to_dict(plan), "plan_rationale": plan.rationale}
        except Exception as e:
            logger.warning(f"[planner] JSON 解析失败: {type(e).__name__}: {e}")

        # 3) 默认计划兜底
        return self._default_result(intent, "规划失败，回退默认计划")

    def _default_result(self, intent: str, reason: str) -> Dict:
        plan = build_default_plan(intent)
        return {
            "plan": plan_to_dict(plan),
            "plan_rationale": f"{reason}：{plan.rationale}",
        }
